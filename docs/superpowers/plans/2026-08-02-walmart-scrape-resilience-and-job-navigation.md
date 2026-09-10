# Walmart Scrape Resilience and Job Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the supplied Walmart product complete a real scrape-to-report task and let users leave an in-progress task without cancelling it.

**Architecture:** Keep navigation purely in the Next.js task page and keep task execution in the existing desktop Worker. Diagnose the Walmart browser boundary first, then make the smallest evidence-backed scraper changes; fail CAPTCHA promptly instead of waiting in an invisible browser. Gate package delivery on one persisted completed real task for product `5257371669`.

**Tech Stack:** Next.js 15, React Query, Vitest/MSW, Python 3.13, Playwright/CDP, pytest, Electron/NSIS.

---

### Task 1: Running-task navigation

**Files:**
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: Write failing navigation tests**

Add a stable `pushMock`, assert queued/running pages contain `返回工作台`, click it and assert `pushMock("/")`; assert completed pages do not render the running-state button and failed pages render a return action next to retry.

- [ ] **Step 2: Run the focused test and confirm red state**

Run: `npm.cmd exec vitest run tests/job-detail.test.tsx`

Expected: tests fail because the button does not exist and the router mock is not invoked.

- [ ] **Step 3: Implement navigation without task mutation**

Use the existing `useRouter()` instance and render a secondary button for `queued`/`running`; render the same return action in the failed block. Its only handler is `router.push("/")`; it must not call retry or any cancellation endpoint.

- [ ] **Step 4: Verify the focused tests**

Run: `npm.cmd exec vitest run tests/job-detail.test.tsx`

Expected: all job-detail tests pass.

### Task 2: CAPTCHA timing and error contract

**Files:**
- Modify: `app/infrastructure/walmart/scraper.py`
- Create: `tests/test_walmart_scraper.py`
- Modify: `backend/workers/jobs.py` only if the existing error mapper cannot preserve the actionable message.

- [ ] **Step 1: Write failing scraper tests**

Create fake Playwright pages for a normal page and a persistent `/blocked` page. Assert a normal page proceeds immediately; assert a blocked page raises `ScrapeError` without executing the current 100 iterations of three-second passive waiting; assert the message identifies Walmart CAPTCHA and that no product DTO is returned.

- [ ] **Step 2: Run the focused tests and confirm red state**

Run: `.venv\Scripts\python.exe -m pytest tests/test_walmart_scraper.py tests/test_product_service.py -q`

Expected: the blocked-page test fails against the 300-second passive-wait contract.

- [ ] **Step 3: Implement the minimal CAPTCHA behavior**

Replace the invisible five-minute manual-verification wait with a short bounded confirmation period. Preserve one recheck so transient redirects may resolve, then raise a clear `ScrapeError` such as `Walmart 要求人工验证，本次未抓取到商品数据，模型尚未调用`.

- [ ] **Step 4: Verify scraper tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_walmart_scraper.py tests/test_product_service.py backend/tests/test_worker_jobs.py -q`

Expected: all focused tests pass and worker mapping remains `SCRAPE_FAILED`.

### Task 3: Real Walmart root-cause experiment

**Files:**
- Diagnostic outputs only under `.diagnostics/`; never store cookies, API keys, or tokens.
- Modify scraper/browser files only after a single hypothesis is confirmed.

- [ ] **Step 1: Reproduce with the packaged Chromium**

Run the supplied product URL through the same `DESKTOP_BROWSER_EXECUTABLE`, browser manager, user-data location and Worker environment used by Electron. Record URL, page title, HTTP/navigation outcome, presence of public structured product data, and detected block state. Do not record HTML containing user/session data.

- [ ] **Step 2: Compare blocked and working page paths**

Inspect `app/infrastructure/browser/__init__.py`, the Walmart scraper and a normal page response. Confirm whether the trigger is a fresh ephemeral context, navigation parameters, missing persisted profile, or an upstream block independent of selectors.

- [ ] **Step 3: Test one minimal hypothesis**

Change only the confirmed boundary—for example, reuse the desktop persistent browser context or parse already-present public JSON before DOM selectors. Re-run the supplied URL once and require non-empty title and price.

- [ ] **Step 4: Add a regression test for the confirmed fix**

Model the exact working page shape in `tests/test_walmart_scraper.py`; ensure incomplete title/price still fails in `tests/test_product_service.py`.

### Task 4: Real report acceptance

**Files:**
- No source modification unless the real task exposes a new reproducible defect.
- Append every real failure to `docs/优化迭代记录.md` without credentials.

- [ ] **Step 1: Start source desktop services with packaged browser parity**

Use the real desktop database, session authentication, SQLite queue, Worker heartbeat and packaged Chromium path. Confirm the currently selected verified providers are visible before submission.

- [ ] **Step 2: Submit the supplied Walmart URL**

Create one named hypothesis task and poll by state changes rather than arbitrary sleeps. Capture only job id, stage, progress, error code and sanitized product/report metadata.

- [ ] **Step 3: Enforce the acceptance gate**

Require `status=completed`, `progress=100`, real product id `5257371669`, non-empty title/image, and a persisted analysis result. If CAPTCHA or any other error occurs, return to Task 3 and do not build an installer.

### Task 5: Regression and release package

**Files:**
- Modify: `docs/优化迭代记录.md`
- Build outputs: `release/组合选品控制台-Setup-0.1.1.exe` and `.sha256`

- [ ] **Step 1: Run automated regression**

Run focused backend tests, full frontend Vitest, `npm.cmd run typecheck`, `npm.cmd run build`, and applicable Ruff checks. Record exact pass/fail counts.

- [ ] **Step 2: Build the Windows package**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows-installer.ps1`

Expected: exit code 0 and a newly timestamped NSIS installer.

- [ ] **Step 3: Smoke-test the packaged app**

Launch `release/win-unpacked/组合选品控制台.exe`; require frontend HTTP 200, API and Worker processes, model selections loaded, and zero remaining package processes after exact-path shutdown.

- [ ] **Step 4: Record and deliver**

Append build size, SHA-256, automated results and real task id to `docs/优化迭代记录.md`. Deliver the installer only after the Task 4 gate passed.
