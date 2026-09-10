# 历史任务名称行内编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在历史记录列表直接补充、修改或清空任务备注名称，而不影响任务分析数据和运行状态。

**Architecture:** 复用既有 `analysis_jobs.name` 字段，通过单字段 PATCH 接口完成持久化；前端 API 客户端封装请求，历史表格用独立行内编辑组件管理草稿、键盘操作和错误。服务端只更新 `name` 与版本号，前端成功后刷新任务列表缓存。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy Async、pytest、Next.js、React、TypeScript、TanStack Query、Vitest、Testing Library。

---

## 文件结构

- 修改 `backend/api/schemas/jobs.py`：新增 `JobNameUpdate` 请求模型。
- 修改 `backend/db/repositories.py`：新增只更新名称的 `rename` 方法。
- 修改 `backend/api/routes/jobs.py`：新增 PATCH 改名接口。
- 修改 `backend/tests/test_jobs_api.py`、`backend/tests/test_provider_repository.py` 或新增聚焦 repository 测试：覆盖持久化和接口边界。
- 修改 `frontend/lib/api/jobs.ts`：新增 `renameJob`。
- 修改 `frontend/tests/provider-api-client.test.ts` 或新增 `frontend/tests/jobs-api-client.test.ts`：验证请求路径和请求体。
- 新增 `frontend/components/history/job-name-editor.tsx`：封装单行编辑状态和交互。
- 修改 `frontend/components/history/job-table.tsx`：拆分详情链接并接入编辑器。
- 修改 `frontend/tests/batch-history.test.tsx`：覆盖历史列表改名流程。
- 修改 `docs/优化迭代记录.md`：记录 RED、修复、验证和回滚。

### Task 1: 后端任务名称更新契约与仓储

**Files:**
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/db/repositories.py`
- Test: `backend/tests/test_provider_repository.py`（若已有 JobRepository fixture 则沿用；否则在 `backend/tests/test_jobs_api.py` 的 fake repository 中覆盖）

- [ ] **Step 1: 写 repository 与 schema 失败测试**

测试必须断言：`"  采购复核  "` 归一化为 `"采购复核"`；空白字符串变为 `None`；101 字符校验失败；`rename` 只改变 `name` 并保留 status、progress、result_payload。

```py
def test_job_name_update_trims_and_clears_blank_names():
    assert JobNameUpdate(name="  采购复核  ").name == "采购复核"
    assert JobNameUpdate(name="   ").name is None

def test_job_name_update_rejects_more_than_100_characters():
    with pytest.raises(ValidationError):
        JobNameUpdate(name="名" * 101)
```

Repository 异步测试使用现有 session fixture 创建任务后调用：

```py
renamed = await repository.rename(job.id, "采购复核")
assert renamed is not None
assert renamed.name == "采购复核"
assert renamed.status == original_status
assert renamed.progress == original_progress
assert renamed.result_payload == original_result
assert renamed.version == original_version + 1
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py backend/tests/test_provider_repository.py -k "job_name or rename" -q`

Expected: FAIL，提示 `JobNameUpdate` 或 `JobRepository.rename` 不存在。

- [ ] **Step 3: 实现 schema 归一化**

在 `backend/api/schemas/jobs.py` 增加：

```py
class JobNameUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
```

将 `JobNameUpdate` 加入 `__all__`。

- [ ] **Step 4: 实现单字段仓储更新**

在 `JobRepository` 增加：

```py
async def rename(self, job_id: UUID, name: str | None) -> AnalysisJob | None:
    statement = (
        update(AnalysisJob)
        .where(AnalysisJob.id == job_id)
        .values(name=name, version=AnalysisJob.version + 1)
        .returning(AnalysisJob)
    )
    result = await self._session.execute(statement)
    job = result.scalar_one_or_none()
    await self._session.commit()
    return job
```

- [ ] **Step 5: 运行聚焦测试确认 GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py backend/tests/test_provider_repository.py -k "job_name or rename" -q`

Expected: 新增测试全部通过。

### Task 2: 新增 PATCH 改名接口

**Files:**
- Modify: `backend/api/routes/jobs.py`
- Modify: `backend/tests/test_jobs_api.py`

- [ ] **Step 1: 写 API 失败测试**

通过现有 dependency override/fake repository 覆盖：有效名称返回 200 和归一化名称；空名称返回 `name: null`；未知 UUID 返回 404 `JOB_NOT_FOUND`；101 字符返回 422。

