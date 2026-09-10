# 2026-08-13 Third-Party Anthropic Compatibility Verification

## Scope

This verification covers custom-provider Anthropic Messages API compatibility for release `0.1.13`. It does not change OpenAI/DeepSeek transport, database schema, history records, scraper behavior, model candidate ordering, or V2.1 report-quality gates.

## Source And Plan

- Design: `docs/superpowers/specs/2026-08-13-third-party-anthropic-compatibility-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-13-third-party-anthropic-compatibility.md`
- Iteration record: `docs/优化迭代记录.md`, latest entry `I-207`
- Reference implementation reviewed: `D:\参考代码\anthropic_chat.py`, `README.md`, `requirements.txt`

## Test Evidence

Commands were run from `F:\组合品7-31\web-platform-v2.1-work`.

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | `753 passed, 9 skipped, 2 warnings` |
| `npm.cmd --prefix frontend test -- --run` | `247 passed, 7 skipped` |
| `npm.cmd --prefix frontend run typecheck` | exit `0` |
| `npm.cmd --prefix desktop test -- --run` | `9 passed` |
| `npm.cmd --prefix desktop run typecheck` | exit `0` |
| `.venv\Scripts\python.exe -m ruff check ... --select F,I` (target Anthropic/provider/rotation files) | `All checks passed!` |
| `git diff --check` | exit `0`; only existing LF/CRLF conversion warnings were printed by Git |

Focused TDD evidence:

- Endpoint normalization RED: `9 failed, 25 deselected`; GREEN: `9 passed`.
- Anthropic stable error mapping RED: `13 failed`; GREEN: `13 passed`.
- Provider/domain hardcoding regression RED: `11 failed, 2 passed`; GREEN: `13 passed` and core Anthropic/provider/service regression `85 passed, 6 skipped`.
- Worker/rotation regression: `49 passed`.
- Frontend guidance RED: `12 failed`; GREEN: `34 passed, 5 skipped`.
- Anthropic adapter final focused regression: `24 passed`.

The two Python warnings are pre-existing asynchronous connection cleanup warnings in readiness/worker tests. Frontend tests retain an existing MSW informational message for an unhandled provider settings request; neither warning changed the exit code.

## Build Evidence

Command:

```powershell
.\scripts\build-windows-installer.ps1
```

Result: exit code `0`; Next production build, PyInstaller API/Worker builds, Chromium packaging, Electron TypeScript build, and NSIS installer build all completed.

New artifact:

- Path: `release\组合选品控制台-Setup-0.1.13.exe`
- ProductVersion/FileVersion: `0.1.13`
- Size: `380,544,116` bytes
- SHA-256: `A4F4726ACFC2F47C0E5D79FFD5CB79C42D88D2BA4FB671104C162BA1E9B64D1B`
- Sidecar: `release\组合选品控制台-Setup-0.1.13.exe.sha256`

Previous artifact preservation check, recorded before and after the build:

- Path: `release\组合选品控制台-Setup-0.1.12.exe`
- Size: `380,530,233` bytes
- SHA-256 before and after: `D827F52E624F4A2800FDE17BA2C9B696F0284400A3176E9129ED9BD74E506599`
- The `0.1.12` installer was not overwritten.

Electron Builder emitted non-blocking metadata warnings that description/author are absent from `desktop/package.json`, and used the default Electron icon. These are unrelated to Anthropic transport and did not prevent a valid installer from being produced.

## Isolated Packaged Smoke Test

The unpacked executable `release\win-unpacked\组合选品控制台.exe` was launched with a new temporary `LOCALAPPDATA` and `APPDATA` under `.package-smoke-0.1.13-final-*`. No real user database or API key was used.

Observed results:

- Worker heartbeat revision: `0.1.13`
- Worker model contract: `combination_model_v2.1`
- SQLite Alembic revision: `0011`
- Frontend `/`: HTTP `200`
- Frontend `/history`: HTTP `200`
- Frontend `/settings/api`: HTTP `200`
- Database job count: `0`
- Root Electron process and its child processes were terminated by PID tree after verification; no process from this smoke test remained.

## Security And Data Boundaries

- API keys, authorization headers, complete prompts, and complete model output are not written to the new adapter errors or verification document.
- No database migration was added for this feature.
- No real user database, history task, API key, Cookie, or token was modified.
- No Git commit, branch, tag, push, reset, checkout, clean, or other Git write operation was performed.

## Residual Risk

The verification uses mocked SDK responses for status/error mapping. A real third-party endpoint still needs one operator-controlled model verification and, ideally, one representative report run before production use. That real verification request is intentionally short but can consume a small number of tokens, as shown in the settings UI.
