# API Settings and Low-Glare UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure runtime API configuration for OpenAI, CatToken, DeepSeek, and one custom OpenAI-compatible provider, then apply the approved mist-gray and ink-green UI without breaking existing jobs.

**Architecture:** Store provider records in PostgreSQL, encrypt API keys with a backend-owned Fernet key, expose masked localhost-only settings endpoints, and resolve provider clients when the Worker starts a job. The Next.js app gets a dedicated API settings page, loads available providers into existing job forms, and applies semantic theme tokens across the current shell and content views.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy Async, Alembic, PostgreSQL/SQLite tests, cryptography/Fernet, ARQ, Next.js 15, React 19, TypeScript, Tailwind CSS, React Query, React Hook Form, Zod, Vitest, Playwright.

**Execution constraint:** The current `.git` file points to missing metadata at `D:/Desktop/bundling-system/.git/worktrees/web-platform`. Do not initialize a replacement repository or rewrite `.git`. Run each listed commit only after the original Git worktree metadata is restored.

---

## File Map

**Backend files to create**

- `backend/security/provider_crypto.py`: load or create the local Fernet key, encrypt/decrypt provider secrets, and mask keys.
- `backend/db/provider_repository.py`: persistence boundary for provider configurations.
- `backend/api/schemas/providers.py`: request and response schemas with API keys excluded from read models.
- `backend/application/provider_service.py`: validation, draft testing, transactional save, environment import, and public availability projection.
- `backend/application/provider_clients.py`: provider settings DTO, OpenAI-compatible connection test, and LLM client factory.
- `backend/api/routes/providers.py`: localhost-only settings endpoints.
- `backend/migrations/versions/0003_add_provider_configurations.py`: provider table migration.
- `backend/tests/test_provider_crypto.py`: encryption, masking, and key-file behavior.
- `backend/tests/test_provider_repository.py`: provider persistence and uniqueness.
- `backend/tests/test_provider_service.py`: save, rollback, environment import, and fallback rules.
- `backend/tests/test_providers_api.py`: API security, masking, validation, and status codes.
- `backend/tests/test_provider_clients.py`: provider client construction and connection error mapping.

**Backend files to modify**

- `.gitignore`: ignore `backend/.api-config.key` and `.superpowers/`.
- `backend/requirements.txt`: add `cryptography`.
- `backend/config.py`: configure encryption key file and settings-route loopback enforcement.
- `backend/db/models.py`: add `ProviderConfiguration`.
- `backend/db/repositories.py`: leave job repository focused; only export job-related types.
- `backend/api/dependencies.py`: provide provider repository, crypto, service, and resolver dependencies.
- `backend/api/router.py`: include provider routes.
- `backend/main.py`: allow `PUT` in CORS and run idempotent environment import at startup.
- `backend/api/schemas/jobs.py`: allow `custom` as a main provider.
- `backend/application/job_service.py`: reject missing or disabled main-provider configurations before enqueue.
- `backend/workers/jobs.py`: resolve primary and DeepSeek clients from current provider settings.
- `app/infrastructure/llm/__init__.py`: allow explicit `api_key`, `base_url`, and model constructor parameters while retaining `.env` defaults.
- `backend/tests/test_jobs_api.py`, `backend/tests/test_job_service.py`, `backend/tests/test_worker_jobs.py`, `backend/tests/test_security.py`: extend current behavior coverage.

**Frontend files to create**

- `frontend/lib/api/providers.ts`: provider settings API client.
- `frontend/lib/schemas/provider-settings.ts`: form schema and URL restrictions.
- `frontend/app/settings/api/page.tsx`: API settings route.
- `frontend/components/settings/provider-settings-panel.tsx`: provider tabs, form state, status, save, and test interactions.
- `frontend/components/settings/secret-input.tsx`: explicit replace/cancel password interaction.
- `frontend/tests/provider-settings.test.tsx`: settings-page behavior.
- `frontend/tests/provider-api-client.test.ts`: request and response mapping.

**Frontend files to modify**

- `frontend/lib/api/types.ts`: provider DTOs and `custom` provider type.
- `frontend/lib/query-keys.ts`: provider query keys.
- `frontend/components/workbench/model-select.tsx`: render enabled main providers and custom model entry.
- `frontend/components/workbench/hypothesis-form.tsx`, `judgment-form.tsx`, `batch-form.tsx`: query provider availability and block invalid submission.
- `frontend/components/layout/sidebar.tsx`, `mobile-nav.tsx`: stable navigation plus API settings.
- `frontend/components/layout/app-shell.tsx`: stable shell surfaces and accessible appearance control.
- `frontend/app/globals.css`, `frontend/tailwind.config.ts`: approved semantic palette.
- `frontend/tests/job-forms.test.tsx`, `app-shell.test.tsx`, `accessibility.test.tsx`: regression coverage.
- `frontend/e2e/workbench.spec.ts`: settings-to-workbench smoke flow with mocked API.

