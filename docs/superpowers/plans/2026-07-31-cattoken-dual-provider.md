# CatToken Dual Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add independent `CatToken OpenAI` and `CatToken Claude` provider windows that can be enabled simultaneously with separate encrypted API keys and verified models.

**Architecture:** Keep historical slug `cattoken` as the OpenAI Responses provider and add fixed slug `cattoken_claude` for Anthropic Messages. Reuse the provider configuration table and encryption layer; select the runtime client from the provider slug and fixed protocol. Extend frontend provider identity types and labels without rewriting historical job data.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, OpenAI SDK, Anthropic SDK, pytest, Next.js 15, React 19, TypeScript, React Hook Form, Vitest, Testing Library.

---

## File structure

- `backend/api/schemas/providers.py`: add the new provider slug to API validation.
- `backend/application/provider_service.py`: define both fixed CatToken slots, enforce each protocol, and preserve the old slot.
- `backend/application/provider_clients.py`: test and resolve each CatToken protocol with the correct SDK/client.
- `frontend/lib/api/types.ts`: add `cattoken_claude` to the shared frontend slug union.
- `frontend/components/settings/provider-settings-panel.tsx`: render both fixed provider tabs with independent form state and fixed protocol behavior.
- `frontend/components/workbench/model-select.tsx`: expose verified models from both slots.
- `frontend/lib/model-label.ts`: render unambiguous CatToken identities in task results.
- Backend and frontend tests listed below: capture migration, protocol, security, selection, and history compatibility.
- `docs/verification/2026-07-31-cattoken-dual-provider.md`: record commands and live acceptance evidence without secrets.
- `docs/优化迭代记录.md`: record every success and failure.

### Task 1: Add the fixed Claude provider identity

**Files:**
- Modify: `backend/api/schemas/providers.py`
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: Write failing service and API tests**

Add assertions equivalent to:

```python
result = await service.list_public()
assert [item.slug for item in result] == [
    "openai", "cattoken", "cattoken_claude", "deepseek", "custom"
]
claude = next(item for item in result if item.slug == "cattoken_claude")
assert claude.display_name == "CatToken Claude"
assert claude.api_protocol == "anthropic"
assert claude.base_url == "https://www.cattoken.vip"
assert claude.configured is False
assert claude.is_enabled is False
```

Also assert that the existing `cattoken` public object remains configured with its existing masked key, model and status.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
pytest backend/tests/test_provider_service.py backend/tests/test_providers_api.py -q
```

Expected: failures because `cattoken_claude` is not a valid slug or provider slot.

- [ ] **Step 3: Add the slug and fixed slots**

Implement the schema union and provider definitions:

```python
ProviderSlug = Literal[
    "openai", "cattoken", "cattoken_claude", "deepseek", "custom"
]

"cattoken": ProviderSlot(
    "openai_compatible", "CatToken OpenAI", "primary",
    "https://www.cattoken.vip/v1", "gpt-5.4",
),
"cattoken_claude": ProviderSlot(
    "anthropic_compatible", "CatToken Claude", "primary",
    "https://www.cattoken.vip", "claude-sonnet-4-6",
),
```

Make `_to_public()` return the slot’s fixed protocol for an absent record. Do not import or copy any legacy key into `cattoken_claude`.

- [ ] **Step 4: Enforce fixed protocol per slot**

Use a helper such as:

```python
def expected_protocol(slug: str) -> str:
    return "anthropic" if slug == "cattoken_claude" else "openai"
```

Allow `custom` to remain selectable. Reject a mismatched fixed protocol with `PROVIDER_PROTOCOL_INVALID` and a provider-specific message.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 6: Commit the isolated provider identity change**

```powershell
git add backend/api/schemas/providers.py backend/application/provider_service.py backend/tests/test_provider_service.py backend/tests/test_providers_api.py
git commit -m "feat: add CatToken Claude provider slot"
```

### Task 2: Test CatToken Claude with Anthropic Messages

**Files:**
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_clients.py`

- [ ] **Step 1: Write the failing connection test**

