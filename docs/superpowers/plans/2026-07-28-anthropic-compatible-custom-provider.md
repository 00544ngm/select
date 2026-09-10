# Anthropic-Compatible Custom Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a selectable Anthropic Messages API protocol to the existing custom provider while preserving the current OpenAI-compatible path and all existing analysis behavior.

**Architecture:** Persist a protocol discriminator with each provider configuration, carry it through the existing runtime configuration boundary, and choose an OpenAI or Anthropic client at connection-test and job-execution time. The Anthropic adapter implements the existing LLM interface, normalizes system messages for `/v1/messages`, and preserves the current JSON parsing and retry contract.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy/Alembic, Anthropic Python SDK, pytest, Next.js 15, React 19, TypeScript, React Hook Form, Zod, TanStack Query, Vitest.

## Verification Record

- [x] Tasks 1-4 implemented in isolated commits.
- [x] PostgreSQL migrated to revision `0005`; legacy provider rows retained `api_protocol="openai"`.
- [x] Backend suite: `199 passed` (one pre-existing resource cleanup warning).
- [x] Frontend suite: `99 passed`; TypeScript and production build passed.
- [x] API, Worker, and frontend restarted; database, Redis, and Worker readiness checks passed.
- [x] Local settings UI exposes OpenAI-compatible and Anthropic-compatible protocol choices.
- [x] Runtime logs contain no credential-like values from this implementation.
- [ ] Real Anthropic-compatible provider acceptance requires the user's Base URL, API Key, and model.

---

## File Map

- `backend/migrations/versions/0005_add_provider_api_protocol.py`: add the compatible database default.
- `backend/db/models.py`: persist `api_protocol` on provider rows.
- `backend/db/provider_repository.py`: round-trip the protocol in upserts.
- `backend/api/schemas/providers.py`: publish and accept the protocol contract.
- `backend/application/provider_service.py`: validate custom-only protocol selection and preserve defaults.
- `backend/application/provider_clients.py`: select protocol-specific connection tests and runtime clients.
- `app/infrastructure/llm/anthropic_client.py`: isolate Anthropic message normalization, generation, and structured JSON behavior.
- `app/infrastructure/llm/__init__.py`: export the new adapter without changing fixed-provider behavior.
- `requirements.txt`: install the official Anthropic SDK.
- `frontend/lib/api/types.ts`: represent the protocol in frontend API contracts.
- `frontend/lib/schemas/provider-settings.ts`: validate protocol form values.
- `frontend/components/settings/provider-settings-panel.tsx`: render the selector and invalidate stale connection-test state.
- Backend and frontend provider tests: prove compatibility, protocol routing, security, and UI behavior.

### Task 1: Persist The Protocol Contract

**Files:**
- Create: `backend/migrations/versions/0005_add_provider_api_protocol.py`
- Modify: `backend/db/models.py`
- Modify: `backend/db/provider_repository.py`
- Modify: `backend/api/schemas/providers.py`
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_provider_repository.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: Write failing repository and public-contract tests**

Add assertions that an upsert with `api_protocol="anthropic"` persists the value, that existing public slots default to `openai`, and that a custom draft accepts `anthropic` while a fixed provider rejects it. Use this contract in tests:

```python
assert saved.api_protocol == "anthropic"
assert public_provider.api_protocol == "openai"

update = ProviderUpdate(
    api_protocol="anthropic",
    base_url="https://api.example.com",
    default_model="claude-sonnet",
    api_key=SecretStr("secret"),
    is_enabled=True,
)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_repository.py backend/tests/test_provider_service.py backend/tests/test_providers_api.py -q
```

Expected: failures report missing `api_protocol` schema/model/upsert fields.

- [ ] **Step 3: Add the migration and contract implementation**

Create revision `0005` after `0004` with a non-null string column and compatible default:

```python
op.add_column(
    "provider_configurations",
    sa.Column("api_protocol", sa.String(length=20), nullable=False, server_default="openai"),
)
op.alter_column("provider_configurations", "api_protocol", server_default=None)
```

Add `APIProtocol = Literal["openai", "anthropic"]`, default draft input to `openai`, return it publicly, and add it to repository upserts. In `ProviderService._resolve_runtime`, reject `anthropic` for any slug except `custom` with `PROVIDER_PROTOCOL_INVALID`. Legacy imports and fixed slots always persist `openai`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit the database and API contract**

```powershell
git add backend/migrations/versions/0005_add_provider_api_protocol.py backend/db/models.py backend/db/provider_repository.py backend/api/schemas/providers.py backend/application/provider_service.py backend/tests/test_provider_repository.py backend/tests/test_provider_service.py backend/tests/test_providers_api.py
git commit -m "feat: persist provider API protocol"
```