```py
response = await client.patch(
    f"/api/v1/jobs/{job_id}/name",
    json={"name": "  采购复核  "},
)
assert response.status_code == 200
assert response.json()["name"] == "采购复核"
repository.rename.assert_awaited_once_with(job_id, "采购复核")
```

- [ ] **Step 2: 运行 API 测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py -k "rename_job" -q`

Expected: FAIL，接口返回 405 或 404。

- [ ] **Step 3: 实现路由**

在动态 `GET /{job_id}` 路由附近新增：

```py
@router.patch("/{job_id}/name", response_model=JobSummary)
async def rename_job(
    job_id: UUID,
    request: JobNameUpdate,
    repository: JobRepository = Depends(get_job_repository),
) -> JobSummary:
    job = await repository.rename(job_id, request.name)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "Analysis job was not found",
                "retryable": False,
            },
        )
    return JobSummary.model_validate(job)
```

补充 `JobNameUpdate` 导入，确保静态 `/{job_id}/name` 在行为上不会被 `/{job_id}` 错误消费。

- [ ] **Step 4: 运行 API 测试与 Ruff**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_jobs_api.py -k "rename_job" -q`

Expected: 全部通过。

Run: `.venv\Scripts\python.exe -m ruff check backend/api/schemas/jobs.py backend/db/repositories.py backend/api/routes/jobs.py backend/tests/test_jobs_api.py`

Expected: `All checks passed!`；若只报告项目既有 FastAPI `Depends` B008，则使用仓库现有 Ruff 配置/既有忽略方式，不修改本轮无关路由。

### Task 3: 前端 API 客户端

**Files:**
- Modify: `frontend/lib/api/jobs.ts`
- Create: `frontend/tests/jobs-api-client.test.ts`（若已有同类 jobs 客户端测试则合并到该文件）

- [ ] **Step 1: 写客户端失败测试**

```ts
it("patches a historical job name", async () => {
  server.use(
    http.patch(`${API_BASE}/api/v1/jobs/:jobId/name`, async ({ request, params }) => {
      expect(params.jobId).toBe("job-1");
      expect(await request.json()).toEqual({ name: "采购复核" });
      return HttpResponse.json({ id: "job-1", name: "采购复核" });
    }),
  );
  expect((await renameJob("job-1", "采购复核")).name).toBe("采购复核");
});
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm.cmd test -- --run tests/jobs-api-client.test.ts`

Working directory: `frontend`

Expected: FAIL，提示 `renameJob` 未导出。

- [ ] **Step 3: 实现客户端方法**

```ts
export async function renameJob(jobId: string, name: string | null): Promise<JobSummary> {
  return apiFetch<JobSummary>(`/jobs/${jobId}/name`, {
    method: "PATCH",
    body: { name },
  });
}
```

- [ ] **Step 4: 运行客户端测试确认 GREEN**

Run: `npm.cmd test -- --run tests/jobs-api-client.test.ts`

Working directory: `frontend`

Expected: 新增测试通过。

### Task 4: 历史列表行内编辑交互

**Files:**
- Create: `frontend/components/history/job-name-editor.tsx`
- Modify: `frontend/components/history/job-table.tsx`
- Modify: `frontend/tests/batch-history.test.tsx`

- [ ] **Step 1: 写 UI 失败测试**

在历史页 MSW handler 中增加 PATCH，测试：点击“修改任务备注”不会导航；现有名称进入输入框并全选；Enter 保存并显示新名称；Esc 取消；清空保存后显示“未命名任务”；500 时保留草稿和编辑状态并显示“保存失败，请稍后重试”；开启第二行编辑时关闭第一行。

```ts
await user.click(screen.getAllByRole("button", { name: "修改任务备注" })[0]);
const input = screen.getByRole("textbox", { name: "任务备注" });
expect(input).toHaveValue("未命名任务" === displayedName ? "" : displayedName);
await user.clear(input);
await user.type(input, "采购复核{Enter}");
expect(await screen.findByText("采购复核")).toBeInTheDocument();
expect(patchedBody).toEqual({ name: "采购复核" });
```

- [ ] **Step 2: 运行 UI 测试确认 RED**

Run: `npm.cmd test -- --run tests/batch-history.test.tsx`

Working directory: `frontend`

Expected: FAIL，找不到“修改任务备注”按钮。

- [ ] **Step 3: 新建受控行内编辑组件**

`JobNameEditor` 接收：

```ts
interface JobNameEditorProps {
  jobId: string;
  name: string | null;
  editing: boolean;
  saving: boolean;
  error?: string;
  onStart: () => void;
  onSave: (name: string | null) => void;
  onCancel: () => void;
}
```

