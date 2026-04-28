import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from huggingface_hub import AsyncInferenceClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.middleware import get_current_user
from app.config import settings
from app.deps import get_db
from app.memory.service import get_context

router = APIRouter(tags=["Events"])
logger = logging.getLogger(__name__)

HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"

class TradeEvent(BaseModel):
    tradeId: str
    userId: str
    sessionId: str
    assetClass: str
    direction: str
    entryPrice: float
    quantity: float
    entryAt: str
    exitPrice: Optional[float] = None
    exitAt: Optional[str] = None
    status: Optional[str] = None
    outcome: Optional[str] = None
    pnl: Optional[float] = None
    planAdherence: Optional[str] = None
    emotionalState: Optional[str] = None
    entryRationale: Optional[str] = None
    revengeFlag: Optional[bool] = None

def detect_signal_realtime(trade: TradeEvent) -> Optional[dict]:
    """Heuristic real-time signal detector for a single trade event.

    Checks explicit flags first (highest confidence), then scans
    ``entryRationale``, ``emotionalState``, ``planAdherence``, and entry
    hour for known pathology patterns drawn from the seed dataset.

    Signal priority (first match wins):
        1. revenge_trading  — explicit flag or "recover" rationale
        2. overtrading      — scalping momentum cue
        3. fomo_entries     — FOMO rationale
        4. plan_non_adherence — off-plan rationale or very low adherence
        5. premature_exit   — early exit rationale
        6. loss_running     — holding-on-hope rationale
        7. session_tilt     — fearful/anxious state after a recorded loss
        8. position_sizing_inconsistency — size-up-on-win language
        9. time_of_day_bias — afternoon entry with confirmed loss outcome

    Returns a dict with ``signal`` and ``claim`` keys, or ``None`` when no
    signal is detected.
    """
    rationale = trade.entryRationale or ""
    rationale_lower = rationale.lower()
    emotional_state = (trade.emotionalState or "").lower()
    plan_adherence = trade.planAdherence  # int 1-5 or None

    # ── 1. Revenge trading ────────────────────────────────────────────────────
    if trade.revengeFlag:
        return {
            "signal": "revenge_trading",
            "claim": "User showed explicit signs of revenge trading.",
        }
    if any(
        phrase in rationale_lower
        for phrase in ("recover fast", "make it back", "get it back", "trying to recover")
    ):
        return {
            "signal": "revenge_trading",
            "claim": "Entry rationale indicates an attempt to recover prior losses rapidly.",
        }

    # ── 2. Overtrading ────────────────────────────────────────────────────────
    if any(
        phrase in rationale_lower
        for phrase in ("scalping momentum", "quick scalp", "scalping the move")
    ):
        return {
            "signal": "overtrading",
            "claim": "High-frequency scalping language detected in entry rationale.",
        }

    # ── 3. FOMO entries ───────────────────────────────────────────────────────
    if "catch the rest of the move" in rationale_lower:
        return {
            "signal": "fomo_entries",
            "claim": "User entered trade out of Fear Of Missing Out (FOMO).",
        }
    if any(
        phrase in rationale_lower
        for phrase in ("price already moved", "don't want to miss", "dont want to miss", "chasing the move")
    ):
        return {
            "signal": "fomo_entries",
            "claim": "Entry rationale shows fear-of-missing-out pattern.",
        }

    # ── 4. Plan non-adherence ─────────────────────────────────────────────────
    if "not in plan" in rationale_lower:
        return {
            "signal": "plan_non_adherence",
            "claim": "User consistently executed setups not in their trading plan.",
        }
    if any(
        phrase in rationale_lower
        for phrase in ("felt like a good setup", "outside my plan", "off plan", "not planned")
    ):
        return {
            "signal": "plan_non_adherence",
            "claim": "Entry rationale indicates deviation from the pre-defined trading plan.",
        }
    # Very low adherence score alone is a strong signal
    if plan_adherence is not None and emotional_state in ("greedy", "anxious"):
        try:
            if int(plan_adherence) == 1:
                return {
                    "signal": "plan_non_adherence",
                    "claim": "Minimum plan-adherence score combined with elevated emotional state detected.",
                }
        except (ValueError, TypeError):
            pass

    # ── 5. Premature exit ─────────────────────────────────────────────────────
    if "cut early" in rationale_lower:
        return {
            "signal": "premature_exit",
            "claim": "User cut trades prematurely out of fear.",
        }
    if any(
        phrase in rationale_lower
        for phrase in ("scared it would reverse", "fear of reversal", "exited too soon", "closed early")
    ):
        return {
            "signal": "premature_exit",
            "claim": "Entry/exit rationale indicates premature position closure driven by fear.",
        }

    # ── 6. Loss running ───────────────────────────────────────────────────────
    if "hoping it would come back" in rationale_lower or "kept hoping" in rationale_lower:
        return {
            "signal": "loss_running",
            "claim": "User let a losing trade run beyond planned exit.",
        }
    if any(
        phrase in rationale_lower
        for phrase in ("holding through the loss", "waited for recovery", "held past my stop")
    ):
        return {
            "signal": "loss_running",
            "claim": "Rationale indicates holding a losing trade beyond the planned stop.",
        }

    # ── 7. Session tilt ───────────────────────────────────────────────────────
    # Detectable in a single event when emotional state is clearly degraded
    # and the trade is a recorded loss.
    if emotional_state in ("fearful", "anxious") and trade.outcome == "loss":
        return {
            "signal": "session_tilt",
            "claim": "Negative emotional state combined with a loss indicates potential session tilt.",
        }

    # ── 8. Position sizing inconsistency ─────────────────────────────────────
    if any(
        phrase in rationale_lower
        for phrase in (
            "went bigger",
            "size up",
            "sized up",
            "felt confident after last win",
            "increased my position",
        )
    ):
        return {
            "signal": "position_sizing_inconsistency",
            "claim": "Entry rationale suggests emotionally-driven position size increase.",
        }

    # ── 9. Time-of-day bias ───────────────────────────────────────────────────
    # Detectable only when we know the trade was a loss and it was entered
    # during the afternoon session (hour >= 13 UTC).
    if trade.outcome == "loss" and trade.entryAt:
        try:
            entry_hour = int(trade.entryAt[11:13])
            if entry_hour >= 13:
                return {
                    "signal": "time_of_day_bias",
                    "claim": (
                        f"Losing trade entered during the afternoon session "
                        f"(hour {entry_hour}:00 UTC). User may be over-trading "
                        "in historically weak time windows."
                    ),
                }
        except (ValueError, IndexError):
            pass

    return None