### Task 1: Provider Persistence and Secret Encryption

**Files:**
- Modify: `.gitignore`
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`
- Modify: `backend/db/models.py`
- Create: `backend/db/provider_repository.py`
- Create: `backend/security/provider_crypto.py`
- Create: `backend/security/__init__.py`
- Create: `backend/migrations/versions/0003_add_provider_configurations.py`
- Create: `backend/tests/test_provider_crypto.py`
- Create: `backend/tests/test_provider_repository.py`

- [ ] **Step 1: Add failing encryption tests**

```python
from backend.security.provider_crypto import ProviderCrypto


def test_crypto_round_trip_and_mask(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    encrypted = crypto.encrypt("sk-test-secret-4F2A")

    assert encrypted != "sk-test-secret-4F2A"
    assert crypto.decrypt(encrypted) == "sk-test-secret-4F2A"
    assert crypto.mask("sk-test-secret-4F2A") == "••••4F2A"
    assert (tmp_path / "provider.key").exists()


def test_empty_key_has_no_identifying_suffix(tmp_path):
    crypto = ProviderCrypto(key_file=tmp_path / "provider.key")
    assert crypto.mask("abc") == "••••"
```

- [ ] **Step 2: Run the encryption tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_crypto.py -q`

Expected: collection fails because `backend.security.provider_crypto` does not exist.

- [ ] **Step 3: Add the dependency and implement `ProviderCrypto`**

Add `cryptography>=45,<46` to `backend/requirements.txt`. Add `backend/.api-config.key` and `.superpowers/` to `.gitignore`.

```python
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class ProviderDecryptionError(RuntimeError):
    pass


class ProviderCrypto:
    def __init__(self, *, key_file: Path, configured_key: str | None = None) -> None:
        self._key_file = key_file
        key = configured_key.encode("ascii") if configured_key else self._load_or_create_key()
        self._fernet = Fernet(key)

    def _load_or_create_key(self) -> bytes:
        if self._key_file.exists():
            return self._key_file.read_bytes().strip()
        self._key_file.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        self._key_file.write_bytes(key + b"\n")
        try:
            os.chmod(self._key_file, 0o600)
        except OSError:
            pass
        return key

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as error:
            raise ProviderDecryptionError("Provider credential must be re-entered") from error

    @staticmethod
    def mask(value: str) -> str:
        return f"••••{value[-4:]}" if len(value) >= 4 else "••••"
```

Add `provider_encryption_key: str | None = None` and `provider_key_file: Path = Path("backend/.api-config.key")` to `BackendSettings`.

- [ ] **Step 4: Run encryption tests and verify pass**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_crypto.py -q`

Expected: all tests pass.

- [ ] **Step 5: Add failing repository tests**

```python
@pytest.mark.asyncio
async def test_provider_repository_upserts_one_row_per_slug(session):
    repository = ProviderConfigurationRepository(session)
    first = await repository.upsert(
        slug="openai",
        provider_type="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        encrypted_api_key="cipher-1",
        api_key_last4="1111",
        is_enabled=True,
    )
    second = await repository.upsert(
        slug="openai",
        provider_type="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1",
        encrypted_api_key="cipher-2",
        api_key_last4="2222",
        is_enabled=True,
    )

    assert first.id == second.id
    assert second.default_model == "gpt-4.1"
    assert len(await repository.list_all()) == 1
```

- [ ] **Step 6: Add the model, migration, and repository**

`ProviderConfiguration` must use the exact columns from the approved design. `slug` is unique and `last_test_status` defaults to `untested`.

```python
class ProviderConfiguration(Base):
    __tablename__ = "provider_configurations"
    __table_args__ = (UniqueConstraint("slug"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    default_model: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    is_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_test_status: Mapped[str] = mapped_column(String(16), default="untested", nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
```

The migration revision is `0003`, revises `0002`, creates the table and unique constraint, and drops the table in `downgrade()`.

- [ ] **Step 7: Run repository and migration tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_repository.py backend/tests/test_job_repository.py -q`

Expected: all tests pass and existing job repository behavior remains unchanged.

- [ ] **Step 8: Commit after Git metadata is restored**

```powershell
git add .gitignore backend/requirements.txt backend/config.py backend/db/models.py backend/db/provider_repository.py backend/security backend/migrations/versions/0003_add_provider_configurations.py backend/tests/test_provider_crypto.py backend/tests/test_provider_repository.py
git commit -m "feat: add encrypted provider configuration storage"
```

### Task 2: Provider Service and Localhost-Only Settings API

**Files:**
- Create: `backend/api/schemas/providers.py`
- Create: `backend/application/provider_clients.py`
- Create: `backend/application/provider_service.py`
- Create: `backend/api/routes/providers.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/router.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_provider_clients.py`
- Create: `backend/tests/test_provider_service.py`
- Create: `backend/tests/test_providers_api.py`

- [ ] **Step 1: Write failing schema and masking API tests**

```python
@pytest.mark.asyncio
async def test_provider_list_never_returns_secret():
    service = AsyncMock()
    service.list_public.return_value = [
        ProviderPublic(
            slug="openai",
            display_name="OpenAI",
            role="primary",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o",
            is_enabled=True,
            configured=True,
            masked_api_key="••••4F2A",
            last_test_status="success",
            last_tested_at=None,
            last_test_message="Connection successful",
        )
    ]
    app = create_app()
    app.dependency_overrides[get_provider_service] = lambda: service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get("/api/v1/settings/providers")

    body = response.json()
    assert response.status_code == 200
    assert body[0]["masked_api_key"] == "••••4F2A"
    assert "encrypted_api_key" not in response.text
    assert "sk-" not in response.text
```

- [ ] **Step 2: Run API tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_providers_api.py -q`

Expected: collection fails because provider schemas, dependency, and route do not exist.

- [ ] **Step 3: Implement provider schemas with strict input**

```python
ProviderSlug = Literal["openai", "cattoken", "deepseek", "custom"]


class ProviderDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(None, min_length=1, max_length=80)
    base_url: HttpUrl | None = None
    default_model: str = Field(min_length=1, max_length=120)
    api_key: SecretStr | None = None


class ProviderUpdate(ProviderDraft):
    is_enabled: bool
    clear_api_key: bool = False


class ProviderPublic(BaseModel):
    slug: ProviderSlug
    display_name: str
    role: Literal["primary", "secondary"]
    base_url: str | None
    default_model: str
    is_enabled: bool
    configured: bool
    masked_api_key: str | None
    last_test_status: Literal["untested", "success", "failed"]
    last_tested_at: datetime | None
    last_test_message: str | None
```

- [ ] **Step 4: Implement provider client testing and stable error mapping**

Create `ProviderConnectionError(code, message, retryable)`. Use `AsyncOpenAI` with a five-second timeout and call `chat.completions.create` with `messages=[{"role": "user", "content": "Reply OK"}]`, `max_tokens=1`, and the draft model. Map authentication, not-found/model, timeout, rate-limit, and connection exceptions to the approved stable codes. Never include the upstream response body or key in `message`.

- [ ] **Step 5: Write failing transactional-save tests**

```python
@pytest.mark.asyncio
async def test_failed_connection_does_not_replace_existing_configuration():
    repository = AsyncMock()
    existing = provider_row(encrypted_api_key="old-cipher", default_model="gpt-4o")
    repository.get.return_value = existing
    tester = AsyncMock(side_effect=ProviderConnectionError("PROVIDER_AUTH_FAILED", "Authentication failed", False))
    service = ProviderService(repository=repository, crypto=crypto_stub(), connection_test=tester)

    with pytest.raises(ProviderConnectionError):
        await service.save("openai", ProviderUpdate(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4.1",
            api_key=SecretStr("sk-new"),
            is_enabled=True,
        ))

    repository.upsert.assert_not_awaited()
```

- [ ] **Step 6: Implement `ProviderService`**

Use fixed slot definitions so callers cannot alter built-in provider type or role:

```python
PROVIDER_SLOTS = {
    "openai": Slot("openai", "OpenAI", "primary", "https://api.openai.com/v1", "gpt-4o"),
    "cattoken": Slot("openai_compatible", "CatToken", "primary", "https://www.cattoken.vip/v1", "gpt-5.4"),
    "deepseek": Slot("openai_compatible", "DeepSeek", "secondary", "https://api.deepseek.com", "deepseek-chat"),
    "custom": Slot("openai_compatible", "自定义 API", "primary", None, "gpt-4o"),
}
```

`save()` resolves the retained or replacement key, validates the endpoint, tests changed or enabled configurations, encrypts only after a successful test, and calls one repository upsert. `list_public()` always returns four slots even before rows exist.

- [ ] **Step 7: Add localhost-only routes and dependencies**

```python
def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "test"}:
        raise HTTPException(
            status_code=403,
            detail={"code": "SETTINGS_LOCAL_ONLY", "message": "API settings are available only on this computer", "retryable": False},
        )
```

Routes:

- `GET /settings/providers` calls `list_public()`.
- `POST /settings/providers/{slug}/test` calls `test_draft()`.
- `PUT /settings/providers/{slug}` calls `save()`.

Add `PUT` to FastAPI CORS methods. Include `providers_router` in `backend/api/router.py`.

- [ ] **Step 8: Run provider service and API tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py backend/tests/test_provider_service.py backend/tests/test_providers_api.py backend/tests/test_security.py -q`

Expected: all tests pass; response serialization contains no encrypted key or plaintext key.

- [ ] **Step 9: Commit after Git metadata is restored**

```powershell
git add backend/api/schemas/providers.py backend/application/provider_clients.py backend/application/provider_service.py backend/api/routes/providers.py backend/api/dependencies.py backend/api/router.py backend/main.py backend/tests/test_provider_clients.py backend/tests/test_provider_service.py backend/tests/test_providers_api.py backend/tests/test_security.py
git commit -m "feat: expose secure provider settings API"
```

### Task 3: Environment Import, Runtime Client Resolution, and Job Validation

**Files:**
- Modify: `backend/application/provider_service.py`
- Modify: `backend/main.py`
- Modify: `app/infrastructure/llm/__init__.py`
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/application/job_service.py`
- Modify: `backend/workers/jobs.py`
- Modify: `backend/tests/test_provider_service.py`
- Modify: `backend/tests/test_job_service.py`
- Modify: `backend/tests/test_worker_jobs.py`

- [ ] **Step 1: Write failing environment-import tests**

```python
@pytest.mark.asyncio
async def test_import_env_is_idempotent_and_never_overwrites_database():
    repository = AsyncMock()
    repository.get.side_effect = [None, provider_row(default_model="gpt-4.1")]
    service = ProviderService(repository=repository, crypto=crypto_stub(), connection_test=AsyncMock())
    env = LegacyProviderSettings(openai_api_key="sk-env", openai_model="gpt-4o")

    await service.import_legacy_env(env)
    await service.import_legacy_env(env)

    assert repository.upsert.await_count == 1
```

- [ ] **Step 2: Implement idempotent startup import**

`import_legacy_env()` imports only non-empty built-in provider keys into missing slots, encrypts without a paid connection test, sets `last_test_status="untested"`, and never updates an existing row. Register it in a FastAPI lifespan function so startup completes before requests are accepted.

- [ ] **Step 3: Write failing explicit-client constructor tests**

```python
def test_cattoken_client_accepts_runtime_credentials(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.infrastructure.llm.AsyncOpenAI", FakeOpenAI)
    CatTokenLLMClient(api_key="runtime-key", base_url="https://proxy.example/v1", model="gpt-5.4")

    assert captured == {"api_key": "runtime-key", "base_url": "https://proxy.example/v1"}
```

- [ ] **Step 4: Refactor LLM constructors without breaking `.env` defaults**

Use constructor signatures:

```python
def __init__(
    self,
    model: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> None:
```

For each client, resolve explicit values first and existing settings second. `OpenAILLMClient` passes `base_url` only when provided. CatToken and DeepSeek retain their current default URLs and model behavior.

- [ ] **Step 5: Write failing job validation tests**

```python
@pytest.mark.asyncio
async def test_submit_rejects_disabled_provider_before_creating_job():
    repository = AsyncMock()
    queue = AsyncMock()
    availability = AsyncMock(return_value=False)
    service = JobService(repository=repository, queue=queue, provider_available=availability)

    with pytest.raises(ServiceUnavailableError) as caught:
        await service.submit_hypothesis(HypothesisJobCreate(
            url="https://www.walmart.com/ip/example/12345",
            provider="custom",
        ))

    assert caught.value.code == "PROVIDER_NOT_CONFIGURED"
    repository.create.assert_not_awaited()
```

- [ ] **Step 6: Validate provider at submission and expand job schemas**

Change provider validation to `^(openai|cattoken|custom)?$`. Inject an async availability function into `JobService`; default missing provider to `openai`. Reject disabled or unconfigured providers before creating a database job.

- [ ] **Step 7: Write failing Worker resolver tests**

```python
@pytest.mark.asyncio
async def test_worker_resolves_custom_primary_and_optional_deepseek(mock_ctx):
    primary = AsyncMock(name="custom-primary")
    secondary = AsyncMock(name="deepseek-secondary")
    resolver = AsyncMock()
    resolver.primary.return_value = primary
    resolver.secondary_deepseek.return_value = secondary

    await run_worker_with_claimed_payload(
        mock_ctx,
        {"url": "https://walmart.com/ip/test", "provider": "custom", "model": "model-x"},
        resolver=resolver,
    )

    resolver.primary.assert_awaited_once_with("custom", "model-x")
    resolver.secondary_deepseek.assert_awaited_once()
```

- [ ] **Step 8: Implement runtime `ProviderClientResolver` and update Worker**

Resolver behavior:

```python
async def primary(self, slug: str, model: str | None):
    resolved = await self._load_required(slug)
    return self._build(resolved, model or resolved.default_model)

async def secondary_deepseek(self):
    resolved = await self._load_optional("deepseek")
    return None if resolved is None else self._build(resolved, resolved.default_model)
```

Create the resolver with the Worker's current SQLAlchemy session and crypto service. Remove `_create_llm`, `_create_cattoken_llm`, and `_create_deepseek_llm` after all call sites use the resolver. Preserve existing `models.gpt` and `models.deepseek` result keys.

- [ ] **Step 9: Run job and Worker regressions**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_job_service.py backend/tests/test_job_schemas.py backend/tests/test_worker_jobs.py backend/tests/test_analysis_runner.py -q`

Expected: all tests pass for OpenAI, CatToken, custom primary, optional DeepSeek, and existing retry behavior.

- [ ] **Step 10: Commit after Git metadata is restored**

```powershell
git add backend/application/provider_service.py backend/main.py app/infrastructure/llm/__init__.py backend/api/schemas/jobs.py backend/application/job_service.py backend/workers/jobs.py backend/tests/test_provider_service.py backend/tests/test_job_service.py backend/tests/test_worker_jobs.py
git commit -m "feat: resolve provider settings at job runtime"
```

### Task 4: Frontend Provider API and Settings Page

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/query-keys.ts`
- Create: `frontend/lib/api/providers.ts`
- Create: `frontend/lib/schemas/provider-settings.ts`
- Create: `frontend/components/settings/secret-input.tsx`
- Create: `frontend/components/settings/provider-settings-panel.tsx`
- Create: `frontend/app/settings/api/page.tsx`
- Create: `frontend/tests/provider-api-client.test.ts`
- Create: `frontend/tests/provider-settings.test.tsx`

- [ ] **Step 1: Add failing API client tests**

```typescript
it("updates one provider without sending a masked key", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(providerFixture), { status: 200 })
  );

  await updateProvider("openai", {
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
    is_enabled: true,
  });

  expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:8000/api/v1/settings/providers/openai",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        base_url: "https://api.openai.com/v1",
        default_model: "gpt-4o",
        is_enabled: true,
      }),
    })
  );
});
```

- [ ] **Step 2: Implement provider types, query keys, schemas, and API client**

Use these stable TypeScript types:

```typescript
export type ProviderSlug = "openai" | "cattoken" | "deepseek" | "custom";
export type ProviderRole = "primary" | "secondary";

