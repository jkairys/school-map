# 04 — Postgres-backed job queue

## What to build

A deep module that owns the queue semantics, used by the producer (issue 12) and the worker loop (issue 11). The interface:

```
async def enqueue(job: NewJob) -> Job
async def claim_next() -> Job | None
async def complete(job_id: int) -> None
async def fail(job_id: int, error_class: ErrorClass, message: str) -> Job  # increments attempts; transitions to deadletter when exhausted
```

Backed by a `scrape_job` table with status enum (`queued | running | succeeded | failed | deadletter`) and an `attempts` counter. `claim_next()` uses `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` to atomically transition `queued → running` and stamp `claimed_at`. `complete` and `fail` are idempotent under retries (calling `complete` on an already-succeeded job is a no-op).

Retry policy is not enforced inside the queue module — the worker passes an `error_class`, and the queue increments attempts and decides `queued | deadletter` based on per-class limits configured in env (transient: max 3, anti-bot: max 1, parse: max 0).

## Acceptance criteria

- [ ] `scrape_job` table created via Alembic migration with all columns from the PRD schema section.
- [ ] Concurrency test: 10 concurrent tasks calling `claim_next()` against 5 queued jobs result in each job claimed exactly once and 5 receive `None`. Run against a real Postgres in a test container.
- [ ] `fail` correctly transitions to `deadletter` when attempts reach the per-class limit.
- [ ] `complete` is idempotent (second call is a no-op, no error).
- [ ] An interrupted `running` job (claimed_at older than configurable TTL) is reclaimable — write the test, even if the reclaim path is exercised only by an admin endpoint added later.
- [ ] All unit tests pass under `pytest -k queue`.

## Blocked by

- 01 — Bootstrap repo skeleton, docker-compose, Postgres, Alembic
