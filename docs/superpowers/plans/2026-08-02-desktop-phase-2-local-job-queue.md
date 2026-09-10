# Desktop Phase 2 Local Job Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 SQLite 持久化单Worker队列替换桌面运行时 Redis/ARQ，同时保持现有任务 API、进度、错误分类和历史结果协议。

**Architecture:** 将队列记录与分析任务分表保存；API 只负责创建任务和投递队列记录，独立 Worker 原子领取。现有 `run_analysis_job` 与 `run_cross_review` 作为处理函数继续复用。

**Tech Stack:** SQLAlchemy asyncio、SQLite WAL、FastAPI、asyncio、Pytest

---

### Task 1: 队列表模型与迁移

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/migrations/versions/0007_add_desktop_job_queue.py`
- Test: `backend/tests/test_local_queue_repository.py`

- [ ] **Step 1: 写失败测试**

```python
def test_queue_item_defaults():
    item = LocalQueueItem(function="run_analysis_job", arguments=["job-id"])
    assert item.status == "queued"
    assert item.attempts == 0
    assert item.cancel_requested is False
```

- [ ] **Step 2: 验证 RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_local_queue_repository.py -q
```

预期：`LocalQueueItem` 不存在。

- [ ] **Step 3: 实现模型**

```python
class LocalQueueItem(Base):
    __tablename__ = "local_queue_items"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    function: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

增加 `(status, created_at)` 索引，迁移 upgrade/downgrade 必须对 SQLite 可执行。

### Task 2: 原子领取与重复执行保护

**Files:**
- Create: `backend/application/local_queue.py`
- Test: `backend/tests/test_local_queue_repository.py`

- [ ] **Step 1: 写并发失败测试**

```python
@pytest.mark.asyncio
async def test_two_workers_cannot_claim_same_item(queue_repository):
    item = await queue_repository.enqueue("run_analysis_job", "job-1")
    first, second = await asyncio.gather(
        queue_repository.claim_next("worker-a"),
        queue_repository.claim_next("worker-b"),
    )
    claimed = [value for value in (first, second) if value is not None]
    assert [value.id for value in claimed] == [item.id]
```

- [ ] **Step 2: 验证 RED 后实现条件更新领取**

```python
statement = (
    update(LocalQueueItem)
    .where(LocalQueueItem.id == candidate_id, LocalQueueItem.status == "queued")
    .values(status="running", claimed_by=worker_id, started_at=utc_now(), attempts=LocalQueueItem.attempts + 1)
    .returning(LocalQueueItem)
)
```

SQLite 中在短事务内选择最早 queued 项并执行条件更新；返回 0 行时重新进入下一轮，不复用陈旧候选。

- [ ] **Step 3: 验证领取、完成与失败**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_local_queue_repository.py -q
```

预期：原子领取、FIFO、完成、失败和重复领取测试通过。

### Task 3: 实现 `SqliteJobQueue`

**Files:**
- Modify: `backend/application/queue.py`
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/test_job_service.py`

- [ ] **Step 1: 写桌面队列投递测试**

```python
@pytest.mark.asyncio
async def test_sqlite_queue_persists_function_and_args(session_factory):
    queue = SqliteJobQueue(session_factory)
    await queue.enqueue("run_analysis_job", "job-1")
    assert await queued_functions(session_factory) == [("run_analysis_job", ["job-1"])]
```

- [ ] **Step 2: 实现协议适配**

```python
class SqliteJobQueue:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def enqueue(self, function: str, *args: str) -> None:
        if function not in {"run_analysis_job", "run_cross_review"}:
            raise ValueError("Unsupported local queue function")
        async with self._session_factory() as session:
            session.add(LocalQueueItem(function=function, arguments=list(args)))
            await session.commit()
```

`get_job_queue()` 根据 `runtime_mode` 返回 SQLite 或 ARQ 实现；服务端模式暂时保留 ARQ。

- [ ] **Step 3: 验证 API 契约不变**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_job_service.py backend/tests/test_jobs_api.py -q
```