export interface ProviderConfiguration {
  slug: ProviderSlug;
  display_name: string;
  role: ProviderRole;
  base_url: string | null;
  default_model: string;
  is_enabled: boolean;
  configured: boolean;
  masked_api_key: string | null;
  last_test_status: "untested" | "success" | "failed";
  last_tested_at: string | null;
  last_test_message: string | null;
}
```

`listProviders`, `testProvider`, and `updateProvider` call the exact endpoints from Task 2. The form schema requires a model, requires custom display name and Base URL, allows omitted replacement Key, and never accepts the displayed masked value as `api_key`.

- [ ] **Step 3: Run API client tests**

Run: `npm --prefix frontend test -- --run tests/provider-api-client.test.ts`

Expected: tests pass and request bodies contain no masked secret.

- [ ] **Step 4: Add failing settings interaction tests**

```typescript
it("keeps the stored key masked until replacement is requested", async () => {
  render(<ProviderSettingsPanel />, { wrapper: QueryWrapper });
  expect(await screen.findByText("••••4F2A")).toBeInTheDocument();
  expect(screen.queryByLabelText("新 API Key")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "替换密钥" }));
  expect(screen.getByLabelText("新 API Key")).toHaveAttribute("type", "password");
});

it("does not discard draft values when connection testing fails", async () => {
  server.use(failedProviderTestHandler);
  render(<ProviderSettingsPanel />, { wrapper: QueryWrapper });
  const model = await screen.findByLabelText("默认模型");
  await userEvent.clear(model);
  await userEvent.type(model, "custom-model");
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("认证失败");
  expect(model).toHaveValue("custom-model");
});
```

- [ ] **Step 5: Implement `SecretInput` and `ProviderSettingsPanel`**

`SecretInput` renders the masked value, a Key icon, “替换密钥”, and after activation a password input with show/hide icon buttons and tooltips. Cancel clears the draft replacement only.

`ProviderSettingsPanel` uses one query for the four slots, a controlled active tab, React Hook Form per selected provider, mutations for test and save, and query invalidation after successful save. DeepSeek displays a visible “二次验证” role label. A failed mutation renders a role `alert` and retains form values.

- [ ] **Step 6: Implement the route and responsive layout**

`frontend/app/settings/api/page.tsx` renders a compact page title, configured-count status, and the panel in a constrained `max-w-4xl` content area. On small screens the two-column field grid becomes one column and action buttons wrap without truncation.

- [ ] **Step 7: Run settings component tests and type check**

Run: `npm --prefix frontend test -- --run tests/provider-api-client.test.ts tests/provider-settings.test.tsx`

Run: `npm --prefix frontend run typecheck`

Expected: all tests and TypeScript checks pass.

- [ ] **Step 8: Commit after Git metadata is restored**

```powershell
git add frontend/lib/api/types.ts frontend/lib/query-keys.ts frontend/lib/api/providers.ts frontend/lib/schemas/provider-settings.ts frontend/components/settings frontend/app/settings/api/page.tsx frontend/tests/provider-api-client.test.ts frontend/tests/provider-settings.test.tsx
git commit -m "feat: add visual API settings page"
```

### Task 5: Workbench Provider Availability and Navigation

**Files:**
- Modify: `frontend/components/workbench/model-select.tsx`
- Modify: `frontend/components/workbench/hypothesis-form.tsx`
- Modify: `frontend/components/workbench/judgment-form.tsx`
- Modify: `frontend/components/workbench/batch-form.tsx`
- Modify: `frontend/lib/schemas/job-forms.ts`
- Modify: `frontend/components/layout/sidebar.tsx`
- Modify: `frontend/components/layout/mobile-nav.tsx`
- Modify: `frontend/tests/job-forms.test.tsx`
- Modify: `frontend/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing workbench availability tests**