```python
@pytest.mark.asyncio
async def test_connection_tester_uses_messages_for_cattoken_claude():
    create = AsyncMock(return_value=SimpleNamespace(
        content=[SimpleNamespace(type="text", text="OK")]
    ))
    tester = ProviderConnectionTester(
        anthropic_client_factory=AsyncMock(
            return_value=SimpleNamespace(messages=SimpleNamespace(create=create))
        )
    )
    config = ProviderRuntimeConfig(
        slug="cattoken_claude",
        provider_type="anthropic_compatible",
        api_protocol="anthropic",
        display_name="CatToken Claude",
        role="primary",
        base_url="https://www.cattoken.vip",
        default_model="claude-sonnet-4-6",
        api_key="secret",
    )
    result = await tester(config)
    assert result.models == ("claude-sonnet-4-6",)
    create.assert_awaited_once_with(
        model="claude-sonnet-4-6",
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply OK"}],
    )
```

- [ ] **Step 2: Add error mapping tests**

Cover Anthropic authentication, not-found, rate-limit, timeout/connection and API status errors. Assert stable error codes and ensure messages do not contain the test key.

- [ ] **Step 3: Run the focused test and verify RED**

```powershell
pytest backend/tests/test_provider_clients.py -q
```

Expected: the new Claude test fails until the CatToken Claude path is recognized and error messages are provider-specific.

- [ ] **Step 4: Implement the minimal Anthropic connection path**

Keep `_test_anthropic()` as the single Messages implementation. Return only the model that completed the real `Reply OK` call. Map network and upstream errors using `config.display_name`; never include request headers or keys.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the command from Step 3. Expected: all provider client tests pass.

- [ ] **Step 6: Commit the connection test change**

```powershell
git add backend/application/provider_clients.py backend/tests/test_provider_clients.py
git commit -m "feat: test CatToken Claude messages API"
```

### Task 3: Resolve the correct runtime client and preserve history

**Files:**
- Modify: `backend/application/provider_clients.py`
- Test: `backend/tests/test_provider_clients.py`
- Test: `backend/tests/test_analysis_runner.py`
- Test: `backend/tests/test_job_service.py`

- [ ] **Step 1: Write failing resolver tests**

Assert:

```python
assert type(_default_client_builder(openai_config, "gpt-5.4")).__name__ == "CatTokenLLMClient"
assert type(_default_client_builder(claude_config, "claude-sonnet-4-6")).__name__ == "AnthropicLLMClient"
```

Use mocks where constructors would require real credentials. Add an analysis identity test proving `provider="cattoken_claude"` is persisted for new Claude jobs while historical `provider="cattoken"` still resolves to the OpenAI CatToken client.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
pytest backend/tests/test_provider_clients.py backend/tests/test_analysis_runner.py backend/tests/test_job_service.py -q
```

Expected: `cattoken_claude` falls through to the wrong client or is rejected.

- [ ] **Step 3: Implement explicit client routing**

```python
if config.slug == "cattoken":
    return CatTokenLLMClient(**kwargs)
if config.slug == "cattoken_claude":
    return AnthropicLLMClient(**kwargs)
```

Treat both slots as primary in `_load()`. Do not add legacy environment fallback for `cattoken_claude`; an absent database record must be unconfigured.

- [ ] **Step 4: Verify GREEN and commit**

Run the command from Step 2, then:

```powershell
git add backend/application/provider_clients.py backend/tests/test_provider_clients.py backend/tests/test_analysis_runner.py backend/tests/test_job_service.py
git commit -m "feat: resolve independent CatToken clients"
```

### Task 4: Render two independent API settings tabs

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Test: `frontend/tests/provider-settings.test.tsx`

- [ ] **Step 1: Write failing UI tests**

Extend fixtures with `cattoken` and `cattoken_claude`. Assert both tabs exist and show independent values:

```tsx
expect(await screen.findByRole("tab", { name: "CatToken OpenAI" })).toBeInTheDocument();
expect(screen.getByRole("tab", { name: "CatToken Claude" })).toBeInTheDocument();
await userEvent.click(screen.getByRole("tab", { name: "CatToken Claude" }));
expect(screen.getByDisplayValue("https://www.cattoken.vip")).toBeInTheDocument();
expect(screen.getByText("Anthropic 兼容")).toBeInTheDocument();
expect(screen.queryByText(/原密钥末四位/)).not.toBeInTheDocument();
```

Add a test that editing or testing the Claude tab does not change the OpenAI form values or masked key.

- [ ] **Step 2: Run the UI test and verify RED**

```powershell
Set-Location frontend
npm test -- --run tests/provider-settings.test.tsx
```

Expected: type/fixture failure or missing Claude tab.

- [ ] **Step 3: Extend the slug type and fixed protocol UI**

```ts
export type ProviderSlug =
  | "openai"
  | "cattoken"
  | "cattoken_claude"
  | "deepseek"
  | "custom";
