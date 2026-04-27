# NevUp AI Engine - Track 2

Welcome to the NevUp AI Engine! This project provides the system components for the NevUp Hiring Hackathon 2026. It features a memory layer for trader profiles, a real-time behavioral profiling system, an AI coaching engine, and verification endpoints.

## Architecture

- **Backend:** FastAPI (Python 3.12)
- **Database:** PostgreSQL (with `pgdata` volume for persistence across restarts)
- **Event Bus:** Redis Streams (with `redisdata` volume for persistence)
- **AI Inference:** HuggingFace Inference API (`Qwen/Qwen2.5-72B-Instruct`)
- **Containerization:** Docker + Docker Compose

## Setup Instructions

Single command cold start (includes Postgres + Redis + API, and runs DB migrations automatically):

```bash
docker compose up --build
```

Then verify:

```bash
curl http://localhost:8000/health
```

## Hosting (for submission)

This repo includes a `render.yaml` Blueprint to deploy:
- a Docker-based FastAPI web service
- a managed Postgres database
- a managed Redis instance

Steps:
- Create a new Render project from this repo and select **Blueprint** deploy.
- Set `HF_TOKEN` in the Render dashboard if you want live coaching SSE via Hugging Face Inference.

## Environment Variables

You do **not** need a `.env` file to run locally. If you want to override defaults, you can export env vars or create a `.env` from `.env.example`.

| Variable | Required | Default (docker compose) | Description |
|---|---:|---|---|
| `DATABASE_URL` | No | `postgresql+asyncpg://nevup:nevup@postgres:5432/nevup` | Postgres DSN (asyncpg) |
| `REDIS_URL` | No | `redis://redis:6379/0` | Redis connection URL |
| `JWT_SECRET` | No | *(generated at startup if unset)* | HS256 signing secret for JWT issuance/verification |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_HOURS` | No | `24` | Token expiry window |
| `HF_TOKEN` | No | *(empty)* | HuggingFace Inference API token for coaching SSE |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `POSTGRES_DB` | No | `nevup` | Postgres database name |
| `POSTGRES_USER` | No | `nevup` | Postgres username |
| `POSTGRES_PASSWORD` | No | `nevup` | Postgres password (dev only) |

## API

Base URL: `http://localhost:8000`

### 1) Get a JWT (required for all tenant-protected endpoints)

```bash
export USER_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
export SESSION_ID="b2c3d4e5-f6a7-8901-bcde-f12345678901"

export JWT="$(
  curl -sS -X POST "http://localhost:8000/auth/token" \
    -H "Content-Type: application/json" \
    -d "{\"userId\":\"$USER_ID\",\"name\":\"Hackathon Tester\"}" | jq -r '.token'
)"
```

### 2) Health check (no auth)

```bash
curl -sS http://localhost:8000/health
```

### 3) Upsert session memory (idempotent)

```bash
curl -sS -X PUT "http://localhost:8000/memory/$USER_ID/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Solid session. Stayed disciplined and avoided chasing.",
    "metrics": { "winRate": 0.8, "totalPnl": 312.5 },
    "tags": ["overtrading", "discipline"]
  }'
```

### 4) Get session memory (hallucination audit ground truth lookup)

```bash
curl -sS "http://localhost:8000/memory/$USER_ID/sessions/$SESSION_ID" \
  -H "Authorization: Bearer $JWT"
```

### 5) Get context (requires `relevantTo` query param)

```bash
curl -sS "http://localhost:8000/memory/$USER_ID/context?relevantTo=overtrading" \
  -H "Authorization: Bearer $JWT"
```

### 6) Hallucination audit (verify sessionId references)

The request body is JSON with key `coaching_response`.

```bash
curl -sS -X POST "http://localhost:8000/audit" \
  -H "Content-Type: application/json" \
  -d '{
    "coaching_response": "During session b2c3d4e5-f6a7-8901-bcde-f12345678901 you exhibited signs of overtrading."
  }'
```

### 7) Real-time coaching SSE (trade event → token stream)

This endpoint returns `text/event-stream`. Use `curl -N` to watch tokens stream.

```bash
curl -N -X POST "http://localhost:8000/session/events" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{
    \"tradeId\":\"550e8400-e29b-41d4-a716-446655440000\",
    \"userId\":\"$USER_ID\",
    \"sessionId\":\"$SESSION_ID\",
    \"assetClass\":\"equity\",
    \"direction\":\"long\",
    \"entryPrice\":178.45,
    \"quantity\":10,
    \"entryAt\":\"2025-01-06T09:35:00Z\",
    \"status\":\"closed\",
    \"entryRationale\":\"Not in plan, trying to catch the rest of the move\",
    \"revengeFlag\":false
  }"
```

Notes:
- If `HF_TOKEN` is not set, the stream will emit an `error` event.
- If no behavioral signal is detected, the stream returns a single `done` event.

## Evaluation Harness

You can run the evaluation script to test the behavioral profiler against the ground truth labels in `nevup_seed_dataset.json`. The script outputs the evaluation report to `eval_report.json` and generates an HTML report `eval_report.html`.

```bash
python eval.py
```
