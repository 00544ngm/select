# 桌面版输入焦点与彻底退出修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让桌面版关闭窗口后彻底退出全部本地进程，消除不可见托盘驻留和潜在输入焦点干扰，并发布 0.1.1 修复安装包。

**Architecture:** 保留 Electron 单实例与显式第二实例唤醒，但移除托盘和隐藏窗口路径。普通窗口关闭直接允许，`window-all-closed` 触发应用退出，`before-quit` 统一停止受管子进程。用生命周期单元测试锁定行为，再以真实整包进程树和中文输入检查作为发布门禁。

**Tech Stack:** Electron 37、TypeScript、Vitest、electron-builder、PowerShell、PyInstaller、Next.js standalone。

---

### Task 1：用失败测试锁定关闭行为

**Files:**
- Modify: `desktop/tests/window-options.test.ts`
- Test: `desktop/tests/window-options.test.ts`

- [ ] **Step 1: 把旧的隐藏到托盘断言改成普通关闭允许退出**

```ts
it("allows a normal close so the application can exit", () => {
  expect(handleWindowClose({ quitRequested: false })).toBe("allow-close");
  expect(handleWindowClose({ quitRequested: true })).toBe("allow-close");
});
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm.cmd --prefix desktop test -- --run tests/window-options.test.ts`

Expected: FAIL，旧实现对 `quitRequested: false` 返回 `hide-to-tray`。

### Task 2：删除隐藏托盘并完成退出生命周期

**Files:**
- Modify: `desktop/src/lifecycle/single-instance.ts`
- Modify: `desktop/src/main.ts`
- Test: `desktop/tests/window-options.test.ts`

- [ ] **Step 1: 最小实现普通关闭允许退出**

```ts
export function handleWindowClose(_state: { quitRequested: boolean }) {
  return "allow-close";
}
```

- [ ] **Step 2: 从主进程删除 Tray、Menu、nativeImage、空白图标和 close 阻止逻辑**

主窗口关闭事件不再 `preventDefault()` 或 `hide()`；删除 `createTray()` 调用。保留 `app.on("second-instance", showMainWindow)`，因为它只在用户明确再次启动软件时执行。

- [ ] **Step 3: 最后一个窗口关闭时退出应用**

```ts
app.on("window-all-closed", () => {
  quitRequested = true;
  app.quit();
});
```

- [ ] **Step 4: 运行 GREEN 与类型检查**

Run: `npm.cmd --prefix desktop test -- --run tests/window-options.test.ts`

Expected: 3 tests PASS。

Run: `npm.cmd --prefix desktop run typecheck`

Expected: exit code 0。

### Task 3：提升修复版本并构建发布包

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Generated: `release/组合选品控制台-Setup-0.1.1.exe`

- [ ] **Step 1: 将桌面包版本提升到 0.1.1**

同时修改 `package.json` 和 lockfile 根包版本，不改变依赖版本。

- [ ] **Step 2: 运行桌面完整测试**

Run: `npm.cmd --prefix desktop test -- --run`

Expected: 全部 PASS。

- [ ] **Step 3: 构建 Windows 安装包**

Run: `powershell.exe -ExecutionPolicy Bypass -File scripts/build-windows-installer.ps1`

Expected: 生成 0.1.1 安装器和 SHA-256 文件。

### Task 4：真实整包退出与输入验证

**Files:**
- Create: `docs/verification/2026-08-02-desktop-input-focus-and-exit.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 从 `release/win-unpacked` 启动软件并验证服务**

检查首页、API readiness、Worker 心跳和 SQLite 文件均正常，记录进程树。

- [ ] **Step 2: 关闭主窗口并验证零残留**

关闭窗口后等待有限时间，断言该次启动的 Electron、前端、API 和 Worker PID 均已退出；不以进程名宽泛杀死用户其他程序。

- [ ] **Step 3: 验证输入焦点**

软件运行期间在记事本文本框连续输入英文和中文；关闭软件后再次输入，确认没有周期性失焦或输入法组合态被软件打断。人工输入验证与自动进程验证分别记录。

- [ ] **Step 4: 完成发布记录**

记录测试结果、安装包绝对路径、文件大小、SHA-256、已知边界与回滚方式；不记录 API Key、Cookie 或 Token。
