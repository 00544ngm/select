# Maike 模型真实验证与路由诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留 OpenAI/Anthropic 两种兼容协议，把“目录发现”和“真实可执行”拆开，只允许真实结构化验证成功且未过期的模型进入任务，并把 Maike 账号分组、模型渠道和临时上游错误转换成明确中文提示。

**Architecture:** `provider_configurations.supported_models` 继续只保存目录发现结果；新增 `provider_model_validations` 表保存每个供应商、协议和模型的真实验证状态。连接测试只证明地址、密钥、协议和目录访问；单模型验证使用与正式任务一致的 `chat_structured` 路径。工作台和任务 API 只接受 24 小时内验证成功的模型，任何协议、地址或密钥变更都会清除该供应商的旧验证记录。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy async、Alembic、OpenAI Python SDK、Anthropic Python SDK、React/Next.js、TanStack Query、Vitest、pytest。

---

## File map

- Create `backend/migrations/versions/0006_add_provider_model_validations.py`: 独立模型验证表。
- Modify `backend/db/models.py`: `ProviderModelValidation` ORM。
- Modify `backend/db/provider_repository.py`: 验证结果读写、精确失效。
- Modify `backend/api/schemas/providers.py`: 模型状态、验证请求/响应 schema。
- Modify `backend/application/provider_clients.py`: 单模型结构化探针与上游错误分类。
- Modify `backend/application/provider_service.py`: 配置保存、连接测试、验证模型、24 小时有效期。
- Modify `backend/api/routes/providers.py`: `POST /settings/providers/{slug}/models/verify`。
- Modify `backend/api/routes/jobs.py`: 创建任务前再次校验所选模型。
- Create `frontend/lib/provider-model-status.ts`: 模型状态、中文错误和可执行性纯函数。
- Modify `frontend/lib/api/types.ts`, `frontend/lib/api/providers.ts`: 新 API 类型与客户端。
- Modify `frontend/components/settings/provider-settings-panel.tsx`: 目录状态、验证按钮和地址提示。
- Modify `frontend/components/workbench/provider-availability.tsx`, `frontend/components/workbench/model-select.tsx`: 只展示已验证模型。
- Modify `frontend/app/jobs/[jobId]/page.tsx`: 失败阶段、配置、原因、建议动作和设置页跳转。
- Add/modify corresponding backend and frontend tests listed below.

### Task 1: Persist per-model verification independently from discovery

**Files:**
- Create: `backend/migrations/versions/0006_add_provider_model_validations.py`
- Modify: `backend/db/models.py`
- Modify: `backend/db/provider_repository.py`
- Test: `backend/tests/test_provider_repository.py`

- [ ] **Step 1: Write failing repository tests**

Add tests that upsert one success and one temporary failure, list them by provider, and delete only the selected provider's validations:

```python
@pytest.mark.asyncio
async def test_model_validations_are_independent_from_discovered_models(session):
    repo = ProviderConfigurationRepository(session)
    tested_at = datetime.now(timezone.utc)
    await repo.upsert_model_validation(
        provider_slug="custom",
        api_protocol="anthropic",
        model="claude-opus-5",
        status="verified",
        error_code=None,
        message="结构化验证成功",
        tested_at=tested_at,
    )
    rows = await repo.list_model_validations("custom")
    assert [(row.model, row.status) for row in rows] == [
        ("claude-opus-5", "verified")
    ]

    await repo.delete_model_validations("custom")
    assert await repo.list_model_validations("custom") == []
```

- [ ] **Step 2: Run the repository test and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_repository.py -q`

Expected: FAIL because `upsert_model_validation` and the table do not exist.

- [ ] **Step 3: Add the migration and ORM model**

Create columns: UUID `id`, `provider_slug`, `api_protocol`, `model`, `status`, `error_code`, `message`, timezone `tested_at`; add unique constraint on `(provider_slug, api_protocol, model)` and provider/status index. Do not store API keys, response bodies or prompts.

- [ ] **Step 4: Add repository methods**

Implement exact async methods:

```python
async def list_model_validations(self, provider_slug: str) -> list[ProviderModelValidation]: ...
async def upsert_model_validation(
    self, *, provider_slug: str, api_protocol: str, model: str,
    status: str, error_code: str | None, message: str,
    tested_at: datetime,
) -> ProviderModelValidation: ...
async def delete_model_validations(self, provider_slug: str) -> int: ...
```

- [ ] **Step 5: Run migration/repository tests and Ruff**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_repository.py -q
.venv\Scripts\python.exe -m ruff check backend/db/models.py backend/db/provider_repository.py backend/migrations/versions/0006_add_provider_model_validations.py backend/tests/test_provider_repository.py
```

