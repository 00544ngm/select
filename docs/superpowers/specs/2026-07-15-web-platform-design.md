# A+B Bundling Web Platform Design

**Date:** 2026-07-15  
**Status:** Ready for implementation review  
**Visual reference:** `docs/design/bundling-dashboard-layout.png`

> Repository note: the current workspace is not a Git repository, so this specification cannot be committed until version control is initialized by the owner.

## 1. Objective

Build a separated Next.js frontend and FastAPI backend around the existing A+B bundling system while preserving the current CLI, scraper, LLM, JSON, Excel, and checkpoint behavior. The Web platform adds a durable task model, observable execution, history, and structured APIs; it does not replace the existing domain services.

## 2. Compatibility Contract

The following behavior must remain available throughout implementation:

- `python -m app.main --mode generate --url ...`
- `python -m app.main --mode judge --a-url ... --b-urls ...`
- `python -m app.main --mode batch --input ...`
- Existing JSON and Excel result formats remain readable.
- Existing prompt files remain the source of bundling instructions.
- Existing `ProductService`, `HypothesisService`, and `JudgmentService` remain usable without FastAPI, PostgreSQL, or Redis.

New Web code may call existing services through adapters. Existing services must not import FastAPI, SQLAlchemy, Redis, or frontend concepts.

## 3. Delivery Scope

### Phase 0: Stabilize the Existing Core

Fix the confirmed audit findings before exposing the core through an API:

- Strict hostname validation for Walmart and Amazon URLs.
- Failed checkpoint entries become retryable during resume.
- Required scraped fields are validated before sending data to the LLM.
- LLM structured output uses a real schema and validates returned data.
- Empty judgment results export safely to Excel.
- Result filenames cannot collide within the same second.
- Missing `ProductDTO` type import and current Ruff findings are corrected.
- Browser/CDP ownership and cleanup behavior are made explicit and safe.
- Regression tests cover each behavior.

### Phase 1: Backend Foundation

Add a standalone `backend/` application that imports the existing `app/` package. FastAPI owns HTTP validation, persistence, task submission, status endpoints, and artifact download. ARQ workers consume Redis jobs and invoke existing business services.

PostgreSQL is the source of truth for tasks, product snapshots, results, errors, and artifact metadata. Redis stores queue entries, transient progress, short-lived locks, and optional scrape cache entries. A Redis loss may delay execution but must not erase completed task history.

### Phase 2: Frontend Workbench

Add a standalone `frontend/` Next.js application using TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Hook Form, and Zod. The first screen is the operational workbench shown in the approved layout, not a landing page.

The UI includes:

- Hypothesis generation form.
- Bundle judgment form with one A URL and multiple B URLs.
- Batch task creation and resume/retry controls.
- Live task status and progress polling.
- Result summary, structured details, JSON download, and Excel download.
- Task history with status, mode, product title, timestamps, and retry action.
- Backend, database, Redis, and worker health indicators.

## 4. Repository Boundaries

```text
app/                         Existing domain and CLI application
backend/
  api/                       FastAPI routers and request/response schemas
  application/               Job orchestration adapters
  db/                        SQLAlchemy models, sessions, repositories
  migrations/                Alembic migrations
  workers/                   ARQ settings and job functions
  main.py                    FastAPI entry point
frontend/
  app/                       Next.js App Router pages
  components/                Workbench and shared UI components
  lib/                       API client, query keys, schemas, formatting
  tests/                     Frontend behavior tests
docs/                        Design, plans, and operations documentation
```

The existing `app/` directory is not moved. This avoids import breakage and allows the CLI and Web worker to share the same tested services.

## 5. Backend Architecture

### API Layer

The API is versioned under `/api/v1`.

- `POST /jobs/hypothesis`: submit one product URL.
- `POST /jobs/judgment`: submit one A URL and one or more B URLs.
- `POST /jobs/batch`: submit a URL list.
- `GET /jobs`: paginated task history with mode and status filters.
- `GET /jobs/{job_id}`: status, progress, error, and result summary.
- `POST /jobs/{job_id}/retry`: retry failed work using the original input.
- `GET /jobs/{job_id}/result`: structured JSON result.
- `GET /jobs/{job_id}/artifacts/{kind}`: download JSON or Excel artifact.
- `GET /health/live`: process liveness.
- `GET /health/ready`: PostgreSQL, Redis, and worker readiness.

FastAPI returns immediately after durable job creation and queue submission. Long-running browser and LLM work never executes in the API process.

### Worker Layer

ARQ is used because the workload and existing code are asynchronous and Redis is already available. Workers execute one analysis job at a time by default to avoid competing for the same CDP browser profile. Concurrency becomes configurable only after browser isolation tests pass.

Each worker job:

