# 2026-08-14 Third-Party OpenAI Compatibility Verification

## Scope

This verification covers third-party OpenAI-compatible GPT transport discovery, persisted structured-output capability, fixed runtime routing, stable errors, connection testing, model rotation integration, and desktop release `0.1.14`.

The implementation does not change official OpenAI model-name routing, DeepSeek, Anthropic, model candidate ordering, history persistence, scraper behavior, or the V2.1 report-quality gates.

## Source And Design

- Design: `docs/superpowers/specs/2026-08-14-third-party-openai-compatibility-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-14-third-party-openai-compatibility.md`
- Migration: `backend/migrations/versions/0012_add_openai_compatibility_modes.py`
- Iteration record: `docs/优化迭代记录.md`, entry `I-210`

Custom OpenAI-compatible providers probe Chat Completions in this order: `json_schema`, `json_object`, then prompt JSON. Responses with prompt JSON is attempted only after a proven Chat endpoint/protocol mismatch. Authentication, permission, invalid model, rate limit, timeout, connection, request-size and 5xx failures do not trigger endpoint fallback.

The verified transport and structured-output modes are stored against the provider, protocol, model and connection revision. Formal report calls use that single verified path; they do not switch endpoints during a report and do not create a second paid request through runtime fallback.

## Test Evidence

Commands were run from `F:\组合品7-31\web-platform-v2.1-work`.

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py -q` | `58 passed, 3 skipped` |
| `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py backend/tests/test_provider_service.py backend/tests/test_model_rotation.py backend/tests/test_worker_jobs.py -q` | `128 passed, 6 skipped` |
| `$env:PYTHONUTF8='1'; .venv\Scripts\python.exe -m pytest -q` | `782 passed, 9 skipped, 1 warning` |
| `npm.cmd --prefix frontend test -- --run` | `251 passed, 7 skipped` |
| `npm.cmd --prefix frontend run build` | production build passed |
| `npm.cmd --prefix frontend run typecheck` | exit `0` |
| `npm.cmd --prefix desktop test -- --run` | `9 passed` |
| `npm.cmd --prefix desktop run typecheck` | exit `0` |
| `npm.cmd --prefix desktop run build` | exit `0` |
| Targeted Ruff check for OpenAI compatibility/provider/migration files | `All checks passed!` |
| `git diff --check` | exit `0`; existing LF/CRLF conversion warnings only |

The final connection regression also proves that a non-standard Chat response can fall back to Responses, a rate-limit response cannot fall back, and a non-standard Responses object is classified as `PROVIDER_PROTOCOL_MISMATCH` while a standard response with empty text remains `PROVIDER_EMPTY_RESPONSE`.

The Python warning is the existing asynchronous connection cleanup warning in a Worker test. Frontend tests retain an existing MSW message for an unmatched provider-settings request. A whole-repository Ruff diagnostic also reports pre-existing style debt outside this release scope; the release gate is the targeted command defined by the implementation plan.

## Build Evidence

Command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows-installer.ps1
```

Result: exit `0` after a complete rebuild of the Python API, Python Worker, Next frontend, packaged Chromium, Electron shell and NSIS installer.

Final artifact:

- Path: `release\组合选品控制台-Setup-0.1.14.exe`
- ProductVersion/FileVersion: `0.1.14`
- Size: `380,574,226` bytes
- SHA-256: `6EE978AA55AF4D992F2B8F0747044A177A8C0009384EA799E3D796815089A1F0`
- Sidecar: `release\组合选品控制台-Setup-0.1.14.exe.sha256`, matching the calculated hash

Previous installers were recalculated after the build and remained unchanged:

- `0.1.12`: `380,530,233` bytes, SHA-256 `D827F52E624F4A2800FDE17BA2C9B696F0284400A3176E9129ED9BD74E506599`
- `0.1.13`: `380,544,116` bytes, SHA-256 `A4F4726ACFC2F47C0E5D79FFD5CB79C42D88D2BA4FB671104C162BA1E9B64D1B`

Electron Builder retained the existing non-blocking metadata warnings for missing description/author and the default Electron icon. PyInstaller retained the existing non-blocking `jinja2`, `pysqlite2` and `MySQLdb` hidden-import warnings.

## Isolated Packaged Smoke

The final `release\win-unpacked\组合选品控制台.exe` was launched under:

`F:\组合品7-31\web-platform-v2.1-work\.package-smoke-0.1.14-final-20260814-032019\员工 #100% 空格`

The isolated `LOCALAPPDATA` and `APPDATA` contained no real user database, provider configuration or API key.

Observed results:

- Owned packaged processes started: `8`
- Packaged API live endpoint: HTTP `200`
- Frontend `/`: HTTP `200`
- Frontend `/history`: HTTP `200`
- Frontend `/settings/api`: HTTP `200`
- Worker revision: `0.1.14`
- Worker model contract: `combination_model_v2.1`
- SQLite Alembic revision: `0012`
- `transport_mode` column: present
- `structured_output_mode` column: present
- Isolated database job count: `0`
- Remaining processes under the exact package path after shutdown: `0`

The existing employee-path acceptance script also passed for Chinese characters, spaces, `#` and `%` and confirmed that runtime data was not written into the simulated read-only installation directory.

The packaged `bundling-api.exe` was additionally started with a separate isolated database and a known temporary desktop session token. Its provider endpoint returned HTTP `200`, three empty provider slots, and no encrypted key, session token or Authorization value. Packaged OpenAPI exposed `transport_mode` and `structured_output_mode` as nullable fields. The standalone packaged API left `0` residual processes.

## Token And Security Boundaries

- Connection testing and model capability verification send short model requests and therefore consume a small number of tokens.
- Unchanged valid configuration is not reverified on a timer. Verification occurs when needed after configuration changes, missing capability, or a failed connection.
- Formal reports do not probe or switch endpoints after verification, avoiding hidden duplicate paid requests.
- No API key, Authorization header, complete prompt or complete model output was written to source, logs or this document.
- No real user database, history job, saved provider configuration, Cookie or API key was read or modified.
- No Git stage, commit, branch, tag, push, reset, checkout or clean operation was performed.

## Residual Risk And Rollback

No real third-party OpenAI-compatible endpoint was called during this verification. Before company-wide deployment, an operator should run model verification and one representative report against each actual gateway/model combination. Those requests can consume tokens.

Rollback is to reinstall `0.1.13` while retaining the existing application data directory. Migration `0012` only adds two nullable columns and does not rewrite history tasks. Back up the desktop database before any manual schema downgrade; no downgrade was performed during this release.
