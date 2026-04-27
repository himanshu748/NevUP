"""Memory API router — the core Track 2 endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import verify_user_access
from app.deps import get_db
from app.memory import service
from app.memory.schemas import (
    ContextResponse,
    SessionMemoryResponse,
    SessionUpsertRequest,
)

router = APIRouter(prefix="/memory", tags=["Memory"])


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


@router.put(
    "/{user_id}/sessions/{session_id}",
    response_model=SessionMemoryResponse,
)
async def upsert_session_memory(
    user_id: str,
    session_id: str,
    body: SessionUpsertRequest,
    request: Request,
    _: dict = Depends(verify_user_access),
    db: AsyncSession = Depends(get_db),
):
    """Upsert a session memory snapshot.

    Idempotent — re-PUT replaces the existing record.
    """
    record = await service.upsert_session_memory(
        db=db,
        user_id=uuid.UUID(user_id),
        session_id=uuid.UUID(session_id),
        summary=body.summary,
        metrics=body.metrics,
        tags=body.tags,
    )
    return SessionMemoryResponse(
        sessionId=record.session_id,
        userId=record.user_id,
        summary=record.summary,
        metrics=record.metrics,
        tags=record.tags or [],
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


@router.get(
    "/{user_id}/sessions/{session_id}",
    response_model=SessionMemoryResponse,
)
async def get_session_memory(
    user_id: str,
    session_id: str,
    request: Request,
    _: dict = Depends(verify_user_access),
    db: AsyncSession = Depends(get_db),
):
    """Return the exact stored record (used for hallucination audit)."""
    trace_id = _trace_id(request)

    record = await service.get_session_memory(
        db=db,
        user_id=uuid.UUID(user_id),
        session_id=uuid.UUID(session_id),
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": f"No memory record for session {session_id}.",
                "traceId": trace_id,
            },
        )
    return SessionMemoryResponse(
        sessionId=record.session_id,
        userId=record.user_id,
        summary=record.summary,
        metrics=record.metrics,
        tags=record.tags or [],
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


@router.get(
    "/{user_id}/context",
    response_model=ContextResponse,
)
async def get_context(
    user_id: str,
    request: Request,
    relevantTo: str = "",
    _: dict = Depends(verify_user_access),
    db: AsyncSession = Depends(get_db),
):
    """Return last 5 relevant sessions + active patternIds for a signal."""
    trace_id = _trace_id(request)

    if not relevantTo:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "MISSING_PARAM",
                "message": "Query parameter 'relevantTo' is required.",
                "traceId": trace_id,
            },
        )

    sessions, pattern_ids = await service.get_context(
        db=db,
        user_id=uuid.UUID(user_id),
        signal=relevantTo,
    )

    return ContextResponse(
        userId=uuid.UUID(user_id),
        signal=relevantTo,
        sessions=[
            SessionMemoryResponse(
                sessionId=s.session_id,
                userId=s.user_id,
                summary=s.summary,
                metrics=s.metrics,
                tags=s.tags or [],
                createdAt=s.created_at,
                updatedAt=s.updated_at,
            )
            for s in sessions
        ],
        activePatternIds=pattern_ids,
    )
