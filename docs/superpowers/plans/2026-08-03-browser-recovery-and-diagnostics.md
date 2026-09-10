# Desktop Browser Recovery and Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged desktop app recover once from a pre-model Chromium target closure and provide employees with an in-app environment diagnostic workflow without changing Windows security settings.

**Architecture:** Browser lifecycle recovery stays in `PlaywrightBrowserManager`; the Walmart scraper owns the one-retry policy because it executes before any model call. Post-model market-evidence browser failures are converted into evidence status instead of rerunning analysis. A desktop-only diagnostic API reports structured checks, while Electron exposes safe OS navigation actions and the job error UI presents them.

**Tech Stack:** Python 3.12, Playwright async API, FastAPI, pytest/pytest-asyncio, Electron, Next.js/React, TypeScript, Vitest/Testing Library.

---

### Task 1: Preserve the first browser error during cleanup

**Files:**
- Modify: `app/infrastructure/walmart/scraper.py`
- Test: `tests/test_walmart_scraper.py`

- [ ] **Step 1: Write a failing cleanup test**

Add a test whose scrape operation raises a sentinel exception and whose `page.close()` raises `TargetClosedError`; assert the outward exception retains the sentinel cause instead of becoming the cleanup error.

```python
with pytest.raises(ScrapeError, match="original scrape failure"):
    await scraper.scrape_product(URL)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_walmart_scraper.py -k cleanup -q`

Expected: FAIL because `await page.close()` overrides the original error.

- [ ] **Step 3: Add non-overriding page cleanup**

Implement a small helper that closes a page only when present and logs the cleanup exception without raising it:

```python
async def _safe_close_page(page) -> None:
    try:
        await page.close()
    except Exception as error:
        logger.warning("Page cleanup failed: {}", type(error).__name__)
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same command; expected result: PASS.

### Task 2: Add explicit browser restart semantics

**Files:**
- Modify: `app/infrastructure/browser/__init__.py`
- Test: `tests/test_browser_manager.py`

- [ ] **Step 1: Write failing tests for disconnected cleanup and restart**

Test that `stop()` attempts context, browser and Playwright cleanup independently, and that `restart()` creates a new browser/context after a target closure.

```python
await manager.restart()
assert manager._browser is not old_browser
assert manager._context is not old_context
```

- [ ] **Step 2: Verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_browser_manager.py -q`

Expected: FAIL because `restart()` does not exist and `stop()` stops after its first cleanup exception.

- [ ] **Step 3: Implement isolated cleanup and restart**

Add `restart()` as `await stop(raise_errors=False); await start()`. Refactor `stop()` so context, browser, Playwright and owned Chrome cleanup each run in separate guarded blocks. Normal explicit shutdown may report a summarized `BrowserError`; recovery shutdown suppresses cleanup errors after logging.

- [ ] **Step 4: Verify GREEN**

Run the focused tests; expected result: all browser-manager tests pass.

### Task 3: Retry Walmart product scraping once before model invocation

**Files:**
- Modify: `app/infrastructure/walmart/scraper.py`
- Modify: `app/domain/interfaces/__init__.py` only if the browser interface lacks `restart`
- Test: `tests/test_walmart_scraper.py`
- Test: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: Write RED tests for one recovery and bounded failure**

Create one test where the first page raises a target-closed error and the second page returns product data; create another where both pages close and assert exactly two attempts and stable `BROWSER_TARGET_CLOSED` classification.

```python
product = await scraper.scrape_product(URL)
assert product.title == "Recovered product"
browser.restart.assert_awaited_once()
```

- [ ] **Step 2: Verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_walmart_scraper.py backend/tests/test_analysis_runner.py -k 'target_closed or browser_retry' -q`

Expected: FAIL because the scraper currently performs one attempt.

- [ ] **Step 3: Implement the bounded retry**

Split one scrape attempt into `_scrape_product_once`. In `scrape_product`, loop for at most two attempts; only recognized Playwright target/browser-disconnected exceptions trigger `browser.restart()`. On the second closure raise a stable browser-domain error. Other scrape failures are not retried.

- [ ] **Step 4: Prove the Token boundary**

In `backend/tests/test_analysis_runner.py`, assert the product service completes recovery before `ProductTypeReviewer` and `HypothesisService.generate` are called, and assert the LLM call count remains one.

- [ ] **Step 5: Verify GREEN**

Run the focused test command; expected result: recovery succeeds once, persistent closure fails after two attempts, model count remains one.

### Task 4: Degrade post-model market evidence instead of rerunning models

**Files:**
- Modify: `app/services/market_evidence_service.py`
- Modify: `backend/application/analysis_runner.py` only for serialization/status propagation
- Test: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: Write a failing post-model target-closure test**

Make model generation succeed and market evidence raise `TargetClosedError`; assert the runner returns a report, sets market evidence to pending/partial, and calls each configured model exactly once.

- [ ] **Step 2: Verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -k market_evidence_target_closed -q`

Expected: FAIL because the target closure currently aborts the whole task.

- [ ] **Step 3: Implement narrow degradation**

