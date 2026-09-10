# FastAPI Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable FastAPI API and ARQ worker layer around the stabilized core with PostgreSQL as the source of truth and Redis for queue/progress services.

**Architecture:** `backend/` imports existing `app/` services through adapters; `app/` never imports backend frameworks. API processes validate and enqueue work, while a single-concurrency ARQ worker owns browser/LLM execution.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, asyncpg, Alembic, Redis, ARQ, httpx, pytest.

---

### Task 1: Scaffold Backend Configuration and Application Factory

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/main.py`
- Create: `backend/api/router.py`
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Test: `backend/tests/test_health.py`

- [x] **Step 1: Write a failing liveness test**

```python
from fastapi.testclient import TestClient
from backend.main import create_app


def test_liveness():
    response = TestClient(create_app()).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [x] **Step 2: Verify RED**

Run `.venv\Scripts\python.exe -m pytest backend/tests/test_health.py -q`. Expected: `backend.main` is missing.

- [x] **Step 3: Implement configuration and factory**

`BackendSettings` must define `database_url`, `redis_url`, `cors_origins`, `artifact_dir`, and `api_prefix="/api/v1"`. `create_app()` creates FastAPI, adds configured CORS origins, and includes a router with `/health/live`.

- [x] **Step 4: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_health.py -q
git add backend
git commit -m "feat: scaffold FastAPI backend"
```

### Task 2: Add Job Persistence and Initial Migration

**Files:**
- Create: `backend/db/base.py`
- Create: `backend/db/session.py`
- Create: `backend/db/models.py`
- Create: `backend/db/repositories.py`
- Create: `backend/migrations/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/versions/0001_create_job_tables.py`
- Test: `backend/tests/test_job_repository.py`

- [x] **Step 1: Write failing repository tests**

```python
job = await repository.create(mode="hypothesis", request_payload={"url": product_url})
assert job.status == "queued"
claimed = await repository.transition(job.id, expected="queued", target="running")
assert claimed.status == "running"
assert await repository.transition(job.id, expected="queued", target="running") is None
```

- [x] **Step 2: Verify RED**

Run the repository test. Expected: repository and models are missing.

- [x] **Step 3: Implement models and repository**

Create `AnalysisJob`, `ProductSnapshot`, `JobProduct`, and `Artifact` models using UUID primary keys and timezone-aware timestamps. Store request/result payloads as JSONB. Implement create, get, list, atomic transition, progress, complete, and fail methods.

- [x] **Step 4: Implement migration**

Migration `0001` creates all four tables, status/mode indexes, foreign keys, and a unique `(job_id, kind)` artifact constraint.

- [x] **Step 5: Verify migration and commit**

```powershell
.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini upgrade head
.venv\Scripts\python.exe -m pytest backend/tests/test_job_repository.py -q
git add backend/db backend/migrations backend/tests/test_job_repository.py
git commit -m "feat: persist analysis jobs in PostgreSQL"
```

### Task 3: Define Versioned Job API Schemas

**Files:**
- Create: `backend/api/schemas/jobs.py`
- Create: `backend/api/errors.py`
- Test: `backend/tests/test_job_schemas.py`

- [x] **Step 1: Write failing schema tests**

```python
def test_hypothesis_request_rejects_lookalike_host():
    with pytest.raises(ValidationError):
        HypothesisJobCreate(url="https://walmart.com.evil.example/ip/123")


def test_judgment_requires_at_least_one_b_url():
    with pytest.raises(ValidationError):
        JudgmentJobCreate(a_url=VALID_URL, b_urls=[])
```

- [x] **Step 2: Implement schemas**

Create `HypothesisJobCreate`, `JudgmentJobCreate`, `BatchJobCreate`, `JobSummary`, `JobDetail`, `ArtifactResponse`, and paginated `JobListResponse`. Reuse `detect_product_platform` for every URL. Define stable error payload `{code, message, retryable}`.

- [x] **Step 3: Verify and commit**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_job_schemas.py -q
git add backend/api
git commit -m "feat: define versioned job API contracts"
```

### Task 4: Implement Redis Queue Gateway and Submission Service

**Files:**
- Create: `backend/application/queue.py`
- Create: `backend/application/job_service.py`
- Test: `backend/tests/test_job_service.py`

- [x] **Step 1: Write failing service tests**

```python
job = await service.submit_hypothesis(HypothesisJobCreate(url=VALID_URL))
repository.create.assert_awaited_once()
queue.enqueue.assert_awaited_once_with("run_analysis_job", str(job.id))


queue.enqueue.side_effect = RuntimeError("redis unavailable")
with pytest.raises(ServiceUnavailableError):
    await service.submit_hypothesis(HypothesisJobCreate(url=VALID_URL))
repository.fail.assert_awaited_once()
```