Expected: PASS and `All checks passed!`.

### Task 2: Classify Maike/provider errors without leaking upstream payloads

**Files:**
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_clients.py`

- [ ] **Step 1: Write failing error-classification tests**

Cover both SDKs and assert stable codes/messages:

```python
@pytest.mark.parametrize(
    (raw, code, retryable),
    [
        ("not supported by any configured account in this group", "PROVIDER_MODEL_ROUTE_UNAVAILABLE", False),
        ("model_not_found", "PROVIDER_MODEL_INVALID", False),
        ("rate_limit_error", "PROVIDER_RATE_LIMITED", True),
        ("cloudflare error 502", "PROVIDER_UPSTREAM_UNAVAILABLE", True),
    ],
)
def test_classifies_provider_model_errors(raw, code, retryable):
    result = classify_provider_error(raw, status_code=None)
    assert (result.code, result.retryable) == (code, retryable)
```

Also assert the public message never contains an API key, full response body, prompt or stack trace.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py -q`

Expected: FAIL because `classify_provider_error` does not exist and structured failures expose raw SDK text.

- [ ] **Step 3: Implement one shared classifier**

Add a frozen `ProviderErrorClassification(code, message, retryable)` and map:

```python
"not supported by any configured account" ->
  PROVIDER_MODEL_ROUTE_UNAVAILABLE / "中转站当前账号分组没有该模型的可用渠道" / False
401 or 403 -> PROVIDER_AUTH_FAILED / False
404 model missing -> PROVIDER_MODEL_INVALID / False
429 -> PROVIDER_RATE_LIMITED / True
502 or 503 -> PROVIDER_UPSTREAM_UNAVAILABLE / True
timeout/network -> PROVIDER_UNAVAILABLE / True
```

Use it from OpenAI and Anthropic connection/structured probe paths. Preserve the original exception as `__cause__`, but never return its body to API/UI.

- [ ] **Step 4: Verify GREEN**

Run focused pytest and Ruff on `provider_clients.py` and its tests. Expected: PASS.

### Task 3: Add a real structured model probe

**Files:**
- Modify: `backend/application/provider_clients.py`
- Modify: `backend/api/schemas/providers.py`
- Test: `backend/tests/test_provider_clients.py`

- [ ] **Step 1: Write failing tests for `ProviderModelVerifier`**

Use injected clients and assert the probe uses the selected protocol and a minimal strict schema:

```python
result = await verifier(runtime_config, "claude-opus-5")
assert result.status == "verified"
assert result.model == "claude-opus-5"
assert result.message == "结构化验证成功"
```

Assert route-unavailable and 502 produce `unavailable` and `temporary_error` respectively, with no automatic model substitution and only one request.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: FAIL because the verifier and result schema do not exist.

- [ ] **Step 3: Implement the minimal verifier**

Define the probe schema:

```python
MODEL_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
    "additionalProperties": False,
}
```

Call the same protocol adapter used by tasks with `max_tokens=256`, `max_retries=1`, schema name `provider_model_probe`, and prompt `Return a JSON object whose status is OK.` A successful parse is the only path to `verified`.

- [ ] **Step 4: Verify GREEN and regression**

Run `backend/tests/test_provider_clients.py` and existing LLM adapter tests. Expected: PASS.

### Task 4: Separate configuration save, connection discovery and model verification

**Files:**
- Modify: `backend/application/provider_service.py`
- Modify: `backend/api/schemas/providers.py`
- Modify: `backend/api/routes/providers.py`
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: Write failing service/API tests**

Required behaviors:

