# Third-Party Anthropic Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the custom-provider Anthropic-compatible connection reliable for model verification and long structured reports while preserving existing OpenAI, DeepSeek, history, rotation, and report-quality behavior.

**Architecture:** Keep the official `anthropic` Python SDK as the only Anthropic transport. Normalize the user-entered endpoint once at the provider boundary, pass `max_retries=0` to the SDK, and let the application classify SDK/transport/parse failures into stable provider error codes. Use one streaming structured probe for verification and the existing streaming structured path for reports; the worker continues to decide whether a retry stays on the current model or rotates to the next candidate.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy/Alembic, official `anthropic` SDK, pytest/pytest-asyncio, Next.js/React/TypeScript, Electron Builder/NSIS, PowerShell.

---

### Task 1: Normalize Anthropic service endpoints

**Files:**
- Modify: `app/infrastructure/llm/anthropic_client.py`
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_anthropic_llm.py`
- Test: `backend/tests/test_provider_service.py`

- [ ] **Step 1: Write failing normalization tests**

Add tests for `normalize_anthropic_base_url` (or the equivalent public helper) with these exact cases:

```python
assert normalize_anthropic_base_url("https://api.example.com") == "https://api.example.com"
assert normalize_anthropic_base_url("https://api.example.com/") == "https://api.example.com"
assert normalize_anthropic_base_url("https://api.example.com/v1") == "https://api.example.com"
assert normalize_anthropic_base_url("https://api.example.com/v1/messages") == "https://api.example.com"
assert normalize_anthropic_base_url("https://api.example.com/v1/messages?x=1#frag") == "https://api.example.com"
```

Also assert `ValueError` for a missing scheme, an unsupported scheme such as `ftp://`, and a URL whose path is not a supported Anthropic endpoint. Add a provider-service test proving a custom Anthropic draft stores the normalized value and does not append a second `/v1`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
pytest backend/tests/test_anthropic_llm.py -k "base_url or normalize" -q
pytest backend/tests/test_provider_service.py -k "anthropic.*url or base_url" -q
```

Expected: the new helper is missing or the current `/v1` handling fails at least one assertion.

- [ ] **Step 3: Implement the smallest normalization helper**

In `anthropic_client.py`, parse with `urllib.parse.urlsplit`, require `http` or `https`, remove query/fragment from the saved endpoint, remove trailing slashes, and remove exactly the terminal `/v1/messages` or `/v1` suffix. Preserve all other path prefixes. Export the helper for tests. In `ProviderService._resolve_runtime`, call this helper only for `slug == "custom" and api_protocol == "anthropic"`; leave OpenAI URL behavior unchanged.

- [ ] **Step 4: Make the client use the normalized value**

Normalize `base_url` in `AnthropicLLMClient.__init__` before constructing `AsyncAnthropic`. The SDK factory must receive the normalized base URL and `max_retries=0`; do not add SDK retries implicitly.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the two commands from Step 2. Expected: all selected tests pass, and existing OpenAI provider-service tests remain unchanged.

### Task 2: Add typed Anthropic error classification and explicit retry control

**Files:**
- Modify: `app/infrastructure/llm/anthropic_client.py`
- Modify: `backend/application/provider_clients.py`
- Modify: `app/core/exceptions/__init__.py` only if a typed error needs a shared base
- Test: `backend/tests/test_anthropic_llm.py`
- Test: `backend/tests/test_provider_clients.py`

- [ ] **Step 1: Write failing exception-mapping tests**

Create SDK-like exception objects or monkeypatch the Anthropic exception classes and assert the adapter raises `LLMError` carrying these stable codes and `retryable` values:

```python
assert error.code == "PROVIDER_AUTH_FAILED"          # 401, retryable False
assert error.code == "PROVIDER_PERMISSION_DENIED"   # 403, retryable False
assert error.code == "PROVIDER_MODEL_INVALID"       # 404, retryable False
assert error.code == "PROVIDER_PROTOCOL_MISMATCH"   # incompatible 400, retryable False
assert error.code == "PROVIDER_REQUEST_TOO_LARGE"   # 413, retryable False
assert error.code == "PROVIDER_RATE_LIMITED"        # 429, retryable True
assert error.code == "PROVIDER_UPSTREAM_UNAVAILABLE"# 5xx/529, retryable True
assert error.code == "PROVIDER_CONNECTION_FAILED"   # connection error, retryable True
assert error.code == "PROVIDER_MODEL_TASK_TIMEOUT"  # timeout, retryable True
```

Assert that a caller-provided `max_retries=2` causes exactly two application attempts, while the factory receives `max_retries=0` exactly once. Assert that non-retryable errors do not sleep or issue a second request.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
pytest backend/tests/test_anthropic_llm.py -k "error or retry" -q
pytest backend/tests/test_provider_clients.py -k "anthropic.*error or retry" -q
```

