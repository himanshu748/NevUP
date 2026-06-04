"""Tests for POST /session/events — real-time signal detection and SSE streaming."""

import json
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.events import router as events_router
from app.events.router import (
    build_coaching_prompt,
    coaching_event_generator,
    compact_session_context,
    detect_signal_realtime,
    TradeEvent,
)
from tests.conftest import USER_A_ID, USER_B_ID, auth_header

# ── Unit tests for detect_signal_realtime ─────────────────────────────────────


def _trade(**kwargs) -> TradeEvent:
    """Build a minimal TradeEvent, overriding any field with kwargs."""
    defaults = dict(
        tradeId="t-001",
        userId=USER_A_ID,
        sessionId="sess-001",
        assetClass="forex",
        direction="long",
        entryPrice=1.2000,
        quantity=1.0,
        entryAt="2026-01-15T09:30:00Z",
        revengeFlag=False,
    )
    defaults.update(kwargs)
    return TradeEvent(**defaults)


class TestDetectSignalRealtime:
    def test_revenge_flag_detected(self):
        t = _trade(revengeFlag=True)
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "revenge_trading"

    def test_revenge_rationale_recover_fast(self):
        t = _trade(entryRationale="Trying to recover fast after the big loss")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "revenge_trading"

    def test_fomo_catch_the_move(self):
        t = _trade(entryRationale="Price already moved a lot, trying to catch the rest of the move")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "fomo_entries"

    def test_fomo_price_already_moved(self):
        t = _trade(entryRationale="Price already moved, don't want to miss it")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "fomo_entries"

    def test_overtrading_scalping_momentum(self):
        t = _trade(entryRationale="Scalping momentum on the open")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "overtrading"

    def test_plan_non_adherence_not_in_plan(self):
        t = _trade(entryRationale="Felt like a good setup but not in plan")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "plan_non_adherence"

    def test_plan_non_adherence_low_score_greedy(self):
        t = _trade(planAdherence="1", emotionalState="greedy")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "plan_non_adherence"

    def test_plan_adherence_string_score_is_coerced(self):
        t = _trade(planAdherence="5", emotionalState="calm")
        assert t.planAdherence == 5
        assert detect_signal_realtime(t) is None

    def test_plan_adherence_rejects_out_of_range_score(self):
        with pytest.raises(ValueError):
            _trade(planAdherence=6)

    def test_rejects_oversized_rationale(self):
        with pytest.raises(ValueError):
            _trade(entryRationale="x" * (events_router.MAX_RATIONALE_CHARS + 1))

    def test_rejects_non_positive_entry_price_and_quantity(self):
        with pytest.raises(ValueError):
            _trade(entryPrice=0)

        with pytest.raises(ValueError):
            _trade(quantity=0)

    def test_premature_exit_cut_early(self):
        t = _trade(entryRationale="Cut early — was scared it would reverse")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "premature_exit"

    def test_loss_running_hoping_it_would_come_back(self):
        t = _trade(entryRationale="Kept hoping it would come back")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "loss_running"

    def test_session_tilt_fearful_loss(self):
        t = _trade(emotionalState="fearful", outcome="loss")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "session_tilt"

    def test_position_sizing_inconsistency_went_bigger(self):
        t = _trade(entryRationale="Felt confident after last win, went bigger on this one")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "position_sizing_inconsistency"

    def test_time_of_day_bias_afternoon_loss(self):
        t = _trade(entryAt="2026-01-15T14:00:00Z", outcome="loss")
        result = detect_signal_realtime(t)
        assert result is not None
        assert result["signal"] == "time_of_day_bias"

    def test_no_signal_clean_trade(self):
        """A calm, plan-adherent morning trade should produce no signal."""
        t = _trade(
            entryRationale="Trend continuation setup per morning plan",
            emotionalState="calm",
            planAdherence="4",
            outcome="win",
            entryAt="2026-01-15T09:30:00Z",
        )
        result = detect_signal_realtime(t)
        assert result is None

    def test_afternoon_win_no_time_bias_signal(self):
        """An afternoon trade that resulted in a win must NOT trigger time_of_day_bias."""
        t = _trade(entryAt="2026-01-15T15:00:00Z", outcome="win")
        result = detect_signal_realtime(t)
        # May match another signal but must NOT be time_of_day_bias
        if result is not None:
            assert result["signal"] != "time_of_day_bias"

    def test_compact_session_context_bounds_serialized_memory(self):
        sessions = [
            SimpleNamespace(
                session_id=uuid4(),
                summary="session summary " * 200,
                tags=["revenge_trading", "tilt"],
            )
            for _ in range(5)
        ]

        context = compact_session_context(sessions, max_chars=700)

        assert len(context) <= 760
        assert "sessionId" in context

    def test_build_coaching_prompt_truncates_to_bound(self):
        trade = _trade(entryRationale="x" * events_router.MAX_RATIONALE_CHARS)
        signal_data = {"signal": "fomo_entries", "claim": "FOMO detected"}
        context = json.dumps([{"summary": "y" * 10_000}])

        prompt = build_coaching_prompt(trade, signal_data, context)

        assert len(prompt) <= events_router.MAX_PROMPT_CHARS
        assert "Context truncated" in prompt


# ── Integration tests for POST /session/events ────────────────────────────────


