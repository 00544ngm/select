# Third-Party OpenAI Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make custom OpenAI-compatible GPT providers use a verified, persisted API/structured-output capability instead of selecting Responses API from the model name, then ship it as desktop version `0.1.14`.

**Architecture:** Add a focused OpenAI compatibility adapter for URL normalization, explicit request modes and stable errors. Probe custom providers from most compatible Chat Completions modes to Responses only when an error proves endpoint/parameter incompatibility, persist the winning modes against the existing connection revision, and inject those modes through the resolver into formal report calls. Official OpenAI, DeepSeek and Anthropic retain their current routing.

**Tech Stack:** Python 3.13, OpenAI Python SDK, FastAPI, SQLAlchemy/Alembic, Pydantic, pytest, Next.js 15, React, TypeScript, Vitest, Electron/electron-builder.

**Execution constraint:** The shared worktree already contains extensive user changes. Replace every commit step with a test/status checkpoint; do not run Git staging, commit, branch, reset, checkout or clean commands.

---

## File Structure

- Create `app/infrastructure/llm/openai_compat.py`: URL normalization, capability literals, OpenAI-compatible stable exception classification and response helpers.
- Modify `app/infrastructure/llm/__init__.py`: make `OpenAILLMClient` accept explicit transport/structured modes while preserving official OpenAI defaults.
- Modify `backend/application/provider_clients.py`: capability probe matrix, zero SDK retries, runtime capability fields and resolver injection.
- Modify `backend/application/provider_service.py`: normalize custom OpenAI URLs and persist/expose probe capabilities.
- Modify `backend/db/models.py` and `backend/db/provider_repository.py`: store and read capability fields.
- Create `backend/migrations/versions/0012_add_openai_compatibility_modes.py`: additive nullable capability columns.
- Modify `backend/api/schemas/providers.py` and `frontend/lib/api/types.ts`: expose capability fields.
- Modify `frontend/components/settings/provider-settings-panel.tsx` and `frontend/components/jobs/job-error.tsx`: explain compatibility and map actionable errors.
- Modify version sources in `backend/main.py`, `desktop/package.json` and `desktop/package-lock.json`.
- Add focused tests to existing Python/frontend test files and create migration coverage in existing SQLite migration tests.
- Create `docs/verification/2026-08-14-third-party-openai-compatibility.md`: final commands, package identity and isolated smoke results.

### Task 1: Normalize Custom OpenAI URLs and Add Explicit Client Modes

**Files:**
- Create: `app/infrastructure/llm/openai_compat.py`
- Modify: `app/infrastructure/llm/__init__.py`
- Test: `tests/test_llm.py`
- Test: `backend/tests/test_provider_service.py`

- [ ] **Step 1: Write failing URL and routing tests**

Add parameterized tests proving these mappings:

```python
@pytest.mark.parametrize(("raw", "expected"), [
    ("https://api.example.com", "https://api.example.com/v1"),
    ("https://api.example.com/v1/", "https://api.example.com/v1"),
    ("https://api.example.com/v1/chat/completions?x=1#part", "https://api.example.com/v1"),
    ("https://gateway.example.com/openai/v1/responses", "https://gateway.example.com/openai/v1"),
])
def test_normalize_openai_compatible_base_url(raw, expected):
    assert normalize_openai_compatible_base_url(raw) == expected

@pytest.mark.asyncio
async def test_custom_gpt56_can_use_chat_completions_explicitly():
    client = OpenAILLMClient(
        model="gpt-5.6", api_key="secret",
        base_url="https://proxy.example/v1",
        transport_mode="chat_completions",
        structured_output_mode="prompt_json",
    )
    # install an AsyncMock chat client, call chat_structured(), and assert
    # chat.completions.create awaited once while responses.create is never called.
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_llm.py backend/tests/test_provider_service.py -k "openai_compatible_base_url or custom_gpt56" -q
```

Expected: import/signature/assertion failures because the normalizer and explicit modes do not exist.

- [ ] **Step 3: Implement the compatibility primitives**

Create literal aliases and a normalizer:

```python
OpenAITransportMode = Literal["chat_completions", "responses"]
OpenAIStructuredOutputMode = Literal["json_schema", "json_object", "prompt_json"]

def normalize_openai_compatible_base_url(raw: str) -> str:
    parsed = urlsplit(raw.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("OpenAI-compatible base URL must use http or https")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
```

Extend `OpenAILLMClient.__init__` with optional modes. Defaults retain current official behavior; explicit custom modes override `_uses_responses_api(model)`. Build response format only for the selected mode, and omit it for `prompt_json`.