Expected: current `LLMError` messages lack stable code attributes and the connection tester currently groups several statuses under `PROVIDER_UNAVAILABLE`.

- [ ] **Step 3: Implement a typed adapter error**

Add an internal `AnthropicLLMError(LLMError)` with `code`, `retryable`, `status_code`, and a redacted user-facing message. Map official `anthropic` exceptions by type first, then status code/message fallback for compatible proxies. Extract `retry-after` from response headers when present, otherwise use bounded exponential backoff with jitter. Never include API keys, authorization headers, full request bodies, or full model output in the exception text.

- [ ] **Step 4: Route both chat methods through one retry loop**

Keep `max_retries` as the total attempt count, clamp it to at least one, and retry only classifications marked retryable. Preserve the current model for transport retries. Let JSON parse/truncation failures be `MODEL_INVALID_JSON` and retry on the same model before control returns to the worker.

- [ ] **Step 5: Update provider classification and connection testing**

In `backend/application/provider_clients.py`, import the typed error where appropriate and make `_classify_exception` preserve its code/retryability. Update Anthropic connection handling to distinguish 401/403/404/413/429/529/5xx, timeout, connection, empty response, and protocol-shape errors. Set `max_retries=0` in the Anthropic client factory and let the connection tester make one explicit probe attempt.

- [ ] **Step 6: Run focused tests to verify GREEN**

Run:

```powershell
pytest backend/tests/test_anthropic_llm.py backend/tests/test_provider_clients.py -q
```

Expected: all Anthropic and provider resolver tests pass, including legacy OpenAI and DeepSeek cases.

### Task 3: Harden streaming structured output parsing

**Files:**
- Modify: `app/infrastructure/llm/anthropic_client.py`
- Test: `backend/tests/test_anthropic_llm.py`
- Test: `backend/tests/test_analysis_runner.py` only for any changed error propagation contract

- [ ] **Step 1: Add failing stream-shape tests**

Cover a final message containing multiple text blocks plus non-text blocks, whitespace-only blocks, fenced JSON with a language tag, and `stop_reason="max_tokens"`. Assert all text blocks are concatenated in order, non-text blocks are ignored, empty text raises `PROVIDER_EMPTY_RESPONSE`, and truncated or invalid JSON raises `MODEL_INVALID_JSON`.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
pytest backend/tests/test_anthropic_llm.py -k "stream or block or truncated or empty" -q
```

- [ ] **Step 3: Implement stream parsing without hand-written SSE**

Continue using `client.messages.stream(**request)` and `get_final_message()`. Centralize `_response_text`, fenced-JSON cleanup, stop-reason checks, and JSON decoding. Reject an empty aggregate text before parsing. Keep the compact-output instruction and existing direction-count constraint unchanged.

- [ ] **Step 4: Verify GREEN and regression behavior**

Run:

```powershell
pytest backend/tests/test_anthropic_llm.py backend/tests/test_analysis_runner.py -q
```

Expected: streaming reports still return the existing schema and quality gates receive the same Python object on success.

### Task 4: Replace domain hardcoding with real capability verification

**Files:**
- Modify: `backend/application/provider_clients.py`
- Modify: `backend/application/provider_service.py` only where verification status is persisted
- Test: `backend/tests/test_provider_clients.py`
- Test: `backend/tests/test_provider_service.py`

- [ ] **Step 1: Write failing regression tests**

Assert that an Anthropic custom endpoint containing `maike-ai.top` is sent through the real model verifier. A successful structured probe must return `status="verified"`; an invalid/truncated response must return `status="unavailable"` with `MODEL_INVALID_JSON`; a 429 must return `temporary_error` with `PROVIDER_RATE_LIMITED`. Assert no test can pass solely because of a hostname substring.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
pytest backend/tests/test_provider_clients.py -k "maike or verifier" -q
```

