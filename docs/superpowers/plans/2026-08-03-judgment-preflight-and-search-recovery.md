# 对比审判模型预检与搜索恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让对比审判在入队前淘汰已失效模型，并让桌面搜索使用正确 API 通道且在 Walmart 机器人验证时给出可操作的中文降级入口。

**Architecture:** `ProviderService` 复用现有 `ProviderModelVerifier` 做提交前实时探测并持久化最新模型状态；前端对比审判在服务端拒绝后刷新供应商目录。搜索表单统一经过 `apiFetch`，后端把已识别的 Walmart 机器人验证转换为稳定 409 业务错误，前端提供编码后的外部搜索链接。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy repository、pytest、TypeScript、React、TanStack Query、Vitest、Testing Library、Electron/Next.js。

---

## 文件结构

- 修改 `backend/application/provider_service.py`：历史验证通过后执行实时模型探测，并统一保存探测状态与取消失效选择。
- 修改 `backend/tests/test_provider_service.py`：覆盖实时成功、明确失效和临时错误。
- 修改 `frontend/components/workbench/judgment-form.tsx`：模型提交失败后刷新供应商目录。
- 修改 `frontend/tests/job-forms.test.tsx`：覆盖模型错误后的目录刷新和失效偏好清理路径。
- 修改 `backend/workers/jobs.py`：Worker 捕获执行期模型路由失效并持久化验证状态、取消勾选。
- 修改 `backend/tests/test_worker_jobs.py`：覆盖模型在入队后失效的二次防御。
- 修改 `backend/api/routes/search.py`：将机器人验证映射为稳定 409 业务错误。
- 修改 `backend/tests/test_search_api.py`：区分机器人验证、普通网络错误和正常空结果。
- 修改 `frontend/components/workbench/search-form.tsx`：改用 `searchWalmart`/`apiFetch` 并渲染外部搜索降级入口。
- 创建 `frontend/tests/search-form.test.tsx`：覆盖桌面 API 客户端调用、中文错误和 URL 编码。
- 修改 `docs/优化迭代记录.md`：记录每次成功变更、失败尝试和最终验收结果。

### Task 1：提交前实时模型预检

- [x] **Step 1：写失败测试**

在 `backend/tests/test_provider_service.py` 为 `is_model_available` 注入 `AsyncMock` verifier：历史记录为 24 小时内 `verified + is_selected`，探测分别返回 `verified`、`unavailable/PROVIDER_MODEL_INVALID`、`temporary_error/PROVIDER_RATE_LIMITED`。断言成功返回 `True`；另外两种返回 `False`；所有探测都调用 `upsert_model_validation`；明确失效额外调用：

```python
repository.set_model_selected.assert_awaited_once_with(
    "custom", "openai", "claude-opus-4-5-20251101", False
)
```

- [x] **Step 2：确认测试先失败**

运行：

```powershell
pytest backend/tests/test_provider_service.py -k "live_probe" -q
```

预期：FAIL，现有实现不会调用 verifier，也不会更新模型验证状态。

- [x] **Step 3：实现最小实时预检**

在 `ProviderService` 增加私有 runtime 构造与探测结果持久化方法；`is_model_available` 只有找到新鲜且已勾选的历史记录后才解密密钥并执行：

```python
probe = await self._model_verifier(runtime, selected_model)
await self._repository.upsert_model_validation(
    provider_slug=slug,
    api_protocol=record.api_protocol,
    model=selected_model,
    status=probe.status,
    error_code=probe.error_code,
    message=probe.message,
    tested_at=datetime.now(timezone.utc),
)
if probe.status != "verified":
    await self._repository.set_model_selected(
        slug, record.api_protocol, selected_model, False
    )
    return False
return True
```

解密失败、安全配置失败均返回 `False`，不得输出密钥。

- [x] **Step 4：运行后端定向测试**

运行：

```powershell
pytest backend/tests/test_provider_service.py backend/tests/test_job_service.py -q
```

预期：PASS。

### Task 2：对比审判失败后刷新模型目录

- [x] **Step 1：写失败测试**

在 `frontend/tests/job-forms.test.tsx` mock `submitJudgment` 第一次抛出：

```ts
new ApiError("PROVIDER_MODEL_INVALID", "当前模型不存在或暂不可用", false, 409)
```

提交表单后断言 `listProviders` 被再次调用，界面显示中文错误，旧模型不再保持可选。

- [x] **Step 2：确认前端测试先失败**

运行：

```powershell
cd frontend
npm test -- --run tests/job-forms.test.tsx
```

预期：FAIL，当前 mutation 没有刷新 `queryKeys.providers.all`。

- [x] **Step 3：实现目录刷新**

在 `judgment-form.tsx` 引入 `useQueryClient`、`ApiError` 与 `queryKeys`。mutation 失败且错误码属于 `PROVIDER_MODEL_INVALID`、`PROVIDER_MODEL_ROUTE_UNAVAILABLE` 或 `PROVIDER_MODEL_NOT_VERIFIED` 时执行：

```ts
void queryClient.invalidateQueries({ queryKey: queryKeys.providers.all });
```

保留服务端中文错误，不自动重提任务。

- [x] **Step 4：运行工作台定向测试**

运行：

```powershell
cd frontend
npm test -- --run tests/job-forms.test.tsx tests/model-select.test.tsx tests/workbench-model-preference.test.ts
```

预期：PASS。

### Task 3：Worker 执行期模型失效二次防御

- [x] **Step 1：写失败测试**

在 `backend/tests/test_worker_jobs.py` 让 runner 抛出包含 404 model-not-found 的 `LLMError`，任务 payload 使用 `provider="custom"`、`model="claude-opus-4-5-20251101"`。断言任务失败后 Provider repository 写入 `unavailable/PROVIDER_MODEL_INVALID`，并执行：

