# 模型目录历史排序、搜索与自动验证实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 永久保留模型验证历史，自动验证已选及最近使用模型，并提供搜索、最近使用入口和多种排序方式。

**Architecture:** 通过 0009 迁移为供应商连接和模型记录增加修订号与使用统计；ProviderService 负责当前连接有效性和单模型验证，JobService 在任务成功入队后记录使用；前端使用独立纯函数完成筛选排序，并在设置页按会话去重顺序执行自动验证。

**Tech Stack:** FastAPI、SQLAlchemy/Alembic、SQLite/PostgreSQL、Pydantic、React/Next.js、TanStack Query、Vitest、Pytest、Electron/NSIS。

**Execution constraint:** 用户明确要求当前会话内联执行，不使用子智能体；不执行 Git 提交、分支、合并或清理。

---

### Task 1: 数据库迁移与模型使用字段

**Files:**
- Create: `backend/migrations/versions/0009_add_model_usage_and_connection_revision.py`
- Modify: `backend/db/models.py`
- Modify: `backend/db/provider_repository.py`
- Test: `backend/tests/test_sqlite_migrations.py`
- Test: `backend/tests/test_provider_repository.py`

- [ ] **Step 1: 写迁移与 Repository 红灯测试**

新增测试断言 0009 后 `provider_configurations.validation_revision == 1`，模型记录包含 `connection_revision`、`last_used_at`、`use_count`、`last_auto_tested_at`；并断言 `record_model_usage()` 将次数从 0 增至 1、写入最近使用时间。

