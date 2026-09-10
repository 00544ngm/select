# 全品类食品准入门槛与模型复核实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有“非食品词表未命中即失败”改为规则优先、模型复核、失败可降级的全品类食品准入流程，并让主品与辅品得到一致、可解释的处理。

**Architecture:** 保留 `ingestible_classifier` 作为无网络的高置信度规则层，新建独立 `ProductTypeReviewer` 负责 UNKNOWN 的结构化模型复核与安全降级。`AnalysisRunner` 在抓取后调用统一异步门槛：主品确认食品时阻断任务，辅品确认食品时由方向过滤逻辑淘汰；其他状态继续并把来源、置信度和证据写入结果。

**Tech Stack:** Python 3.12、asyncio、Pydantic/dataclass、现有 `LLMClient.chat`、pytest、FastAPI worker、Next.js/TypeScript/Vitest。

---

## 文件结构

- 修改 `app/domain/ingestible_classifier.py`：仅维护高置信度规则证据和规则结论，不负责调用模型。
- 新建 `app/services/product_type_reviewer.py`：统一规则、模型复核、JSON 校验和降级决策。
- 新建 `app/infrastructure/llm/prompts/product_type_review.txt`：全品类食品判定契约。
- 修改 `backend/application/analysis_runner.py`：主品、审判 A/B 商品和批量商品接入异步复核；序列化证据。
- 修改 `app/domain/dto/__init__.py`、`app/domain/schemas/hypothesis.py`：保存复核状态与证据。
- 修改 `backend/application/result_quality.py`：接受带提醒继续的结果，仍拒绝食品方向。
- 修改 `frontend/lib/api/types.ts`、`frontend/components/jobs/stickiness-scorecard.tsx`：中文展示判断来源、理由、证据和处理结果。
- 测试 `tests/test_ingestible_classifier.py`、新建 `tests/test_product_type_reviewer.py`、修改 `backend/tests/test_analysis_runner.py`、`backend/tests/test_result_quality.py`、`frontend/tests/result-workbench-ui.test.tsx`。

### Task 1：收紧规则层职责并锁定锅铲回归

**Files:**
- Modify: `app/domain/ingestible_classifier.py`
- Test: `tests/test_ingestible_classifier.py`

- [ ] **Step 1: 写失败测试，证明锅铲和全品类代表样例不会被当作食品**

```python
@pytest.mark.parametrize("title", [
    "LELE LIFE Metal Spatula Cooking Cast Iron 2pcs Griddle Spatula Turner",
    "Solid Wood Bedside Table with Drawer",
    "Cotton Crew Neck T Shirt",
    "Cordless Drill Driver Kit",
    "Stainless Steel Pet Feeding Bowl",
])
def test_clear_non_ingestible_entities_are_confirmed(title):
    result = classify_product_type(title)
    assert result.status is ProductTypeStatus.NON_FOOD


@pytest.mark.parametrize("title", [
    "Chocolate Protein Bar 12 Count",
    "Vitamin C Gummies Dietary Supplement",
    "Chicken Flavor Dog Treats",
])
def test_ingestible_products_remain_blocked(title):
    assert classify_product_type(title).status is ProductTypeStatus.INGESTIBLE
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ingestible_classifier.py -q`

Expected: 锅铲、家具、服装或工具样例至少一项返回 `unknown`。

- [ ] **Step 3: 用实体类别强信号扩充规则层，不添加单商品品牌特例**

```python
_NON_FOOD_ENTITY_PHRASES = (
    "spatula", "turner", "kitchen utensil", "hand tool", "power tool",
    "furniture", "table", "chair", "shirt", "clothing", "pet bowl",
    "food container", "water bottle",
)
```

将匹配结果原因改为可审计的 `confirmed non-ingestible entity evidence`；保留食品与非食品同时命中时返回 UNKNOWN，交给下一层复核。

