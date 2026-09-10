# 历史任务持久化与模型轮换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 0.1.8 中让所有任务可靠出现在历史页，并提供可选、可审计、只对技术失败生效的模型轮换，同时保持 V2.1 结果质量契约。

**Architecture:** 保留 `AnalysisJob` 作为一条用户任务的根实体，在任务创建事务中保存不可变的模型/轮换快照；新增 `JobModelAttempt` 保存每次实际模型调用的阶段、耗时和规范化错误。单模型业务流程继续由 `AnalysisRunner` 执行，新增任务级编排器只负责候选选择、技术失败判定和最终一次产物提交。历史 API/UI 先修复 `interrupted` 序列化，再扩展尝试审计和错误态。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy async、Alembic、SQLite/PostgreSQL JSON、现有本地 Worker 队列、Next.js/React、TanStack Query、Vitest、pytest、Ruff、TypeScript、Electron/NSIS 打包。

---

## 执行约束

- 当前工作区包含大量用户和前序任务的未提交改动；所有步骤只触碰列出的文件，不执行 reset、clean、checkout、commit、branch、merge 或 push。
- Python 使用 `.venv\\Scripts\\python.exe`；前端命令从 `frontend` 目录运行。Next 构建必须在停止 dev 服务后串行执行。
- 每个生产代码步骤前先写并运行对应 RED 测试；每个任务结束运行该任务的聚焦测试和 `git diff --check`。
- 不把真实 API Key、模型原文、请求头、上游响应体或本机数据路径写入测试、日志、文档或输出。
- 迁移、历史数据和安装包验证使用临时目录或独立 LocalAppData，不触碰用户数据库 `C:\Users\\Administrator\\AppData\\Local\\组合选品控制台\\data\\bundling.db`。

## 文件地图

后端状态和数据：

- Modify: `backend/api/schemas/jobs.py`，扩展 `JobStatus`、任务创建请求和摘要/详情返回类型。
- Modify: `backend/db/models.py`，增加 `JobModelAttempt` 和任务轮换字段映射。
- Create: `backend/migrations/versions/0010_add_job_model_attempts_and_rotation.py`，只新增 0010 表/索引并保留 0001–0009 数据。
- Modify: `backend/db/repositories.py`，任务快照写入、尝试 CRUD、状态转换和分页读取。
- Modify: `backend/api/routes/jobs.py`，历史列表/详情/重试/尝试审计响应。
- Modify: `backend/application/job_service.py`，提交前校验轮换快照和中断重试。
- Modify: `backend/application/job_recovery.py`，恢复任务和正在运行的模型尝试。

后端运行和模型准入：

- Create: `backend/application/model_rotation.py`，候选快照、技术失败分类、一次尝试编排和终态判定。
- Modify: `backend/workers/jobs.py`，以任务编排器替换单模型调用路径并保存尝试审计。
- Modify: `backend/application/provider_clients.py`，模型级超时/结构化响应能力和稳定错误分类。
- Modify: `backend/application/result_quality.py`，公开“业务完成但无候选”与质量失败的区分，不放宽既有门禁。
- Modify: `backend/application/provider_service.py`、`backend/db/provider_repository.py`，增加代表性完整报告验证状态和连接修订号准入。
- Modify: `backend/api/routes/providers.py`、`backend/api/schemas/providers.py`，公开完整报告验证字段/操作。

前端：

- Modify: `frontend/lib/api/types.ts`、`frontend/lib/api/jobs.ts`、`frontend/lib/api/client.ts`，同步状态、轮换和尝试 API 类型。
- Modify: `frontend/app/history/page.tsx`、`frontend/components/history/job-table.tsx`，显示 `interrupted`、查询错误、重试和尝试摘要。
- Create: `frontend/components/history/job-attempt-timeline.tsx`，可访问的尝试时间线。
- Modify: `frontend/components/workbench/model-select.tsx`、`frontend/components/workbench/hypothesis-form.tsx`、`frontend/components/workbench/judgment-form.tsx`、`frontend/components/workbench/batch-form.tsx`，加入轮换开关和候选排序快照。

测试与记录：

