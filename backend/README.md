# DocIntel AI — backend

FastAPI API, Celery workers, outbox dispatcher, scheduler and migrations for
DocIntel AI. One codebase and one Docker image; the process type is chosen by
the container command ([`docker/entrypoint.sh`](docker/entrypoint.sh)):
`api`, `worker`, `dispatcher`, `beat`, `migrate`, `bootstrap`.

System overview, setup and the full command list are in the
[root README](../README.md); design details in
[docs/architecture.md](../docs/architecture.md) and the API in
[docs/api.md](../docs/api.md).

## Working on the backend

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/). Commands run
from this directory (or use the root `make` targets).

```bash
uv sync --frozen                     # dependencies into .venv
uv run pytest tests/unit             # fast unit tests, no Docker
uv run pytest                        # + integration tests (Testcontainers starts PostgreSQL, Redis, MinIO)
uv run ruff check . && uv run ruff format --check . && uv run mypy app
```

To run the API while editing, use `make dev` at the root: the API runs in
Docker with hot reload from `app/`, and PostgreSQL (5432), Redis (6379) and
MinIO (9000) are published on localhost for tools and debugging.

## Layout

| Path | Contents |
|---|---|
| `app/api/` | HTTP layer: dependencies, idempotency, health, `/api/v1` routers |
| `app/core/` | settings, logging, errors, middleware, database, security, metrics |
| `app/modules/` | domain modules: documents, parsing, extraction, validation, comparison, reviews, search, jobs, identity, auditing |
| `app/workers/` | Celery app, stage handlers, dispatcher, local file cache |
| `app/shared/` | money, dates, text, enums |
| `alembic/` | migrations (`uv run alembic revision -m "…"`) |
| `tests/` | `unit/`, `api/`, `workers/`, `security/`, `integration/` |
| `evaluation/` | labeled dataset, generator, evaluation runner, measured results |
| `scripts/` | `init_env`, `bootstrap`, `create_admin`, `smoke_test`, `benchmark`, `reindex`, `export_openapi` |

## Conventions

* Money is `Decimal` end to end (`NUMERIC(20,4)` in the database); floats are rejected.
* Enumerations are `StrEnum`s in `app/shared/enums.py`, stored as `VARCHAR`
  with a `CHECK` constraint. A new member needs a migration.
* Every background stage is idempotent and commits its result together with
  the next stage's outbox event.
* After changing a request or response model, run `make api-types` at the
  root so the frontend's types follow; CI fails on drift.
