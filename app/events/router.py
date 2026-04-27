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
    rationale = trade.entryRationale or ""
    rationale_lower = rationale.lower()
    
    if trade.revengeFlag:
        return {"signal": "revenge_trading", "claim": "User showed explicit signs of revenge trading."}
    if "catch the rest of the move" in rationale_lower:
        return {"signal": "fomo_entries", "claim": "User entered trade out of Fear Of Missing Out (FOMO)."}
    if "not in plan" in rationale_lower:
        return {"signal": "plan_non_adherence", "claim": "User consistently executed setups not in their trading plan."}
    if "cut early" in rationale_lower:
        return {"signal": "premature_exit", "claim": "User cut trades prematurely out of fear."}
    if "hoping it would come back" in rationale_lower:
        return {"signal": "loss_running", "claim": "User let a losing trade run beyond planned exit."}
        
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
