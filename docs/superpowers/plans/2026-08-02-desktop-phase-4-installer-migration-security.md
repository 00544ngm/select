# Desktop Phase 4 Installer Migration Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打包独立 Python/Chromium运行环境，使用 DPAPI 保护API Key，交付可备份、迁移、覆盖升级和默认保留数据的 NSIS 安装包。

**Architecture:** PyInstaller 生成 API 与 Worker 可执行文件；Electron Builder/NSIS 打包桌面资源。首次启动迁移由独立迁移协调器完成，候选数据库校验通过后原子切换。

**Tech Stack:** PyInstaller、Electron Builder、NSIS、Windows DPAPI、Playwright Chromium、SQLite

---

### Task 1: DPAPI 凭据实现与旧Fernet迁移

**Files:**
- Create: `backend/security/credential_store.py`
- Create: `backend/security/windows_dpapi.py`
- Modify: `backend/security/provider_crypto.py`
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_windows_dpapi.py`
- Test: `backend/tests/test_provider_crypto_migration.py`

- [ ] **Step 1: 写失败测试**

```python
def test_dpapi_ciphertext_does_not_contain_plaintext(dpapi):
    encrypted = dpapi.encrypt("sk-sensitive")
    assert "sk-sensitive" not in encrypted
    assert dpapi.decrypt(encrypted) == "sk-sensitive"
```

- [ ] **Step 2: 定义可替换协议**

```python
class CredentialStore(Protocol):
    def encrypt(self, value: str) -> str: ...
    def decrypt(self, value: str) -> str: ...
```

Windows实现调用 `CryptProtectData/CryptUnprotectData`，加入固定应用熵；非Windows测试使用显式 fake，不静默退回明文。

- [ ] **Step 3: 迁移旧密钥**

```python
plain = legacy_crypto.decrypt(row.encrypted_api_key)
row.encrypted_api_key = dpapi_store.encrypt(plain)
await session.commit()
```

仅在本机迁移进程内短暂持有明文；失败时回滚整批供应商配置，不覆盖旧密文。

- [ ] **Step 4: 验证**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_windows_dpapi.py backend/tests/test_provider_crypto_migration.py backend/tests/test_provider_service.py -q
```

预期：加解密、错误用户、损坏密文和旧Fernet回滚测试通过。

### Task 2: 独立 Python 可执行文件

**Files:**
- Create: `packaging/api.spec`
- Create: `packaging/worker.spec`
- Create: `backend/desktop/api_entry.py`
- Create: `backend/desktop/worker_entry.py`
- Create: `scripts/build-python-runtime.ps1`
- Test: `backend/tests/test_packaged_entrypoints.py`

- [ ] **Step 1: 写入口参数测试**

```python
def test_api_entry_binds_loopback_only():
    args = build_uvicorn_args(port=43127)
    assert args == {"host": "127.0.0.1", "port": 43127, "app": "backend.main:app"}
```

- [ ] **Step 2: 实现显式入口**

```python
def main() -> None:
    port = int(os.environ["DESKTOP_API_PORT"])
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_config=None)
```

Worker入口验证 `RUNTIME_MODE=desktop` 后运行本地Worker；任何缺失配置用中文错误和非零退出码终止。

- [ ] **Step 3: 构建**

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean packaging\api.spec
.\.venv\Scripts\python.exe -m PyInstaller --clean packaging\worker.spec
```

预期：`dist/api/bundling-api.exe` 与 `dist/worker/bundling-worker.exe` 生成。

- [ ] **Step 4: 启动冒烟**

使用临时数据目录、临时端口和无外部API配置启动可执行文件；`/live` 返回 200，进程可被安全关闭。

### Task 3: 固定 Playwright Chromium 资源

**Files:**
- Create: `backend/desktop/browser_paths.py`
- Modify: `app/infrastructure/browser/__init__.py`
- Modify: `app/infrastructure/walmart/scraper.py`
- Modify: `app/infrastructure/amazon/scraper.py`
- Create: `scripts/install-packaged-browser.ps1`
- Test: `backend/tests/test_packaged_browser_path.py`

- [ ] **Step 1: 写路径测试**

```python
def test_packaged_browser_path_is_inside_resources(tmp_path):
    path = resolve_browser_executable(resource_dir=tmp_path)
    assert path.is_relative_to(tmp_path)
    assert path.name.lower() in {"chrome.exe", "chromium.exe"}
```

- [ ] **Step 2: 实现资源路径优先**

桌面模式必须使用 `DESKTOP_RESOURCE_DIR` 下固定浏览器；缺失时抛出 `PACKAGED_BROWSER_MISSING`，不在线下载、不借用用户Chrome。

- [ ] **Step 3: 验证无网络启动**

断开网络时浏览器进程仍能启动并打开本地测试页；真实商品抓取留到阶段五联网验收。

### Task 4: 备份保留与恢复

**Files:**
- Modify: `backend/desktop/backup.py`
- Create: `backend/api/routes/desktop.py`
- Modify: `backend/api/router.py`
- Test: `backend/tests/test_desktop_backup_api.py`

- [ ] **Step 1: 写保留策略测试**

```python
def test_backup_retention_keeps_five_newest(tmp_path):
    paths = create_six_backups(tmp_path)
    prune_backups(tmp_path, keep=5)
    assert sorted(tmp_path.glob("*.db")) == paths[-5:]
