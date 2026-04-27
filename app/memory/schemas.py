"""Pydantic schemas for memory endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request schemas ──────────────────────────────────────────────────────────


class SessionUpsertRequest(BaseModel):
    """PUT /memory/{userId}/sessions/{sessionId} body."""

    summary: str | None = None
    metrics: dict | None = None
    tags: list[str] = Field(default_factory=list)


# ── Response schemas ─────────────────────────────────────────────────────────


class SessionMemoryResponse(BaseModel):
    """Single session memory record."""

    sessionId: UUID
    userId: UUID
    summary: str | None = None
    metrics: dict | None = None
    tags: list[str] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}


class EvidenceItem(BaseModel):
    sessionId: str | None = None
    tradeId: str | None = None


class PatternResponse(BaseModel):
    patternId: UUID
    userId: UUID
    signalType: str
    evidence: list[dict] = Field(default_factory=list)
    createdAt: datetime

    model_config = {"from_attributes": True}


class ContextResponse(BaseModel):
    """GET /memory/{userId}/context response."""

    userId: UUID
    signal: str
    sessions: list[SessionMemoryResponse] = Field(default_factory=list)
    activePatternIds: list[UUID] = Field(default_factory=list)