### Task 2: Implement The Anthropic LLM Adapter

**Files:**
- Create: `app/infrastructure/llm/anthropic_client.py`
- Modify: `app/infrastructure/llm/__init__.py`
- Modify: `requirements.txt`
- Test: `backend/tests/test_anthropic_llm.py`

- [ ] **Step 1: Add the SDK dependency and write failing adapter tests**

Add `anthropic>=0.75.0,<1.0.0`. Write tests around an injected or monkeypatched `AsyncAnthropic` client that prove:

```python
result = await client.chat(
    [
        {"role": "system", "content": "System A"},
        {"role": "user", "content": "Question"},
    ],
    max_retries=1,
)
assert result == "part onepart two"
request = create.await_args.kwargs
assert request["system"] == "System A"
assert request["messages"] == [{"role": "user", "content": "Question"}]
```

Also test fenced JSON, empty content, invalid JSON, retry count, and multiple text blocks.

- [ ] **Step 2: Run adapter tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_anthropic_llm.py -q
```

Expected: import failure because `AnthropicLLMClient` does not exist.

- [ ] **Step 3: Implement the focused adapter**

Implement `AnthropicLLMClient` with constructor inputs `model`, `api_key`, `base_url`, `timeout`, and optional client factory. Normalize all system-message content into one separate system string, retain only user/assistant messages, and call:

```python
response = await self._client.messages.create(
    model=model,
    max_tokens=max_tokens,
    messages=anthropic_messages,
    **({"system": system_text} if system_text else {}),
)
```

Extract and join blocks where `block.type == "text"`. For structured output, append the schema-only instruction to the system value, call the same Messages API, and reuse the repository's fence-tolerant JSON parser. Raise `LLMError` with `empty response` or `invalid JSON` in the final reason.

- [ ] **Step 4: Install dependencies and verify GREEN**

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest backend/tests/test_anthropic_llm.py backend/tests/test_llm_runtime_config.py -q
```

Expected: all Anthropic and existing LLM runtime tests pass.

- [ ] **Step 5: Commit the adapter**

```powershell
git add requirements.txt app/infrastructure/llm/anthropic_client.py app/infrastructure/llm/__init__.py backend/tests/test_anthropic_llm.py
git commit -m "feat: add Anthropic-compatible LLM client"
```

### Task 3: Route Connection Tests And Jobs By Protocol

**Files:**
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_clients.py`
- Test: `backend/tests/test_worker_jobs.py`

- [ ] **Step 1: Write failing protocol-routing tests**

Create tests where `ProviderRuntimeConfig(api_protocol="anthropic")` uses an Anthropic client factory and sends:

```python
messages_create.assert_awaited_once_with(
    model="claude-sonnet",
    max_tokens=16,
    messages=[{"role": "user", "content": "Reply OK"}],
)
```

Assert the connection result models are `("claude-sonnet",)` when the response contains text, and assert an empty response is a failed connection. Add a resolver test that a saved custom Anthropic configuration builds `AnthropicLLMClient`, while a saved custom OpenAI configuration still builds `OpenAILLMClient`.

- [ ] **Step 2: Run protocol-routing tests and verify RED**

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py backend/tests/test_worker_jobs.py -q
```

Expected: failures show the runtime config lacks protocol routing and attempts OpenAI Chat Completions.

- [ ] **Step 3: Implement separate tester factories and resolver routing**

Extend `ProviderConnectionTester` with `openai_client_factory` and `anthropic_client_factory`. Use Anthropic exception classes for the same stable error codes without including exception bodies that may contain secrets. Return only the configured model for a successful Anthropic test because model-list discovery is not part of the Messages API.

Add `api_protocol` to `ProviderRuntimeConfig`, load it from saved records with the compatible `openai` fallback, and change `_default_client_builder` so only a custom provider with `anthropic` builds `AnthropicLLMClient`.

- [ ] **Step 4: Run routing and worker tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass and existing custom OpenAI behavior remains covered.

- [ ] **Step 5: Commit runtime protocol routing**

```powershell
git add backend/application/provider_clients.py backend/tests/test_provider_clients.py backend/tests/test_worker_jobs.py
git commit -m "feat: route custom providers by protocol"
```

