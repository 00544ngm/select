# API Model Catalog and Cross-Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make API settings the single source of truth for tested provider/model identities and let users run cross-review with two explicitly selected, usable models.

**Architecture:** Reuse the existing provider configuration API as the model catalog. Add a small server-side validation/serialization boundary for cross-review requests, persist a redacted model identity snapshot and status in the existing job JSON payload, and render the same identity in API settings, job results, and history. Keep legacy `gpt`/`deepseek` payloads readable without migration.

**Tech Stack:** FastAPI, SQLAlchemy JSON payloads, Python pytest, Next.js/React, React Query, Vitest, Testing Library, MSW, existing shadcn/ui primitives.

---

## Task 1: Define shared model identity and catalog formatting

**Files:**
- Modify: `backend/api/schemas/providers.py`
- Modify: `backend/application/provider_clients.py`
- Modify: `frontend/lib/api/types.ts`
- Create: `frontend/lib/model-identity.ts`
- Test: `backend/tests/test_providers_api.py`
- Test: `frontend/tests/provider-api-client.test.ts`

- [ ] **Step 1: Write failing tests**

Add assertions that a public provider exposes a stable model option containing `provider`, `provider_display_name`, `api_protocol`, `model`, `is_default`, `is_enabled`, `test_status`, `tested_at`, and `test_message`, and that the frontend formatter returns `供应商 · 协议 · 模型` without exposing secrets.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run from `backend/`: `.venv\Scripts\python.exe -m pytest tests/test_providers_api.py -q`.
Run from `frontend/`: `npm.cmd test -- --run tests/provider-api-client.test.ts`.
Expected: failures because the catalog contract and formatter do not exist yet.

- [ ] **Step 3: Implement the minimal contract**

Add a Pydantic `ProviderModelOption` and return catalog options derived from `supported_models`; mark `default_model` as default and expose only public status fields. Add TypeScript types and a formatter that uses the protocol's Chinese label while retaining the raw model name.

- [ ] **Step 4: Run focused tests and verify green**

Repeat both commands; expected result is zero failures and no secret value in response serialization.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/schemas/providers.py backend/application/provider_clients.py frontend/lib/api/types.ts frontend/lib/model-identity.ts backend/tests/test_providers_api.py frontend/tests/provider-api-client.test.ts
git commit -m "feat: expose tested provider model catalog"
```

## Task 2: Show the model catalog and test state in API settings

**Files:**
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Modify: `frontend/tests/provider-settings.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Assert that the settings panel renders each supported model with provider, protocol, default badge, test status, and a visible “可用于交叉验证” status only when the provider is enabled and its last test succeeded. Add a failed-test case that renders the sanitized error and does not mark the model usable.

- [ ] **Step 2: Run the focused UI test and verify red**

Run from `frontend/`: `npm.cmd test -- --run tests/provider-settings.test.tsx`.
Expected: new assertions fail because only the default model control is currently rendered.

- [ ] **Step 3: Implement the catalog section**

Render a responsive model list below the default model control. Reuse existing `availableModels`, `last_test_status`, `last_tested_at`, and `last_test_message`; do not display API keys. Keep current save/retest gating unchanged.

- [ ] **Step 4: Run the focused UI tests and verify green**

Run the same command and confirm all existing and new provider settings tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/components/settings/provider-settings-panel.tsx frontend/tests/provider-settings.test.tsx
git commit -m "feat: show provider model catalog and test status"
```

## Task 3: Add selectable, server-validated cross-review request

**Files:**
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/api/routes/jobs.py`
- Modify: `backend/db/repositories.py`
- Modify: `backend/workers/jobs.py`
- Modify: `backend/application/analysis_runner.py`
- Test: `backend/tests/test_jobs_api.py`
- Test: `backend/tests/test_cross_review_worker.py`

- [ ] **Step 1: Write failing backend tests**

Cover: two enabled/successful distinct model identities are accepted; same identity, disabled provider, untested provider, missing dual-model result, and existing queued/running cross-review are rejected with explicit conflict codes. Add a worker test proving the selected provider/model are passed to the runner and that a provider error persists `cross_review.status = failed` with a redacted message.

- [ ] **Step 2: Run the focused backend tests and verify red**

Run from `backend/`: `.venv\Scripts\python.exe -m pytest tests/test_jobs_api.py tests/test_cross_review_worker.py -q`.
Expected: failures because the endpoint accepts no body and the worker is hard-coded to GPT/DeepSeek.

- [ ] **Step 3: Implement request validation and persistence**

Add `CrossReviewCreate` and `ModelIdentity` schemas. Resolve each requested provider/model through the provider repository, require enabled + successful test status, reject duplicate identities, and save a redacted selection snapshot under `cross_review` with `status=queued`. Prevent duplicate queued/running submissions. Update the worker to use the snapshot, call the runner with the selected clients, write generic reviewer keys plus identity metadata, and persist `failed`/`skipped` states.

- [ ] **Step 4: Run focused backend tests and verify green**