- [ ] **Step 4: Run GREEN and regression tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_llm.py backend/tests/test_provider_service.py -q
```

Expected: all tests pass; existing official GPT 5.x Responses tests remain green.

- [ ] **Step 5: Record checkpoint**

Record RED/GREEN commands and results in `docs/优化迭代记录.md`; do not commit.

### Task 2: Add Stable OpenAI Errors and Capability Probe Matrix

**Files:**
- Modify: `app/infrastructure/llm/openai_compat.py`
- Modify: `app/infrastructure/llm/__init__.py`
- Modify: `backend/application/provider_clients.py`
- Test: `tests/test_llm.py`
- Test: `backend/tests/test_provider_clients.py`

- [ ] **Step 1: Write failing stable-error and probe-order tests**

Define expected verifier output fields:

```python
assert result.transport_mode == "chat_completions"
assert result.structured_output_mode == "json_object"
assert attempted_modes == [
    ("chat_completions", "json_schema"),
    ("chat_completions", "json_object"),
]
```

Add separate tests that:

- fall through from `json_schema` to `json_object` only on `PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED`;
- fall through from Chat to Responses only on `PROVIDER_PROTOCOL_MISMATCH`;
- do not fall through on 401, 403, 404 model error, 413, 429, timeout, connection failure or 5xx;
- preserve `MODEL_INVALID_JSON` and empty response metadata;
- construct all OpenAI SDK clients with `max_retries=0`.

- [ ] **Step 2: Run RED**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_llm.py backend/tests/test_provider_clients.py -k "openai_error or capability or structured_output or no_fallback" -q
```

Expected: missing result fields/error class and incorrect fall-through behavior.

- [ ] **Step 3: Implement stable error classification**

Add:

```python
class OpenAICompatibleLLMError(LLMError):
    def __init__(self, *, code: str, message: str, retryable: bool, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code
```

Classify SDK exceptions and response failures into the design error matrix without including request bodies, keys or full model output. Retry only errors marked `retryable`; never allow SDK implicit retries.

- [ ] **Step 4: Implement the custom OpenAI probe matrix**

Extend `ProviderModelVerificationResult` with optional capability fields. For custom OpenAI only, call a builder for this exact sequence:

```python
CHAT_PROBE_MODES = (
    ("chat_completions", "json_schema"),
    ("chat_completions", "json_object"),
    ("chat_completions", "prompt_json"),
)
RESPONSES_PROBE_MODE = ("responses", "prompt_json")
```

Move to the next structured mode only for the structured-output unsupported code. Move to Responses only when Chat returns the protocol mismatch code. All other failures return immediately with their stable status/error code.

- [ ] **Step 5: Run GREEN and regression tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_llm.py backend/tests/test_provider_clients.py -q
```

Expected: all focused tests pass and Anthropic verifier behavior remains unchanged.

- [ ] **Step 6: Record checkpoint**

Append the exact RED/GREEN evidence to the iteration record; do not commit.

### Task 3: Persist Capability Modes with Migration 0012

**Files:**
- Create: `backend/migrations/versions/0012_add_openai_compatibility_modes.py`
- Modify: `backend/db/models.py`
- Modify: `backend/db/provider_repository.py`
- Modify: `backend/api/schemas/providers.py`
- Modify: `frontend/lib/api/types.ts`
- Test: `backend/tests/test_sqlite_migrations.py`
- Test: `backend/tests/test_provider_repository.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: Write failing migration and repository tests**

Assert migration head contains nullable fields and round-trips old data:

```python
assert validation_columns["transport_mode"] == (0, None)
assert validation_columns["structured_output_mode"] == (0, None)
```

Assert `upsert_model_validation(..., transport_mode="chat_completions", structured_output_mode="json_schema")` saves and returns both values, while old calls default to `None`.