### Task 4: Add The Frontend Protocol Selector

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/schemas/provider-settings.ts`
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Modify: `frontend/tests/provider-settings.test.tsx`
- Modify: provider fixtures under `frontend/tests/*.test.tsx` and `frontend/e2e/workbench.spec.ts`

- [ ] **Step 1: Write failing UI tests**

Add a custom provider fixture and assert that selecting its tab reveals two protocol controls. Change to Anthropic and verify test/save payloads contain `api_protocol: "anthropic"`. After a successful test, switch protocols and verify the success message and verified-model list disappear and the enabled save action requires retesting.

```typescript
expect(screen.getByRole("radio", { name: "Anthropic 兼容" })).toBeInTheDocument();
await user.click(screen.getByRole("radio", { name: "Anthropic 兼容" }));
expect(requestBody.api_protocol).toBe("anthropic");
```

- [ ] **Step 2: Run the provider settings tests and verify RED**

```powershell
npm --prefix frontend test -- --run tests/provider-settings.test.tsx tests/provider-api-client.test.ts
```

Expected: protocol controls and payload fields are missing.

- [ ] **Step 3: Implement frontend types, validation, and state invalidation**

Add `ProviderApiProtocol = "openai" | "anthropic"`, require `api_protocol` in public configurations and draft payloads, and default the form from the selected provider. Render a two-option segmented radio group only for `custom`. Use a stable configuration signature of protocol, base URL, model, and key-presence/edit state; store it after a successful test and clear it when any signed field changes. Disable enabled-save while the current signature has not passed a test, while still allowing disabled configurations to be saved.

- [ ] **Step 4: Update typed fixtures and verify GREEN**

Add `api_protocol: "openai"` to all existing provider fixtures, then run:

```powershell
npm --prefix frontend test -- --run tests/provider-settings.test.tsx tests/provider-api-client.test.ts tests/model-select.test.tsx tests/job-forms.test.tsx
npm --prefix frontend run typecheck
```

Expected: selected tests and TypeScript pass.

- [ ] **Step 5: Commit the frontend feature**

```powershell
git add frontend/lib/api/types.ts frontend/lib/schemas/provider-settings.ts frontend/components/settings/provider-settings-panel.tsx frontend/tests frontend/e2e/workbench.spec.ts
git commit -m "feat: configure custom provider protocol"
```

### Task 5: Migrate And Verify The Complete Application

**Files:**
- Verify all modified files
- Update: `docs/superpowers/plans/2026-07-28-anthropic-compatible-custom-provider.md` checklist states

- [ ] **Step 1: Run the database migration**

```powershell
.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini upgrade head
```

Expected: database reaches revision `0005`; existing provider rows report `api_protocol="openai"`.

- [ ] **Step 2: Run complete backend verification**

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Expected: zero failures.

- [ ] **Step 3: Run complete frontend verification**

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: zero test/type errors and a successful production build.

- [ ] **Step 4: Restart API and worker and verify local UI**

Restart only this project's API and worker processes. Open `http://localhost:3000/settings/api`, select custom API, confirm the protocol control appears, and verify the existing OpenAI option loads without changing saved secrets. Exercise an Anthropic draft with a deliberately invalid non-secret endpoint or mocked test only when no real credential is available; do not claim external success without a real endpoint.

- [ ] **Step 5: Run security and diff checks**

```powershell
git diff --check
git status --short
rg -n "x-api-key|Authorization|api_key" logs -g '*.log'
```

Expected: no whitespace errors, only intentional plan-status changes, and no newly logged credential values.

- [ ] **Step 6: Commit verification metadata only if changed**

```powershell
git add docs/superpowers/plans/2026-07-28-anthropic-compatible-custom-provider.md
git commit -m "docs: record Anthropic provider verification"
```

### Task 6: Real Anthropic-Compatible Acceptance

**Files:**
- No source changes unless acceptance reveals a reproducible defect, in which case start a new red-green cycle.

- [ ] **Step 1: Obtain runtime values through the UI**

Use the user-provided Anthropic-compatible base URL, API key, and model. Never print or copy the key into commands, logs, chat, or task payloads.

- [ ] **Step 2: Test and save the provider**

Select `Anthropic compatible`, enter the values, run the real connection test, verify returned text and the configured model, enable the provider, and save it.

- [ ] **Step 3: Run one workbench task**

Select the custom provider and verified model. Submit a supported Walmart or Amazon product URL and monitor until a terminal state.

- [ ] **Step 4: Verify acceptance evidence**

Confirm the task request payload retains `provider=custom` and the selected model, progress reaches 100%, complete results and images render, and history contains the successful custom Anthropic task. If the external provider rejects the request, report its exact sanitized status and do not substitute another provider.