async def coaching_event_generator(request: Request, trade: TradeEvent, db: AsyncSession, signal_data: dict):
    # Exponential backoff parameters for connection resilience (client side handling, but we can do keep-alives)
    user_id = UUID(trade.userId)
    relevant_sessions, active_patterns = await get_context(db, user_id, signal_data["signal"], limit=5)
    
    context_str = json.dumps([
        {"sessionId": str(s.session_id), "summary": s.summary, "tags": s.tags}
        for s in relevant_sessions
    ])
    
    prompt = (
        f"You are a trading coach. The user just executed a trade with ID {trade.tradeId}.\n"
        f"Detected behavioral signal: {signal_data['signal']}\n"
        f"Evidence: {signal_data['claim']}\n"
        f"Trade rationale: {trade.entryRationale}\n"
        f"Past session context: {context_str}\n\n"
        "Provide a specific, evidence-based coaching message in 2-3 sentences. Do not be generic. "
        "Cite past sessions if relevant. Make it actionable and helpful."
    )
    
    messages = [
        {"role": "system", "content": "You are a professional trading coach."},
        {"role": "user", "content": prompt}
    ]
    
    if not settings.HF_TOKEN:
        logger.warning("HF_TOKEN is not set. Cannot call HF Inference API.")
        yield {
            "event": "error",
            "data": json.dumps({"error": "HF_TOKEN not configured"})
        }
        return

    client = AsyncInferenceClient(model=HF_MODEL, token=settings.HF_TOKEN)
    
    try:
        # We need first token within 400ms, stream=True allows us to yield tokens as they arrive
        response = await client.chat_completion(messages, max_tokens=150, stream=True)
        index = 0
        async for chunk in response:
            if await request.is_disconnected():
                logger.info(f"Client disconnected during SSE stream for user {trade.userId}")
                break
            
            token = chunk.choices[0].delta.content
            if token:
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token, "index": index})
                }
                index += 1
                
        yield {
            "event": "done",
            "data": json.dumps({"fullMessage": "Stream complete"})
        }
    except Exception as e:
        logger.error(f"Error generating coaching message: {str(e)}")
        yield {
            "event": "error",
            "data": json.dumps({"error": str(e)})
        }

@router.post("/session/events")
async def process_trade_event(
    trade: TradeEvent,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    trace_id = getattr(request.state, "trace_id", None)
    
    if current_user.get("sub") != trade.userId:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": "Cross-tenant access denied. JWT sub does not match userId.",
                "traceId": trace_id,
            },
        )
        
    signal_data = detect_signal_realtime(trade)
    
    if signal_data:
        # Start SSE stream
        return EventSourceResponse(coaching_event_generator(request, trade, db, signal_data))
    else:
        # No signal detected, return empty or generic response
        # Returning a 204 or just an empty stream
        async def empty_stream():
            yield {"event": "done", "data": json.dumps({"fullMessage": "No coaching required at this time."})}
            
        return EventSourceResponse(empty_stream())