```typescript
it("shows only enabled primary providers", async () => {
  server.use(providerListHandler([
    provider({ slug: "openai", role: "primary", is_enabled: true, configured: true }),
    provider({ slug: "cattoken", role: "primary", is_enabled: false, configured: true }),
    provider({ slug: "deepseek", role: "secondary", is_enabled: true, configured: true }),
  ]));
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  await userEvent.click(screen.getByText(/高级选项/));

  expect(await screen.findByRole("option", { name: /OpenAI/ })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /CatToken/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /DeepSeek/ })).not.toBeInTheDocument();
});

it("links to API settings when no primary provider is available", async () => {
  server.use(providerListHandler([]));
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  expect(await screen.findByRole("link", { name: "前往 API 设置" })).toHaveAttribute("href", "/settings/api");
});
```

- [ ] **Step 2: Refactor `ModelSelect` to accept provider data**

Replace local provider state defaults with props:

```typescript
interface ModelSelectProps {
  providers: ProviderConfiguration[];
  modelRegistration: UseFormRegisterReturn;
  providerRegistration: UseFormRegisterReturn;
}
```

Filter `role === "primary" && configured && is_enabled`. Retain grouped built-in model suggestions for OpenAI and CatToken. For `custom`, render a text input bound to `model` with the configured default model as the initial value.

