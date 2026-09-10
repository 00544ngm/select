# Backend Verification

**Date:** 2026-07-15  
**Branch:** `feature/web-platform`  
**Python:** 3.13.12

## Infrastructure

```powershell
docker compose config
```

Expected: docker-compose.yml validates without error.

## Test Suite

```powershell
.venv\Scripts\python.exe -m pytest tests backend/tests -q
```

## Lint

```powershell
.venv\Scripts\ruff.exe check app tests backend
```

## Bytecode Compilation

```powershell
.venv\Scripts\python.exe -m compileall -q app backend tests
```

## Verified Behaviors

- Liveness endpoint returns `{"status": "ok"}` without dependencies.
- Readiness probes database, redis, and worker independently (2s timeout).
- CORS rejects unknown origins and allows configured frontend origin.
- Unhandled exceptions return `{code, message, retryable}` without stack traces or secrets.
- Responses include `X-Request-ID` header (from client or auto-generated).
- Job CRUD: create, list (paginated with mode/status filters), get by ID.
- Atomic status transitions prevent double-claiming by workers.
- Failed jobs can be retried; non-failed jobs return 409.
- Result access before completion returns 409.
- Artifact download validates kind, path safety, and file existence.
- Hypothesis/judgment/batch jobs enqueue to Redis via ARQ.
- Worker claims jobs atomically, reports progress via Redis, and persists artifacts.
- Worker classifies known exceptions (ScrapeError, LLMError, etc.) to stable error codes.
- Worker sanitizes unknown exceptions to `INTERNAL_ERROR`.