1. Claims the PostgreSQL job with an atomic status transition.
2. Publishes progress to Redis and PostgreSQL.
3. Starts the browser manager.
4. Calls the existing product and analysis services.
5. Saves JSON and Excel artifacts using collision-safe names.
6. Persists the normalized result and artifact metadata.
7. Marks the job completed or failed with a user-safe error.
8. Stops owned browser resources in a `finally` block.

### Persistence Model

`analysis_jobs` stores job ID, mode, status, request payload, progress, result payload, error code/message, retry lineage, timestamps, and optimistic version. `product_snapshots` stores the product URL, platform, scraped fields, and scrape timestamp. `job_products` links A/B/input roles to snapshots. `artifacts` stores job ID, type, path, size, checksum, and creation time.

Large binaries are kept on local disk in the first release; PostgreSQL stores metadata and paths. The repository interface leaves room for object storage later without changing API contracts.

## 6. Frontend Architecture

The approved layout becomes a responsive application shell:

- Desktop: fixed 232 px sidebar, flexible work area, 412 px status inspector.
- Tablet: collapsible sidebar and inspector below the form.
- Mobile: top navigation, stacked form/status/result sections, no horizontal overflow.

The visual system uses white, graphite, neutral gray, and semantic green. Cards are reserved for status summaries and result rows; primary page sections remain flat and bordered. Lucide icons are used for familiar actions. All forms use accessible labels, keyboard navigation, visible focus states, and inline validation.

Server state is handled by TanStack Query. Forms validate with shared Zod schemas. Job pages poll while status is `queued` or `running`, then stop automatically on `completed` or `failed`.

## 7. Data Flow

```text
User submits form
  -> Next.js validates input
  -> FastAPI validates and creates PostgreSQL job
  -> FastAPI enqueues Redis job
  -> ARQ worker invokes existing services
  -> Worker writes result/artifacts and updates PostgreSQL
  -> Frontend polls job endpoint
  -> Frontend renders result and download actions
```

CLI calls continue to invoke existing services directly and do not require the Web stack.

## 8. Error Handling

Errors use stable codes such as `INVALID_URL`, `SCRAPE_INCOMPLETE`, `CAPTCHA_REQUIRED`, `LLM_UNAVAILABLE`, `LLM_INVALID_OUTPUT`, `EXPORT_FAILED`, and `INTERNAL_ERROR`. API responses do not expose API keys, browser profile paths, stack traces, raw provider responses, or complete scraped review text.

Retry policy is explicit:

- Validation failures are not retryable.
- Temporary browser, network, Redis, and LLM failures are retryable with capped backoff.
- Failed user-triggered jobs can be retried from the UI.
- A retry creates a new job linked to the failed job, preserving audit history.

## 9. Security

- Parse URLs with `urllib.parse` and compare normalized hostnames against an allowlist.
- Restrict CORS to configured frontend origins.
- Keep OpenAI keys and database credentials only in backend environment variables.
- Treat all scraped content as untrusted data and delimit it in prompts.
- Validate LLM responses before persistence and rendering.
- Prevent arbitrary artifact path access by resolving downloads through artifact IDs.
- Avoid logging secrets, request headers, or complete external page content.

Authentication is out of scope for the first local deployment. The API binds to localhost by default. Authentication must be added before exposing the service beyond a trusted network.

## 10. Testing Strategy

- Existing Python unit tests remain and gain regression coverage for Phase 0 fixes.
- Backend unit tests cover schemas, repositories, status transitions, and adapters.
- FastAPI integration tests use dependency overrides and a test database.
- Worker tests use fake browser/LLM adapters and a real result store contract.
- Frontend component tests cover forms, states, progress, result rendering, and errors.
- Playwright end-to-end tests cover hypothesis submission, judgment submission, failed retry, history, and artifact download.
- A CLI smoke test confirms existing command parsing and service construction remain intact.

Every behavior change follows red-green-refactor. Completion requires Python tests, Ruff, frontend tests, TypeScript checks, Next.js build, and Playwright desktop/mobile screenshots.

## 11. Local Operations

Docker Compose will define PostgreSQL and Redis defaults while allowing external connection URLs. Backend and frontend run as separate development processes. Required environment variables are documented in `.env.example` files without copying secrets from the existing `.env`.

Expected local endpoints:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## 12. Acceptance Criteria

- Existing CLI modes remain available and their core tests pass.
- Web users can submit generate, judgment, and batch jobs.
- Jobs survive API restarts because PostgreSQL is authoritative.
- Failed jobs are visible and retryable.
- Completed jobs expose structured results and JSON/Excel downloads.
- The frontend matches the approved layout across desktop and mobile.
- No secrets appear in API responses, frontend bundles, logs, or committed examples.
- Full verification commands and local startup instructions are documented.

## 13. Explicit Non-Goals

- User accounts, roles, billing, and multi-tenant isolation.
- Public internet deployment.
- Replacing local artifacts with cloud object storage.
- Parallel browser workers sharing one Chrome profile.
- Migrating or deleting existing output files.
- Rewriting the existing domain services solely for stylistic consistency.
