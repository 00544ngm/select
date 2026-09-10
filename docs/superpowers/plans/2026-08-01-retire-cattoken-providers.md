# CatToken Providers Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove CatToken OpenAI and CatToken Claude from every new configuration and task path, securely delete their saved configurations, and preserve historical task rendering.

**Architecture:** Treat CatToken slugs as retired write-time identities while preserving read-time labels for historical payloads. Remove provider slots from the settings service and task schemas, sanitize browser preferences, and perform an exact-slug database cleanup that never decrypts secrets.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async repositories, React/Next.js, TypeScript, Vitest, pytest.

---

### Task 1: Retire CatToken at backend write boundaries

**Files:**
- Modify: `backend/api/schemas/providers.py`
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/application/provider_service.py`
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_job_service.py`
- Test: `backend/tests/test_provider_clients.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: Write failing tests**

Assert provider listing omits both CatToken slugs, job schemas reject both slugs, and resolver returns a stable non-retryable retired-provider error for either slug.

- [ ] **Step 2: Run focused RED tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_job_service.py backend/tests/test_provider_clients.py backend/tests/test_providers_api.py -q`

Expected: failures showing CatToken slots and task literals are still accepted.

- [ ] **Step 3: Implement minimal retirement rules**

Remove CatToken from active `ProviderSlug`/`TaskProvider` literals and active provider slots. Add a resolver guard equivalent to:

```python
RETIRED_PROVIDER_SLUGS = frozenset({"cattoken", "cattoken_claude"})

if slug in RETIRED_PROVIDER_SLUGS:
    raise ProviderResolutionError(
        code="PROVIDER_RETIRED",
        message="该供应商已下线，请选择其他供应商",
        retryable=False,
    )
```

Do not remove historical label formatting or rewrite stored task payloads.

- [ ] **Step 4: Run focused GREEN tests and Ruff**

Run the focused pytest command and Ruff on the four production Python files plus modified tests. Expected: all pass.

### Task 2: Remove CatToken from frontend configuration and task entry points

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/workbench-model-preference.ts`
- Modify: `frontend/components/workbench/model-select.tsx`
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Modify: task form components that consume `ProviderSlug`
- Test: `frontend/tests/provider-settings.test.tsx`
- Test: `frontend/tests/job-forms.test.tsx`
- Test: `frontend/tests/model-select.test.tsx`
- Test: `frontend/tests/workbench-model-preference.test.ts`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: Write failing UI and preference tests**

Assert settings tabs and every task/cross-review select contain neither CatToken label. Seed stored preferences with both retired slugs and assert each entry resolves to OpenAI and persists the sanitized selection.

- [ ] **Step 2: Run focused RED tests**

Run: `npm.cmd test -- --run tests/provider-settings.test.tsx tests/job-forms.test.tsx tests/model-select.test.tsx tests/workbench-model-preference.test.ts tests/job-detail.test.tsx`

Expected: CatToken remains visible or stale preferences remain selected.

- [ ] **Step 3: Implement minimal frontend removal**

Remove CatToken from active frontend provider unions and defaults. Keep historical labels in `frontend/lib/model-label.ts`. Add preference validation equivalent to:

```ts
const activeProviders = new Set(["openai", "custom"]);
const provider = activeProviders.has(saved.provider) ? saved.provider : "openai";
```

Use the actual provider catalog to validate model availability before persisting the fallback.

- [ ] **Step 4: Run focused GREEN tests, typecheck, and targeted diff check**

Expected: focused tests and `npm.cmd run typecheck` pass; CatToken strings remain only in historical-label compatibility tests/code.

### Task 3: Securely delete saved CatToken configurations

**Files:**
- Modify or create a narrowly scoped backend maintenance/migration module following the existing provider repository pattern
- Test: corresponding backend repository/service test
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Write the deletion safety test**

Insert fixtures for `openai`, `cattoken`, `cattoken_claude`, `deepseek`, and `custom`; execute cleanup; assert exactly the two CatToken records are deleted, the other records are byte-for-byte unchanged, and a second cleanup deletes zero rows.

- [ ] **Step 2: Run the focused RED test**

Expected: cleanup function is missing.

- [ ] **Step 3: Implement exact-slug idempotent cleanup**

Use an explicit allowlist and repository/database transaction. Never decrypt, print, return, or log encrypted key values. Return only a deletion count.

- [ ] **Step 4: Inspect targets, execute cleanup once, and verify**

Before deletion, query only target slugs/count. Execute cleanup. Query target slugs/count again and assert zero; query non-target count before/after and assert unchanged. Record only counts and slugs in the Chinese iteration log.

### Task 4: Full regression and live UI verification

**Files:**
- Modify: `docs/verification/2026-08-01-retire-cattoken-providers.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Run backend and frontend regression**

Run full backend pytest, focused/full Ruff, full frontend Vitest, TypeScript typecheck, Next.js production build, and `git diff --check`.

- [ ] **Step 2: Restart and verify runtime health**

Run `启动.ps1`; verify frontend HTTP 200 and backend live/ready health are OK.

- [ ] **Step 3: Verify live pages**

Confirm API settings has no CatToken tabs, each workbench entry has no CatToken option, a stale saved CatToken preference falls back to OpenAI, and a historical CatToken task remains readable with its historical label.

- [ ] **Step 4: Write final verification record**

Record commands, pass counts, exact deletion counts, known warnings, rollback limitation, and confirmation that no credentials or historical tasks were deleted.
