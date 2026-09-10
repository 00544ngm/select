# Desktop Phase 5 Release Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在升级电脑和干净Windows电脑上完成业务、安全、迁移、安装与回滚验收，产出首个可发布安装版。

**Architecture:** 自动化测试负责可重复契约，专用Windows测试机负责安装生命周期和真实Chromium/API流程。发布门禁汇总机器可读结果，任何阻断失败都禁止发布。

**Tech Stack:** Pytest、Vitest、Playwright Test、PowerShell、NSIS、SHA-256

---

### Task 1: 桌面端到端测试夹具

**Files:**
- Create: `desktop/e2e/fixtures/desktop-app.ts`
- Create: `desktop/e2e/lifecycle.spec.ts`
- Create: `desktop/playwright.config.ts`
- Test: `desktop/e2e/lifecycle.spec.ts`

- [ ] **Step 1: 写启动与托盘测试**

```ts
test("closing the main window keeps a running job alive", async ({ desktopApp }) => {
  await desktopApp.submitFixtureJob();
  await desktopApp.closeMainWindow();
  await expect.poll(() => desktopApp.jobStatus()).toBe("running");
  await desktopApp.restoreFromTray();
  await expect(desktopApp.mainWindow()).toBeVisible();
});
```

- [ ] **Step 2: 实现测试夹具**

夹具使用临时 `LOCALAPPDATA`、fake LLM和本地商品fixture，不调用真实付费模型；每个测试后完全退出并确认子进程消失。

- [ ] **Step 3: 运行**

```powershell
npm.cmd --prefix desktop run test:e2e
```

预期：单实例、托盘、完全退出、API崩溃和Worker崩溃场景通过。

### Task 2: 迁移演练与抽查工具

**Files:**
- Create: `scripts/verify-desktop-migration.ps1`
- Create: `backend/desktop/migration/audit.py`
- Test: `backend/tests/test_migration_audit.py`

- [ ] **Step 1: 定义审计输出**

```json
{
  "status": "passed",
  "counts_match": true,
  "sampled_jobs": 10,
  "readable_results": 10,
  "secret_findings": 0
}
```

- [ ] **Step 2: 实现只读抽查**

固定种子从 completed/failed/不同mode各抽样；只比较ID、状态、结构哈希和可读性，不输出完整result payload。

- [ ] **Step 3: 在当前电脑进行只读演练**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-desktop-migration.ps1 -DryRun
```

预期：旧库无写入，候选库和报告写入临时/测试目录；失败不切换正式库。

### Task 3: 安装与覆盖升级矩阵

**Files:**
- Create: `docs/verification/windows-install-matrix.md`
- Create: `scripts/verify-installed-app.ps1`

- [ ] **Step 1: 在干净 Windows 10 x64 测试**

步骤：安装 → 首启 → 提交fixture任务 → 托盘运行 → 完全退出 → 重启 → 卸载默认保留数据 → 重装确认数据仍在。

- [ ] **Step 2: 在干净 Windows 11 x64 测试**

重复相同矩阵，并检查管理员UAC、桌面快捷方式、开始菜单和自定义安装目录。

- [ ] **Step 3: 覆盖升级测试**

安装 N-1 测试版本并生成任务数据，再安装当前版本。断言升级前备份存在、数据库迁移成功、历史可读、API配置密文可解密。

- [ ] **Step 4: 升级失败回滚测试**

使用签名测试故障注入让迁移校验失败，确认旧程序数据和备份保留，新版不进入正常主界面。

### Task 4: 业务全回归与真实联网验收

**Files:**
- Create: `docs/verification/2026-08-02-desktop-business-acceptance.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 自动化全回归**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
npm.cmd --prefix desktop test -- --run
npm.cmd --prefix desktop run test:e2e
```

预期：全部退出码 0。

- [ ] **Step 2: 真实抓取验收**

在用户明确提供的测试商品链接上验证 Walmart抓取和内置Chromium。记录状态、耗时和错误分类，不保存页面Cookie或不必要的完整页面正文。

- [ ] **Step 3: 真实供应商验收**

仅使用用户在软件中已配置并主动选择的供应商/模型各做一次最小连接验证，再执行一项明确测试任务。不得自动切换其他付费模型；记录Token前后差值和任务ID，不记录API Key。

- [ ] **Step 4: 三入口业务验收**

分别验证假设分析、对比审判和搜索/批量入口的提交、进度、结果、历史、任务改名、图片/商品ID、中文依据和交叉评审展示。

### Task 5: 安全与隐私发布门禁

**Files:**
- Create: `scripts/scan-release-secrets.ps1`
- Create: `docs/verification/2026-08-02-desktop-security.md`

- [ ] **Step 1: 扫描发布物与日志**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\scan-release-secrets.ps1 -ReleaseDir .\release
```

扫描 API Key 常见前缀、Authorization、Cookie、会话Token和已知测试密钥；命中任何真实凭据立即阻断发布。

- [ ] **Step 2: 网络边界**

确认 API 只监听 127.0.0.1，局域网地址无法连接；无桌面会话头的本机请求返回401；开发者工具默认关闭。

- [ ] **Step 3: 数据删除边界**

卸载默认保留数据；显式勾选删除时展示范围和不可恢复提示，并只删除已解析验证位于应用用户数据目录内的目标。

### Task 6: 发布材料与最终门禁

**Files:**
- Create: `docs/桌面版安装说明.md`
- Create: `docs/桌面版备份恢复说明.md`
- Create: `docs/verification/2026-08-02-desktop-release.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 生成发布清单**

```text
组合选品控制台-Setup-<version>.exe
组合选品控制台-Setup-<version>.exe.sha256
桌面版安装说明.md
桌面版备份恢复说明.md
版本变更记录.md
```

- [ ] **Step 2: 汇总阻断状态**

只有阶段1至阶段5报告全部 `passed`，Windows 10/11安装矩阵无阻断，密钥扫描0命中，才标记 `release_ready=true`。

- [ ] **Step 3: 最终确认**

```powershell
Get-FileHash .\release\组合选品控制台-Setup-*.exe -Algorithm SHA256
git diff --check
```

预期：哈希与发布文件一致，diff无空白错误。当前共享工作区仍不执行Git提交，除非用户另行授权并解决既有未提交改动。