- [ ] **Step 3: Load provider availability once per form**

Use React Query with `queryKeys.providers.all`. While loading, disable submit. If no main provider is available, render a compact status row and settings link. Ensure mutation payloads send only `openai`, `cattoken`, or `custom` and the selected model.

- [ ] **Step 4: Add failing navigation tests**

```typescript
it("renders stable desktop API settings navigation", () => {
  render(<AppShell>content</AppShell>);
  expect(screen.getAllByRole("link", { name: "API 设置" }).length).toBeGreaterThanOrEqual(1);
  expect(screen.getByTestId("desktop-sidebar")).toHaveClass("w-56");
});
```

- [ ] **Step 5: Make desktop navigation stable and add settings links**

Remove hover width state from `Sidebar`. Use a fixed `w-56`, deep navigation surface, current-route styling through `usePathname`, and icons `LayoutDashboard`, `FileText`, `History`, and `KeyRound`. Add the same four destinations to `MobileNav`; retain close-on-navigation and dialog semantics.

- [ ] **Step 6: Run workbench and shell tests**

Run: `npm --prefix frontend test -- --run tests/job-forms.test.tsx tests/app-shell.test.tsx tests/accessibility.test.tsx`

Expected: all tests pass, including no-provider and mobile navigation behavior.

- [ ] **Step 7: Commit after Git metadata is restored**