Expected: the current `_full_report_model_block` causes the success case to fail before any client call.

- [ ] **Step 3: Remove `_full_report_model_block` and use probe results**

Delete the hostname-specific block and invoke the configured client’s `chat_structured` probe for every Anthropic model. Preserve the existing `ProviderModelVerificationResult` statuses and persist the stable error code returned by the adapter. Do not infer protocol from a Claude model name.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
pytest backend/tests/test_provider_clients.py backend/tests/test_provider_service.py -q
```

### Task 5: Validate Anthropic models with the same streaming capability as reports

**Files:**
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_clients.py`

- [ ] **Step 1: Add a failing streaming-verification test**

Use a fake Anthropic client exposing `messages.stream` and assert model verification uses it with `max_tokens=256`, the compact JSON schema, and `max_retries=1`. Assert the final message is parsed and the returned status is verified.

- [ ] **Step 2: Run the test to verify RED**

Run:

```powershell
pytest backend/tests/test_provider_clients.py -k "streaming.*verification" -q
```

- [ ] **Step 3: Implement the streaming probe**

Make `ProviderModelVerifier` call `chat_structured` for Anthropic and pass `max_retries=1`. Keep the probe schema exactly `{"type":"object","properties":{"status":{"type":"string"}},"required":["status"],"additionalProperties":False}` and require a non-empty `status` string. Map parse, timeout, transport, and SDK errors through the stable classifier.

- [ ] **Step 4: Verify GREEN and persistence contract**

Run:

```powershell
pytest backend/tests/test_provider_clients.py backend/tests/test_provider_service.py -q
```

Expected: verification records retain `api_protocol="anthropic"`, the current connection revision, status, error code, and automatic/manual flag.

### Task 6: Preserve worker rotation and attempt semantics

**Files:**
- Modify: `backend/workers/jobs.py` only if the new error type is not already recognized
- Modify: `backend/application/model_rotation.py` only if classification imports require it
- Test: `backend/tests/test_worker_jobs.py`
- Test: `backend/tests/test_model_rotation.py`

- [ ] **Step 1: Add failing worker regressions**