```python
saved = await service.save("custom", update)
connection_test.assert_not_awaited()  # save does not spend tokens
assert saved.model_options[0].test_status == "discovered"

verified = await service.verify_model("custom", "claude-opus-5")
assert verified.test_status == "verified"
assert verified.is_default is True
```

Also test that changing protocol, normalized base URL or API key deletes old validations, while changing display name does not.

- [ ] **Step 2: Run tests and verify RED**

Run provider service/API tests. Expected: FAIL on missing endpoint and current save-time connection call.

- [ ] **Step 3: Add schema contracts**

Use:

```python
ProviderModelTestStatus = Literal[
    "discovered", "verified", "unavailable", "temporary_error", "expired"
]

class ProviderModelVerifyRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    set_default: bool = True

class ProviderModelVerifyResult(BaseModel):
    provider: ProviderSlug
    model: str
    test_status: ProviderModelTestStatus
    tested_at: datetime
    test_message: str
    error_code: str | None = None
```

Extend `ProviderModelOption` with `error_code` and use per-model status rather than provider-wide connection status.

- [ ] **Step 4: Normalize custom base URLs by protocol**

In `_resolve_runtime`:

```python
if api_protocol == "anthropic" and base_url.endswith("/v1"):
    base_url = base_url[:-3]
elif api_protocol == "openai" and not base_url.endswith("/v1"):
    base_url = f"{base_url}/v1"
```

Only apply this to the custom provider; preserve paths other than the exact trailing `/v1` rule.

- [ ] **Step 5: Implement save and verification flow**

`save()` validates/encrypts and persists configuration without network access. `test_draft()` continues testing connection/discovery. `verify_model()` loads the saved key, calls `ProviderModelVerifier`, persists the result, and sets `default_model` only after success when `set_default=True`.

- [ ] **Step 6: Add the loopback-only endpoint**

Add:

```python
@router.post("/{slug}/models/verify", response_model=ProviderModelVerifyResult)
async def verify_provider_model(...): ...
```

Return 200 for all completed verification outcomes, including `unavailable` and `temporary_error`; reserve 422/503 for invalid configuration or inability to perform the probe.

- [ ] **Step 7: Verify GREEN**

Run provider service/API tests and Ruff. Expected: PASS.

### Task 5: Enforce a 24-hour verified-model gate at task creation

**Files:**
- Modify: `backend/api/routes/jobs.py`
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_jobs_api.py`
- Test: `backend/tests/test_provider_service.py`

- [ ] **Step 1: Write failing gate tests**

Cover verified, expired, unavailable, and missing validation:

```python
assert await service.is_model_available("custom", "claude-opus-5", now=now)
assert not await service.is_model_available(
    "custom", "claude-opus-5", now=now + timedelta(hours=24, seconds=1)
)
```

Job API must return `422 PROVIDER_MODEL_NOT_VERIFIED` or `422 PROVIDER_MODEL_VERIFICATION_EXPIRED` before enqueueing. Assert queue call count is zero.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: FAIL because current job gate trusts provider-wide connection status and `supported_models`.

- [ ] **Step 3: Implement the gate**

Define `MODEL_VERIFICATION_TTL = timedelta(hours=24)`. A model is executable only when status is `verified`, protocol matches the current provider configuration, provider is enabled/configured, and `tested_at >= now - TTL`.

- [ ] **Step 4: Verify GREEN**

Run job API, provider service and job service tests. Expected: PASS and no task is queued for an invalid model.

### Task 6: Update API settings to distinguish discovered and verified models

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/providers.ts`
- Create: `frontend/lib/provider-model-status.ts`
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Test: `frontend/tests/provider-api-client.test.ts`
- Test: `frontend/tests/provider-settings.test.tsx`
- Create: `frontend/tests/provider-model-status.test.ts`

- [ ] **Step 1: Write failing UI and pure-function tests**

Assert:

- connection success says “接口连接成功，发现 14 个模型；目录模型尚未逐一验证”；
- discovered cards do not say “可用于交叉验证”;
- each card has exactly one “验证此模型” button;
- route-unavailable displays the account-group explanation;
- 502 displays “上游渠道暂时不可用”;
- switching protocol invalidates visible verification state;
- Anthropic address preview shows site root, OpenAI preview shows `/v1`.

