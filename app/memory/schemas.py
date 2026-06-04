"""Pydantic schemas for memory endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── Request schemas ──────────────────────────────────────────────────────────

MAX_SUMMARY_CHARS = 2_000
MAX_TAGS = 20
MAX_TAG_CHARS = 64


class SessionUpsertRequest(BaseModel):
    """PUT /memory/{userId}/sessions/{sessionId} body."""

    summary: str | None = Field(default=None, max_length=MAX_SUMMARY_CHARS)
    metrics: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("summary must not be blank when provided")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in value:
            cleaned = tag.strip().lower().replace(" ", "_")
            if not cleaned:
                raise ValueError("tags must not contain blank values")
            if len(cleaned) > MAX_TAG_CHARS:
                raise ValueError(f"tags must be {MAX_TAG_CHARS} characters or fewer")
            if cleaned not in seen:
                normalized.append(cleaned)
                seen.add(cleaned)
        return normalized


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
