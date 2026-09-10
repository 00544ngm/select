# Walmart Navigation Timeout Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Walmart navigation timeouts distinguishable from anti-bot verification, automatically open the existing visible browser for manual verification, and keep scraping failures out of AI model rotation.

**Architecture:** Keep the existing `ProductDetailScraper` recovery loop and `verification_status` callback. Add a small navigation classifier that inspects only URL/title/short body markers after a Playwright navigation timeout, then raises either the existing CAPTCHA signal or stable navigation/network exceptions. Worker and frontend consume those stable codes without changing job/history schemas or model provider routing.

**Tech Stack:** Python 3.12/3.13, Playwright async API, pytest/pytest-asyncio, FastAPI worker error mapping, Next.js/React/Vitest, Electron packaged Chromium smoke tests.

**Execution constraint:** The shared worktree contains extensive user changes. Use test/status checkpoints instead of Git commits. Do not stage, commit, branch, reset, checkout, clean, tag or push. Do not modify real user databases, provider keys, cookies or history jobs.

---

### Task 1: Add failing navigation-classification tests

**Files:**
- Modify: `tests/test_walmart_scraper.py`
- Modify: `backend/tests/test_worker_jobs.py`

- [ ] **Step 1: Inspect existing fake page/browser fixtures**

Read `tests/test_walmart_scraper.py` and use its existing fake page/browser classes. The new tests must model `page.goto()` raising a Playwright timeout while still allowing `page.url`, `page.title()` and a short body marker to be read.

- [ ] **Step 2: Write a failing test for a timeout on a Walmart verification page**

Add a test with this behavior:

```python
page.goto.side_effect = PlaywrightTimeoutError("Timeout 30000ms exceeded")
page.url = "https://www.walmart.com/blocked"
page.title = AsyncMock(return_value="Robot or human?")
page.locator(...).inner_text = AsyncMock(return_value="Robot or human?")
browser.restart_visible = AsyncMock()
verification_status = AsyncMock()

product = await ProductDetailScraper(
    browser,
    verification_status=verification_status,
).scrape_product(PRODUCT_URL)

browser.restart_visible.assert_awaited_once()
verification_status.assert_any_await(True)
assert product.title == "..."
```

The fake visible retry must return a normal product page on its second call. This test currently fails because the timeout is wrapped as generic `ScrapeError` before the CAPTCHA recovery loop can run.

- [ ] **Step 3: Write a failing test for a normal navigation timeout**

Assert that a timeout with a normal URL/title/body raises `WalmartNavigationTimeoutError` with code `WALMART_NAVIGATION_TIMEOUT`, does not call `restart_visible`, and does not call `verification_status(True)`.

- [ ] **Step 4: Write a failing test for network failure classification**

Make `page.goto()` raise a Playwright error containing `net::ERR_PROXY_CONNECTION_FAILED` and assert the scraper raises `WalmartNetworkError` with code `WALMART_NETWORK_FAILED`. Do not assert or record the full URL in the error message.

- [ ] **Step 5: Write worker regression tests before production edits**

Extend `backend/tests/test_worker_jobs.py` so a scraper raising each new navigation exception causes `repository.fail()` with the stable code, creates no model attempt, and does not invoke the rotation runner/provider resolver. Keep the existing `WalmartCaptchaTimeoutError` no-model test green.

- [ ] **Step 6: Run the RED tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_walmart_scraper.py backend/tests/test_worker_jobs.py -k "navigation_timeout or network_failed or timeout_verification or captcha" -q
```

Expected: the new tests fail because the exception classes/classifier and timeout recovery do not exist; existing tests may remain green.

### Task 2: Implement stable navigation exceptions and page signal detection

**Files:**
- Modify: `app/core/exceptions/__init__.py`
- Modify: `app/infrastructure/walmart/scraper.py`

- [ ] **Step 1: Add stable exception types**

Add exceptions next to the existing Walmart CAPTCHA exceptions:

```python
class WalmartNavigationTimeoutError(ScrapeError):
    code = "WALMART_NAVIGATION_TIMEOUT"
    retryable = True

    def __init__(self) -> None:
        self.message = "Walmart 商品页面加载超时，请检查网络、代理或稍后重试"
        super().__init__(self.message)


class WalmartNetworkError(ScrapeError):
    code = "WALMART_NETWORK_FAILED"
    retryable = True

    def __init__(self) -> None:
        self.message = "无法连接 Walmart，请检查网络、代理或安全软件后重试"
        super().__init__(self.message)
```

Export both classes through `__all__`.

- [ ] **Step 2: Add bounded verification marker inspection**

Implement a private async helper in `ProductDetailScraper` that reads only `page.url`, `page.title()` and a bounded body text sample (for example, 4,000 characters). Return a boolean for known verification markers such as `/blocked`, `Robot or human?`, `captcha`, `verify you are human`, or `security challenge`. Catch page-read errors and return `False`; never log body text.

- [ ] **Step 3: Classify navigation exceptions at the source**

Wrap only the initial product `page.goto` call:

```python
try:
    await page.goto(url, wait_until="domcontentloaded", timeout=settings.timeout_ms)
except PlaywrightTimeoutError as error:
    if await self._is_walmart_verification_page(page):
        raise WalmartCaptchaRequiredError("Walmart verification required") from error
    raise WalmartNavigationTimeoutError() from error
except PlaywrightError as error:
    if await self._is_walmart_verification_page(page):
        raise WalmartCaptchaRequiredError("Walmart verification required") from error
    if _is_network_navigation_error(error):
        raise WalmartNetworkError() from error
    raise WalmartNavigationTimeoutError() from error
