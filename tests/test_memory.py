"""Tests for PUT/GET /memory/{userId}/sessions/{sessionId} and GET /memory/{userId}/context."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.deps import get_db
from app.main import app
from tests.conftest import (
    SESSION_ID,
    USER_A_ID,
    USER_B_ID,
    auth_header,
    make_token,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_session_record():
    """Return a minimal mock SessionMemory ORM object."""
    from datetime import datetime, timezone

    record = MagicMock()
    record.session_id = UUID(SESSION_ID)
    record.user_id = UUID(USER_A_ID)
    record.summary = "Test session"
    record.metrics = {"winRate": 0.6}
    record.tags = ["revenge_trading"]
    now = datetime.now(timezone.utc)
    record.created_at = now
    record.updated_at = now
    return record


# ── GET /memory/{userId}/sessions/{sessionId} ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_session_happy_path(client, user_a_token):
    """A known session is returned for the authenticated owner."""
    record = _make_session_record()

    db_mock = AsyncMock()
    scalar_mock = MagicMock(scalar_one_or_none=lambda: record)
    db_mock.execute = AsyncMock(return_value=scalar_mock)

    async def _mock_db():
        yield db_mock

    app.dependency_overrides[get_db] = _mock_db
    try:
        response = await client.get(
            f"/memory/{USER_A_ID}/sessions/{SESSION_ID}",
            headers=auth_header(user_a_token),
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == SESSION_ID
    assert body["summary"] == "Test session"
    assert "revenge_trading" in body["tags"]


@pytest.mark.asyncio
async def test_get_session_not_found_returns_404(client, user_a_token):
    """A missing session returns 404 with SESSION_NOT_FOUND."""
    db_mock = AsyncMock()
    scalar_mock = MagicMock(scalar_one_or_none=lambda: None)
    db_mock.execute = AsyncMock(return_value=scalar_mock)

    async def _mock_db():
        yield db_mock

    app.dependency_overrides[get_db] = _mock_db
    try:
        response = await client.get(
            f"/memory/{USER_A_ID}/sessions/{SESSION_ID}",
            headers=auth_header(user_a_token),
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_session_cross_tenant_forbidden(client, user_b_token):
    """User B cannot read User A's session — expect 403 FORBIDDEN."""
    response = await client.get(
        f"/memory/{USER_A_ID}/sessions/{SESSION_ID}",
        headers=auth_header(user_b_token),
    )
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "FORBIDDEN"


# ── PUT /memory/{userId}/sessions/{sessionId} ─────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_session_happy_path(client, user_a_token):
    """A valid PUT creates a session and returns the record."""
    record = _make_session_record()

    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=lambda: None)
    )
    db_mock.commit = AsyncMock()
    db_mock.refresh = AsyncMock(side_effect=lambda r: None)
    db_mock.add = MagicMock()

    # After add+commit, simulate the refreshed record
    async def _refresh(r):
        r.session_id = UUID(SESSION_ID)
        r.user_id = UUID(USER_A_ID)
        r.summary = "Test session"
        r.metrics = {"winRate": 0.6}
        r.tags = ["revenge_trading"]
        from datetime import datetime, timezone
        r.created_at = datetime.now(timezone.utc)
        r.updated_at = datetime.now(timezone.utc)

    db_mock.refresh = AsyncMock(side_effect=_refresh)

    async def _mock_db():
        yield db_mock

    app.dependency_overrides[get_db] = _mock_db
    try:
        response = await client.put(
            f"/memory/{USER_A_ID}/sessions/{SESSION_ID}",
            headers=auth_header(user_a_token),
            json={
                "summary": "Test session",
                "metrics": {"winRate": 0.6},
                "tags": ["revenge_trading"],
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == SESSION_ID


@pytest.mark.asyncio
async def test_upsert_session_cross_tenant_forbidden(client, user_b_token):
    """User B cannot write to User A's session."""
    response = await client.put(
        f"/memory/{USER_A_ID}/sessions/{SESSION_ID}",
        headers=auth_header(user_b_token),
        json={"summary": "hack", "tags": []},
    )
    assert response.status_code == 403


# ── GET /memory/{userId}/context ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_context_missing_param_returns_400(client, user_a_token):
    """Omitting the 'relevantTo' query parameter returns 400."""
    response = await client.get(
        f"/memory/{USER_A_ID}/context",
        headers=auth_header(user_a_token),
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "MISSING_PARAM"


@pytest.mark.asyncio
async def test_get_context_happy_path(client, user_a_token):
    """A valid context request returns the expected structure."""
    db_mock = AsyncMock()
    # First execute call: patterns query (returns empty)
    # Second execute call: sessions query (returns empty)
    db_mock.execute = AsyncMock(
        return_value=MagicMock(
            scalars=lambda: MagicMock(all=lambda: []),
            scalar_one_or_none=lambda: None,
        )
    )

    async def _mock_db():
        yield db_mock

    app.dependency_overrides[get_db] = _mock_db
    try:
        response = await client.get(
            f"/memory/{USER_A_ID}/context?relevantTo=fomo_entries",
            headers=auth_header(user_a_token),
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["signal"] == "fomo_entries"
    assert "sessions" in body
    assert "activePatternIds" in body


@pytest.mark.asyncio
async def test_get_context_cross_tenant_forbidden(client, user_b_token):
    """User B cannot query User A's context."""
    response = await client.get(
        f"/memory/{USER_A_ID}/context?relevantTo=fomo_entries",
        headers=auth_header(user_b_token),
    )
    assert response.status_code == 403