- [ ] **Step 2: Run frontend focused tests and verify RED**

Run:

```powershell
npm.cmd test -- --run tests/provider-api-client.test.ts tests/provider-settings.test.tsx tests/provider-model-status.test.ts
```

Expected: FAIL because all discovered models currently inherit provider-wide success.

- [ ] **Step 3: Implement types and API client**

Add `verifyProviderModel(slug, {model, set_default})` and exact response types from Task 4. Keep secret values write-only.

- [ ] **Step 4: Implement pure status labels**

`provider-model-status.ts` exports `isExecutableModel`, `modelStatusLabel`, and `providerErrorGuidance`. No component should duplicate error-code mappings.

- [ ] **Step 5: Update settings UI**

Rename protocol labels to `OpenAI 兼容` and `Anthropic Messages（官方接口包推荐）`. Render directory count separately from verified count. Add per-card validation mutation, pending state and last verification time. Saving configuration must not implicitly test or verify.

- [ ] **Step 6: Verify GREEN, typecheck and accessibility**

Run focused Vitest, `npm.cmd run typecheck`, and existing accessibility tests. Expected: PASS.

### Task 7: Restrict workbench selection and improve failed-task guidance

**Files:**
- Modify: `frontend/components/workbench/provider-availability.tsx`
- Modify: `frontend/components/workbench/model-select.tsx`
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Modify: `frontend/lib/result-labels.ts`
- Test: `frontend/tests/model-select.test.tsx`
- Test: `frontend/tests/job-forms.test.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: Write failing workbench/detail tests**

Assert discovered/expired/unavailable models are absent from task selectors; verified models remain. For `PROVIDER_MODEL_ROUTE_UNAVAILABLE`, task detail must render:

```text
失败阶段：模型分析
使用配置：claude / Anthropic Messages / claude-opus-5
原因：中转站当前账号分组没有该模型的可用渠道
建议：重新验证该模型，或联系中转站检查账号分组
```

Assert the “前往验证该模型” link equals `/settings/api?provider=custom&model=claude-opus-5` and historical raw error remains unchanged in API fixtures.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: FAIL because selectors trust provider-wide success and task detail lacks structured guidance.

- [ ] **Step 3: Implement selector filtering and detail guidance**

Use only `isExecutableModel(option)`. Do not silently fall back to OpenAI or another model. Add query-parameter focus on the settings page without automatically launching verification.

- [ ] **Step 4: Verify GREEN**

Run the three focused suites plus TypeScript. Expected: PASS.

### Task 8: Full verification, real Maike acceptance and records

**Files:**
- Create: `docs/verification/2026-08-01-maike-model-verification-and-routing.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Run backend full verification**

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check backend app tests
```

Expected: all tests pass; record any warning separately.

- [ ] **Step 2: Run frontend full verification**

```powershell
Set-Location frontend
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 3: Migrate and restart**

From the project root run `启动.ps1`. Confirm live/ready health checks and worker availability before opening the UI.

- [ ] **Step 4: Perform bounded real Maike verification**

Using the saved encrypted key, not a command-line key:

1. Save custom provider as Anthropic Messages with `https://maike-ai.top`.
2. Test interface once.
3. Verify `claude-opus-5` once with the structured probe.
4. Confirm the card becomes “验证可用” and appears in the workbench.
5. Do not verify all catalog models; do not auto-switch providers or models.
6. If the probe returns account-group 404, confirm the Chinese route-unavailable message and no automatic retry.

- [ ] **Step 5: Verify historical compatibility**

Open historical job `1d581d92-95dd-49d0-9414-44b761ed2182`. Confirm its stored error and progress remain unchanged while the UI presents the new Chinese interpretation.

- [ ] **Step 6: Record every RED, command failure and final result**

Append exact test counts, runtime outcome, real request count, known limitations and rollback notes to `docs/优化迭代记录.md`. Never record the API key, prompt body, model response body, cookie or account data.

- [ ] **Step 7: Write the verification report and check the diff**

Run `git diff --check`; create the verification document with automated and real-run evidence. Because the worktree is shared and dirty, do not stage, commit, reset or clean unrelated changes unless the user explicitly requests it.