```

Use Playwright exception imports already available in the project. `_is_network_navigation_error` must match only transport markers (`ERR_PROXY_CONNECTION_FAILED`, `ERR_CONNECTION_RESET`, `ERR_CONNECTION_CLOSED`, `ERR_NAME_NOT_RESOLVED`, `ERR_INTERNET_DISCONNECTED`, `ERR_TIMED_OUT`) and must not treat a verification marker as a network failure.

- [ ] **Step 4: Preserve the existing visible-browser recovery loop**

Let `WalmartCaptchaRequiredError` continue through `scrape_product()` so it calls `restart_visible`, sets `verification_status(True)`, waits for the configured manual window, and retries the same URL. On successful retry, clear the status. On timeout, keep `WalmartCaptchaTimeoutError` and do not invoke any model.

- [ ] **Step 5: Keep fallback HTML behavior bounded**

Do not make `_fetch_public_html` a second unrestricted navigation path. It may remain the existing short public fallback after a detected CAPTCHA, but no full HTML or URL query string may be logged. Do not increase `settings.timeout_ms` globally.

- [ ] **Step 6: Run the focused GREEN tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_walmart_scraper.py -q
```

Expected: all Walmart scraper tests pass, including timeout-to-visible-browser recovery, ordinary timeout classification, and network classification.

### Task 3: Align Worker and rotation error handling

**Files:**
- Modify: `backend/workers/jobs.py`
- Modify: `backend/application/model_rotation.py` only if focused tests prove a mapping gap
- Test: `backend/tests/test_worker_jobs.py`
- Test: `backend/tests/test_model_rotation.py` if changed

- [ ] **Step 1: Map stable scrape errors without changing history schema**

Because `_classify_error` already returns `exc.code`/`exc.message`, verify the new exceptions persist `WALMART_NAVIGATION_TIMEOUT` and `WALMART_NETWORK_FAILED` directly. Add explicit message sanitization only if a test shows an underlying Playwright message leaks into the persisted error.

- [ ] **Step 2: Ensure scrape errors cannot rotate models**

Keep the scrape phase before `run_one()` and assert the worker does not create attempts or call `_create_provider_resolver` when scraping raises either stable navigation exception. Do not add these errors to provider rotation or provider diagnosis sets.

- [ ] **Step 3: Run worker/rotation GREEN tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_worker_jobs.py backend/tests/test_model_rotation.py -q
```

Expected: existing candidate ordering, provider error rotation and CAPTCHA timeout behavior remain unchanged.

### Task 4: Add frontend error guidance

**Files:**
- Modify: `frontend/components/jobs/job-error.tsx`
- Modify: `frontend/tests/job-error.test.tsx`

- [ ] **Step 1: Write failing UI assertions**

Add cases asserting:

```text
WALMART_NAVIGATION_TIMEOUT -> Walmart 页面加载超时；检查网络、代理或安全软件
WALMART_NETWORK_FAILED -> 无法连接 Walmart；检查网络或代理
WALMART_CAPTCHA_TIMEOUT -> Walmart 人工验证超时；重新提交任务
```

Assert the UI does not render the raw `Page.goto` call log for these stable codes.

- [ ] **Step 2: Implement the existing error-advice map extension**

Add the three codes to the current advice mapping and keep the existing retry/return-to-workbench actions. Do not expose the full product URL or browser internals.

- [ ] **Step 3: Run focused UI tests and typecheck**

Run:

```powershell
npm.cmd --prefix frontend test -- --run tests/job-error.test.tsx
npm.cmd --prefix frontend run typecheck
```

Expected: all focused tests pass and TypeScript exits `0`.

### Task 5: Full regression, packaged smoke and documentation

**Files:**
- Modify: `docs/优化迭代记录.md`
- Create: `docs/verification/2026-08-14-walmart-navigation-timeout-recovery.md`
- Generated: new `release\组合选品控制台-Setup-0.1.15.exe` only if version bump is explicitly requested during release execution

- [ ] **Step 1: Run complete test gates**

Run serially:

```powershell
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix desktop test -- --run
npm.cmd --prefix desktop run typecheck
npm.cmd --prefix desktop run build
```

Expected: no new failures; preserve known async cleanup/MSW/build metadata warnings as documented.

- [ ] **Step 2: Run isolated packaged smoke**

Use a fresh `.package-smoke-walmart-timeout-*` directory and simulated employee path containing Chinese characters, spaces, `#` and `%`. Start `release\win-unpacked\组合选品控制台.exe`, verify API live, frontend readiness, Worker heartbeat, and no model calls while the scrape fixture reports CAPTCHA. Stop only processes whose executable paths are under the package directory and assert zero residue.

- [ ] **Step 3: Record evidence**

Document test counts, stable error codes, UI behavior, package smoke path, process residue, and the explicit boundary that no real Walmart CAPTCHA or third-party endpoint was bypassed. Do not record credentials, cookies, full HTML or complete prompts.

- [ ] **Step 4: Final static verification**

Run targeted Ruff and `git diff --check`. Re-read the design and plan, scan for placeholders, and verify no old installer was overwritten. Do not stage or commit.

## Plan Self-Review

- Spec coverage: navigation timeout detection, verification recovery, network classification, worker non-rotation, frontend guidance, Token/security boundaries, tests, package smoke and rollback are covered by Tasks 1-5.
- Placeholder scan: no `TBD`, `TODO`, “later” or undefined interface is used in the tasks.
- Type consistency: exception codes are exposed through `code`/`message`, the existing Worker `_classify_error` consumes those fields, and frontend cases use the same literal codes.
- Scope: no provider/model/database schema changes are included; version `0.1.15` is conditional and is not changed without an explicit release decision.