Add cases showing a retryable Anthropic 429/529/timeout retries the same candidate before rotation, a non-retryable auth/model/protocol error rotates immediately only when rotation is enabled, and rotation-disabled jobs fail without selecting another paid model. Assert each persisted attempt contains the actual `api_protocol`, model, stable error code, and retry count.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
pytest backend/tests/test_worker_jobs.py backend/tests/test_model_rotation.py -k "anthropic or retryable or rotation" -q
```

- [ ] **Step 3: Implement only the required error-code bridge**

Teach the worker’s existing retry/rotation predicate to read `error.code` from `AnthropicLLMError` and preserve existing policy boundaries. Do not alter candidate ordering, history persistence, report-quality gates, or the user-facing rotation toggle.

- [ ] **Step 4: Verify GREEN**

Run the two test files without `-k` and confirm all existing model-rotation tests pass.

### Task 7: Improve frontend protocol guidance and stable error explanations

**Files:**
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Modify: `frontend/components/jobs/job-error.tsx`
- Test: `frontend/tests/provider-settings.test.tsx`
- Test: `frontend/tests/job-error.test.tsx`

- [ ] **Step 1: Add failing UI tests**

Assert that selecting Anthropic displays the exact requirement `POST /v1/messages`, accepts a base URL or `/v1/messages` URL, and states that automatic verification sends a short request that may consume a small number of tokens. Assert stable error codes render targeted Chinese guidance for auth, permission, invalid model, protocol mismatch, rate limit, upstream unavailable, request too large, timeout, connection failure, empty response, and invalid JSON.

- [ ] **Step 2: Run RED tests**

Run:

```powershell
npm.cmd --prefix frontend test -- --run frontend/tests/provider-settings.test.tsx frontend/tests/job-error.test.tsx
```

- [ ] **Step 3: Implement the copy and mapping**

Add the endpoint guidance beside the existing protocol selector without changing OpenAI/DeepSeek fields. Extend `explainProviderFailure` to match stable error codes before message substrings, preserving existing browser and Windows DPAPI guidance.

- [ ] **Step 4: Verify GREEN and typecheck**

Run:

```powershell
npm.cmd --prefix frontend test -- --run frontend/tests/provider-settings.test.tsx frontend/tests/job-error.test.tsx
npm.cmd --prefix frontend run typecheck
```

### Task 8: Version, documentation, and release verification

**Files:**
- Modify: `backend/main.py` (`0.1.12` -> `0.1.13`)
- Modify: `desktop/package.json` (`0.1.12` -> `0.1.13`)
- Modify: any packaged version manifest discovered by `rg -n "0.1.12"` under `desktop`, `packaging`, and `backend`
- Create: `docs/verification/2026-08-13-third-party-anthropic-compatibility.md`
- Modify: `docs/优化迭代记录.md` or the existing iteration log selected by the repository

- [ ] **Step 1: Add release verification assertions**

Create a verification document that records the exact commands, pass/fail output summaries, installer path, installer SHA-256, and the fact that the existing `release/组合选品控制台-Setup-0.1.12.exe` hash and bytes were unchanged before the build.

- [ ] **Step 2: Update only the new version**

Change all runtime/package version declarations identified by the version scan to `0.1.13`. Add an iteration entry describing endpoint normalization, SDK retry disabling, typed error codes, streaming verification, and removal of hostname hardcoding. Do not edit historical release records.

- [ ] **Step 3: Run Python and frontend validation**

Run:

```powershell
pytest backend/tests app/tests tests -q
ruff check app backend tests
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix desktop run typecheck
git diff --check
```

Expected: all commands exit 0. If an unrelated pre-existing failure is encountered, record its exact test name and output in the verification document instead of changing unrelated code.

- [ ] **Step 4: Build the Windows installer**

Run:

```powershell
pwsh -File scripts/build-windows-installer.ps1
```

Expected: a new `release/组合选品控制台-Setup-0.1.13.exe` and adjacent `.sha256` file. Do not delete or overwrite the `0.1.12` installer.

- [ ] **Step 5: Perform isolated packaged smoke test**

Launch the generated installer or unpacked executable with a temporary `LOCALAPPDATA` directory such as `F:\组合品7-31\web-platform-v2.1-work\.package-smoke-0.1.13`, confirm the app starts, the settings page renders, an Anthropic custom endpoint can be saved without duplicate `/v1`, and the history page remains readable. Do not point the smoke test at the real user database or real API key.

- [ ] **Step 6: Record final evidence**

Append the installer path, version, SHA-256, test summaries, isolated smoke-test result, and any known residual risk to `docs/verification/2026-08-13-third-party-anthropic-compatibility.md`. Git commits, branches, pushes, and resets are intentionally skipped to preserve the user’s existing worktree policy.

## Self-Review

Spec coverage: Tasks 1-3 cover endpoint normalization, official SDK transport, streaming text aggregation, truncation, JSON parsing, and explicit retry behavior. Tasks 4-6 cover real capability verification, stable error codes, worker retry/rotation semantics, and attempt persistence. Task 7 covers settings and task-error UI guidance. Task 8 covers compatibility, tests, packaging, versioning, and isolated Windows acceptance. No OpenAI/DeepSeek, database schema, history, scraper, or report-quality behavior is intentionally changed.

Placeholder scan: this plan contains no `TBD`, `TODO`, or unspecified “add appropriate handling” steps; every implementation step names files, functions, exact assertions, commands, and expected results.

Type consistency: `AnthropicLLMError.code` and `.retryable` are consumed by `_classify_exception` and the worker bridge; `normalize_anthropic_base_url` is used by both `ProviderService` and `AnthropicLLMClient`; verification continues to return `ProviderModelVerificationResult` and persist its existing fields.

Execution note: because the current worktree contains extensive user changes and the standing constraint forbids Git writes, execute this plan inline with checkpoints and do not create commits.
