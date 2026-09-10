# A+B Bundling Platform Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the existing bundling engine, expose it through a durable FastAPI/Redis/PostgreSQL backend, and build the approved Next.js operations workbench without breaking the existing CLI.

**Architecture:** Keep `app/` as the framework-independent core. Add `backend/` as an API, persistence, and worker adapter layer, and add `frontend/` as an independent Next.js client. PostgreSQL is authoritative; Redis provides queue/progress/cache services.

**Tech Stack:** Python 3.13, pytest, Ruff, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL, Redis, ARQ, Next.js, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Hook Form, Zod, Vitest, Testing Library, Playwright.

---

## Source Documents

- Design: `docs/superpowers/specs/2026-07-15-web-platform-design.md`
- UI reference: `docs/design/bundling-dashboard-layout.png`
- Phase 0: `docs/superpowers/plans/2026-07-15-core-stabilization.md`
- Backend: `docs/superpowers/plans/2026-07-15-fastapi-backend.md`
- Frontend: `docs/superpowers/plans/2026-07-15-nextjs-frontend.md`

## Mandatory Execution Order

- [x] **Checkpoint 1: Core stabilization**

  Execute every task in `2026-07-15-core-stabilization.md`. Do not scaffold the Web stack until regression tests, Ruff, and CLI smoke tests pass with a healthy Python interpreter.

- [ ] **Checkpoint 2: Backend foundation**

  Execute every task in `2026-07-15-fastapi-backend.md`. Stop after API/worker integration tests, Alembic migration checks, and health endpoints pass.

- [ ] **Checkpoint 3: Frontend workbench**

  Execute every task in `2026-07-15-nextjs-frontend.md`. Stop after component tests, TypeScript checks, Next.js production build, and responsive Playwright screenshots pass.

- [ ] **Checkpoint 4: Integrated verification**

  Run:

  ```powershell
  python -m pytest tests backend/tests -q
  ruff check app tests backend
  npm --prefix frontend test -- --run
  npm --prefix frontend run typecheck
  npm --prefix frontend run build
  docker compose config
  ```

  Expected: all commands exit `0` and report no failures.

- [ ] **Checkpoint 5: Local smoke test**

  Start PostgreSQL, Redis, API, worker, and frontend. Submit one mocked/safe hypothesis job, verify progress reaches `completed`, open the result page, and download JSON and Excel artifacts.

## Commit Policy

Each numbered task ends with a local commit. Do not combine unrelated tasks. Do not push or create a remote repository unless explicitly requested.

Suggested phase tags after verification:

```powershell
git tag -a core-stable-v1 -m "Core stabilization complete"
git tag -a backend-v1 -m "FastAPI backend complete"
git tag -a web-v1 -m "Next.js workbench complete"
```

Tags are optional and must only be created after their corresponding fresh verification commands pass.

