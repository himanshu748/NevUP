"""Application settings loaded from environment variables.

This repository is intended to be runnable via `docker compose up` without
requiring a pre-existing local `.env`. For local/dev, we generate a JWT signing
secret at runtime if one is not provided.
"""

import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://nevup:nevup@localhost:5432/nevup"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    HF_TOKEN: str = ""
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

if not settings.JWT_SECRET:
    # Generated at process start; sufficient for local/dev and hackathon demo.
    settings.JWT_SECRET = secrets.token_urlsafe(48)
