# Desktop Phase 3 Electron Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Electron 提供单实例窗口、托盘、本地服务监督、会话认证和安全退出，并加载现有 Next.js 界面。

**Architecture:** 新建独立 `desktop` 包；Electron 主进程启动打包后的 FastAPI 与Worker，等待 readiness 后创建 BrowserWindow。preload 只暴露最小桌面状态接口，业务数据继续走现有 HTTP API。

**Tech Stack:** Electron、TypeScript、Vitest、Next.js standalone、FastAPI、Node child_process

---

### Task 1: Electron 包与最小安全窗口

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/tsconfig.json`
- Create: `desktop/vitest.config.ts`
- Create: `desktop/src/main.ts`
- Create: `desktop/src/preload.ts`
- Test: `desktop/tests/window-options.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
expect(buildWindowOptions().webPreferences).toMatchObject({
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
});
```

- [ ] **Step 2: 验证 RED**

```powershell
npm.cmd --prefix desktop test -- --run
```

预期：桌面包或 `buildWindowOptions` 不存在。

- [ ] **Step 3: 实现安全默认值**

```ts
export function buildWindowOptions(): BrowserWindowConstructorOptions {
  return {
    width: 1440,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    show: false,
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  };
}
```

preload 只暴露 `getDesktopStatus()`、`requestQuit()` 和 `openLogDirectory()`；不暴露 shell 或文件系统通用能力。

- [ ] **Step 4: 运行测试与类型检查**

```powershell
npm.cmd --prefix desktop test -- --run
npm.cmd --prefix desktop run typecheck
```

预期：通过。

### Task 2: 单实例与托盘生命周期

**Files:**
- Create: `desktop/src/lifecycle/single-instance.ts`
- Create: `desktop/src/lifecycle/tray.ts`
- Modify: `desktop/src/main.ts`
- Test: `desktop/tests/lifecycle.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
it("hides the window instead of quitting on close", () => {
  const result = handleWindowClose({ quitRequested: false });
  expect(result).toBe("hide-to-tray");
});
```

- [ ] **Step 2: 实现明确状态机**

```ts
export function handleWindowClose(state: { quitRequested: boolean }) {
  return state.quitRequested ? "allow-close" : "hide-to-tray";
}
```

主进程使用 `app.requestSingleInstanceLock()`；`second-instance` 恢复并聚焦现有窗口。托盘菜单固定为“打开主界面、当前任务状态、完全退出”。

- [ ] **Step 3: 验证**

```powershell
npm.cmd --prefix desktop test -- --run
```

预期：单实例、关闭隐藏、托盘恢复和完全退出状态测试通过。

### Task 3: 子进程监督与动态端口

**Files:**
- Create: `desktop/src/services/ports.ts`
- Create: `desktop/src/services/process-supervisor.ts`
- Create: `desktop/src/services/readiness.ts`
- Test: `desktop/tests/process-supervisor.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
it("restarts a crashed worker once and then stops", async () => {
  const supervisor = createTestSupervisor({ restartLimit: 1 });
  await supervisor.recordCrash("worker");
  await supervisor.recordCrash("worker");
  expect(supervisor.restartCount("worker")).toBe(1);
  expect(supervisor.status("worker")).toBe("blocked");
});
```

- [ ] **Step 2: 实现启动契约**

```ts
type ManagedService = "api" | "worker";
type ServiceState = "stopped" | "starting" | "ready" | "failed" | "blocked";

