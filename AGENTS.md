# NevUP Agent Notes

## Project Shape
- FastAPI service for trader behavior memory, signal detection, audit checks, and coaching SSE.
- Persistence uses SQLAlchemy async models with Alembic migrations under `alembic/`.
- Tests live in `tests/` and use mocked async DB dependencies for route behavior.

## Common Commands
- Tests: `python -m pytest`
- Syntax check: `python -m compileall app tests`
- Evaluation harness: `python eval.py`
- Local stack: `docker compose up --build`

## Conventions
- Keep tenant checks strict: JWT `sub` must match every protected `userId`.
- Validate user-facing event fields in Pydantic models instead of parsing free-form strings in route logic.
- Keep memory and audit request bounds in Pydantic schemas: summaries, tags, metrics, and audit text should fail fast with 422 when malformed or oversized.
- Do not commit generated artifacts such as `*.egg-info/`, `eval_report.html`, or `eval_report.json`.
- Local development may generate an ephemeral JWT secret, but production must set `JWT_SECRET`.
- Keep SSE responses graceful: emit structured `token`, `done`, or `error` events rather than raw exceptions, and do not stream provider exception details to clients.
