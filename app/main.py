"""FastAPI application factory with structured JSON logging middleware."""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.auth.router import router as auth_router
from app.config import settings
from app.health.router import router as health_router
from app.memory.router import router as memory_router
from app.events.router import router as events_router
from app.audit.router import router as audit_router

# ── Structured JSON logging ──────────────────────────────────────────────────

logger = logging.getLogger("nevup")


class JSONFormatter(logging.Formatter):
    """Emit every log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        # Merge extra fields (traceId, userId, latency, statusCode)
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        return json.dumps(log_entry)


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger("nevup")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger.info("NevUp AI Engine starting up")
    yield
    logger.info("NevUp AI Engine shutting down")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NevUp AI Engine — Track 2",
    description="Behavioral AI engine for trader pathology detection.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Request logging middleware ───────────────────────────────────────────────


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    """Attach traceId, measure latency, log structured JSON per request."""
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id

    start = time.perf_counter()
    response: Response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    # Try to extract userId from resolved JWT (set by dependency)
    user_id = getattr(request.state, "user_id", None)

    logger.info(
        "%s %s → %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "extra_fields": {
                "traceId": trace_id,
                "userId": user_id,
                "latency": latency_ms,
                "statusCode": response.status_code,
                "method": request.method,
                "path": request.url.path,
            }
        },
    )

    # Echo traceId in response header for client correlation
    response.headers["X-Trace-Id"] = trace_id
    return response


# ── Routers ──────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(memory_router)
app.include_router(health_router)
app.include_router(events_router)
app.include_router(audit_router)
