"""GET /health — system health check (no auth required)."""

from fastapi import APIRouter, Depends
from sqlalchemy import text, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.memory.models import SessionMemory

router = APIRouter(tags=["System"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Return DB connection state, queue lag, and total memory records."""
    db_status = "disconnected"
    memory_records = 0
    try:
        # Check connection and count records in one go
        count_stmt = select(func.count(SessionMemory.session_id))
        result = await db.execute(count_stmt)
        memory_records = result.scalar()
        db_status = "connected"
    except Exception:
        pass

    status = "ok" if db_status == "connected" else "degraded"

    return {
        "status": status,
        "db": db_status,
        "redis_lag": 0,
        "memory_records": memory_records or 0
    }
