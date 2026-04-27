"""JWT token creation and verification using HS256."""

from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def create_token(user_id: str, name: str) -> dict:
    """Create a signed JWT with sub=userId, name, iat, exp."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "name": name,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return {
        "token": token,
        "expiresAt": (now + timedelta(hours=settings.JWT_EXPIRE_HOURS)).isoformat(),
    }


def verify_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