```powershell
git add frontend/components/workbench frontend/lib/schemas/job-forms.ts frontend/components/layout/sidebar.tsx frontend/components/layout/mobile-nav.tsx frontend/tests/job-forms.test.tsx frontend/tests/app-shell.test.tsx
git commit -m "feat: connect workbench to provider availability"
```

### Task 6: Apply the Approved Mist-Gray and Ink-Green Theme

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/components/layout/app-shell.tsx`
- Modify: `frontend/components/layout/sidebar.tsx`
- Modify: `frontend/components/layout/mobile-nav.tsx`
- Modify: relevant `frontend/app/**/*.tsx` and `frontend/components/**/*.tsx` only where hard-coded colors conflict with the semantic theme
- Modify: `frontend/tests/shell.test.tsx`

- [ ] **Step 1: Add a failing semantic-token test**

```typescript
it("uses the approved low-glare shell surfaces", () => {
  render(<AppShell><div>content</div></AppShell>);
  expect(screen.getByTestId("app-shell")).toHaveClass("bg-canvas");
  expect(screen.getByTestId("desktop-sidebar")).toHaveClass("bg-navigation");
});
```

- [ ] **Step 2: Define semantic colors**

Set the approved light tokens in `globals.css`:

```css
:root {
  --background: 140 9% 94%;
  --foreground: 145 13% 18%;
  --card: 0 0% 100%;
  --card-foreground: 145 13% 18%;
  --primary: 148 52% 28%;
  --primary-foreground: 0 0% 100%;
  --secondary: 135 10% 89%;
  --secondary-foreground: 145 16% 24%;
  --muted: 135 9% 91%;
  --muted-foreground: 145 7% 42%;
  --accent: 140 13% 86%;
  --accent-foreground: 148 48% 24%;
  --destructive: 9 63% 56%;
  --destructive-foreground: 0 0% 100%;
  --success: 148 45% 38%;
  --success-foreground: 0 0% 100%;
  --warning: 39 73% 48%;
  --warning-foreground: 145 13% 16%;
  --border: 140 9% 82%;
  --input: 140 9% 79%;
  --ring: 148 52% 28%;
  --canvas: 140 9% 94%;
  --navigation: 148 15% 14%;
  --navigation-foreground: 135 13% 88%;
  --radius: 6px;
}
```

Expose `canvas`, `navigation`, and `navigation-foreground` in `tailwind.config.ts`. Do not introduce viewport-scaled font sizes, gradients, decorative blobs, or radii above 8px.

- [ ] **Step 3: Apply tokens to the shell and major views**

Use `bg-canvas` on the shell and `bg-navigation text-navigation-foreground` on desktop navigation. Main page sections remain unframed; individual forms, repeated results, and settings panels may use white surfaces with `border-border`. Replace hard-coded gray/black backgrounds that undermine the palette, while retaining green/red/blue analytical status distinctions where they communicate data.

Keep the existing background-image control. When an image is active, use the approved canvas color for the opacity overlay rather than pure white.

- [ ] **Step 4: Scan for one-note and conflicting hard-coded colors**

Run: `rg -n "bg-(white|gray|slate|zinc|neutral)|text-(gray|slate|zinc|neutral)|#[0-9A-Fa-f]{6}" frontend/app frontend/components`

Expected: remaining matches are intentional data-status colors or documented image overlays; shell and form structure use semantic tokens.

- [ ] **Step 5: Run UI tests and production build**

Run: `npm --prefix frontend test -- --run tests/shell.test.tsx tests/app-shell.test.tsx tests/accessibility.test.tsx tests/provider-settings.test.tsx`

Run: `npm --prefix frontend run typecheck`

Run: `npm --prefix frontend run build`

Expected: all tests pass, type check exits zero, and Next.js production build succeeds.

- [ ] **Step 6: Commit after Git metadata is restored**

```powershell
git add frontend/app/globals.css frontend/tailwind.config.ts frontend/components/layout frontend/app frontend/components frontend/tests/shell.test.tsx
git commit -m "style: apply low-glare operations theme"
```

### Task 7: Migration, Full Regression, and Browser Acceptance

**Files:**
- Modify: `frontend/e2e/workbench.spec.ts`
- Modify: `backend/README.md`
- Modify: `frontend/README.md`
- Modify: `.env.example`
- Verification output only: do not commit generated logs, screenshots, `.superpowers/`, `.next/`, or test artifacts

- [ ] **Step 1: Install the new backend dependency**

Run: `.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`

Expected: `cryptography` installs successfully without changing source files outside dependency metadata already listed in Task 1.

- [ ] **Step 2: Run the database migration**

Run: `.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini upgrade head`

Expected: Alembic applies revision `0003` and preserves existing analysis jobs.

- [ ] **Step 3: Add a mocked end-to-end settings-to-workbench test**

The Playwright test must intercept `/api/v1/settings/providers`, `/test`, and `PUT`, then verify this sequence:

```typescript
await page.goto("/settings/api");
await page.getByRole("tab", { name: "自定义 API" }).click();
await page.getByLabel("服务名称").fill("内部模型服务");
await page.getByLabel("服务地址").fill("https://llm.example/v1");
await page.getByLabel("默认模型").fill("model-x");
await page.getByRole("button", { name: "替换密钥" }).click();
await page.getByLabel("新 API Key").fill("test-secret");
await page.getByRole("button", { name: "测试连接" }).click();
await expect(page.getByText("连接成功")).toBeVisible();
await page.getByRole("button", { name: "保存配置" }).click();
await page.goto("/");
await page.getByText(/高级选项/).click();
await page.getByLabel("供应商").selectOption("custom");
await expect(page.getByLabel("模型")).toHaveValue("model-x");
```

- [ ] **Step 4: Run all backend verification**

Run: `.venv\Scripts\python.exe -m pytest tests backend/tests -q`

Run: `.venv\Scripts\ruff.exe check app backend tests`

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Run all frontend verification**

Run: `npm --prefix frontend test -- --run`

Run: `npm --prefix frontend run typecheck`

Run: `npm --prefix frontend run build`

Expected: Vitest, TypeScript, and Next.js build all succeed.

- [ ] **Step 6: Start services and run Playwright**

Start PostgreSQL/Redis if needed, then API, Worker, and frontend using the documented commands. Run:

`npm --prefix frontend exec playwright test e2e/workbench.spec.ts`

Expected: the mocked settings-to-workbench flow and existing workbench scenarios pass without calling a paid API.

- [ ] **Step 7: Perform visual acceptance at desktop and mobile sizes**

At `1440x900` and `390x844`, verify:

- navigation labels are visible and do not resize the content on hover;
- API settings fields and buttons do not overlap or truncate;
- masked keys never appear in password inputs;
- no-provider state links to `/settings/api`;
- canvas is mist gray, navigation is ink green, and failure states use coral;
- workbench, history, result, and job detail pages remain usable;
- custom background images still render and the overlay uses the theme canvas.

- [ ] **Step 8: Update operator documentation**

Document the `/settings/api` workflow, the automatically generated `backend/.api-config.key`, backup implications, one-time migration, `.env` fallback rule, and the fact that remote deployment requires administrator authentication.

- [ ] **Step 9: Final commit after Git metadata is restored**

```powershell
git add frontend/e2e/workbench.spec.ts backend/README.md frontend/README.md .env.example
git commit -m "test: verify API settings workflow end to end"
```

## Completion Gate

Do not claim completion until all of the following are true:

- Alembic revision `0003` applies successfully.
- Provider API returns masked configuration only.
- Invalid replacement credentials do not overwrite a working configuration.
- Existing `.env` settings import once and are not overwritten on subsequent startup.
- OpenAI, CatToken, and custom primary provider resolution tests pass.
- DeepSeek remains optional secondary analysis and cross-review remains compatible.
- Workbench blocks submission when no main provider is usable.
- API settings page works with keyboard and mobile layout.
- Existing backend tests, frontend tests, type check, production build, and targeted Playwright tests pass.
- Visual inspection confirms the approved low-glare theme and no text/control overlap.