- [ ] **Step 4: 运行规则测试确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ingestible_classifier.py -q`

Expected: 全部通过，食品反例仍为 `ingestible`。

- [ ] **Step 5: 提交该原子改动**

```powershell
git add app/domain/ingestible_classifier.py tests/test_ingestible_classifier.py
git commit -m "fix: recognize clear non-food product entities"
```

### Task 2：建立结构化模型复核服务和安全降级

**Files:**
- Create: `app/services/product_type_reviewer.py`
- Create: `app/infrastructure/llm/prompts/product_type_review.txt`
- Test: `tests/test_product_type_reviewer.py`

- [ ] **Step 1: 写模型确认、食品阻断、不确定和异常降级测试**

```python
@pytest.mark.asyncio
async def test_unknown_rule_uses_model_and_accepts_non_food():
    llm = FakeLLM('{"status":"confirmed_non_food","confidence":0.98,"entity_type":"kitchen utensil","designed_for_ingestion":false,"reason":"金属锅铲不可摄入","evidence":["metal spatula"]}')
    result = await ProductTypeReviewer(llm).review(product("ACME Metal Spatula"), role="main product")
    assert result.status == "confirmed_non_food"
    assert result.source == "model"


@pytest.mark.asyncio
async def test_model_failure_degrades_without_blocking():
    result = await ProductTypeReviewer(FailingLLM()).review(product("ACME Model X"), role="auxiliary product")
    assert result.status == "needs_review"
    assert result.action == "continue_with_review"
```

同时覆盖：规则确认食品不调用模型、模型无证据却声称食品时降级为 `needs_review`、无效 JSON 重试后降级、`likely_non_food` 正常继续。

- [ ] **Step 2: 运行测试确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_product_type_reviewer.py -q`

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 定义稳定的复核结果类型**

```python
ReviewStatus = Literal[
    "confirmed_non_food", "confirmed_food", "likely_non_food", "needs_review"
]

@dataclass(frozen=True)
class ProductTypeReview:
    status: ReviewStatus
    source: Literal["rule", "model", "fallback"]
    confidence: float
    reason: str
    evidence: tuple[str, ...]
    action: Literal["continue", "continue_with_review", "block"]
```

- [ ] **Step 4: 实现规则优先和模型复核**

```python
async def review(self, product: ProductDTO, *, role: str) -> ProductTypeReview:
    rule = classify_product_type(product.title, keywords=product.bullet_points,
                                 product_type=_product_type(product),
                                 description=product.description or "")
    if rule.status is ProductTypeStatus.NON_FOOD:
        return _from_rule(rule, status="confirmed_non_food", action="continue")
    if rule.status is ProductTypeStatus.INGESTIBLE:
        return _from_rule(rule, status="confirmed_food", action="block")
    try:
        payload = await self._chat_and_validate(product, role=role)
        return _safe_model_decision(payload)
    except Exception:
        return ProductTypeReview("needs_review", "fallback", 0.0,
                                 "商品类型复核暂不可用，任务继续并需人工复核", (),
                                 "continue_with_review")
```

`_safe_model_decision` 只有在 `designed_for_ingestion=true`、状态为 `confirmed_food` 且 `evidence` 非空时允许 `block`；其余冲突结果降级为 `needs_review`。

- [ ] **Step 5: 编写严格提示词**

提示词明确：判断“商品实体是否设计为供人或动物摄入”；食品接触用品、容器、烹饪器具、加工设备不是食品；只能返回 JSON；必须引用输入事实，不得根据品牌或常识虚构证据。

- [ ] **Step 6: 运行服务测试确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_product_type_reviewer.py tests/test_ingestible_classifier.py -q`

Expected: 全部通过。

- [ ] **Step 7: 提交复核服务**

```powershell
git add app/services/product_type_reviewer.py app/infrastructure/llm/prompts/product_type_review.txt tests/test_product_type_reviewer.py
git commit -m "feat: add model fallback for product type review"
```

### Task 3：主品和辅品统一接入异步准入门槛

**Files:**
- Modify: `backend/application/analysis_runner.py`
- Modify: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: 写运行器失败回归**

新增测试断言：锅铲主品不再抛 `PRODUCT_TYPE_VERIFICATION_REQUIRED`；明确食品主品仍抛 `INGESTIBLE_PRODUCT_BLOCKED`；UNKNOWN + 模型异常继续进入分析；审判模式过滤食品 B 商品、保留其不准入证据并继续审判其他 B 商品；批量模式把食品条目记录为不准入结果后继续处理其余商品，不能让一条食品终止整批。

```python
assert result.result_payload["product_type_review"]["status"] == "confirmed_non_food"
assert fake_llm.analysis_calls == 1
```

- [ ] **Step 2: 运行运行器测试确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -q`