预期：所有现有提交、失败和重试断言通过。

### Task 4: 本地 Worker 循环与处理器注册表

**Files:**
- Create: `backend/workers/local_worker.py`
- Modify: `backend/workers/jobs.py`
- Test: `backend/tests/test_local_worker.py`

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.asyncio
async def test_worker_executes_one_item_at_a_time(fake_repo, handlers):
    worker = LocalWorker(fake_repo, handlers, worker_id="desktop-1")
    await worker.run_once()
    assert handlers.max_concurrency == 1
    assert fake_repo.completed_ids == [fake_repo.first.id]
```

- [ ] **Step 2: 实现单次循环**

```python
HANDLERS = {
    "run_analysis_job": run_analysis_job,
    "run_cross_review": run_cross_review,
}

async def run_once(self) -> bool:
    item = await self._repository.claim_next(self.worker_id)
    if item is None:
        return False
    try:
        await self._handlers[item.function]({}, *item.arguments)
        await self._repository.complete(item.id)
    except BaseException as error:
        await self._repository.fail(item.id, classify_worker_error(error))
    return True
```

CLI 入口支持 `python -m backend.workers.local_worker`，轮询使用可取消事件，不使用无界忙循环。

- [ ] **Step 3: 验证取消与崩溃**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_local_worker.py backend/tests/test_worker_jobs.py -q
```

预期：单并发、未知函数、处理失败和关闭事件测试通过。

### Task 5: 取消、异常中断与重新提交

**Files:**
- Modify: `backend/db/repositories.py`
- Modify: `backend/api/routes/jobs.py`
- Modify: `backend/api/schemas/jobs.py`
- Create: `backend/application/job_recovery.py`
- Test: `backend/tests/test_job_recovery.py`
- Test: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: 写行为测试**

```python
@pytest.mark.asyncio
async def test_startup_marks_stale_running_job_interrupted(repository):
    job = await repository.create(mode="hypothesis", request_payload={"url": "https://example.test"})
    await repository.transition(job.id, expected="queued", target="running")
    await recover_interrupted_jobs(repository, now=utc_now() + timedelta(minutes=5))
    recovered = await repository.get(job.id)
    assert recovered.status == "interrupted"
    assert recovered.error_code == "APP_INTERRUPTED"
```

- [ ] **Step 2: 实现安全状态**

增加 `cancel_requested` 或队列取消记录；API：`POST /jobs/{job_id}/cancel`。queued 直接取消，running 只设置请求，由进度回调和阶段边界检查。

```python
if await repository.is_cancel_requested(job_uuid):
    raise JobCancelledError("任务已由用户安全停止")
```

- [ ] **Step 3: 验证旧结果不被重跑**

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_job_recovery.py backend/tests/test_jobs_api.py backend/tests/test_worker_jobs.py -q
```

预期：只恢复 queued；running 变为 interrupted；completed 不变。

### Task 6: 桌面健康检查替换 Redis 信号

**Files:**
- Modify: `backend/api/routes/health.py`
- Create: `backend/workers/local_identity.py`
- Test: `backend/tests/test_readiness.py`

- [ ] **Step 1: 写桌面 readiness 测试**

```python
def test_desktop_readiness_reports_queue_and_worker(client, fresh_identity):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["queue"] == "ok"
    assert response.json()["worker"] == "ok"
    assert "redis" not in response.json()
```

- [ ] **Step 2: 实现模式化探针**

桌面模式从数据库读取最近 Worker 心跳和可读队列表；服务端模式继续使用 Redis。两种模式都输出 `contract_match`。

- [ ] **Step 3: 全量验证**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend app tests
git diff --check
```

预期：全部通过；桌面模式不要求 Redis，服务端模式行为不回退。

### Task 7: 阶段二验证报告

**Files:**
- Create: `docs/verification/2026-08-02-desktop-phase-2.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 记录证据**

报告列出原子领取、单并发、排队取消、运行中安全停止、异常中断、Worker心跳和现有任务 API 全量回归结果。不得把模拟测试描述成真实外部 API 验证。