- [x] **Step 2: Implement gateway/service**

Define a `JobQueue` protocol and `ArqJobQueue`. `JobService` creates the PostgreSQL row before enqueueing; enqueue failures mark it failed with `QUEUE_UNAVAILABLE` and raise a retryable API error.

- [x] **Step 3: Verify and commit**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_job_service.py -q
git add backend/application backend/tests/test_job_service.py
git commit -m "feat: enqueue durable analysis jobs"
```

### Task 5: Expose Job, Retry, Result, and Artifact Routes

**Files:**
- Create: `backend/api/routes/jobs.py`
- Create: `backend/api/dependencies.py`
- Modify: `backend/api/router.py`
- Test: `backend/tests/test_jobs_api.py`

- [x] **Step 1: Write failing API tests**

Cover `POST /jobs/hypothesis` returning `202`, `GET /jobs`, `GET /jobs/{id}`, missing job `404`, failed-job retry creating a linked job, result access before completion `409`, and artifact download by registered ID only.

- [x] **Step 2: Implement routes**

Routes delegate to `JobService`; they never instantiate browser or LLM services. Artifact download resolves the unique `(job_id, kind)` database record, verifies the resolved path is under `artifact_dir`, and returns `FileResponse` with a fixed media type.

- [x] **Step 3: Verify and commit**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py -q
git add backend/api backend/tests/test_jobs_api.py
git commit -m "feat: expose analysis job APIs"
```

### Task 6: Build the Core Analysis Adapter and ARQ Worker

**Files:**
- Create: `backend/application/analysis_runner.py`
- Create: `backend/workers/jobs.py`
- Create: `backend/workers/settings.py`
- Test: `backend/tests/test_analysis_runner.py`
- Test: `backend/tests/test_worker_jobs.py`

- [x] **Step 1: Write failing runner tests**

Test hypothesis, judgment, and batch dispatch with injected browser, LLM, storage, and exporter factories. Assert browser stop runs after success and failure. Assert progress sequence is monotonic: `5, 20, 55, 85, 100`.

- [x] **Step 2: Implement adapter**

`AnalysisRunner.run(job)` constructs existing `ProductService`, `HypothesisService`, or `JudgmentService`, persists product snapshots, invokes collision-safe storage/export, and returns `{result, artifacts}` without importing FastAPI.

- [x] **Step 3: Implement worker**

`run_analysis_job(ctx, job_id)` atomically claims the job, calls the runner, writes progress to Redis/PostgreSQL, and maps known exceptions to stable codes. `WorkerSettings.max_jobs = 1`.

- [x] **Step 4: Verify and commit**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py backend/tests/test_worker_jobs.py -q
git add backend/application/analysis_runner.py backend/workers backend/tests
git commit -m "feat: execute analysis jobs in ARQ worker"
```

### Task 7: Add Readiness, Logging, and Security Boundaries

**Files:**
- Create: `backend/api/routes/health.py`
- Create: `backend/logging.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_readiness.py`
- Test: `backend/tests/test_security.py`

- [x] **Step 1: Write failing tests**

Assert readiness reports separate `database`, `redis`, and `worker` states; CORS rejects unknown origins; exception responses omit stack traces, API keys, provider payloads, and local paths.

- [x] **Step 2: Implement boundaries**

Add dependency-injected probes with a two-second timeout, structured request IDs, and exception handlers that return stable error payloads. Bind the documented default server command to `127.0.0.1`.

- [x] **Step 3: Verify and commit**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_readiness.py backend/tests/test_security.py -q
git add backend
git commit -m "feat: harden backend health and error handling"
```

### Task 8: Add Local Infrastructure and Backend Verification

**Files:**
- Create: `docker-compose.yml`
- Create: `backend/README.md`
- Create: `docs/verification/backend.md`

- [x] **Step 1: Define local services**

Compose defines PostgreSQL 17 and Redis 8 with named volumes, health checks, localhost-only ports, and credentials sourced from environment variables with documented local defaults.

- [x] **Step 2: Document commands**

Document database migration, API, worker, tests, and external PostgreSQL/Redis URL overrides.

- [x] **Step 3: Run verification**

```powershell
docker compose config
.venv\Scripts\python.exe -m pytest tests backend/tests -q
.venv\Scripts\ruff.exe check app tests backend
.venv\Scripts\python.exe -m compileall -q app backend tests
```

Expected: all commands exit `0`.

- [x] **Step 4: Commit**

```powershell
git add docker-compose.yml backend/README.md docs/verification/backend.md
git commit -m "chore: document and verify backend stack"
```

## Phase Completion Gate

Do not start frontend API integration until a real PostgreSQL migration, Redis enqueue/dequeue, API readiness, and mocked worker completion have all been verified locally.
