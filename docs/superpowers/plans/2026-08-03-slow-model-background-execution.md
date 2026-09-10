# Slow Model Background Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user explicitly prohibited subagents, so execute inline in the current session and do not create Git commits.

**Goal:** Give OpenAI gpt-5.5 models one visible, non-retried 10-minute window for full-report generation while preserving the stable 120-second path for other models.

**Architecture:** Keep the existing persistent Worker queue and polling page. Add one pure model-to-timeout policy in the OpenAI LLM adapter, pass the chosen timeout per SDK request, and render elapsed/background guidance from existing job timestamps without a database migration.

**Tech Stack:** Python 3.12, OpenAI Python SDK, Pytest, Next.js 15, React Query, TypeScript, Vitest/Testing Library, Electron/PyInstaller/NSIS.

---

### Task 1: Model-specific single-request timeout

**Files:**
- Modify: `tests/test_llm.py`
- Modify: `app/infrastructure/llm/__init__.py`

- [ ] **Step 1: Write the failing timeout-policy tests**

Add tests asserting `_structured_report_timeout_seconds("gpt-5.5")`, `gpt-5.5-pro`, and dated 5.5 variants return `600.0`, while `gpt-5.4` returns `120.0`. Extend the timeout exception test so the mocked Responses request receives `timeout=600.0`, the exception reports 600 seconds, and `create.await_count == 1`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_llm.py -k "structured_report_timeout or task_timeout" -q`

Expected: FAIL because `_structured_report_timeout_seconds` does not exist and the request does not receive a per-request timeout.

- [ ] **Step 3: Implement the minimal policy**

Add a pure helper that lowercases and trims the model name, recognizes `gpt-5.5`, `gpt-5.5-pro`, and `gpt-5.5-*`, otherwise returns 120. In `chat_structured`, choose the timeout after resolving the model, pass it as the OpenAI SDK request `timeout`, and use the same value in `LLMTaskTimeoutError`. Keep `max_retries=1` at the service boundary.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command and require zero failures.

### Task 2: Running-job elapsed time and background guidance

**Files:**
- Modify: `frontend/tests/job-detail.test.tsx`
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Optionally create: `frontend/lib/job-runtime.ts` only if the formatting logic cannot remain a small pure helper in the page.

- [ ] **Step 1: Write failing UI tests**

Add a running `gpt-5.5` job fixture at progress 35 with a fixed `created_at`. Assert the page contains `模型正在生成完整报告`, an elapsed-time value, `慢模型最长等待 10 分钟，超时不会自动重试`, `返回后任务继续在后台运行，可在历史记录查看`, and an enabled `返回工作台` button. Add a `gpt-5.4` fixture asserting the 10-minute slow-model message is absent.

- [ ] **Step 2: Run the focused frontend tests and verify RED**

Run: `npm.cmd --prefix frontend test -- --run tests/job-detail.test.tsx`

Expected: FAIL because the running-state guidance does not exist.

- [ ] **Step 3: Implement the minimal running panel**

Use a one-second interval only while `job.status` is `queued` or `running`. Format elapsed seconds from `created_at`; for progress 35 render the model-generation wording, otherwise render the current stage plus elapsed time. Detect normalized `gpt-5.5` prefixes from `request_payload.model`. Keep the existing router navigation behavior and add the background guidance beside the existing return button.

- [ ] **Step 4: Run the focused frontend tests and verify GREEN**

Run the Step 2 command and require zero failures and no act-timer leak.

### Task 3: Remove the obsolete production block

**Files:**
- Modify: `backend/tests/test_provider_clients.py`
- Modify: `backend/application/provider_clients.py`

- [ ] **Step 1: Replace the old rejection expectation with a failing acceptance test**

For official `https://api.openai.com/v1`, assert verified `gpt-5.5` and `gpt-5.5-pro` models resolve successfully for tasks. Preserve the Maike full-report instability rejection test.

- [ ] **Step 2: Run focused provider tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend\tests\test_provider_clients.py -k "gpt_5_5 or maike" -q`

Expected: FAIL because the existing resolver still rejects 5.5 models.

- [ ] **Step 3: Remove only the official-OpenAI 5.5 rejection**

Delete the special-case 5.5/5.5-pro timeout rejection from provider verification and task resolution. Do not weaken model verification, enabled-provider checks, key checks, or the Maike production block.

- [ ] **Step 4: Run focused provider tests and verify GREEN**

Run the Step 2 command and require zero failures.

### Task 4: Regression, real observation, and installer

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Modify: `docs/优化迭代记录.md`
- Produce: `release/组合选品控制台-Setup-0.1.6.exe`

- [ ] **Step 1: Run full automated verification**

Run backend full Pytest, frontend full Vitest and production build, desktop tests and typecheck, Ruff on changed Python files, and `git diff --check`. Record every failure before correcting it.

- [ ] **Step 2: Run real API observations**

Using temporary process-only secrets, run the supplied Walmart sample through `gpt-5.5` for up to 600 seconds and verify no second model request. Then run `gpt-5.4` and require a completed JSON and Excel report. Remove the temporary environment variables immediately after each run.

- [ ] **Step 3: Version and build from current sources**

Increment desktop version to `0.1.6`, run `scripts/build-windows-installer.ps1` with the working domestic Electron mirrors, and require the complete PyInstaller + Next.js + NSIS pipeline to exit 0.

- [ ] **Step 4: Verify the actual package**

Start `release/win-unpacked/组合选品控制台.exe` with a fresh workspace-contained LocalAppData; require API/Worker/frontend processes to respond and heartbeat revision `0.1.6`. Verify SHA-256 and scan the package for supported OpenAI and Maike key formats with no hits.

- [ ] **Step 5: Record and hand off**

Append exact test counts, real-model outcome, failures, installer size/hash, and rollback information to `docs/优化迭代记录.md`. Hand off only the `.exe`; do not claim 5.5 success if it merely remains processing or reaches the 600-second timeout.

## Plan self-review

- Every design requirement maps to a task: model timeout (Task 1), visible background execution (Task 2), selectable model (Task 3), no duplicate request and real verification (Tasks 1/4), package delivery (Task 4).
- No database migration is required; timestamps and persistent Worker state already exist.
- No TODO/TBD placeholders, no subagent step, no Git write, and no key persistence are present.
