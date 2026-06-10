# Docket

A **pull-based task queue** built on FastAPI and Postgres. Producers submit
tasks; worker services **pull** work when they are free, hold it under a
renewable **lease**, and report success or failure. Crashed workers are
recovered automatically, failed tasks are retried up to a budget and then
dead-lettered.

The name is deliberate: workers pull from a docket of pending work — there is
no central dispatcher pushing tasks at them.

## Why a pull queue?

Push-based dispatchers have to track which workers are alive and free, and they
stall the moment that bookkeeping is wrong. Docket inverts the control flow: an
idle worker asks for the next task, so capacity is discovered, not guessed.

It fits well when you have:

- **Long-running or heavy jobs** (minutes to hours) where a worker may crash
  mid-task — the lease + heartbeat model reclaims the work without losing it.
- **A pool of heterogeneous workers** that each handle one task at a time and
  pull more when ready.
- **At-least-once delivery** needs with bounded retries and a dead-letter
  outcome, without standing up Redis / RabbitMQ / Celery — Postgres is the only
  moving part.

It is intentionally small and dependency-light: SQLAlchemy Core (no ORM),
`SELECT ... FOR UPDATE SKIP LOCKED` for concurrency, and a clean hexagonal
core you can read in an afternoon.

## How it works

### Task lifecycle

```
            submit                 claim                complete
   (producer) ─────▶  PENDING  ──(worker pulls)──▶  RUNNING  ─────────▶  SUCCEEDED
                        ▲                              │
                        │  fail (attempts < max)       │  fail (attempts >= max)
                        └──────────────────────────────┴───────────────▶  FAILED
                        ▲                              │                  (dead-letter)
                        │      lease expires           │
                        └────  (reaper reclaims)  ◀────┘
```

- **submit** — a task is created `PENDING` and enqueued.
- **claim** — a worker pulls the highest-priority pending task. The pull
  **leases** it to that worker (`SELECT ... FOR UPDATE SKIP LOCKED`, so
  concurrent claims never double-claim), the task moves to `RUNNING`, an
  `Assignment` audit record is written, and the service is marked busy.
- **heartbeat** — the worker periodically renews the lease while it runs.
- **complete** — the task becomes `SUCCEEDED`; the lease and service are freed.
- **fail** — the attempt is over the budget → `FAILED` (dead-letter); otherwise
  the task returns to `PENDING` to be retried (it keeps `error` as the
  last-failure reason).
- **reaper** — a periodic sweep reclaims tasks whose lease lapsed (a crashed or
  stalled worker), applying the same retry/dead-letter policy.

### The lease is the single source of truth

While a task is `RUNNING`, the **lease** (`locked_by` + `lease_expires_at`) is
the sole authority over it. A worker owns its task only as long as it holds a
live lease, so:

- It **must heartbeat well within `lease_timeout`** or it loses the task to the
  reaper.
- `complete` / `fail` authorize by atomically releasing the lease first; if the
  lease has lapsed the write is rejected and nothing is rolled back. A resolve
  and a concurrent reclaim serialize on that one conditional write, so exactly
  one of them takes effect.

The attempts budget (`max_attempts`, default 3) counts **every** dispatch —
both explicit failures and lease-expiry reclaims, since a lost delivery is a
real attempt. The recorded error distinguishes the cause (`failed: <error>` vs
`lease expired`).

## Architecture

Hexagonal / ports-and-adapters, so the application logic never depends on
FastAPI or SQLAlchemy:

```
docket/
├── domain/            # pure core — no external imports
│   ├── models.py      # Task, Service, Assignment (+ enums)
│   ├── ports.py       # Protocols: Broker, TaskRepository, ...
│   └── exceptions.py  # DomainError
├── use_cases/         # application logic, one class per use case
│   ├── submit_task.py · claim_task.py · heartbeat.py
│   ├── resolve_task.py        # CompleteTask / FailTask
│   ├── reclaim_expired.py     # the reaper's work
│   └── read_tasks.py · read_services.py · register_service.py
├── infrastructure/    # adapters implementing the ports
│   ├── broker.py      # SqlBroker (Postgres) + InMemoryBroker (tests)
│   ├── repositories.py# SQLAlchemy Core repositories
│   └── tables.py      # table definitions
├── api/               # FastAPI: routes wire use cases to HTTP
└── config.py          # pydantic-settings (DOCKET_* env vars)
```