```

- [ ] **Step 2: 实现安全备份**

SQLite使用在线 backup API 或在停止写入后复制，并生成 SHA-256 清单。恢复前先备份当前库；校验和失败时拒绝恢复。

- [ ] **Step 3: API 边界**

`POST /desktop/backups` 创建备份，`POST /desktop/backups/{id}/restore` 仅桌面会话可用；响应不返回任意文件路径，只返回受控ID、时间和大小。

- [ ] **Step 4: 验证**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_backup.py backend/tests/test_desktop_backup_api.py -q
```

预期：创建、五份保留、损坏拒绝、恢复前保护备份通过。

### Task 5: 设置页备份与恢复入口

**Files:**
- Create: `frontend/components/settings/desktop-data-panel.tsx`
- Create: `frontend/lib/api/desktop.ts`
- Modify: `frontend/app/settings/api/page.tsx`
- Test: `frontend/tests/desktop-data-panel.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
render(<DesktopDataPanel />, { wrapper: Wrapper });
expect(screen.getByRole("button", { name: "立即备份" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "从备份恢复" })).toBeInTheDocument();
```

- [ ] **Step 2: 实现受控 API 客户端**

```ts
export async function createDesktopBackup(): Promise<DesktopBackup> {
  return apiFetch("/desktop/backups", { method: "POST" });
}

export async function restoreDesktopBackup(id: string): Promise<void> {
  await apiFetch(`/desktop/backups/${encodeURIComponent(id)}/restore`, { method: "POST" });
}
```

- [ ] **Step 3: 实现明确交互**

“立即备份”显示时间、大小和成功状态。“从备份恢复”先展示备份列表，用户选择一项后再次确认；确认文案明确说明软件将安全重启，恢复前会先保护当前数据。Web开发/服务端模式不显示桌面数据面板。

- [ ] **Step 4: 验证**

```powershell
npm.cmd --prefix frontend test -- --run desktop-data-panel
npm.cmd --prefix frontend run typecheck
```

预期：桌面模式显示并可操作；取消确认不发请求；恢复失败显示中文错误且不丢失选择。

### Task 6: 首次迁移协调器

**Files:**
- Create: `desktop/src/migration/coordinator.ts`
- Create: `desktop/src/migration/progress-window.ts`
- Modify: `desktop/src/main.ts`
- Test: `desktop/tests/migration-coordinator.test.ts`

- [ ] **Step 1: 写状态机测试**

```ts
expect(nextMigrationState("validated")).toBe("promoting");
expect(() => nextMigrationState("validation-failed")).toThrow("MIGRATION_BLOCKED");
```

- [ ] **Step 2: 实现状态机**

```ts
type MigrationState = "detecting" | "backing-up" | "exporting" | "importing" | "validating" | "promoting" | "completed" | "failed";
```

迁移子进程通过 JSON Lines 只上报阶段、百分比、脱敏错误和计数；不输出密钥、完整请求或模型正文。

- [ ] **Step 3: 失败回滚测试**

模拟导出失败、计数不一致、密钥重加密失败和磁盘替换失败，断言旧库未修改且桌面程序不进入正常主界面。

### Task 7: Electron Builder 与 NSIS

**Files:**
- Modify: `desktop/package.json`
- Create: `desktop/electron-builder.yml`
- Create: `packaging/nsis/installer.nsh`
- Create: `scripts/build-windows-installer.ps1`
- Test: `desktop/tests/builder-config.test.ts`

- [ ] **Step 1: 写配置测试**

```ts
expect(config.win.target).toContainEqual(expect.objectContaining({ target: "nsis", arch: ["x64"] }));
expect(config.nsis.perMachine).toBe(true);
expect(config.nsis.deleteAppDataOnUninstall).toBe(false);
```

- [ ] **Step 2: 配置安装包**

```yaml
appId: com.company.bundling-console
productName: 组合选品控制台
win:
  target:
    - target: nsis
      arch: [x64]
nsis:
  perMachine: true
  oneClick: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  deleteAppDataOnUninstall: false
```

`extraResources` 明确列出 API、Worker、Chromium、Next.js资源和迁移工具。

自定义 NSIS 卸载页增加默认未勾选的“同时删除个人数据”。只有用户主动勾选后，卸载器才调用受控清理程序；清理程序必须先解析并验证目标位于 `%LOCALAPPDATA%\组合选品控制台` 内，禁止接收任意路径。

- [ ] **Step 3: 构建安装包**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-windows-installer.ps1
```

预期：`release/组合选品控制台-Setup-<version>.exe` 和 SHA-256 文件生成。

### Task 8: 阶段四验证报告

**Files:**
- Create: `docs/verification/2026-08-02-desktop-phase-4.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 记录 DPAPI、独立可执行文件、固定Chromium、备份恢复、迁移回滚和安装包哈希证据**

不得记录任何明文密钥；安装/卸载属于有状态操作，只能在专用测试机或明确临时环境执行。