```

Continue using the existing active provider/reset flow so each database record supplies its own masked key and values. Show protocol controls only for `custom`; fixed tabs display a non-editable protocol label. Keep model catalog pagination unchanged.

- [ ] **Step 4: Run UI tests and verify GREEN**

Run the command from Step 2. Expected: all provider settings tests pass.

- [ ] **Step 5: Commit the settings UI change**

```powershell
git add frontend/lib/api/types.ts frontend/components/settings/provider-settings-panel.tsx frontend/tests/provider-settings.test.tsx
git commit -m "feat: add independent CatToken settings tabs"
```

### Task 5: Distinguish both providers in task and result selectors

**Files:**
- Modify: `frontend/components/workbench/model-select.tsx`
- Modify: `frontend/lib/model-label.ts`
- Modify: `frontend/components/jobs/result-reliability-summary.tsx`
- Test: `frontend/tests/model-select.test.tsx`
- Test: `frontend/tests/model-label.test.ts`
- Test: `frontend/tests/job-forms.test.tsx`

- [ ] **Step 1: Write failing identity tests**

```ts
expect(resultModelLabel("gpt", {
  provider: "cattoken_claude",
  model: "claude-sonnet-4-6",
})).toBe("CatToken Claude · claude-sonnet-4-6");
```

Render both enabled providers with successful model catalogs and assert both full identities are selectable. Assert an untested/failed Claude provider is absent from task choices.

- [ ] **Step 2: Run tests and verify RED**

```powershell
Set-Location frontend
npm test -- --run tests/model-select.test.tsx tests/model-label.test.ts tests/job-forms.test.tsx
```

- [ ] **Step 3: Implement labels and filtering**

Add explicit labels:

```ts
cattoken: "CatToken OpenAI",
cattoken_claude: "CatToken Claude",
```

Keep provider selection based on enabled/configured/test-success data returned by the existing jobs API. Do not rewrite historical payloads.

- [ ] **Step 4: Verify GREEN and commit**

Run the command from Step 2, then commit only the listed files with message:

```powershell
git commit -m "feat: distinguish CatToken model identities"
```

### Task 6: Full regression and live CatToken Claude acceptance

**Files:**
- Create: `docs/verification/2026-07-31-cattoken-dual-provider.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Run backend regression**

```powershell
pytest backend/tests tests -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run frontend regression and build**

```powershell
Set-Location frontend
npm test -- --run
npm run build
```

Expected: all tests pass and Next.js build exits 0. Record any pre-existing warnings separately.

- [ ] **Step 3: Restart only this project’s frontend after build**

Resolve port 3000, verify its command line belongs to `F:\组合品7-31\web-platform-v2.1-work\frontend`, restart it hidden, and verify `/settings/api` returns HTTP 200. Do not stop an unrelated process.

- [ ] **Step 4: Configure Claude without exposing its key**

In `CatToken Claude`, enter the user-authorized key, keep root URL `https://www.cattoken.vip`, test a CatToken-supported Claude model, and save only after success. Do not print or store the key outside encrypted provider storage.

- [ ] **Step 5: Run one minimum real task**

Submit a minimal analysis using `provider=cattoken_claude` and the verified model. Verify task completion and non-empty structured output.

- [ ] **Step 6: Verify CatToken-side evidence**

Read the authorized CatToken dashboard and confirm Claude request count or usage increased. Do not create, edit, disable or delete CatToken keys.

- [ ] **Step 7: Record evidence and failures**

Write exact commands, pass counts, HTTP status and the masked provider/model identity to the verification document. Append every optimization and failure to `docs/优化迭代记录.md`; never include credentials.

- [ ] **Step 8: Final diff and secret scan**

```powershell
git diff --check
rg -n "297449102@qq.com|Aa4453287|sk-[A-Za-z0-9]" backend frontend docs tests
```

Expected: no credential matches in changed project files. If generic test fixtures match `sk-`, manually verify they are synthetic and not the user’s key.

- [ ] **Step 9: Commit verification records**

```powershell
git add docs/verification/2026-07-31-cattoken-dual-provider.md docs/优化迭代记录.md
git commit -m "docs: verify dual CatToken providers"
```
