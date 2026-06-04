"""Tests for POST /audit hallucination-audit endpoint."""

import pytest


@pytest.mark.asyncio
async def test_audit_without_references_returns_zero_rate(client):
    response = await client.post(
        "/audit",
        json={"coaching_response": "No stored session reference was cited."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["references"] == []
    assert body["hallucination_rate"] == 0.0


@pytest.mark.asyncio
async def test_audit_rejects_blank_response(client):
    response = await client.post("/audit", json={"coaching_response": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_audit_rejects_oversized_response(client):
    response = await client.post(
        "/audit",
        json={"coaching_response": "x" * 8_001},
    )

    assert response.status_code == 422
