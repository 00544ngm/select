# Provider Connection Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider connection checks tolerate normal CatToken latency and report temporary upstream failures accurately.

**Architecture:** Keep `ProviderConnectionTester` as the single connection-test boundary. Configure retry/timeout behavior through `AsyncOpenAI`, then translate SDK exceptions into the existing `ProviderConnectionError` contract.

**Tech Stack:** Python, OpenAI Python SDK, pytest, pytest-asyncio

---

### Task 1: Connection test retry and error mapping

**Files:**
- Modify: `backend/tests/test_provider_clients.py`
- Modify: `backend/application/provider_clients.py`

- [x] **Step 1: Write failing configuration and 502 mapping tests**

Add tests which assert that the client factory receives `timeout=30.0` and `max_retries=2`, and that an OpenAI `InternalServerError` with a 502 response becomes `ProviderConnectionError(code="PROVIDER_UNAVAILABLE")` with `CatToken 上游服务暂时不可用，请稍后重试`.

- [x] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_provider_clients.py -q
```

Expected: configuration assertion fails because the implementation still uses a five-second timeout and zero retries; 502 mapping fails because the exception is not handled.

- [x] **Step 3: Implement the minimal retry and error mapping**

Set `timeout` to `30.0`, set `max_retries` to `2`, catch `InternalServerError`, and map timeout/connection errors separately with provider-specific Chinese messages.

- [x] **Step 4: Run focused and full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_provider_clients.py -q
.\.venv\Scripts\python.exe -m pytest tests backend\tests -q
```

Expected: all tests pass.

- [x] **Step 5: Confirm service health after restart**

Restart the API and worker, then verify `/api/v1/health/ready` returns `database`, `redis`, and `worker` as `ok`. Git commit is omitted because this workspace's `.git` metadata is unavailable.