```python
provider_repository.set_model_selected.assert_awaited_once_with(
    "custom", "openai", "claude-opus-4-5-20251101", False
)
```

- [x] **Step 2：确认测试先失败**

运行：

```powershell
pytest backend/tests/test_worker_jobs.py -k "invalidates_unroutable" -q
```

预期：FAIL，现有 Worker 只保存任务失败，不更新模型验证记录。

- [x] **Step 3：实现 Worker 失效持久化**

在 `backend/workers/jobs.py` 增加私有 helper，使用 `classify_provider_error(str(exc))`。仅当错误码为 `PROVIDER_MODEL_INVALID` 或 `PROVIDER_MODEL_ROUTE_UNAVAILABLE` 且 provider/model 非空时，通过 `ProviderConfigurationRepository(session)` 读取协议、写入 unavailable 验证并取消勾选。认证、限流、超时和普通分析错误不得取消模型。

- [x] **Step 4：运行 Worker 定向测试**

运行：

```powershell
pytest backend/tests/test_worker_jobs.py -q
```

预期：PASS。

### Task 4：搜索机器人验证稳定错误

- [x] **Step 1：更新失败测试期望**

修改 `backend/tests/test_search_api.py::test_reports_bot_detection_as_structured_failure`：

```python
assert response.status_code == 409
assert response.json()["detail"] == {
    "code": "WALMART_SEARCH_REQUIRES_BROWSER",
    "message": "Walmart 要求人工验证，请在浏览器中打开搜索并复制商品链接。",
}
```

继续断言 page/context 均关闭。

- [x] **Step 2：确认测试先失败**

运行：

```powershell
pytest backend/tests/test_search_api.py -q
```

预期：机器人验证用例 FAIL（当前是 502/`SEARCH_FAILED`），其他用例 PASS。

- [x] **Step 3：实现精确错误映射**

在 `backend/api/routes/search.py` 捕获 `RuntimeError`，仅当消息包含 `bot detection` 时返回：

```python
raise HTTPException(
    status_code=409,
    detail={
        "code": "WALMART_SEARCH_REQUIRES_BROWSER",
        "message": "Walmart 要求人工验证，请在浏览器中打开搜索并复制商品链接。",
    },
) from error
```

其他异常仍为 502 `SEARCH_FAILED`，finally 继续释放页面资源。

- [x] **Step 4：运行搜索 API 测试**

运行：

```powershell
pytest backend/tests/test_search_api.py -q
```

预期：PASS。

### Task 5：搜索表单统一桌面 API 与降级入口

- [x] **Step 1：创建失败测试**

创建 `frontend/tests/search-form.test.tsx`，mock `searchWalmart`。用例一断言输入 `orthopedic dog bed` 后调用：

```ts
expect(searchWalmart).toHaveBeenCalledWith("orthopedic dog bed");
```

用例二让其抛出 `ApiError("WALMART_SEARCH_REQUIRES_BROWSER", ...)`，断言中文说明和链接：

```ts
expect(link).toHaveAttribute(
  "href",
  "https://www.walmart.com/search?q=orthopedic%20dog%20bed"
);
```

- [x] **Step 2：确认组件测试先失败**

运行：

```powershell
cd frontend
npm test -- --run tests/search-form.test.tsx tests/search-api-client.test.ts
```

预期：FAIL，当前组件使用本地 raw fetch 且没有降级链接。

- [x] **Step 3：实现统一客户端和中文降级 UI**

删除 `search-form.tsx` 内部 `searchProducts`；改为：

```ts
mutationFn: () => searchWalmart(keyword.trim()),
select: (response) => response.results,
```

当 `search.error instanceof ApiError` 且 code 为 `WALMART_SEARCH_REQUIRES_BROWSER` 时显示错误说明与：

```tsx
<a
  href={`https://www.walmart.com/search?q=${encodeURIComponent(keyword.trim())}`}
  target="_blank"
  rel="noopener noreferrer"
>
  在浏览器打开 Walmart 搜索
</a>
```

- [x] **Step 4：运行前端搜索回归**

运行：

```powershell
cd frontend
npm test -- --run tests/search-form.test.tsx tests/search-api-client.test.ts tests/result-workbench-ui.test.tsx
```

预期：PASS。

### Task 6：全量验证、真实验收与安装包

- [x] **Step 1：运行后端全量测试**

```powershell
pytest backend/tests -q
```

预期：全部 PASS；若有既存 skip，数量与修改前基线一致。

- [x] **Step 2：运行前端全量测试与类型检查**

```powershell
cd frontend
npm test -- --run
npm run typecheck
npm run build
```

预期：测试、类型检查、生产构建全部成功。

- [x] **Step 3：桌面开发版真实验收**

启动桌面应用后：失效 `claude-opus-4-5-20251101` 在对比审判入队前被拒绝并从目录取消勾选；选择仍可用模型完成至少一条真实 A/B 任务。搜索 `orthopedic dog bed` 若被 Walmart 拦截，应在数秒内显示外部浏览器入口而不是等待五分钟或伪装为空结果。

- [x] **Step 4：构建并验证安装包**

使用项目现有桌面打包命令生成安装包；核对文件存在、大小、SHA-256，并从整包启动执行健康检查。只有整包启动和核心流程通过后才把新安装包交付给用户。

- [x] **Step 5：更新中文迭代记录**

把测试数量、真实任务 ID、搜索实际行为、安装包路径/大小/SHA-256、所有失败及修复写入 `docs/优化迭代记录.md`，不写入任何 API Key。
