# Windows 原生桌面安装版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有本地 Web 软件分阶段改造成多台 Windows 电脑可独立安装、可迁移旧数据、可托盘后台运行的桌面软件。

**Architecture:** Electron 作为桌面宿主，保留 Next.js 与 FastAPI；用 SQLite 替换桌面运行时 PostgreSQL，用 SQLite 持久化单Worker队列替换 Redis/ARQ，并通过 NSIS 交付管理员安装包。五个阶段逐一形成可测试、可回滚的工作软件。

**Tech Stack:** Electron、Electron Builder、NSIS、Next.js 15、FastAPI、SQLAlchemy asyncio、SQLite/aiosqlite、Alembic、Playwright、PyInstaller、Windows DPAPI、Vitest、Pytest

---

## 执行规则

- 每次文件操作前完整读取 `docs/优化迭代记录.md`。
- 每次优化和失败都追加到该中文记录。
- 仅在 `F:\组合品7-31\web-platform-v2.1-work` 内操作。
- 当前工作区有大量未提交用户改动；不得执行 `git add`、commit、reset、checkout 或清理无关文件。每个任务以测试结果和迭代记录作为检查点。
- 不删除或改写旧 PostgreSQL 数据，不重新运行历史任务，不为迁移产生模型 Token。
- 不自动切换供应商或付费模型。

## 阶段顺序

1. [SQLite 数据层与只读迁移](2026-08-02-desktop-phase-1-sqlite-data-migration.md)
2. [SQLite 持久化任务队列](2026-08-02-desktop-phase-2-local-job-queue.md)
3. [Electron 桌面宿主与安全生命周期](2026-08-02-desktop-phase-3-electron-shell.md)
4. [Windows 安装、DPAPI、迁移与恢复](2026-08-02-desktop-phase-4-installer-migration-security.md)
5. [完整验收与发布](2026-08-02-desktop-phase-5-release-acceptance.md)

## 阶段门禁

- 阶段一完成前不得删除 PostgreSQL 或 Redis 依赖。
- 阶段二完成且现有任务 API 全量回归通过后，桌面模式才允许绕过 Redis/ARQ。
- 阶段三完成前不得生成对用户发布的安装包。
- 阶段四必须先进行只读迁移演练，数量与抽查不一致时禁止原子切换。
- 阶段五全部验收通过前不得称为正式安装版。

## 最终验证命令

```powershell
Get-Content -LiteralPath 'docs\优化迭代记录.md' -Raw -Encoding utf8 | Out-Null
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend test -- --run
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
npm.cmd --prefix desktop test -- --run
npm.cmd --prefix desktop run build:win
```

预期：所有测试、类型检查、生产构建和 Windows 安装包构建退出码均为 0；安装机验收报告无阻断项。