- Modify/Create: `backend/tests/test_jobs_api.py`、`backend/tests/test_job_repository.py`、`backend/tests/test_job_recovery.py`、`backend/tests/test_model_rotation.py`、`backend/tests/test_worker_jobs.py`、`backend/tests/test_sqlite_migrations.py`、`backend/tests/test_provider_service.py`、`backend/tests/test_providers_api.py`。
- Modify/Create: `frontend/tests/batch-history.test.tsx`、`frontend/tests/job-detail.test.tsx`、`frontend/tests/job-forms.test.tsx`、`frontend/tests/model-select.test.tsx`、`frontend/tests/jobs-api-client.test.ts`、`frontend/tests/history-error.test.tsx`。
- Modify: `docs/优化迭代记录.md`，每个 RED/GREEN、失败原因、验证和安全边界追加记录；不重写旧条目。

### Task 1: 固化 `interrupted` 历史契约并暴露真实查询错误

**Files:**
- Modify: `backend/api/schemas/jobs.py`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/app/history/page.tsx`
- Modify: `frontend/components/history/job-table.tsx`
- Test: `backend/tests/test_jobs_api.py`
- Test: `frontend/tests/history-error.test.tsx`

- [ ] **Step 1: 写后端 RED 测试**

在 `backend/tests/test_jobs_api.py` 增加混合状态夹具，创建一个 `completed`、一个 `failed`、一个 `interrupted` 任务，调用 `GET /api/v1/jobs` 和 `GET /api/v1/jobs/{id}`，断言状态原样返回且 HTTP 200：

```python
def test_list_jobs_serializes_interrupted_job(client, job_factory):
    completed = job_factory(status="completed")
    failed = job_factory(status="failed")
    interrupted = job_factory(status="interrupted", error_code="APP_INTERRUPTED")

    response = client.get("/api/v1/jobs?page=1&page_size=20")

    assert response.status_code == 200
    assert {item["status"] for item in response.json()["items"]} == {
        "completed", "failed", "interrupted"
    }
    detail = client.get(f"/api/v1/jobs/{interrupted.id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "interrupted"
```

- [ ] **Step 2: 运行 RED**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_jobs_api.py -k interrupted -q`

预期：失败于 `JobStatus` literal validation，当前 History API 返回 500。

- [ ] **Step 3: 写前端 RED 测试**

在 `frontend/tests/history-error.test.tsx` 覆盖两条路径：`listJobs` reject 时渲染“历史加载失败”和可点击的重新加载按钮；`interrupted` 行显示“已中断”和重新提交按钮。

- [ ] **Step 4: 实现最小契约修复**

将后端 `JobStatus` 改为 `Literal["queued", "running", "completed", "failed", "interrupted"]`；前端 `JobStatus` 和 `statusLabels` 同步。History `useQuery` 读取 `isError/refetch`，错误时不渲染 `data?.items ?? []`；表格把 `interrupted` 视为非完成状态，显示“已中断”，并允许调用现有 retry API。`MatchTime` 对中断显示结束时间，不显示仍在运行。

- [ ] **Step 5: 运行 GREEN 与差异检查**

运行：

```powershell
\.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py -k interrupted -q
cd frontend; npm.cmd test -- --run tests/history-error.test.tsx; npm.cmd run typecheck; cd ..
git diff --check -- backend/api/schemas/jobs.py frontend/app/history/page.tsx frontend/components/history/job-table.tsx
```

预期：新增测试通过，前端错误不再伪装为空历史。

### Task 2: 新增 0010 迁移与模型尝试实体

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/migrations/versions/0010_add_job_model_attempts_and_rotation.py`
- Modify: `backend/db/repositories.py`
- Test: `backend/tests/test_sqlite_migrations.py`
- Test: `backend/tests/test_job_repository.py`

- [ ] **Step 1: 写迁移 RED 测试**

增加空库全迁移和 0009 数据升级测试，断言 `job_model_attempts` 存在、唯一键 `(job_id, ordinal)` 生效，已有 `analysis_jobs` 和 `provider_model_validations` 行数不变。

```python
def test_0010_preserves_existing_jobs_and_creates_attempt_table(database):
    upgrade_to(database, "0009")
    job_id = insert_job(database, status="interrupted")
    upgrade_to(database, "0010")

    assert table_exists(database, "job_model_attempts")
    assert count_rows(database, "analysis_jobs") == 1
    assert fetch_job(database, job_id)["status"] == "interrupted"
```

Repository RED 测试先调用尚不存在的 `create_attempt`, `finish_attempt` 和 `list_attempts`。

- [ ] **Step 2: 运行 RED**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_job_repository.py -k "0010 or attempt" -q`

预期：缺少迁移表/ORM 类和 Repository 方法。

- [ ] **Step 3: 实现 ORM 与迁移**

在 `backend/db/models.py` 增加 `JobModelAttempt`，字段为 `id/job_id/ordinal/provider/api_protocol/model/status/stage/error_code/error_message/started_at/finished_at/duration_ms/created_at/updated_at`；`job_id` 使用 `ForeignKey("analysis_jobs.id", ondelete="CASCADE")`，`ordinal` 建唯一约束。迁移 down_revision 指向 0009，只新增表和索引，SQLite 使用项目已有 batch-alter/类型模式。

在 `AnalysisJob.request_payload` 中保留 JSON 快照，不为旧任务添加必填列；摘要字段从快照/尝试回退计算。

- [ ] **Step 4: 实现 Repository 封装**

新增：`create_attempt(job_id, ordinal, provider, api_protocol, model) -> JobModelAttempt`、`finish_attempt(attempt_id, status, stage, error_code, error_message, finished_at) -> JobModelAttempt | None`、`list_attempts(job_id) -> list[JobModelAttempt]`，每次写入提交并刷新；`duration_ms` 从 UTC 开始/结束计算，错误消息由调用方传入规范化文本。

- [ ] **Step 5: 运行 GREEN 与迁移回归**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_sqlite_migrations.py backend/tests/test_job_repository.py -k "0010 or attempt" -q`。

预期：迁移、唯一键、级联删除、尝试写入和耗时计算通过；随后运行 `.venv\\Scripts\\python.exe -m ruff check backend/db/models.py backend/db/repositories.py backend/migrations/versions/0010_add_job_model_attempts_and_rotation.py`。

### Task 3: 任务快照、提交校验和中断恢复

**Files:**
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/application/job_service.py`
- Modify: `backend/application/job_recovery.py`
- Modify: `backend/db/repositories.py`
- Test: `backend/tests/test_job_service.py`
- Test: `backend/tests/test_job_recovery.py`

- [ ] **Step 1: 写提交与恢复 RED 测试**

覆盖轮换关闭只保存一个 requested model；轮换开启保留有序 `rotation_candidates`；候选重复/未完整验证返回 422；队列入队失败仍保留 `failed` 历史行；running 任务及 running attempt 恢复为 `interrupted`/`failed(APP_INTERRUPTED)`；`retry` 接受 interrupted。

```python
async def test_submit_persists_rotation_snapshot_before_enqueue(service, repository, queue):
    queue.enqueue = AsyncMock()
    job = await service.submit_hypothesis(
        HypothesisJobCreate(
            url="https://www.walmart.com/ip/123",
            model="gpt-5.4",
            rotation_enabled=True,
            rotation_candidates=[{"provider": "openai", "model": "gpt-5.4"}],
        )
    )
    payload = repository.created[0].request_payload
    assert payload["rotation_enabled"] is True
    assert payload["rotation_candidates"][0]["model"] == "gpt-5.4"
```

- [ ] **Step 2: 运行 RED**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_job_service.py backend/tests/test_job_recovery.py -k "rotation or interrupted" -q`

预期：请求 schema 不接受字段，恢复器不处理尝试，retry 拒绝 interrupted。

- [ ] **Step 3: 扩展请求 schema 与快照**

定义 `RotationCandidate(provider, model, api_protocol, connection_revision)` 和请求公共字段 `rotation_enabled: bool = False`、`rotation_candidates: list[RotationCandidate] | None`。`JobService._submit` 在创建前规范化 provider/model、去重、检查当前连接修订号和 `full_report_verified`；关闭时强制候选为请求模型，开启时保留用户顺序并拒绝空列表/失效模型。写入 `rotation_snapshot_version=1`、`requested_model` 和候选列表后再调用 Repository create。

- [ ] **Step 4: 扩展恢复与重试**

恢复器在同一事务中把 `AnalysisJob.status == "running"` 更新为 `interrupted`，把该任务的 `JobModelAttempt.status == "running"` 更新为 `failed`、stage=`recovery`、error_code=`APP_INTERRUPTED`；`JobService.retry` 的允许集合改为 `{failed, interrupted}`，复制原请求快照创建新任务。

- [ ] **Step 5: 运行 GREEN**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_job_service.py backend/tests/test_job_recovery.py -k "rotation or interrupted" -q`，再运行现有 `backend/tests/test_job_service.py backend/tests/test_job_recovery.py` 全文件。

### Task 4: 稳定技术失败分类与单次模型尝试编排

**Files:**
- Create: `backend/application/model_rotation.py`
- Modify: `backend/workers/jobs.py`
- Modify: `backend/application/provider_clients.py`
- Modify: `backend/application/result_quality.py`
- Test: `backend/tests/test_model_rotation.py`
- Test: `backend/tests/test_worker_jobs.py`

- [ ] **Step 1: 写分类器与编排 RED 测试**

新增参数化测试覆盖 timeout、429、502/503、空响应、截断 JSON、非法 JSON、schema 错误、质量错误都返回 `retryable=True`；认证、模型不存在、抓取失败、食品阻断、用户取消返回 `retryable=False`。编排测试用三个 fake LLM，断言关闭时只调用第一个，开启时第一个技术失败才调用第二个，业务有效无方向结果不调用第二个，每个模型只调用一次。

```python
@pytest.mark.parametrize("error, code", [
    (TimeoutError(), "MODEL_TIMEOUT"),
    (UpstreamRateLimitError(), "MODEL_RATE_LIMITED"),
    (InvalidJsonError(), "MODEL_INVALID_JSON"),
])
def test_classify_technical_failure(error, code):
    failure = classify_rotation_failure(error, stage="request")
    assert failure.retryable is True
    assert failure.code == code
```

- [ ] **Step 2: 运行 RED**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_model_rotation.py backend/tests/test_worker_jobs.py -k "rotation or classify" -q`。

预期：模块/分类器不存在，或现有 Worker 在第一种异常后直接失败。

- [ ] **Step 3: 实现稳定错误类型与分类**

在 `model_rotation.py` 定义 `RotationCandidate`、`AttemptFailure(code, stage, message, retryable)`、`RotationOutcome` 和 `classify_rotation_failure(exc, stage)`。分类只依据异常类型、HTTP 状态和解析/质量错误类型；对外消息使用固定中文/英文稳定文案，不使用 `str(exc)`。技术失败码固定为 `MODEL_TIMEOUT`、`MODEL_RATE_LIMITED`、`MODEL_UPSTREAM_UNAVAILABLE`、`MODEL_EMPTY_RESPONSE`、`MODEL_INVALID_JSON`、`MODEL_SCHEMA_INVALID`、`MODEL_RESULT_QUALITY_INVALID`。

- [ ] **Step 4: 实现一次尝试循环**

实现 `run_with_rotation(job, candidates, run_one)`：按快照顺序创建 attempt，调用 `run_one(candidate)` 一次；成功必须已完成 JSON 解析、V2.1 schema 和 result quality，立即返回 `successful_model`；`completed_no_qualified_candidates` 与 `completed_needs_evidence` 作为成功；仅 `retryable=True` 且仍有候选时继续。所有候选技术失败后抛出聚合 `MODEL_ROTATION_EXHAUSTED`，不生成 Artifact。

- [ ] **Step 5: 接入 Worker 并保存审计**

在 `backend/workers/jobs.py` 保留现有抓取/业务 Runner，围绕单模型 `AnalysisRunner` 调用接入编排器。每次候选开始写 attempt，结束写 succeeded/failed、stage、规范化码、耗时；任务成功只在循环返回后调用现有 complete/export 一次。产物写失败使用 `ARTIFACT_PERSIST_FAILED`，不再轮换。

- [ ] **Step 6: 运行 GREEN 与后端回归**

运行：

```powershell
\.venv\Scripts\python.exe -m pytest backend/tests/test_model_rotation.py backend/tests/test_worker_jobs.py -q
\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_quality.py backend/tests/test_worker_jobs.py -q
```

预期：技术失败轮换、业务成功不轮换、审计完整且单次请求测试通过。

### Task 5: 代表性完整报告模型准入与模型级配置

**Files:**
- Modify: `backend/db/models.py`
- Modify: `backend/db/provider_repository.py`
- Modify: `backend/application/provider_service.py`
- Modify: `backend/application/provider_clients.py`
- Modify: `backend/api/schemas/providers.py`
- Modify: `backend/api/routes/providers.py`
- Test: `backend/tests/test_provider_service.py`
- Test: `backend/tests/test_provider_repository.py`
- Test: `backend/tests/test_providers_api.py`

- [ ] **Step 1: 写完整报告准入 RED 测试**

为 lightweight probe 通过但完整报告 schema 失败的模型增加反例：该模型不能加入轮换；完整报告通过 schema、质量门且连接修订号一致时才能加入；连接修订号变化后旧记录仍保留但 `is_rotation_eligible=False`。增加超时配置测试，断言 5.5 版本化型号使用长上限，其他模型使用对应配置。

- [ ] **Step 2: 运行 RED**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_provider_repository.py backend/tests/test_providers_api.py -k "full_report or rotation_eligible or timeout" -q`。

预期：当前只有轻量验证状态，缺少代表性报告准入和模型级配置。

- [ ] **Step 3: 增加验证字段与准入函数**

在既有 `ProviderModelValidation` 上增加 `validation_kind`（`probe`/`full_report`）、`schema_version`、`quality_status`、`duration_ms`；Repository 提供 `record_full_report_validation` 和 `is_full_report_verified(provider, protocol, model, revision)`。Service 只把同 revision、`validation_kind=full_report`、status=`success`、quality=`passed` 的记录返回为候选。

- [ ] **Step 4: 接入代表性验证路径**

新增显式服务方法，使用现有 Provider client 和 `AnalysisRunner` 的相同解析/schema/quality 流程，但只使用合成输入且不创建用户历史任务。成功写验证记录，失败写规范化码；不自动重试、不写原始模型输出。API 暴露验证结果和触发入口，保留既有 lightweight probe 行为。

- [ ] **Step 5: 实现模型级运行配置**

新增纯函数 `report_timeout_seconds(model, protocol)` 和 `supports_structured_report(model, protocol)`；配置默认来自已验证证据，5.5 及版本化后缀采用现有 600 秒策略，5.4/其他模型继续既有上限。调用方只读取配置，不在异常后重复请求。

- [ ] **Step 6: 运行 GREEN**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_provider_service.py backend/tests/test_provider_repository.py backend/tests/test_providers_api.py -q`，再运行改动文件 Ruff 和 `git diff --check`。

### Task 6: 历史详情尝试 API 与轮换工作台控件

**Files:**
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/api/routes/jobs.py`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/jobs.ts`
- Modify: `frontend/components/history/job-table.tsx`
- Create: `frontend/components/history/job-attempt-timeline.tsx`
- Modify: `frontend/components/workbench/model-select.tsx`
- Modify: `frontend/components/workbench/hypothesis-form.tsx`
- Modify: `frontend/components/workbench/judgment-form.tsx`
- Modify: `frontend/components/workbench/batch-form.tsx`
- Test: `frontend/tests/jobs-api-client.test.ts`
- Test: `frontend/tests/job-detail.test.tsx`
- Test: `frontend/tests/job-forms.test.tsx`
- Test: `frontend/tests/model-select.test.tsx`

- [ ] **Step 1: 写前端契约 RED 测试**

断言 `JobSummary` 可解析 interrupted/attempt_count/successful_model；详情显示候选顺序和三次尝试；轮换关闭请求体不含备用候选；轮换开启请求体保留排序且去重；未通过完整报告验证的模型不可选。

- [ ] **Step 2: 运行 RED**

运行：`cd frontend; npm.cmd test -- --run tests/jobs-api-client.test.ts tests/job-detail.test.tsx tests/job-forms.test.tsx tests/model-select.test.tsx`。

预期：类型/请求体/组件缺少新字段和控件。

- [ ] **Step 3: 实现 API 类型与客户端**

同步 `JobStatus`、`RotationCandidate`、`JobAttempt`、`JobRotationSnapshot`；`listJobAttempts(jobId)` 调用新端点。创建请求体在开关关闭时仅发送 `rotation_enabled:false` 和 requested model，在开启时发送有序候选快照。

- [ ] **Step 4: 实现工作台开关与排序**

在现有模型选择器下增加二值开关；开启后展示已通过 `full_report_verified` 的候选，并用上移/下移图标按钮调整顺序，按钮带 aria-label/tooltip。切换模型或目录刷新时重新校验候选；无候选时禁用提交并显示现有验证提示。不开启时不改变既有固定模型行为。

- [ ] **Step 5: 实现历史尝试时间线**

创建无卡片嵌套的紧凑时间线组件：每项显示 ordinal、provider/model、状态、stage、耗时、规范化错误；模型原文永不显示。任务行增加 `attempt_count`/`successful_model` 摘要，中断行支持重试。

- [ ] **Step 6: 运行 GREEN 与类型检查**

运行：`cd frontend; npm.cmd test -- --run tests/jobs-api-client.test.ts tests/job-detail.test.tsx tests/job-forms.test.tsx tests/model-select.test.tsx; npm.cmd run typecheck; cd ..`。

### Task 7: 混合历史回归、迁移验收和 0.1.8 打包门禁

**Files:**
- Modify: `backend/tests/test_jobs_api.py`
- Modify: `backend/tests/test_sqlite_migrations.py`
- Modify: `frontend/tests/batch-history.test.tsx`
- Modify: `frontend/tests/history-error.test.tsx`
- Modify: `docs/优化迭代记录.md`
- Verify: `release/组合选品控制台-Setup-0.1.8.exe`

- [ ] **Step 1: 写端到端 RED/夹具**

用临时 SQLite 生成 completed/failed/interrupted、无尝试旧任务、单次成功任务、轮换两次尝试任务；用 MSW 返回 API 500，断言历史页错误态而不是空态；用合成模型 fake 验证 `completed_no_qualified_candidates` 不轮换。

- [ ] **Step 2: 运行聚焦回归**

运行：

```powershell
\.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py backend/tests/test_job_recovery.py backend/tests/test_sqlite_migrations.py backend/tests/test_model_rotation.py -q
cd frontend; npm.cmd test -- --run tests/history-error.test.tsx tests/batch-history.test.tsx tests/job-detail.test.tsx; npm.cmd run typecheck; cd ..
```

预期：混合历史、恢复、轮换和错误显示全部通过。

- [ ] **Step 3: 运行现有全量门禁**

按串行顺序运行改动文件 Ruff、根目录全量 Python pytest、前端全量 Vitest、前端 TypeScript、桌面测试/TypeScript、`git diff --check`；记录既有 warning，但任何退出码非零都不能宣称通过。

- [ ] **Step 4: 验证升级和数据边界**

在独立临时 LocalAppData 执行 0001→0010、0009→0010、已有 13 条混合任务数据库升级、WAL/备份恢复和中文/空格/#/% 路径验收；断言用户数据库行数、历史结果和 API 密文不变，不输出路径或密钥。

- [ ] **Step 5: 真实端到端模型验收**

对已配置并已通过代表性验证的 5.4、5.5、5.6（若尚未验证则先不加入轮换）各运行一次代表性报告；记录模型、耗时、状态和质量门结果，不记录原文或凭据。至少验证一次技术失败切换和一次“无合格组合”成功不切换。

- [ ] **Step 6: 构建 0.1.8 并记录结果**

更新所有版本文件到 0.1.8，停止 Next dev 后以至少 10 分钟外层预算运行 `scripts/build-windows-installer.ps1`；在独立路径启动 `release/win-unpacked/组合选品控制台.exe`，验证 API/Next/Worker、数据库 0010、History 混合状态和轮换设置。计算安装包 SHA-256，扫描 OpenAI/Maike 密钥格式命中为 0，追加新的失败/成功/I-201 记录到 `docs/优化迭代记录.md`。

## 自检结果

- **Spec coverage:** 任务 1 覆盖 `interrupted` 根因和错误态；任务 2–3 覆盖 0010、任务/尝试实体、快照和恢复；任务 4 覆盖技术失败矩阵、业务成功和一次请求；任务 5 覆盖代表性完整报告准入与模型差异；任务 6 覆盖前端开关、排序、历史详情和重试；任务 7 覆盖迁移、全量测试、真实模型和 0.1.8 打包。
- **Placeholder scan:** 本计划没有未定义占位步骤；每个生产步骤给出文件、行为、测试命令和预期结果。
- **Type consistency:** `JobModelAttempt`、`RotationCandidate`、`rotation_enabled`、`rotation_candidates`、`successful_model`、`full_report_verified` 和稳定错误码在前后端任务中使用同一名称；旧任务缺失字段统一按轮换关闭和空尝试回退。
- **Scope check:** 后端、模型准入和前端是同一跨层功能的必要边界，按任务切分后每个阶段都有可独立验证的测试；未引入无关重构或新依赖。