The `Broker` and the `TaskRepository` are two views over **one** task store
(the `tasks` table for Postgres; a shared dict for the in-memory test double),
so a submitted task is immediately both pullable and visible to reads.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Point Docket at a database (defaults to local Postgres) and run the API:

```powershell
$env:DOCKET_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/docket"
uvicorn docket.api.main:app --reload
```

The schema is created on startup and the lease reaper runs in the background.
Open http://127.0.0.1:8000/docs for the interactive API.

## API

Producers submit and read tasks freely. **Worker actions are authenticated**: a
service registers once, receives a bearer token (shown only once), and sends it
as `Authorization: Bearer <token>` on claim/heartbeat/complete/fail. The acting
service is taken from the token, so one worker cannot act as another.

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /services` | – | Register a service; returns the bearer token **once** |
| `GET /services` · `GET /services/{id}` | – | List / fetch services (token hash never exposed) |
| `POST /tasks` | – | Submit a task (`name`, `payload`, `priority`) |
| `GET /tasks/pending` · `GET /tasks/{id}` | – | List pending / fetch a task |
| `POST /tasks/claim` | ✓ | Claim the next task; `null` when the queue is empty |
| `POST /tasks/{id}/heartbeat` | ✓ | Renew the lease on a running task |
| `POST /tasks/{id}/complete` | ✓ | Finish a task (`result`) |
| `POST /tasks/{id}/fail` | ✓ | Report failure (`error`); requeues or dead-letters |

### A worker loop, end to end

```bash
# 1. Register a worker (do this once; save the token)
TOKEN=$(curl -s -X POST localhost:8000/services \
  -H 'content-type: application/json' -d '{"name":"worker-1"}' | jq -r .token)
AUTH="authorization: Bearer $TOKEN"

# 2. A producer submits work
curl -s -X POST localhost:8000/tasks \
  -H 'content-type: application/json' \
  -d '{"name":"resize-image","payload":{"path":"/a.png"},"priority":20}'

# 3. The worker claims it (returns the task, or null if the queue is empty)
TASK=$(curl -s -X POST localhost:8000/tasks/claim -H "$AUTH")
ID=$(echo "$TASK" | jq -r .id)

# 4. While working, heartbeat to keep the lease alive
curl -s -X POST localhost:8000/tasks/$ID/heartbeat -H "$AUTH"

# 5. Report the outcome
curl -s -X POST localhost:8000/tasks/$ID/complete \
  -H "$AUTH" -H 'content-type: application/json' -d '{"result":{"ok":true}}'
# ...or on error:
# curl -s -X POST localhost:8000/tasks/$ID/fail \
#   -H "$AUTH" -H 'content-type: application/json' -d '{"error":"bad input"}'
```

Workers are plain HTTP clients — Docket ships the queue and its guarantees, not
the worker runtime, so you can write workers in any language.

## Configuration

All settings load from environment variables prefixed `DOCKET_` (or a `.env`
file). Validation is fail-fast at startup.

| Variable | Default | Meaning |
|---|---|---|
| `DOCKET_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/docket` | Async SQLAlchemy URL |
| `DOCKET_MAX_ATTEMPTS` | `3` | Dispatches before a task is dead-lettered |
| `DOCKET_LEASE_TIMEOUT` | `300` | Seconds a pulled task stays leased (heavy-work sized) |
| `DOCKET_REAPER_INTERVAL` | `30` | Seconds between expired-lease sweeps |
| `DOCKET_LOG_LEVEL` | `INFO` | Logging level |
| `DOCKET_APP_NAME` | `docket` | Application name |

## Development

```powershell
ruff check .          # lint
ruff format --check . # formatting
mypy docket           # type check (strict)
pytest                # tests
```

Tests run against an in-memory SQLite database by default, so the suite is fast
and needs no services. The broker conformance suite runs the same lease
behaviour against both the in-memory and SQL brokers, and the full lifecycle is
exercised on both pairings.

### Concurrency tests on real Postgres

`SELECT ... FOR UPDATE SKIP LOCKED` is a no-op on SQLite, so the true
concurrency guarantees (no double-claim under parallel pulls; coherent
reclaim-vs-complete races) are proven against a real Postgres started via
[`testcontainers`](https://testcontainers.com/). These tests **skip cleanly**
when Docker is unavailable, so the default run stays green:

```powershell
pytest -m postgres        # run only the Postgres tests (needs Docker)
pytest -m "not postgres"  # skip them explicitly
```

## License

See the repository for license details.