Repeat the focused command; expected all new validation and failure persistence cases pass while legacy endpoint tests remain green.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/schemas/jobs.py backend/api/routes/jobs.py backend/db/repositories.py backend/workers/jobs.py backend/application/analysis_runner.py backend/tests/test_jobs_api.py backend/tests/test_cross_review_worker.py
git commit -m "feat: validate selectable cross-review models"
```

## Task 4: Replace hard-coded cross-review UI with model selectors and status feedback

**Files:**
- Modify: `frontend/components/jobs/cross-review-panel.tsx`
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Modify: `frontend/lib/api/types.ts`
- Create or modify: `frontend/lib/api/cross-review.ts`
- Test: `frontend/tests/job-detail.test.tsx`
- Test: `frontend/tests/cross-review-format.test.ts`

- [ ] **Step 1: Write failing UI tests**

Assert that the job page loads the provider catalog, renders two complete model selectors, blocks equal or untested selections, posts `{reviewer_a, reviewer_b}`, and shows queued/running/completed/failed feedback with the selected identities. Add a legacy payload test ensuring old GPT/DeepSeek keys still render.

- [ ] **Step 2: Run focused frontend tests and verify red**

Run from `frontend/`: `npm.cmd test -- --run tests/job-detail.test.tsx tests/cross-review-format.test.ts`.
Expected: failures because the current page posts an empty request and hard-codes the labels and keys.

- [ ] **Step 3: Implement the selectors and result rendering**

Use `listProviders()` to build the enabled/test-success catalog, keep selections as `{provider, model}`, submit them through a typed client, stop polling on `completed` or `failed`, and show a sanitized error plus retry action on failure. In `CrossReviewPanel`, render conclusion first, identity cards second, raw text collapsed last; support both generic reviewer keys and legacy keys.

- [ ] **Step 4: Run focused frontend tests and verify green**

Repeat the focused command and confirm the submit body and rendered model identities match the selected options.

- [ ] **Step 5: Commit**

```powershell
git add frontend/components/jobs/cross-review-panel.tsx frontend/app/jobs/[jobId]/page.tsx frontend/lib/api/types.ts frontend/lib/api/cross-review.ts frontend/tests/job-detail.test.tsx frontend/tests/cross-review-format.test.ts
git commit -m "feat: select tested models for cross review"
```

## Task 5: Add model identity to history and compatibility formatting

**Files:**
- Modify: `backend/api/routes/jobs.py`
- Modify: `frontend/components/history/history-table.tsx`
- Modify: `frontend/lib/result-format.ts`
- Modify: `frontend/tests/history.test.tsx`
- Test: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: Write failing history tests**

Assert new results expose a model identity summary, legacy payloads show compatibility labels, and payloads without identity show “历史任务未记录模型身份” rather than guessing from a requested model.

- [ ] **Step 2: Run the focused tests and verify red**

Run backend job tests and the frontend history test; expected failures because history currently has no model identity field.

- [ ] **Step 3: Implement compatibility highlights**

Derive a public identity summary from persisted `provider`, `provider_model`, and cross-review snapshots. Preserve existing score/title highlights and never change historical payloads.

- [ ] **Step 4: Run focused tests and verify green**

Repeat the backend and frontend focused commands.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/routes/jobs.py frontend/components/history/history-table.tsx frontend/lib/result-format.ts frontend/tests/history.test.tsx backend/tests/test_jobs_api.py
git commit -m "feat: display model identity in history"
```

## Task 6: Full verification, restart, and real usability check

**Files:**
- Modify: `docs/优化迭代记录.md`
- Create: `docs/verification/2026-07-31-provider-model-catalog-cross-review.md`

- [ ] **Step 1: Run the complete automated verification**

From `backend/`: `.venv\Scripts\python.exe -m pytest -q`.
From `frontend/`, sequentially run `npm.cmd run build`, `npm.cmd run typecheck`, and `npm.cmd test -- --run`.
Run `git diff --check` from the repository root.

- [ ] **Step 2: Restart services and verify health**

Run `启动.ps1`; check frontend `/`, `/settings`, `/history`, the target job URL, `/api/v1/health/live`, and `/api/v1/health/ready`. Confirm database, Redis, worker, API/Worker contract, and revision are healthy.

- [ ] **Step 3: Perform one real provider-backed check**

In API settings, test the configured provider and select two distinct successful models. On a completed dual-model job, submit cross-review once, observe queued → running → completed or failed, and confirm the result shows the exact provider/protocol/model identities. Do not expose or record secrets and do not overwrite existing history.

- [ ] **Step 4: Record evidence and failures**

Append a new optimization iteration and any failure cases to `docs/优化迭代记录.md`; write command outputs, URLs, selected model identities (without keys), and known limitations to the verification document.

- [ ] **Step 5: Commit the verification record**

```powershell
git add docs/优化迭代记录.md docs/verification/2026-07-31-provider-model-catalog-cross-review.md
git commit -m "docs: verify selectable cross-review models"
```

## Self-review checklist

- The plan covers API settings, selection, backend enforcement, worker execution, result/history rendering, legacy compatibility, failures, and real verification.
- No task changes scoring, prompts, product/keyword data, profit logic, or provider protocols.
- Every production change has a preceding failing test step.
- API keys, cookies, tokens, and full request headers are excluded from payloads, logs, specs, and verification notes.
- Builds and type checks run sequentially to avoid the previously recorded `.next/types` race.
