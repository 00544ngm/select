# A+B Bundling API

FastAPI backend with PostgreSQL persistence, Redis queue, and ARQ worker.

## Prerequisites

- Python 3.13+
- PostgreSQL 17 (via Docker or local install)
- Redis 8 (via Docker or local install)

## Quick Start

```powershell
# Start infrastructure
docker compose up -d postgres redis

# Run database migrations
.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini upgrade head

# Start the API server
.venv\Scripts\uvicorn.exe backend.main:app --host 127.0.0.1 --port 8000 --reload

# Start the ARQ worker (separate terminal)
.venv\Scripts\python.exe -m arq backend.workers.settings.WorkerSettings
```

## Configuration

Copy `.env.example` to `backend/.env` and customize:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://bundling:bundling@127.0.0.1:5432/bundling` | PostgreSQL connection string |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection string |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed CORS origins |
| `ARTIFACT_DIR` | `output/bundling` | Artifact storage directory |
| `API_PREFIX` | `/api/v1` | API URL prefix |
| `PROVIDER_ENCRYPTION_KEY` | empty | Optional fixed Fernet key for encrypting provider secrets |
| `PROVIDER_KEY_FILE` | `backend/.api-config.key` | Local encryption-key file generated when no fixed key is supplied |

### API Provider Settings

Open the frontend at `/settings/api` to configure the global provider settings used by all new tasks. OpenAI, CatToken, and the custom OpenAI-compatible service can be enabled as primary providers. DeepSeek is reserved for secondary verification.

Provider API keys are encrypted before they are stored in PostgreSQL. API responses expose only a masked value and the settings endpoints accept loopback clients (`127.0.0.1` or `::1`) only. This is a local administration boundary, not user authentication; do not expose the backend settings endpoints through a public reverse proxy.

When `PROVIDER_ENCRYPTION_KEY` is not set, the backend creates `backend/.api-config.key`. Back up that file together with the PostgreSQL database. Restoring only the database, or losing/regenerating the key file, makes stored API keys unreadable. The key file is ignored by Git and must remain private.

On startup, legacy provider values from the root `.env` are imported only when that provider has no database configuration. The import is idempotent and never overwrites values saved from `/settings/api`; use the frontend for subsequent changes.

### External Services

Override URLs to use hosted services:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
$env:REDIS_URL="redis://user:pass@host:6379/0"
```

## Commands

```powershell
# Run database migrations
.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini upgrade head

# Create a new migration
.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini revision --autogenerate -m "description"

# Run tests
.venv\Scripts\python.exe -m pytest backend/tests -q

# Lint
.venv\Scripts\ruff.exe check backend/

# Type check (optional)
.venv\Scripts\mypy.exe backend/
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health/live` | Liveness probe |
| GET | `/api/v1/health/ready` | Readiness probe (DB, Redis, Worker) |
| GET | `/api/v1/settings/providers` | List masked provider settings (localhost only) |
| POST | `/api/v1/settings/providers/{slug}/test` | Test a draft provider configuration (localhost only) |
| PUT | `/api/v1/settings/providers/{slug}` | Save an encrypted provider configuration (localhost only) |
| POST | `/api/v1/jobs/hypothesis` | Submit a hypothesis analysis |
| POST | `/api/v1/jobs/judgment` | Submit a judgment analysis |
| POST | `/api/v1/jobs/batch` | Submit a batch analysis |
| GET | `/api/v1/jobs` | List jobs (paginated) |
| GET | `/api/v1/jobs/{id}` | Get job details |
| POST | `/api/v1/jobs/{id}/retry` | Retry a failed job |
| GET | `/api/v1/jobs/{id}/result` | Get completed job result |
| GET | `/api/v1/jobs/{id}/artifacts/{kind}` | Download artifact (json/excel) |

## Architecture

```
FastAPI (process)                ARQ Worker (single-concurrency process)
     │                                   │
     ├── POST /jobs → validate+enqueue   ├── claim job atomically
     ├── GET  /jobs → read from DB       ├── run browser/LLM analysis
     └── GET  /health → probe services   └── write artifacts + result
               │                                   │
          ┌────┴──────────────┐              ┌─────┴──────┐
     PostgreSQL           Redis           Redis         Local FS
    (source of truth)  (queue/progress)  (queue)    (artifact store)
```

The `app/` package (business core) never imports FastAPI, SQLAlchemy, or Redis.
