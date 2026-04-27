"""Shared test fixtures for the NevUp test suite."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.deps import get_db
from app.main import app


# ── Event loop ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Mock DB session ──────────────────────────────────────────────────────────


def _mock_db_session():
    """Return a mock AsyncSession for auth-only tests."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])))
    return session


@pytest.fixture(autouse=True)
def override_db():
    """Replace the real DB dependency with a mock for all tests."""
    async def mock_get_db():
        yield _mock_db_session()

    app.dependency_overrides[get_db] = mock_get_db
    yield
    app.dependency_overrides.clear()


# ── HTTP client ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── JWT helpers ──────────────────────────────────────────────────────────────

USER_A_ID = "f412f236-4edc-47a2-8f54-8763a6ed2ce8"
USER_B_ID = "fcd434aa-2201-4060-aeb2-f44c77aa0683"
SESSION_ID = "4f39c2ea-8687-41f7-85a0-1fafd3e976df"


def make_token(user_id: str, name: str = "Test User", expired: bool = False) -> str:
    """Create a valid (or expired) JWT for testing."""
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=24)
    payload = {"sub": user_id, "name": name, "iat": now, "exp": exp}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def user_a_token() -> str:
    return make_token(USER_A_ID, "Alex Mercer")


@pytest.fixture
def user_b_token() -> str:
    return make_token(USER_B_ID, "Jordan Lee")


@pytest.fixture
def expired_token() -> str:
    return make_token(USER_A_ID, expired=True)


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
