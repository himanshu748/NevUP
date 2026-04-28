"""Business logic for memory persistence and retrieval."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import Pattern, SessionMemory


async def upsert_session_memory(
    db: AsyncSession,
    user_id: UUID,
    session_id: UUID,
    summary: str | None,
    metrics: dict | None,
    tags: list[str],
) -> SessionMemory:
    """Insert or update a session memory record.

    Idempotent: if session_id already exists for user_id, update it.
    """
    stmt = select(SessionMemory).where(
        SessionMemory.session_id == session_id,
        SessionMemory.user_id == user_id,
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is not None:
        # Update existing
        record.summary = summary
        record.metrics = metrics
        record.tags = tags
        record.updated_at = datetime.now(timezone.utc)
    else:
        # Insert new
        record = SessionMemory(
            session_id=session_id,
            user_id=user_id,
            summary=summary,
            metrics=metrics,
            tags=tags,
        )
        db.add(record)

    await db.commit()
    await db.refresh(record)
    return record


async def get_session_memory(
    db: AsyncSession,
    user_id: UUID,
    session_id: UUID,
) -> SessionMemory | None:
    """Retrieve the exact stored record for a session (hallucination audit)."""
    stmt = select(SessionMemory).where(
        SessionMemory.session_id == session_id,
        SessionMemory.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_context(
    db: AsyncSession,
    user_id: UUID,
    signal: str,
    limit: int = 5,
) -> tuple[list[SessionMemory], list[UUID]]:
    """Return last N relevant sessions and active pattern IDs for a signal.

    Relevance: sessions whose tags contain the signal, OR sessions
    referenced in patterns matching the signal_type.
    """
    # 1. Find active patterns for this signal
    pattern_stmt = select(Pattern).where(
        Pattern.user_id == user_id,
        Pattern.signal_type == signal,
    )
    pattern_result = await db.execute(pattern_stmt)
    patterns = list(pattern_result.scalars().all())
    active_pattern_ids = [p.pattern_id for p in patterns]

    # 2. Collect session IDs from pattern evidence
    evidence_session_ids: set[UUID] = set()
    for p in patterns:
        if p.evidence:
            for item in p.evidence:
                sid = item.get("sessionId")
                if sid:
                    try:
                        evidence_session_ids.add(UUID(sid) if isinstance(sid, str) else sid)
                    except (ValueError, AttributeError):
                        pass

    # 3. Find sessions matching by tag OR by evidence reference
    session_stmt = select(SessionMemory).where(
        SessionMemory.user_id == user_id,
    )

    # Fetch all sessions for this user and filter in Python for tag containment.
    # This is portable across DB backends (avoiding ARRAY @> operator differences).
    # Scale note: for users with thousands of sessions this full-scan approach
    # would be a bottleneck.  A production system should index the ``tags`` column
    # (e.g. GIN index on JSONB/ARRAY) and push the tag-containment filter into
    # SQL so the database only returns the matching rows.
    session_result = await db.execute(
        session_stmt.order_by(SessionMemory.created_at.desc())
    )
    all_sessions = list(session_result.scalars().all())

    relevant: list[SessionMemory] = []
    for s in all_sessions:
        if len(relevant) >= limit:
            break
        # Match if tags contain the signal or session is in evidence
        tag_match = s.tags and signal in s.tags
        evidence_match = s.session_id in evidence_session_ids
        if tag_match or evidence_match:
            relevant.append(s)

    return relevant, active_pattern_ids
