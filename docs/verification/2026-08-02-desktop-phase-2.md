# Windows 桌面版 Phase 2 验证报告

## 结论

桌面模式已具备 SQLite 持久化队列和单 Worker 运行链路，不再依赖 Redis/ARQ。服务端模式保持原行为。

## 验证证据

- 聚焦及任务 API、worker、迁移回归：`83 passed, 1 skipped, 1 warning`。
- 新增/修改文件限定 Ruff：通过。
- `git diff --check`：通过，仅显示工作区既有换行符提示。

## 契约

- 队列 FIFO，条件更新保证同一任务不会被两个 Worker 同时领取。
- 处理器仅允许 `run_analysis_job` 和 `run_cross_review`。
- Worker 单并发；未知函数和处理异常落为失败。
- 软件异常退出后，运行中业务任务标记 `interrupted/APP_INTERRUPTED`，completed 历史不变且不自动重跑。
- 桌面 readiness 输出 `queue` 和 `worker`，不访问或输出 `redis`。
- 队列写入使用 Phase 1 的 `database_write_guard`，满足安全切换前置条件。

## 已知限制

- Worker 心跳通过应用数据目录中的原子 JSON 文件跨进程传递；文件不含业务正文或凭据。
- 运行中任务的主动取消将在 Electron 安全退出流程中按阶段边界完成，不提供默认强杀。
- 既有 readiness 不可用场景仍偶发一条异步连接取消 warning，测试不失败。