- [ ] **Step 2: 运行红灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_provider_repository.py -q`
Expected: FAIL，提示新增列或 `record_model_usage` 不存在。

- [ ] **Step 3: 实现 0009 与 Repository 最小能力**

迁移新增：

```python
op.add_column("provider_configurations", sa.Column("validation_revision", sa.Integer(), nullable=False, server_default="1"))
op.add_column("provider_model_validations", sa.Column("connection_revision", sa.Integer(), nullable=False, server_default="1"))
op.add_column("provider_model_validations", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
op.add_column("provider_model_validations", sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"))
op.add_column("provider_model_validations", sa.Column("last_auto_tested_at", sa.DateTime(timezone=True), nullable=True))
```

Repository 新增 `record_model_usage(provider_slug, api_protocol, model, used_at)`，使用 SQLAlchemy 读取现有记录后递增 `use_count`，并增加 `increment_validation_revision(slug)`。`upsert_model_validation` 接收当前修订号与是否自动验证，更新验证字段但不覆盖使用统计。

- [ ] **Step 4: 运行绿灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_provider_repository.py -q`
Expected: PASS。

### Task 2: 移除 24 小时 TTL 并隔离连接修订号

**Files:**
- Modify: `backend/application/provider_service.py`
- Modify: `backend/api/schemas/providers.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: 写有效性红灯测试**

覆盖三个行为：30 天前成功且修订号相同的已选模型仍可用；修订号不同不可用；连接身份变化递增供应商修订号但不删除历史验证。

- [ ] **Step 2: 运行红灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_providers_api.py -q`
Expected: FAIL，旧代码仍使用 24 小时 cutoff 或删除验证记录。

- [ ] **Step 3: 实现当前连接有效性**

删除 `timedelta(hours=24)` 判断。有效条件改为：

```python
validation.status == "verified"
and validation.is_selected
and validation.connection_revision == record.validation_revision
```

连接身份变化时调用 `increment_validation_revision`，不再 `delete_model_validations`。`ProviderModelOption` 返回 `connection_revision`、`current_connection_revision`、`last_used_at`、`use_count`、`last_auto_tested_at` 和 `is_current_connection`。

- [ ] **Step 4: 运行绿灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_providers_api.py -q`
Expected: PASS。

### Task 3: 任务预检与使用次数记录

**Files:**
- Modify: `backend/application/job_service.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_job_service.py`

- [ ] **Step 1: 写任务联动红灯测试**

断言历史成功模型提交时会执行一次当前模型预检；队列入队成功后调用 `record_model_usage`；预检失败或队列失败时不增加使用次数。

- [ ] **Step 2: 运行红灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_job_service.py -q`
Expected: FAIL，JobService 尚无 `model_used` 回调。

- [ ] **Step 3: 实现提交成功后的使用记录**

JobService 接收：

```python
model_used: Callable[[str, str], Awaitable[None]] | None = None
```

仅在 `queue.enqueue` 成功后调用；ProviderService 暴露 `record_model_usage` 并由依赖注入连接。错误消息移除“超过 24 小时”，改为明确当前连接尚未验证或模型不可用。

- [ ] **Step 4: 运行绿灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_job_service.py backend/tests/test_jobs_api.py -q`
Expected: PASS。

### Task 4: 模型目录筛选与排序纯函数

**Files:**
- Create: `frontend/lib/model-catalog.ts`
- Create: `frontend/tests/model-catalog.test.ts`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/provider-model-status.ts`
- Test: `frontend/tests/provider-model-status.test.ts`

- [ ] **Step 1: 写搜索、最近使用和排序红灯测试**

测试 `filterAndSortModelCatalog(options, { query, filter, sort })`：搜索 `5.6` 大小写不敏感；recent 只取最近 10 个；智能排序为已选、最近使用、最近验证、名称；同分稳定按名称；历史成功不因时间显示过期。

- [ ] **Step 2: 运行红灯**

Run: `npm.cmd --prefix frontend test -- --run tests/model-catalog.test.ts tests/provider-model-status.test.ts`
Expected: FAIL，模块不存在且旧状态仍显示 24 小时过期。

- [ ] **Step 3: 实现纯函数和状态标签**

导出：

```typescript
export type ModelCatalogFilter = "all" | "recent" | "verified";
export type ModelCatalogSort = "smart" | "recent" | "usage" | "verified" | "name";
export function filterAndSortModelCatalog(options: ProviderModelOption[], state: CatalogState): ProviderModelOption[];
```

`providerModelStatusLabel` 对历史成功显示“历史验证通过”，修订号不一致显示“历史验证通过 · 当前连接待验证”，不再计算 24 小时 TTL。

- [ ] **Step 4: 运行绿灯**

Run: `npm.cmd --prefix frontend test -- --run tests/model-catalog.test.ts tests/provider-model-status.test.ts`
Expected: PASS。

### Task 5: API 设置页搜索、快捷筛选、排序与自动验证

**Files:**
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Modify: `frontend/lib/api/providers.ts`
- Modify: `frontend/tests/provider-settings.test.tsx`

- [ ] **Step 1: 写交互红灯测试**

覆盖：搜索 `5.6` 时匹配项直接出现且分页隐藏；“最近使用模型”最多 10 个；排序选择生效；页面加载后只对已选和最近 10 个模型自动验证；同一会话同一模型只请求一次；一个失败不阻断其他模型和页面交互。

- [ ] **Step 2: 运行红灯**

Run: `npm.cmd --prefix frontend test -- --run tests/provider-settings.test.tsx`
Expected: FAIL，工具栏和自动验证调度尚不存在。

- [ ] **Step 3: 实现目录工具栏和会话去重验证**

新增 `modelQuery`、`modelFilter`、`modelSort` 状态和 `autoVerifiedRef: Set<string>`。自动候选使用：

```typescript
const candidates = unique([
  ...options.filter((item) => item.is_selected),
  ...sortByLastUsed(options).slice(0, 10),
]);
```

按顺序调用现有 `verifyProviderModel(slug, model, false)`，每个调用独立捕获错误并局部刷新 Query；搜索结果不切片，普通结果每页 10 个。卡片显示历史验证、自动验证、最近使用和次数。

- [ ] **Step 4: 运行绿灯**

Run: `npm.cmd --prefix frontend test -- --run tests/provider-settings.test.tsx`
Expected: PASS。

### Task 6: 完整回归与数据库升级验收

**Files:**
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 运行后端全量测试与静态检查**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 全部通过，仅允许已记录的非阻断 warning。

Run: `.venv\Scripts\python.exe -m ruff check --select E9,F63,F7,F82 backend app tests`
Expected: PASS。

- [ ] **Step 2: 运行前端与桌面全量测试**

Run: `npm.cmd --prefix frontend test -- --run && npm.cmd --prefix frontend run typecheck && npm.cmd --prefix frontend run build`
Expected: PASS。

Run: `npm.cmd --prefix desktop test -- --run && npm.cmd --prefix desktop run typecheck`
Expected: PASS。

- [ ] **Step 3: 验证升级保留历史数据**

复制工作区内测试数据库，执行 0008 → 0009 升级，断言供应商、验证记录、选择状态和 API Key 密文数量不变，新增字段默认值正确。

- [ ] **Step 4: 检查差异并写迭代记录**

Run: `git diff --check`
Expected: PASS。记录所有红灯、失败、修复、测试数量和迁移验收；不执行 Git 写操作。

### Task 7: 构建并验收新版 Windows 安装包

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Generated: `release/组合选品控制台-Setup-0.1.7.exe`

- [ ] **Step 1: 版本更新为 0.1.7 并完整构建**

使用 `scripts/build-windows-installer.ps1` 重新构建 PyInstaller API、Worker、Next、Chromium、Electron 和 NSIS，不复用旧可执行文件。

- [ ] **Step 2: 独立 LocalAppData 整包冒烟**

启动 `release/win-unpacked/组合选品控制台.exe`，断言数据库迁移至 0009、Worker revision 为 0.1.7、API HTTP 200、前端 Ready、Electron 存活；结束后精确清理测试进程且残留为 0。

- [ ] **Step 3: 安全与完整性验收**

计算 SHA-256 并与 `.sha256` 一致；按 OpenAI 项目密钥和 Maike 密钥格式扫描安装包，命中必须为 0；运行员工中文、空格、`#`、`%` 路径验收。

- [ ] **Step 4: 最终交付**

只有全量测试、迁移、整包冒烟和密钥扫描全部通过后，才向用户提供 0.1.7 `.exe` 安装包路径与校验值。
