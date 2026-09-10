# Walmart Visible CAPTCHA Recovery Implementation Plan

> **For agentic workers:** Implement inline with TDD and verify each task before moving on.

**Goal:** Let desktop tasks recover from Walmart bot verification by reopening a visible browser, while preserving the rule that no model request starts before product scraping succeeds.

**Architecture:** Desktop browser management starts headless by default. When the Walmart scraper detects a blocked page and the short passive check expires, it requests one visible browser restart and retries the same product URL. The visible page remains open for the employee to complete Walmart verification; once the page is unblocked, scraping continues automatically. A stable timeout error is persisted if verification is not completed.

**Tech Stack:** Python, Playwright, FastAPI worker, React/Next.js, Vitest/Pytest, Electron/NSIS.

---

### Task 1: Browser visibility control

**Files:**
- Modify: `app/domain/interfaces/__init__.py`
- Modify: `app/infrastructure/browser/__init__.py`
- Test: `tests/test_browser_manager.py`

- [ ] Add a regression test proving `restart_visible()` restarts the selected browser with `headless=False`.
- [ ] Run the focused test and observe failure because the interface/manager has no visible restart.
- [ ] Add manager state for headless mode, preserve normal restart behavior, and implement `restart_visible()` without exposing paths.
- [ ] Run browser manager tests and Ruff.

### Task 2: Walmart CAPTCHA recovery

**Files:**
- Modify: `app/core/exceptions/__init__.py`
- Modify: `app/infrastructure/walmart/scraper.py`
- Test: `tests/test_walmart_scraper.py`

- [ ] Add tests for blocked headless page -> visible restart -> successful scrape, and visible verification timeout with stable error code.
- [ ] Run them red.
- [ ] Implement `WalmartCaptchaRequiredError`, one visible restart, bounded visible wait using existing CAPTCHA settings, and automatic continuation.
- [ ] Run scraper regression tests and verify browser errors still do not create model attempts.

### Task 3: User-facing error contract

**Files:**
- Modify: `frontend/components/jobs/job-error.tsx`
- Modify: `frontend/tests/job-detail.test.tsx`

- [ ] Add a UI regression for `WALMART_CAPTCHA_TIMEOUT`.
- [ ] Run it red.
- [ ] Add Chinese guidance stating that the visible Walmart window must be completed and that no model request was made.
- [ ] Run focused frontend tests and typecheck.

### Task 4: Version, record, and package

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Modify: `backend/main.py`
- Modify: `docs/优化迭代记录.md`

- [ ] Bump all product version references to `0.1.12`.
- [ ] Run full Python/frontend/desktop gates.
- [ ] Build the Windows installer and verify SHA-256, file version, isolated startup, and preservation of `0.1.11`.