Catch only recognized browser-closure exceptions around evidence verification. Store a safe failure reason and pending status; re-raise model, schema, data and unexpected errors.

- [ ] **Step 4: Verify GREEN**

Run the focused test; expected result: completed report and one model call.

### Task 5: Add desktop runtime diagnostics API

**Files:**
- Create: `backend/desktop/diagnostics.py`
- Create: `backend/api/routes/diagnostics.py`
- Modify: `backend/api/app.py` or the current router-registration file
- Test: `backend/tests/test_desktop_diagnostics.py`

- [ ] **Step 1: Write failing structured-check tests**

Cover browser missing, browser probe success, browser immediate exit and unwritable runtime directory. Assert the response contains only check name, status, Chinese summary and safe detail.

```python
assert payload["checks"]["browser"]["status"] == "failed"
assert "API Key" not in json.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 2: Verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_diagnostics.py -q`

Expected: collection failure because the diagnostic module/route does not exist.

- [ ] **Step 3: Implement diagnostic units**

Use focused functions for writable-directory probes, packaged-browser existence, Chromium launch/new-page/close, worker-heartbeat age and service readiness. Return `passed`, `failed` or `manual_check`; never modify Defender.

- [ ] **Step 4: Register the desktop-only endpoint**

Expose `GET /api/v1/desktop/diagnostics` behind the existing desktop session dependency. In non-desktop mode return the supported web-safe subset.

- [ ] **Step 5: Verify GREEN**

Run the focused test; expected result: all diagnostics tests pass.

### Task 6: Expose safe Electron operating-system actions

**Files:**
- Modify: `desktop/src/main.ts`
- Modify: `desktop/src/preload.ts`
- Modify: `desktop/src/global.d.ts` or the current bridge type declaration
- Test: `desktop/tests/service-log.test.ts` or a new `desktop/tests/system-actions.test.ts`

- [ ] **Step 1: Write RED bridge tests**

Assert the bridge exposes `openLogDirectory` and `openWindowsSecurity`, and the latter opens `windowsdefender://threatsettings` (with a documented fallback URI) without executing PowerShell configuration commands.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix desktop test -- --run`

Expected: FAIL because the security action is absent.

- [ ] **Step 3: Implement the minimal IPC action**

Register `desktop:open-windows-security` and call Electron `shell.openExternal` with the Windows Security URI. Keep existing log-directory IPC unchanged.

- [ ] **Step 4: Verify GREEN and type safety**

Run desktop tests and `npm --prefix desktop run typecheck`; expected: PASS.

### Task 7: Add the employee-facing diagnostic workflow

**Files:**
- Modify: `frontend/components/jobs/job-error.tsx`
- Modify: `frontend/app/jobs/[jobId]/page.tsx` if callback wiring is required
- Modify: `frontend/lib/api/client.ts` only to add the typed diagnostics request
- Test: `frontend/tests/job-error.test.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: Write RED UI tests**

For `BROWSER_TARGET_CLOSED`, assert Chinese explanation and buttons for automatic retry, environment diagnostics, logs and Windows Security. In browser-only mode assert clicking unavailable desktop actions shows safe guidance rather than throwing.

- [ ] **Step 2: Verify RED**

Run: `npm --prefix frontend test -- --run tests/job-error.test.tsx tests/job-detail.test.tsx`

Expected: FAIL because browser-specific actions do not exist.

- [ ] **Step 3: Implement the diagnostic panel**

Fetch the structured diagnostic endpoint on demand, render each check with passed/failed/manual status, and call `window.desktop.openLogDirectory()` / `openWindowsSecurity()` only when the bridge exists.

- [ ] **Step 4: Verify GREEN and type safety**

Run focused tests and `npm --prefix frontend run typecheck`; expected: PASS.

### Task 8: Regression, employee-path acceptance and installer build

**Files:**
- Modify: `scripts/verify-employee-desktop.ps1`
- Modify: `docs/桌面版安装说明.md`
- Modify: `docs/verification/employee-desktop-acceptance.md`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Extend employee acceptance**

Run diagnostics inside the existing `员工 #100% 空格` path and assert browser probe, writable directories, database migrations and service startup all pass.

- [ ] **Step 2: Run complete regression**

Run backend, frontend and desktop full suites, followed by frontend and desktop typechecks. Record exact pass/skip counts and every warning/failure in the Chinese iteration log.

- [ ] **Step 3: Build the next installer**

Bump the patch version, run the existing desktop packaging command, and produce the setup executable, `.blockmap` and `.sha256` sidecar.

- [ ] **Step 4: Run packaged smoke**

Start `release/win-unpacked/组合选品控制台.exe` with isolated special-character LocalAppData, call readiness and diagnostics, verify API/Worker/frontend logs and heartbeat, then stop only processes whose executable path is inside this workspace package.

- [ ] **Step 5: Publish evidence**

Record installer size, SHA-256, regression counts, package-smoke result and known external security-software boundary. Do not commit, branch, merge or clean the dirty worktree because the user explicitly prohibited Git workflow changes.
