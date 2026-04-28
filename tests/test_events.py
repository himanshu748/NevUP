"""Tests for POST /session/events — real-time signal detection and SSE streaming."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.events.router import detect_signal_realtime, TradeEvent
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