Expected: 现有同步 `_require_non_ingestible_product` 仍对 UNKNOWN 抛错。

- [ ] **Step 3: 将同步门槛替换为异步统一入口**

```python
async def _review_product_type(product, *, role, llm):
    review = await ProductTypeReviewer(llm).review(product, role=role)
    if review.status == "confirmed_food":
        raise ProductTypeGateError(
            code="INGESTIBLE_PRODUCT_BLOCKED",
            message=f"{role} 已确认属于食品：{review.reason}",
        )
    return review
```

在 `run_hypothesis`、`run_judgment`、`run_batch` 抓取商品后 `await` 调用，并把 review 传入结果构造；删除 UNKNOWN 直接抛 `PRODUCT_TYPE_VERIFICATION_REQUIRED` 的路径。

- [ ] **Step 4: 为审判和批量任务保留局部隔离语义**

`run_judgment` 先复核每个 B 商品：`confirmed_food` 不传给 `JudgmentService`，而是写入 `rejected_b_products`，包含 URL、标题、复核证据和“食品不准入”处理结果；其余 B 商品继续审判。若所有 B 商品均被过滤，返回可解释的“没有符合准入条件的 B 商品”结果，不调用审判模型，也不把它伪装成服务故障。

`run_batch` 把每个 URL 视为独立主品：食品条目写入该条目的阻断结果并继续循环，非食品与待复核条目继续分析；汇总中分别给出成功、待复核、食品阻断数量。只有单品 `run_hypothesis` 的主品 `confirmed_food` 才抛全局 `INGESTIBLE_PRODUCT_BLOCKED`。

- [ ] **Step 5: 运行运行器测试确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -q`

Expected: 全部通过。

- [ ] **Step 6: 提交运行器接入**

```powershell
git add backend/application/analysis_runner.py backend/tests/test_analysis_runner.py
git commit -m "feat: apply product type review across job modes"
```

### Task 4：把复核证据纳入领域结果和质量契约

**Files:**
- Modify: `app/domain/dto/__init__.py`
- Modify: `app/domain/schemas/hypothesis.py`
- Modify: `backend/application/analysis_runner.py`
- Modify: `backend/application/result_quality.py`
- Modify: `backend/tests/test_result_quality.py`
- Modify: `tests/test_hypothesis_service.py`

- [ ] **Step 1: 写质量契约 RED 测试**

覆盖 `confirmed_non_food` 可执行、`likely_non_food`/`needs_review` 可执行但结果标记待复核、`confirmed_food` 方向必须 reject、食品状态缺证据为非法结果。

- [ ] **Step 2: 运行测试确认 RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/test_result_quality.py tests/test_hypothesis_service.py -q`

Expected: 新字段或新状态尚不被接受。

- [ ] **Step 3: 增加可序列化字段**

```python
product_type_review_status: str = "needs_review"
product_type_review_source: str = "fallback"
product_type_review_confidence: float = 0.0
product_type_review_reason: str = ""
product_type_review_evidence: list[str] = field(default_factory=list)
```

Schema 使用相同字段名；序列化器原样写入。保持旧 `product_type_status` 和 `food_filter_status` 作为兼容派生字段，不改写历史结果。

- [ ] **Step 4: 更新质量验证规则**

`confirmed_food` 必须对应食品 rejection code 和非空证据；`likely_non_food`、`needs_review` 不触发硬失败，但进入 `completed_needs_evidence`；`confirmed_non_food` 保持可通过。

