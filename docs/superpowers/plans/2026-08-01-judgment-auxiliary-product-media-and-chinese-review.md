# 对比审判辅品身份展示与中文判断依据 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让对比审判结果可靠展示每个辅品的真实图片和商品 ID，并让商品类型判断依据优先以中文呈现且保留历史英文原文。

**Architecture:** 后端在审判结果中新增可选 `b_products` 元数据，并让新商品类型复核结构同时保存中文依据和原始依据。前端使用独立的辅品元数据解析器，将新结构、旧任务 `b_urls` 和现有按辅品拆分结果安全合并，再由列表、抽屉和商品类型复核卡消费；旧任务不联网、不重算。

**Tech Stack:** Python 3.12、Pydantic、pytest、Next.js 15、React、TypeScript、Vitest、Testing Library、Tailwind CSS。

---

## 文件结构

- 修改 `backend/application/analysis_runner.py`：序列化辅品元数据并透传双模型结果。
- 修改 `app/services/product_type_reviewer.py` 与 `app/infrastructure/llm/prompts/product_type_review.txt`：定义中文依据字段和新任务输出契约。
- 修改 `frontend/lib/api/types.ts`：声明辅品元数据和中英文判断依据字段。
- 新建 `frontend/lib/judgment-product-metadata.ts`：唯一负责新旧任务辅品身份安全合并。
- 修改 `frontend/lib/result-format.ts`：让解析后的 `PerBProduct` 可承载身份元数据，不承担匹配规则。
- 修改 `frontend/components/jobs/judgment-analysis.tsx`：展示列表缩略图、ID、抽屉图片与商品链接。
- 修改 `frontend/components/jobs/product-type-review-card.tsx`：中文概括优先和英文原文折叠。
- 修改 `frontend/app/jobs/[jobId]/page.tsx`：向审判视图传入活动模型元数据与任务输入链接。
- 修改后端和前端对应测试，不新增数据库迁移。

### Task 1：持久化辅品真实身份元数据

**Files:**
- Modify: `backend/application/analysis_runner.py`
- Test: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: 写失败测试**

在现有 judgment runner 测试的两个 `ProductDTO` 辅品上设置不同的 `product_id`、URL 和图片，断言：

```python
assert result.result_payload["b_products"] == [
    {
        "title": "Auxiliary One",
        "product_id": "111",
        "product_url": "https://www.walmart.com/ip/auxiliary-one/111",
        "product_image": "https://images.example/auxiliary-one.jpg",
    },
    {
        "title": "Auxiliary Two",
        "product_id": "B0AUX222",
        "product_url": "https://www.amazon.com/dp/B0AUX222",
        "product_image": None,
    },
]
assert result.result_payload["models"]["gpt"]["b_products"] == result.result_payload["b_products"]
assert result.result_payload["models"]["deepseek"]["b_products"] == result.result_payload["b_products"]
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -k "judgment and b_products" -q`

Expected: FAIL，结果中尚无 `b_products`。

- [ ] **Step 3: 实现独立序列化函数**

在 `analysis_runner.py` 增加：

```python
def _serialize_b_products(products_b: list[ProductDTO]) -> list[dict[str, Any]]:
    return [
        {
            "title": product.title,
            "product_id": product.product_id or extract_product_id(product.url),
            "product_url": product.url,
            "product_image": product.images[0] if product.images else None,
        }
        for product in products_b
    ]
```

在第一次 `_serialize_judgment` 后生成一次 `b_products = _serialize_b_products(products_b)`，写入顶层 payload；双模型分支中同时写入 `payload2`，并在 `_wrap_models` 后重新保留顶层 `b_products`。不要使用主品图片作为回退。

- [ ] **Step 4: 运行后端聚焦测试与 Ruff**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -k "judgment or b_products" -q
.venv\Scripts\python.exe -m ruff check backend/application/analysis_runner.py backend/tests/test_analysis_runner.py --ignore B008
```

Expected: 全部 PASS，Ruff `All checks passed!`。

### Task 2：新任务保存中文判断依据并保留原文

**Files:**
- Modify: `app/services/product_type_reviewer.py`
- Modify: `app/infrastructure/llm/prompts/product_type_review.txt`
- Test: `tests/test_product_type_reviewer.py`
- Test: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: 写失败的 schema 与序列化测试**

新增断言，模型返回如下结构时，领域对象和持久化 payload 保留两个字段：

```python
{
    "status": "confirmed_non_food",
    "entity_type": "厨房工具",
    "designed_for_ingestion": False,
    "confidence": 0.98,
    "reason_zh": "该商品是用于分配面糊的厨房工具，本身不是供人摄入的食品。",
    "reason_original": "The product is a kitchen utensil, not food itself.",
    "food_evidence": [],
    "non_food_evidence": [{"source_field": "title", "verbatim_quote": "Batter Dispenser"}],
}
```

断言 `review.reason_zh` 为中文、`review.reason_original` 保留英文，且序列化后两个字段存在。规则判断和 fallback 同样提供中文 `reason_zh`，原文可为 `None`。

- [ ] **Step 2: 运行测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest tests/test_product_type_reviewer.py backend/tests/test_analysis_runner.py -k "reason_zh or product_type_review" -q`

