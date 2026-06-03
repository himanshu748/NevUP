import importlib
import sys

import pytest


def _reload_config(monkeypatch, **env):
    for name in list(sys.modules):
        if name == "app.config":
            del sys.modules[name]

    for key in (
        "APP_ENV",
        "DATABASE_URL",
        "REDIS_URL",
        "JWT_SECRET",
        "JWT_ALGORITHM",
        "JWT_EXPIRE_HOURS",
        "HF_TOKEN",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    return importlib.import_module("app.config")


def test_development_generates_ephemeral_jwt_secret(monkeypatch):
    config = _reload_config(monkeypatch, APP_ENV="development")

    assert config.settings.JWT_SECRET
    assert len(config.settings.JWT_SECRET) > 40


def test_production_requires_jwt_secret(monkeypatch):
    with pytest.raises(RuntimeError, match="JWT_SECRET must be set"):
        _reload_config(monkeypatch, APP_ENV="production")


def test_production_accepts_stable_jwt_secret(monkeypatch):
    config = _reload_config(
        monkeypatch,
        APP_ENV="production",
        JWT_SECRET="stable-secret-for-hosted-production",
    )

    assert config.settings.JWT_SECRET == "stable-secret-for-hosted-production"


def test_rejects_unsupported_jwt_algorithm(monkeypatch):
    with pytest.raises(RuntimeError, match="Unsupported JWT_ALGORITHM"):
        _reload_config(
            monkeypatch,
            APP_ENV="development",
            JWT_ALGORITHM="none",
        )