- [ ] **Step 5: 运行领域和质量测试确认 GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/test_result_quality.py tests/test_hypothesis_service.py -q`

Expected: 全部通过。

- [ ] **Step 6: 提交结果契约**

```powershell
git add app/domain/dto/__init__.py app/domain/schemas/hypothesis.py backend/application/analysis_runner.py backend/application/result_quality.py backend/tests/test_result_quality.py tests/test_hypothesis_service.py
git commit -m "feat: persist product type review evidence"
```

### Task 5：前端展示员工可理解的中文判断

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: 写四状态 UI 测试**

```tsx
expect(screen.getByText("确认非食品")).toBeInTheDocument();
expect(screen.getByText("模型复核")).toBeInTheDocument();
expect(screen.getByText(/不锈钢厨房锅铲/)).toBeInTheDocument();
expect(screen.getByText("允许继续分析")).toBeInTheDocument();
```

另覆盖确认食品、倾向非食品和需要人工复核；断言页面不再向用户展示英文 `PRODUCT_TYPE_VERIFICATION_REQUIRED` 文案。

- [ ] **Step 2: 运行 UI 测试确认 RED**

Run: `cd frontend; npm.cmd test -- --run tests/result-workbench-ui.test.tsx`

Expected: 找不到新的中文状态与证据块。

- [ ] **Step 3: 扩充 API 类型并渲染证据卡**

```ts
export type ProductTypeReviewStatus =
  | "confirmed_non_food"
  | "confirmed_food"
  | "likely_non_food"
  | "needs_review";
```

卡片固定显示“商品类型、判断来源、判断依据、处理结果”；`needs_review` 使用提醒色而非失败红色，`confirmed_food` 使用阻断色。

- [ ] **Step 4: 运行 UI 测试确认 GREEN**

Run: `cd frontend; npm.cmd test -- --run tests/result-workbench-ui.test.tsx`

Expected: 全部通过。

- [ ] **Step 5: 提交前端展示**

```powershell
git add frontend/lib/api/types.ts frontend/components/jobs/stickiness-scorecard.tsx frontend/tests/result-workbench-ui.test.tsx
git commit -m "feat: explain product type review decisions"
```

### Task 6：全量回归、真实失败样例复验和运行验收

**Files:**
- Modify: `docs/优化迭代记录.md`
- Create: `docs/verification/2026-08-01-all-category-food-gate-fallback.md`

- [ ] **Step 1: 运行后端全量测试**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: 0 failed。

- [ ] **Step 2: 运行前端全量测试、类型检查和生产构建**

```powershell
Set-Location frontend
npm.cmd test -- --run
npm.cmd run typecheck
npm.cmd run build
```

Expected: 三条命令退出码均为 0。

- [ ] **Step 3: 检查差异**

Run: `git diff --check`

Expected: 退出码 0；仅允许既有换行提示。

- [ ] **Step 4: 重启软件并检查健康状态**

```powershell
& '.\启动.ps1'
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3000/'
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/api/v1/health/live'
```

Expected: 前端和 API 均返回 HTTP 200。

- [ ] **Step 5: 重新提交锅铲 URL 验收原始问题**

使用工作台重新提交 Walmart 商品 `5818883652`。Expected：任务不再于 5% 返回 `PRODUCT_TYPE_VERIFICATION_REQUIRED`；结果显示“确认非食品”或“倾向非食品”，并进入后续模型分析。不得改写旧任务 `728b5672-34d6-444d-8ca5-efd0886aa5ff`。

- [ ] **Step 6: 记录全部成功和失败**

在 `docs/优化迭代记录.md` 追加测试数量、失败原因、修复、运行状态和回滚范围；在 verification 文档保存非敏感验收摘要，不包含 API Key 或模型原始敏感响应。

- [ ] **Step 7: 提交验收记录**

```powershell
git add docs/优化迭代记录.md docs/verification/2026-08-01-all-category-food-gate-fallback.md
git commit -m "docs: verify all-category food gate fallback"
```