Expected: FAIL，现有 `_ModelReview` 和 `ProductTypeReview` 不接受新字段。

- [ ] **Step 3: 扩展领域结构与提示词**

将 `ProductTypeReview` 扩展为：

```python
@dataclass(frozen=True)
class ProductTypeReview:
    status: ReviewStatus
    source: ReviewSource
    confidence: float
    reason: str
    evidence: tuple[str, ...]
    action: ReviewAction
    role: str
    reason_zh: str | None = None
    reason_original: str | None = None
```

将 `_ModelReview` 的依据改为必填 `reason_zh`、可选 `reason_original`，不再依赖英文 `reason` 作为中文展示来源。为兼容现有内部消费者，构造 `ProductTypeReview` 时令 `reason=reason_zh`；`reason_original` 只保存原文。规则和 fallback 的 `reason_zh` 与 `reason` 使用相同中文文本。

提示词明确要求：

```text
reason_zh 必须使用简洁中文，说明商品实体是什么、为什么属于食品或非食品、系统为何继续或阻断。
reason_original 仅在模型需要保留原始英文判断时填写，否则返回 null。
不得翻译或改写 verbatim_quote；证据摘录必须保持商品原文。
```

- [ ] **Step 4: 运行聚焦测试、提示词测试与 Ruff**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_product_type_reviewer.py tests/test_prompts.py backend/tests/test_analysis_runner.py -k "product_type or reason_zh" -q
.venv\Scripts\python.exe -m ruff check app/services/product_type_reviewer.py backend/application/analysis_runner.py tests/test_product_type_reviewer.py backend/tests/test_analysis_runner.py --ignore B008
```

Expected: 全部 PASS。

### Task 3：实现新旧任务辅品元数据安全合并

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Create: `frontend/lib/judgment-product-metadata.ts`
- Modify: `frontend/lib/result-format.ts`
- Test: `frontend/tests/judgment-product-metadata.test.ts`

- [ ] **Step 1: 写失败测试**

测试以下唯一规则：

1. 新结果按规范化标题将 `b_products` 映射到解析后的辅品；
2. 标题不唯一时不借用图片/ID；
3. 旧结果只有 `b_urls` 且数量与辅品一致时按顺序提取 Walmart/Amazon ID；
4. 数量不一致时不按顺序猜测；
5. 图片为空时保持 `undefined`，不得回退主品图片。

示例断言：

```ts
expect(resolveJudgmentProducts(products, metadata, bUrls)[0]).toMatchObject({
  productId: "111",
  productUrl: "https://www.walmart.com/ip/auxiliary-one/111",
  productImage: "https://images.example/auxiliary-one.jpg",
});
expect(resolveJudgmentProducts(products, [], ["https://www.amazon.com/dp/B0AUX222"])[0].productId)
  .toBe("B0AUX222");
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm.cmd test -- --run tests/judgment-product-metadata.test.ts`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 定义类型和纯函数**

在 `api/types.ts` 增加：

```ts
export interface JudgmentBProductMetadata {
  title: string;
  product_id?: string | null;
  product_url?: string | null;
  product_image?: string | null;
}
```

为 `ModelResult` 与 `JobResultPayload` 增加 `b_products?: JudgmentBProductMetadata[]`；为 `ProductTypeReview` 增加 `reason_zh?: string | null`、`reason_original?: string | null`。

在新文件导出：

```ts
export function resolveJudgmentProducts(
  products: PerBProduct[],
  metadata: JudgmentBProductMetadata[] | undefined,
  bUrls: string[] | undefined,
): PerBProduct[]
```

使用 `trim().toLocaleLowerCase().replace(/\s+/g, " ")` 规范化标题；只接受唯一标题匹配。只有 `metadata` 缺失、`products.length === bUrls.length` 时才按顺序补 URL，并复用项目支持的 URL ID 提取规则。扩展 `PerBProduct` 的 `productId/productUrl/productImage` 可选字段。

- [ ] **Step 4: 运行纯函数测试和类型检查**

Run:

```powershell
npm.cmd test -- --run tests/judgment-product-metadata.test.ts
npm.cmd run typecheck
```

Expected: 测试与 TypeScript 全部通过。

### Task 4：展示辅品图片、ID和中文判断依据

**Files:**
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Modify: `frontend/components/jobs/judgment-analysis.tsx`
- Modify: `frontend/components/jobs/product-type-review-card.tsx`
- Test: `frontend/tests/result-workbench-ui.test.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: 写失败的 UI 测试**