组件内部保存草稿；进入编辑时同步 `name ?? ""`、focus/select；`maxLength={100}`；Enter 调用 `onSave(trimmed || null)`；Esc 调用 `onCancel`；非编辑态显示 `name || "未命名任务"` 和 `Pencil` 图标按钮。按钮 aria-label 分别为“修改任务备注”“保存任务备注”“取消修改”。

- [ ] **Step 4: 在 JobTable 接入 mutation 与单行状态**

新增 `editingJobId`，保存 mutation 调用 `renameJob`：

```ts
const renameMutation = useMutation({
  mutationFn: ({ jobId, name }: { jobId: string; name: string | null }) =>
    renameJob(jobId, name),
  onSuccess: () => {
    setEditingJobId(null);
    setRenameError(null);
    queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all });
  },
  onError: (error) => setRenameError(jobRenameErrorMessage(error)),
});
```

将 `JobAndProduct` 拆为：商品图和主品/任务 ID 保持在详情 `<a>` 中；任务名称编辑器位于链接外。只在当前行传入 `saving=true`。错误转换规则：404→“任务不存在或已被删除”；422→“任务备注不能超过 100 个字符”；其他→“保存失败，请稍后重试”。

- [ ] **Step 5: 运行历史页聚焦测试**

Run: `npm.cmd test -- --run tests/batch-history.test.tsx tests/jobs-api-client.test.ts`

Working directory: `frontend`

Expected: 全部通过。

- [ ] **Step 6: 运行可访问性与类型检查**

Run: `npm.cmd test -- --run tests/accessibility.test.tsx tests/app-shell.test.tsx`

Working directory: `frontend`

Expected: 全部通过。

Run: `npm.cmd run typecheck`

Working directory: `frontend`

Expected: exit code 0。

### Task 5: 全量验证、重启与记录

**Files:**
- Modify: `docs/优化迭代记录.md`
- Verify only: all implementation files

- [ ] **Step 1: 运行后端全量测试**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected baseline: 不少于 `522 passed, 9 skipped`，无失败。

- [ ] **Step 2: 运行前端全量测试**

Run: `npm.cmd test -- --run`

Working directory: `frontend`

Expected baseline: 不少于 `191 passed, 7 skipped`，无失败。

- [ ] **Step 3: 运行生产构建和差异检查**

Run: `npm.cmd run build`

Working directory: `frontend`

Expected: Next.js production build 成功。

Run: `git diff --check -- backend/api/schemas/jobs.py backend/db/repositories.py backend/api/routes/jobs.py backend/tests/test_jobs_api.py frontend/lib/api/jobs.ts frontend/components/history/job-name-editor.tsx frontend/components/history/job-table.tsx frontend/tests/jobs-api-client.test.ts frontend/tests/batch-history.test.tsx docs/优化迭代记录.md`

Expected: 无空白错误。

- [ ] **Step 4: 重启并做不调用模型的本地验收**

Run: `powershell -ExecutionPolicy Bypass -File .\启动.ps1`

Expected: `/api/v1/health/ready` 的 database、redis、worker、contract_match 均为 `ok`；`http://127.0.0.1:3000/history` 返回 200。通过测试任务执行改名、刷新确认持久化、再恢复原名称；此操作不得触发分析任务、供应商请求或 Token 消耗。

- [ ] **Step 5: 追加中文迭代记录**

记录读取的最新条目、精确文件、预期 RED、意外失败、聚焦/全量测试数字、健康状态、已知限制和回滚方式；不得记录 API Key、Cookie、Token 或模型回复正文。

- [ ] **Step 6: 保留共享脏工作区，不提交**

不执行 `git add`、`git commit`、reset 或无关文件清理，只交付本计划涉及的变更。

## 自检结果

- 规格覆盖：行内编辑、Enter/Esc、空值、100 字符、单行保存状态、中文错误、链接隔离、所有任务状态、并发单字段更新和无模型调用均有实现与测试步骤。
- 占位符扫描：没有未完成占位或笼统的“补充测试/错误处理”步骤。
- 类型一致性：后端请求统一为 `JobNameUpdate.name: str | None`，前端统一为 `renameJob(jobId, name: string | null)`，UI 保存回调与客户端一致。
- 范围：后端与前端共同形成一个小型端到端功能，无需拆成多个项目；不包含详情页编辑、批量改名、自动命名或数据库迁移。