@pytest.mark.asyncio
async def test_events_cross_tenant_forbidden(client, user_b_token):
    """User B cannot submit events for User A — expect 403."""
    payload = {
        "tradeId": "t-999",
        "userId": USER_A_ID,
        "sessionId": "sess-001",
        "assetClass": "forex",
        "direction": "long",
        "entryPrice": 1.2000,
        "quantity": 1.0,
        "entryAt": "2026-01-15T09:30:00Z",
    }
    response = await client.post(
        "/session/events",
        json=payload,
        headers=auth_header(user_b_token),
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_events_no_token_returns_401(client):
    """Missing auth header must return 401."""
    payload = {
        "tradeId": "t-001",
        "userId": USER_A_ID,
        "sessionId": "sess-001",
        "assetClass": "forex",
        "direction": "long",
        "entryPrice": 1.2000,
        "quantity": 1.0,
        "entryAt": "2026-01-15T09:30:00Z",
    }
    response = await client.post("/session/events", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_events_invalid_plan_adherence_returns_422(client, user_a_token):
    """planAdherence is a bounded 1-5 score, not arbitrary text."""
    payload = {
        "tradeId": "t-001",
        "userId": USER_A_ID,
        "sessionId": "sess-001",
        "assetClass": "forex",
        "direction": "long",
        "entryPrice": 1.2000,
        "quantity": 1.0,
        "entryAt": "2026-01-15T09:30:00Z",
        "planAdherence": 0,
    }
    response = await client.post(
        "/session/events",
        json=payload,
        headers=auth_header(user_a_token),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_coaching_stream_uses_configured_hf_provider(monkeypatch):
    captured = {}

    async def fake_get_context(db, user_id, signal, limit):
        return (
            [
                SimpleNamespace(
                    session_id=uuid4(),
                    summary="Stayed disciplined after a similar setup.",
                    tags=["discipline"],
                )
            ],
            [],
        )

    class FakeAsyncInferenceClient:
        def __init__(self, *, model, provider, token):
            captured["model"] = model
            captured["provider"] = provider
            captured["token"] = token

        async def chat_completion(self, messages, max_tokens, stream):
            captured["messages"] = messages
            captured["max_tokens"] = max_tokens
            captured["stream"] = stream

            async def stream_chunks():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="Stay patient."))
                    ]
                )

            return stream_chunks()

    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    monkeypatch.setattr(events_router, "get_context", fake_get_context)
    monkeypatch.setattr(events_router, "AsyncInferenceClient", FakeAsyncInferenceClient)
    monkeypatch.setattr(events_router.settings, "HF_TOKEN", "hf-token")
    monkeypatch.setattr(events_router.settings, "HF_MODEL", "org/model")
    monkeypatch.setattr(events_router.settings, "HF_PROVIDER", "fireworks-ai")

    events = [
        event
        async for event in coaching_event_generator(
            request,
            _trade(entryRationale="Not in plan, chasing the move"),
            AsyncMock(),
            {"signal": "fomo_entries", "claim": "FOMO detected"},
        )
    ]

    assert captured["model"] == "org/model"
    assert captured["provider"] == "fireworks-ai"
    assert captured["token"] == "hf-token"
    assert captured["max_tokens"] == events_router.HF_MAX_TOKENS
    assert captured["stream"] is True
    assert events[0]["event"] == "token"
    assert json.loads(events[0]["data"])["token"] == "Stay patient."
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_coaching_stream_sanitizes_provider_error(monkeypatch):
    async def fake_get_context(db, user_id, signal, limit):
        return ([], [])

    class FailingAsyncInferenceClient:
        def __init__(self, *, model, provider, token):
            pass

        async def chat_completion(self, messages, max_tokens, stream):
            raise RuntimeError("provider leaked hf-token")

    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    monkeypatch.setattr(events_router, "get_context", fake_get_context)
    monkeypatch.setattr(events_router, "AsyncInferenceClient", FailingAsyncInferenceClient)
    monkeypatch.setattr(events_router.settings, "HF_TOKEN", "hf-token")
    monkeypatch.setattr(events_router.settings, "HF_MODEL", "org/model")
    monkeypatch.setattr(events_router.settings, "HF_PROVIDER", "fireworks-ai")

    events = [
        event
        async for event in coaching_event_generator(
            request,
            _trade(entryRationale="Not in plan, chasing the move"),
            AsyncMock(),
            {"signal": "fomo_entries", "claim": "FOMO detected"},
        )
    ]

    assert events == [
        {
            "event": "error",
            "data": json.dumps({"error": "COACHING_PROVIDER_ERROR"}),
        }
    ]


@pytest.mark.asyncio
async def test_coaching_stream_treats_blank_hf_token_as_missing(monkeypatch):
    async def fake_get_context(db, user_id, signal, limit):
        return ([], [])

    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    client = MagicMock()
    monkeypatch.setattr(events_router, "get_context", fake_get_context)
    monkeypatch.setattr(events_router, "AsyncInferenceClient", client)
    monkeypatch.setattr(events_router.settings, "HF_TOKEN", "   ")

    events = [
        event
        async for event in coaching_event_generator(
            request,
            _trade(entryRationale="Not in plan, chasing the move"),
            AsyncMock(),
            {"signal": "fomo_entries", "claim": "FOMO detected"},
        )
    ]

    assert events == [
        {
            "event": "error",
            "data": json.dumps({"error": "HF_TOKEN not configured"}),
        }
    ]
    client.assert_not_called()
