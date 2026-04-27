# DECISIONS

This document captures the key architectural decisions made to satisfy the hackathon requirements (Track 2 AI Engine) with a focus on correctness, tenancy safety, and “single command” operability.

## PostgreSQL over Redis for memory (persistence requirement)

- **Persistence & queryability**: Session memory (summaries, metrics JSON, tags, timestamps) must survive restarts and support queries like “last N sessions for a user” and “filter by signal/tag”. PostgreSQL is the most robust fit for durable storage plus query patterns.
- **Data integrity**: PostgreSQL provides transactional guarantees and a schema-backed representation of sessions/patterns that is easier to validate and migrate (Alembic) than ad-hoc key/value structures.
- **Redis is still used, but for the right job**: Redis is kept for the event bus / realtime signals (Streams), not as the system of record.

## Why `Qwen/Qwen2.5-72B-Instruct`

- **Free/low-friction access path**: Hugging Face Inference API makes it easy to run without provisioning GPUs; it is compatible with hackathon demos and quick deploys.
- **Strong reasoning + instruction following**: The model generally performs well for concise, evidence-based coaching messages and helps reduce generic outputs when prompted with explicit evidence context.
- **Vendor flexibility**: The architecture isolates the LLM call behind one module/route so swapping models/providers later is straightforward.

## Why Redis Streams for the event bus

- **Lightweight event ingestion**: Streams provide an append-only log semantics suitable for trade/session events without introducing heavyweight infrastructure.
- **Backpressure & replay**: Consumer groups and stream offsets provide a path to resilient processing and replay if the system is extended beyond synchronous request handling.
- **Hackathon-friendly ops**: Redis is easy to run in Compose, has fast startup, and works well for local + hosted demos.

## JWT tenancy enforcement approach

- **Canonical tenant ID**: The JWT `sub` claim is treated as the authenticated `userId`.
- **Row-level enforcement**:
  - For routes with a `userId` path param (e.g. `/memory/{userId}/...`), the API requires `JWT.sub == userId`.
  - For routes where the payload contains `userId` (e.g. `/session/events`), the API requires `JWT.sub == payload.userId`.
- **Explicit 403 on cross-tenant attempts**: Cross-tenant reads/writes return **HTTP 403** (never 404) to match the spec’s grading requirement.

## SSE streaming architecture choice

- **Fits the UX requirement**: Coaching must stream token-by-token and degrade gracefully on disconnect. Server-Sent Events (`text/event-stream`) is the simplest, browser-native streaming primitive for this.
- **Composable pipeline**: The server produces discrete events (`token`, `done`, `error`) that can be rendered incrementally by the client and are easy to test with `curl -N`.
- **Operational simplicity**: SSE works over plain HTTP and is straightforward to proxy/load-balance for hackathon hosting.