interface ServiceLaunch {
  executable: string;
  args: string[];
  env: Record<string, string>;
  hidden: true;
}
```

API 参数绑定 `127.0.0.1` 和已保留的可用端口；Worker 使用相同 `DATABASE_URL`、数据目录和会话文件。Windows 启动必须隐藏控制台窗口。

- [ ] **Step 3: readiness 后才显示窗口**

轮询 `/api/v1/health/ready`，使用总超时和指数受控间隔；成功后加载页面，失败显示本地诊断窗口，不无限等待。

- [ ] **Step 4: 验证**

```powershell
npm.cmd --prefix desktop test -- --run
```

预期：端口冲突、API超时、Worker一次重启和连续崩溃均有确定状态。

### Task 4: 本地会话认证

**Files:**
- Create: `backend/security/desktop_session.py`
- Modify: `backend/main.py`
- Modify: `backend/config.py`
- Create: `frontend/lib/api/desktop-session.ts`
- Modify: `frontend/lib/api/jobs.ts`
- Modify: `frontend/lib/api/providers.ts`
- Test: `backend/tests/test_desktop_session.py`
- Test: `frontend/tests/desktop-session.test.ts`

- [ ] **Step 1: 写未授权测试**

```python
def test_desktop_api_rejects_missing_session_header(desktop_client):
    response = desktop_client.get("/api/v1/jobs")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "DESKTOP_SESSION_REQUIRED"
```

- [ ] **Step 2: 实现会话中间件**

```python
if settings.runtime_mode == "desktop":
    supplied = request.headers.get("X-Desktop-Session", "")
    if not secrets.compare_digest(supplied, settings.desktop_session_token or ""):
        return JSONResponse(status_code=401, content={"detail": {"code": "DESKTOP_SESSION_REQUIRED", "message": "桌面会话已失效", "retryable": False}})
```

健康 `/live` 可不带凭据；业务 API 和 `/ready` 必须带凭据。Token 每次启动随机生成，只通过子进程环境和 preload 的受限读取路径传递。

- [ ] **Step 3: 前端统一请求头**

所有 API 客户端通过单一 `apiFetch` 注入 `X-Desktop-Session`，Web开发模式不注入。

- [ ] **Step 4: 验证**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_desktop_session.py backend/tests/test_security.py -q
npm.cmd --prefix frontend test -- --run desktop-session
```

预期：缺失/错误凭据拒绝，正确凭据通过，服务端模式不受影响。

### Task 5: Next.js 桌面生产构建

**Files:**
- Modify: `frontend/next.config.ts`
- Create: `frontend/lib/api/config.ts`
- Create: `scripts/build-desktop-frontend.ps1`
- Test: `frontend/tests/api-config.test.ts`

- [ ] **Step 1: 写 API 地址测试**

```ts
expect(resolveApiBase({ desktopPort: 43127 })).toBe("http://127.0.0.1:43127/api/v1");
```

- [ ] **Step 2: 配置 standalone 构建**

```ts
const nextConfig: NextConfig = {
  output: "standalone",
  images: { unoptimized: true },
};
```

桌面启动时通过受限启动配置传入 API 端口；禁止把 API Key 或会话Token写入静态构建文件。

- [ ] **Step 3: 验证前端**

```powershell
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

预期：测试和构建通过，`.next/standalone` 生成。

### Task 6: 安全退出与诊断窗口

**Files:**
- Create: `desktop/src/lifecycle/shutdown.ts`
- Create: `desktop/src/diagnostics/report.ts`
- Create: `desktop/src/diagnostics/window.ts`
- Test: `desktop/tests/shutdown.test.ts`
- Test: `desktop/tests/diagnostics.test.ts`

- [ ] **Step 1: 写脱敏测试**

```ts
expect(redactDiagnostic("api_key=sk-secret Cookie: abc"))
  .toBe("api_key=[REDACTED] Cookie: [REDACTED]");
```

- [ ] **Step 2: 实现退出顺序**

```ts
const SHUTDOWN_ORDER = ["stop-accepting", "request-worker-stop", "wait-worker", "stop-api", "remove-session-file"] as const;
```

有运行任务时显示“缩小到托盘继续运行”与“安全停止并退出”；不提供直接强杀为默认操作。诊断只包含组件、错误类别、版本、时间和脱敏日志尾部。

- [ ] **Step 3: 阶段三全量验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run build
npm.cmd --prefix desktop test -- --run
npm.cmd --prefix desktop run typecheck
git diff --check
```

预期：全部退出码 0。

### Task 7: 阶段三验证报告

**Files:**
- Create: `docs/verification/2026-08-02-desktop-phase-3.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 记录单实例、托盘、进程重启、会话认证、安全退出和前端生产构建证据**

不得记录完整会话Token、API Key、Cookie或模型正文。
