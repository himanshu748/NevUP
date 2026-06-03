"""Application settings loaded from environment variables.

This repository is intended to be runnable via `docker compose up` without
requiring a pre-existing local `.env`. For local/dev, we generate a JWT signing
secret at runtime if one is not provided. Production deployments must provide a
stable JWT secret so tokens survive restarts and cannot be signed by an
unintended ephemeral key.
"""

import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://nevup:nevup@localhost:5432/nevup"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    HF_TOKEN: str = ""
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

ALLOWED_JWT_ALGORITHMS = {"HS256"}

if settings.JWT_ALGORITHM not in ALLOWED_JWT_ALGORITHMS:
    allowed = ", ".join(sorted(ALLOWED_JWT_ALGORITHMS))
    raise RuntimeError(f"Unsupported JWT_ALGORITHM={settings.JWT_ALGORITHM!r}. Allowed: {allowed}")

if not settings.JWT_SECRET:
    if settings.APP_ENV.lower() in {"prod", "production"}:
        raise RuntimeError("JWT_SECRET must be set when APP_ENV=production")
    # Generated at process start; sufficient for local/dev and hackathon demo.
    settings.JWT_SECRET = secrets.token_urlsafe(48)