- [ ] **Step 2: Run RED**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_provider_repository.py backend/tests/test_providers_api.py -k "compatibility_mode or transport_mode or structured_output_mode" -q
```

Expected: columns and function parameters are missing.

- [ ] **Step 3: Add migration, ORM, repository and API fields**

Migration body:

```python
def upgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.add_column(sa.Column("transport_mode", sa.String(24), nullable=True))
        batch_op.add_column(sa.Column("structured_output_mode", sa.String(24), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("provider_model_validations") as batch_op:
        batch_op.drop_column("structured_output_mode")
        batch_op.drop_column("transport_mode")
```

Add optional fields through ORM, repository upsert/full-report preservation, `ProviderModelOption`, and TypeScript `ProviderModelOption`.

- [ ] **Step 4: Run GREEN**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_provider_repository.py backend/tests/test_providers_api.py -q
```

Expected: migration upgrade/downgrade and repository/API regressions pass.

- [ ] **Step 5: Record checkpoint**

Append migration RED/GREEN evidence; do not migrate a real user database and do not commit.

### Task 4: Carry Verified Modes Through Service and Resolver

**Files:**
- Modify: `backend/application/provider_service.py`
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_provider_clients.py`
- Test: `backend/tests/test_llm_runtime_config.py`

- [ ] **Step 1: Write failing service/resolver tests**

Cover:

```python
assert saved.base_url == "https://gateway.example/openai/v1"
repository.upsert_model_validation.assert_awaited_once_with(
    ..., transport_mode="chat_completions", structured_output_mode="json_schema"
)
openai_client.assert_called_once_with(
    model="gpt-5.6", api_key="secret", base_url="https://proxy.example/v1",
    transport_mode="chat_completions", structured_output_mode="prompt_json",
)
```

Also assert expired/missing custom OpenAI capabilities raise `PROVIDER_MODEL_NOT_VERIFIED`, while official OpenAI/DeepSeek/Anthropic builders keep prior arguments and behavior.

- [ ] **Step 2: Run RED**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_provider_clients.py backend/tests/test_llm_runtime_config.py -k "capability or compatible_base_url or fixed_mode" -q
```

Expected: service does not persist/expose modes and resolver does not load them.

- [ ] **Step 3: Implement service persistence and public projection**

Use `normalize_openai_compatible_base_url()` only for `slug == "custom" and api_protocol == "openai"`. Pass verifier result modes into `upsert_model_validation`, and expose them in each `ProviderModelOption` only when its connection revision is current.

- [ ] **Step 4: Implement resolver capability injection**

Extend `ProviderRuntimeConfig` with optional modes. In `resolve_primary`, fetch the selected model validation for custom OpenAI, require verified/current/non-null capability fields, then use `dataclasses.replace(config, transport_mode=..., structured_output_mode=...)`. `_default_client_builder` passes modes only to custom OpenAI `OpenAILLMClient`; official clients retain existing constructor contracts.

- [ ] **Step 5: Run GREEN and runtime regressions**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_provider_clients.py backend/tests/test_llm_runtime_config.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Record checkpoint**

Append evidence; do not commit.

### Task 5: Align Connection Testing and Model Rotation Errors

**Files:**
- Modify: `backend/application/provider_clients.py`
- Modify: `backend/application/model_rotation.py`
- Test: `backend/tests/test_provider_clients.py`
- Test: `backend/tests/test_model_rotation.py`
- Test: `backend/tests/test_worker_jobs.py`

- [ ] **Step 1: Write failing connection/rotation tests**

Assert custom `gpt-5.6` connection testing starts with Chat, official OpenAI `gpt-5.6` still uses Responses, `max_retries=0`, and endpoint mismatch is distinct from model-not-found. Assert configuration errors terminate the candidate while retryable network/upstream/invalid-JSON errors preserve existing rotation behavior and attempt error codes.

- [ ] **Step 2: Run RED**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py backend/tests/test_model_rotation.py backend/tests/test_worker_jobs.py -k "custom_gpt or protocol_mismatch or structured_output or openai_compatible" -q
```

Expected: custom GPT is still routed by model name and SDK retries are still 2 in connection testing.

- [ ] **Step 3: Implement aligned testing and classification**

Make the custom connection tester use the same endpoint selection rules as capability probing, but keep its payload tiny. Refine 404/405 classification using SDK error code/type/message so model 404 remains `PROVIDER_MODEL_INVALID` and endpoint 404/405 becomes `PROVIDER_PROTOCOL_MISMATCH`. Add `PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED` to the non-rotating configuration set; retain `MODEL_INVALID_JSON`, rate limit, connection, timeout and upstream behavior.

- [ ] **Step 4: Run GREEN and worker regressions**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py backend/tests/test_model_rotation.py backend/tests/test_worker_jobs.py -q
```

Expected: all tests pass with unchanged candidate ordering and attempt persistence.

- [ ] **Step 5: Record checkpoint**

Append evidence; do not commit.

### Task 6: Add Frontend Capability Guidance and Error Actions

**Files:**
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Modify: `frontend/components/jobs/job-error.tsx`
- Test: `frontend/tests/provider-settings.test.tsx`
- Test: `frontend/tests/job-error.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Assert custom OpenAI selection shows:

```text
服务需支持 POST /v1/chat/completions 或 POST /v1/responses
可填写基础地址、/v1 或完整接口地址
连接检测和模型验证会消耗少量 Token；配置不变时不会定时重复验证
```

For a verified option, assert labels render `Chat Completions · JSON Schema`, `Chat Completions · JSON Object`, `Chat Completions · 提示词 JSON`, or `Responses · 提示词 JSON`. Add actionable advice assertions for `PROVIDER_PROTOCOL_MISMATCH` and `PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED`.

- [ ] **Step 2: Run RED**

```powershell
npm.cmd --prefix frontend test -- --run tests/provider-settings.test.tsx tests/job-error.test.tsx
```

Expected: missing guidance, capability labels and new error advice.

- [ ] **Step 3: Implement minimal UI**

Add protocol-specific helper text below the existing base URL field, render a compact capability line inside each model option, and extend the existing error advice map. Do not expose API keys and do not change layout structure outside the provider panel/error block.

- [ ] **Step 4: Run GREEN and typecheck**

```powershell
npm.cmd --prefix frontend test -- --run tests/provider-settings.test.tsx tests/job-error.test.tsx
npm.cmd --prefix frontend run typecheck
```

Expected: focused UI tests and TypeScript pass.

- [ ] **Step 5: Record checkpoint**

Append evidence; do not commit.

### Task 7: Version 0.1.14 and Run Complete Code Verification

**Files:**
- Modify: `backend/main.py`
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Modify: `docs/优化迭代记录.md`
- Create: `docs/verification/2026-08-14-third-party-openai-compatibility.md`
- Test: all modified test suites

- [ ] **Step 1: Update version assertions first**

Update existing packaged entrypoint/desktop tests to expect `0.1.14`, then run them to observe the expected mismatch against `0.1.13`.

- [ ] **Step 2: Update runtime and Electron versions**

Set FastAPI and both desktop package lock version locations to `0.1.14`. Do not edit older installer files.

- [ ] **Step 3: Run focused static checks**

```powershell
.venv\Scripts\python.exe -m ruff check app/infrastructure/llm/openai_compat.py app/infrastructure/llm/__init__.py backend/application/provider_clients.py backend/application/provider_service.py backend/application/model_rotation.py backend/db/models.py backend/db/provider_repository.py backend/api/schemas/providers.py backend/migrations/versions/0012_add_openai_compatibility_modes.py
git diff --check
```

Expected: all checks pass.

- [ ] **Step 4: Run complete test/build gates serially where artifacts overlap**

```powershell
$env:PYTHONUTF8='1'; .venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix desktop test -- --run
npm.cmd --prefix desktop run typecheck
npm.cmd --prefix desktop run build
```

Expected baseline or better: Python `753 passed, 9 skipped`; frontend `247 passed, 7 skipped`; desktop `9 passed`; all builds/typechecks exit 0. Run frontend build before frontend typecheck because both access `.next`.

- [ ] **Step 5: Write verification document and iteration result**

Record every command, exit status, count, known warning, changed file group, rollback boundary, and explicitly state whether a real third-party endpoint was tested. Do not include credentials or full prompts/responses.

### Task 8: Build and Smoke-Test the 0.1.14 Installer

**Files:**
- Generated: `release/组合选品控制台-Setup-0.1.14.exe`
- Generated: matching SHA-256 file if release script creates it
- Modify: `docs/verification/2026-08-14-third-party-openai-compatibility.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Capture old installer identities**

Record size, timestamp and SHA-256 for `0.1.12` and `0.1.13` before building.

- [ ] **Step 2: Build without overwriting old installers**

Use the repository's existing packaging scripts/electron-builder configuration to create `0.1.14`. Verify ProductVersion/FileVersion and package name.

- [ ] **Step 3: Run isolated package smoke**

Create a new explicitly named temporary smoke directory inside the project and an isolated `LOCALAPPDATA`. Start the unpacked application, wait for API/Worker/frontend readiness, and assert:

- Worker/runtime revision is `0.1.14`.
- Alembic head is `0012`.
- Home, history and API settings pages return HTTP 200.
- Provider API exposes nullable capability fields without credentials.
- No real user database or saved key is read.

Stop only processes started by this smoke run and verify no owned process remains.

- [ ] **Step 4: Run employee path acceptance**

Use existing path acceptance tooling for Chinese characters, spaces, `#` and `%`, without deleting broad directories or touching the real user profile.

- [ ] **Step 5: Verify release hashes and old-package immutability**

Compute the new installer SHA-256, compare any sidecar hash, and recalculate `0.1.12`/`0.1.13` identities to prove they are unchanged.

- [ ] **Step 6: Final documentation checkpoint**

Append final package path, byte size, SHA-256, smoke evidence, known limits and rollback details to the verification and iteration documents. Do not stage or commit the shared worktree.
