# 2026-08-02 桌面版 Git 控制台抢焦点修复验证

## 用户现象

中文输入法候选词在连续输入时反复重建，表现为文字组合态被截断。新视频同时显示桌面版与其他窗口切换；Windows 工作区为 1920×1040，任务栏仅占底部 40 像素，视频顶部桌面区域只是窗口未最大化，不是屏幕工作区被应用截断。

## 根因证据

运行中的 `bundling-worker.exe` 每 0.5 秒调用 `write_local_worker_identity()` 写心跳。该函数每次调用 `runtime_revision()`；打包版未设置 `APP_REVISION`，因此每次都会执行：

```text
git rev-parse --short HEAD
```

Windows 焦点采样显示，每约 0.62 秒出现一个新的 `ConsoleWindowClass` 前台窗口，标题为 `C:\Program Files\Git\cmd\git.exe`。多个 Git 进程的父 PID 明确指向 Worker PID 31128。每个窗口出现后约 0.1 秒退出并把焦点还给原窗口，正好会中断中文输入法组合态。

## 因果验证

只停止 Worker、保持 Electron、API 和前端不变后：

- 5 秒内前台焦点转换仅 1 次（初始窗口记录）。
- Git 进程为 0。
- 输入窗口不再周期性失焦。

因此根因是 Worker 心跳反复启动可见 Git 控制台，而不是 Electron 全局键盘钩子、托盘、Windows 工作区或输入法本身。

## 修复

Electron 启动本地服务的共同环境变量新增：

```ts
APP_REVISION: app.getVersion()
```

API、Worker 和前端都直接获得安装版本；`runtime_revision()` 优先返回该值，不再启动 Git。未修改心跳频率、任务队列、供应商调用或分析逻辑。

## TDD 与真整包验证

- RED：新增测试要求 `main.ts` 包含 `APP_REVISION: app.getVersion()`；旧实现 1 项失败、4 项通过。
- GREEN：桌面 5 项测试全部通过。
- TypeScript typecheck 和 build 通过。
- 修复后 `win-unpacked` 真整包启动：7 个目标进程，Worker PID 21260 持续运行。
- 心跳文件的 `revision` 为 `0.1.1`。
- 6 秒焦点采样：只有初始 Chrome 记录，周期性跳转为 0。
- 采样结束时 Git 进程为 0。

## 产物

- 安装器：`F:\组合品7-31\web-platform-v2.1-work\release\组合选品控制台-Setup-0.1.1.exe`
- 大小：380,709,235 字节
- SHA-256：`6E6FD3390545FA36B730381D7ACD9580A2E9E531D271BFC1EA5E8EF226B01145`
- 当前屏幕上运行的是 `release/win-unpacked` 修复版，供用户直接输入验证；已安装目录未被自动覆盖。
