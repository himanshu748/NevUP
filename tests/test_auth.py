"""Tests for POST /auth/token."""

import pytest
import pytest_asyncio

from tests.conftest import auth_header, make_token, USER_A_ID


@pytest.mark.asyncio
async def test_issue_token_happy_path(client):
    """A valid request returns a signed token and an expiry timestamp."""
    response = await client.post(
        "/auth/token",
        json={"userId": USER_A_ID, "name": "Alex Mercer"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "token" in body
    assert "expiresAt" in body
    assert isinstance(body["token"], str)
    assert len(body["token"]) > 20


@pytest.mark.asyncio
async def test_issue_token_missing_field(client):
    """Omitting a required field returns 422 Unprocessable Entity."""
    response = await client.post("/auth/token", json={"userId": USER_A_ID})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401(client):
    """Requests without an Authorization header must be rejected."""
    response = await client.get(f"/memory/{USER_A_ID}/context?relevantTo=fomo_entries")
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_expired_token_returns_401(client, expired_token):
    """An expired JWT must be rejected with TOKEN_EXPIRED."""
    response = await client.get(
        f"/memory/{USER_A_ID}/context?relevantTo=fomo_entries",
        headers=auth_header(expired_token),
    )
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_malformed_token_returns_401(client):
    """A garbage Bearer value must be rejected with INVALID_TOKEN."""
    response = await client.get(
        f"/memory/{USER_A_ID}/context?relevantTo=fomo_entries",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["error"] == "INVALID_TOKEN"