测试列表中出现每个辅品自己的 `img`、`商品 ID：111`，打开第一行后抽屉显示同一图片、ID 和“打开商品”链接；第二个无图辅品显示“暂无图片”，且页面中不把主品图片 URL用于辅品。

商品类型复核测试：

```tsx
render(<ProductTypeReviewCard review={{
  status: "confirmed_non_food",
  source: "model",
  action: "continue",
  reason: "The product is a kitchen utensil, not food itself.",
  reason_zh: "该商品是厨房工具，本身不是食品。",
  reason_original: "The product is a kitchen utensil, not food itself.",
}} />);
expect(screen.getByText("该商品是厨房工具，本身不是食品。")).toBeVisible();
expect(screen.getByText("查看英文原文")).toBeVisible();
```

再测试旧任务只有英文 `reason` 时显示由状态/来源/动作生成的中文概括，展开后原英文字符完全一致。

- [ ] **Step 2: 运行 UI 测试确认 RED**

Run: `npm.cmd test -- --run tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx`

Expected: FAIL，尚未显示辅品身份和中文概括。

- [ ] **Step 3: 接入元数据并渲染**

`page.tsx` 从活动模型优先读取：

```ts
const judgmentBProducts = activeResult?.b_products ?? payload?.b_products;
const judgmentBUrls = Array.isArray(job.request_payload.b_urls)
  ? job.request_payload.b_urls.filter((value): value is string => typeof value === "string")
  : undefined;
```

传给 `JudgmentAnalysis`。组件内部先解析分数，再调用 `resolveJudgmentProducts`。列表使用现有 `ProductMedia` 渲染辅品缩略图；抽屉头部复用相同组件并仅在 `productUrl` 存在时显示安全的外部链接。

在 `product-type-review-card.tsx` 新增纯辅助函数：

```ts
export function productTypeReasonZh(review: ProductTypeReview): string {
  if (review.reason_zh?.trim()) return review.reason_zh.trim();
  if (/[\u3400-\u9fff]/.test(review.reason ?? "")) return review.reason!.trim();
  // 仅组合已保存的结论、来源和动作，不翻译英文商品事实
  return `${statusLabels[review.status] ?? "商品类型需要人工复核"}；${sourceSummary(review.source)}；${actionSummary(review.action)}。`;
}
```

英文原文候选优先 `reason_original`，其次是不含中文的 `reason`；用原生 `<details>` 默认收起显示，禁止回写结果。

- [ ] **Step 4: 运行前端聚焦测试与类型检查**

Run:

```powershell
npm.cmd test -- --run tests/judgment-product-metadata.test.ts tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx
npm.cmd run typecheck
```

Expected: 全部 PASS。

### Task 5：全量回归、运行验收和日志

**Files:**
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 每项操作前重读中文迭代记录，并记录所有 RED/工具失败**

将预期 RED、补丁失败、静态检查告警、运行态限制追加为新的 `F-` 条目；不得记录 API Key、Cookie、Token 或模型响应正文。

- [ ] **Step 2: 运行全量验证**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q
Set-Location frontend
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
Set-Location ..
git diff --check
```

Expected: 后端、前端、类型检查、构建和差异检查全部成功；既有非阻断 warning 单独记录，不宣称已修复。

- [ ] **Step 3: 重启与只读验收**

Run: `powershell -ExecutionPolicy Bypass -File .\启动.ps1`

检查：

- `/api/v1/health/ready` 的 database、redis、worker、contract_match 均为 `ok`；
- `/jobs/a9dc87ba-0bc2-4163-a62f-7cfc3ddd42e3` 返回 HTTP 200；
- 旧任务展示中文概括和英文原文折叠；
- 旧任务只在有可靠 ID/图片时展示，不重新抓取、不触发模型；
- 自动化 fixture 验证新任务结构的图片和 ID 展示。

- [ ] **Step 4: 完成迭代记录**

追加完成条目，写明修改文件、测试数量、构建结果、运行健康状态、旧任务兼容边界和回滚方式。共享脏工作区不执行 `git add`、commit、reset 或无关清理。
