# 全品类非食品组合选品与三态门禁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有常规非食品品类共享同一套“主辅品不可摄入”规则，并消除普通风险说明触发硬淘汰、分数显示错误和状态重复的问题。

**Architecture:** 新建独立的商品可摄入分类器，确定性短语规则优先、模型只提供结构化证据、服务器最终裁决。商品类型门禁先于候选生成/评分；非食品候选的六维潜力分与三态业务门禁独立计算，再由结果质量层校验并统一输出到 API、JSON、Excel 和页面。

**Tech Stack:** Python 3.12、Pydantic、FastAPI、pytest、React 19、TypeScript、Vitest、Next.js 15。

---

## 约束与文件边界

- 不修改 V2.1 六维权重和既有 70/78/85 阈值。
- 不增加宠物、家居、汽车等单品类业务特例。
- 不重算或覆盖历史任务。
- 主品与辅品统一采用 `non_food / ingestible / unknown`。
- `food_filter_status` 仅保留为旧协议派生字段，不能独立裁决。

**Files:**
- Create: `app/domain/ingestible_classifier.py`
- Modify: `app/domain/pairing_policy.py`
- Modify: `app/domain/schemas/hypothesis.py`
- Modify: `app/domain/dto/__init__.py`
- Modify: `app/services/hypothesis_service.py`
- Modify: `app/services/market_evidence_service.py`
- Modify: `app/domain/stickiness.py`
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt`
- Modify: `backend/application/analysis_runner.py`
- Modify: `backend/application/result_quality.py`
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/result-labels.ts`
- Modify: `frontend/lib/result-workbench.ts`
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/components/jobs/direction-list.tsx`
- Tests: corresponding files under `tests/`, `backend/tests/`, and `frontend/tests/`

### Task 1：建立全局不可摄入商品分类契约

**Files:**
- Create: `app/domain/ingestible_classifier.py`
- Modify: `app/domain/pairing_policy.py`
- Test: `tests/test_ingestible_classifier.py`

- [ ] **Step 1: 写跨品类失败测试**

```python
import pytest
from app.domain.ingestible_classifier import classify_product_type
from app.domain.pairing_policy import ProductTypeStatus


@pytest.mark.parametrize(
    "title",
    [
        "stainless steel water bottle",
        "glass food storage container",
        "vitamin pill organizer",
        "electric pepper grinder",
        "pet feeding bowl",
        "external use facial cleansing brush",
        "automotive fuel filter",
    ],
)
def test_non_ingestible_products_are_allowed(title):
    assert classify_product_type(title).status is ProductTypeStatus.NON_FOOD


@pytest.mark.parametrize(
    "title",
    [
        "bottled spring water",
        "protein drink",
        "vitamin C tablets",
        "prescription oral medicine",
        "dog food",
        "pet joint supplement chews",
    ],
)
def test_ingestible_products_are_blocked(title):
    assert classify_product_type(title).status is ProductTypeStatus.INGESTIBLE


def test_missing_or_conflicting_product_type_is_unknown():
    assert classify_product_type("ACME Model X").status is ProductTypeStatus.UNKNOWN
```

- [ ] **Step 2: 运行并确认红灯**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ingestible_classifier.py -q`

Expected: FAIL，因为模块和 `INGESTIBLE` 枚举尚不存在。

- [ ] **Step 3: 替换商品类型枚举**

在 `app/domain/pairing_policy.py` 中定义：

```python
class ProductTypeStatus(StrEnum):
    NON_FOOD = "non_food"
    INGESTIBLE = "ingestible"
    UNKNOWN = "unknown"
```

- [ ] **Step 4: 实现短语优先分类器**

```python
from dataclasses import dataclass
from app.domain.pairing_policy import ProductTypeStatus


@dataclass(frozen=True)
class ProductTypeDecision:
    status: ProductTypeStatus
    reason: str
    matched_terms: tuple[str, ...] = ()


def classify_product_type(title: str, *, product_type: str = "", description: str = "") -> ProductTypeDecision:
    text = normalize_text(" ".join((title, product_type, description)))
    non_food_matches = find_phrase_matches(text, NON_FOOD_PHRASES)
    ingestible_matches = find_phrase_matches(text, INGESTIBLE_PHRASES)
    if non_food_matches and not ingestible_matches:
        return ProductTypeDecision(ProductTypeStatus.NON_FOOD, "confirmed non-ingestible product")
    if ingestible_matches and not non_food_matches:
        return ProductTypeDecision(ProductTypeStatus.INGESTIBLE, "product is designed to be ingested")
    if non_food_matches and ingestible_matches:
        return ProductTypeDecision(ProductTypeStatus.UNKNOWN, "conflicting product-type evidence")
    return ProductTypeDecision(ProductTypeStatus.UNKNOWN, "insufficient deterministic product-type evidence")
```

短语表必须覆盖测试中的语义对照；短语优先于单词，禁止用 `water`、`food`、`vitamin` 单词独立裁决。若不可摄入与可摄入证据同时存在，必须返回 unknown，禁止以规则顺序静默覆盖冲突。

- [ ] **Step 5: 运行测试并提交**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ingestible_classifier.py -q`

Expected: PASS。

```powershell
git add app/domain/ingestible_classifier.py app/domain/pairing_policy.py tests/test_ingestible_classifier.py
git commit -m "feat: add all-category ingestible classifier"
```

### Task 2：在主品入口执行不可摄入门禁

**Files:**
- Modify: `backend/application/analysis_runner.py`
- Modify: `backend/application/result_quality.py`
- Test: `backend/tests/test_analysis_runner.py`
- Test: `backend/tests/test_result_quality.py`

- [ ] **Step 1: 写主品食品停止测试**

```python
async def test_ingestible_main_product_stops_before_hypothesis_generation(runner, llm):
    product = product_fixture(title="Vitamin C Tablets", product_type="dietary supplement")
    result = await runner.run_product(product)
    assert result.error_code == "UNSUPPORTED_INGESTIBLE_MAIN_PRODUCT"
    llm.generate_hypotheses.assert_not_awaited()
```

- [ ] **Step 2: 写主品未知暂停测试**

```python
async def test_unknown_main_product_type_requires_verification(runner, llm):
    product = product_fixture(title="ACME Model X", product_type="")
    result = await runner.run_product(product)
    assert result.result_status == "main_product_type_needs_verification"
    llm.generate_hypotheses.assert_not_awaited()
```

- [ ] **Step 3: 运行并确认红灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_quality.py -q`

Expected: FAIL，当前 runner 没有主品类型前置门禁。

- [ ] **Step 4: 在模型调用前裁决**

在主品抓取完成、构造 prompt 之前调用：

```python
product_type = classify_product_type(
    product.title,
    product_type=product.product_type,
    description=product.description,
)
if product_type.status is ProductTypeStatus.INGESTIBLE:
    return unsupported_ingestible_result(product, product_type)
if product_type.status is ProductTypeStatus.UNKNOWN:
    return product_type_verification_result(product, product_type)
```

两类结果必须携带中文理由，但不得创建虚假候选。

- [ ] **Step 5: 运行测试并提交**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_quality.py -q`

Expected: PASS。

```powershell
git add backend/application/analysis_runner.py backend/application/result_quality.py backend/tests/test_analysis_runner.py backend/tests/test_result_quality.py
git commit -m "feat: gate ingestible main products"
```

### Task 3：辅品统一使用商品类型门禁

**Files:**
- Modify: `app/services/hypothesis_service.py`
- Modify: `app/services/market_evidence_service.py`
- Modify: `app/domain/dto/__init__.py`
- Test: `tests/test_hypothesis_service.py`
- Test: `tests/test_market_evidence_service.py`

- [ ] **Step 1: 写三种辅品结果测试**

```python
def test_candidate_type_gate_precedes_business_scoring(service):
    output = hypothesis_output(
        candidates=[
            candidate("stainless water bottle"),
            candidate("bottled spring water"),
            candidate("ACME refill"),
        ]
    )
    directions = service.parse(output)
    by_name = {item.name: item for item in directions}
    assert by_name["stainless water bottle"].product_type_status == "non_food"
    assert by_name["bottled spring water"].product_type_status == "ingestible"
    assert by_name["bottled spring water"].rejection_codes == ["ingestible_blocked"]
    assert by_name["ACME refill"].product_type_status == "unknown"
    assert by_name["ACME refill"].execution_status == "hold"
```

- [ ] **Step 2: 运行并确认红灯**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hypothesis_service.py tests/test_market_evidence_service.py -q`

Expected: FAIL，当前仍使用 `food/allowed/needs_verification` 双轨状态。

- [ ] **Step 3: 使用统一裁决**

```python
classification = classify_product_type(
    direction.canonical_name,
    product_type=direction.product_type_status,
    description=" ".join(direction.keywords.values()),
)
food_blocked = classification.status is ProductTypeStatus.INGESTIBLE
product_type_unknown = classification.status is ProductTypeStatus.UNKNOWN
```

`food_filter_status` 兼容映射固定为：

```python
{
    "non_food": "allowed",
    "ingestible": "food",
    "unknown": "needs_verification",
}
```

市场证据重算必须从 `product_type_status` 重建门禁，不能从旧字段独立判断。

- [ ] **Step 4: 运行测试并提交**

Run: `.venv\Scripts\python.exe -m pytest tests/test_hypothesis_service.py tests/test_market_evidence_service.py -q`

Expected: PASS。

```powershell
git add app/services/hypothesis_service.py app/services/market_evidence_service.py app/domain/dto/__init__.py tests/test_hypothesis_service.py tests/test_market_evidence_service.py
git commit -m "fix: unify candidate ingestible gating"
```

### Task 4：把业务风险改为三态门禁

**Files:**
- Modify: `app/domain/pairing_policy.py`
- Modify: `app/domain/schemas/hypothesis.py`
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt`
- Modify: `app/services/hypothesis_service.py`
- Modify: `app/domain/stickiness.py`
- Test: `tests/test_prompts.py`
- Test: `tests/test_hypothesis_service.py`
- Test: `tests/test_stickiness.py`
- Test: `tests/test_stickiness_regression.py`

- [ ] **Step 1: 写 schema 与 prompt 红灯测试**

```python
def test_gate_assessment_has_three_states():
    assert {item.value for item in GateAssessment} == {
        "clear", "needs_verification", "blocked"
    }


def test_prompt_forbids_using_risk_text_as_blocked_status(prompt_text):
    assert "blocked 必须有确认阻断事实" in prompt_text
    assert "信息不足只能使用 needs_verification" in prompt_text
```

- [ ] **Step 2: 写裁决红灯测试**

```python
def test_unverified_high_score_candidate_is_hold_with_score_preserved():
    result = compute_stickiness(
        v21_ratings_for(84),
        EvidenceLevel.E1,
        GateSignals(compatibility_unverified=True, safety_unverified=True),
    )
    assert result.stickiness_score == 84
    assert result.execution_status == "hold"
    assert result.rejection_codes == ()


def test_confirmed_block_still_rejects_high_score():
    result = compute_stickiness(
        v21_ratings_for(100),
        EvidenceLevel.E4,
        GateSignals(incompatible=True),
    )
    assert result.execution_status == "reject"
    assert result.rejection_codes == ("incompatible",)
```

- [ ] **Step 3: 运行并确认红灯**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompts.py tests/test_hypothesis_service.py tests/test_stickiness.py tests/test_stickiness_regression.py -q`

Expected: FAIL，三态字段尚不存在且文本仍触发硬拒绝。

- [ ] **Step 4: 定义并接入三态**

```python
class GateAssessment(StrEnum):
    CLEAR = "clear"
    NEEDS_VERIFICATION = "needs_verification"
    BLOCKED = "blocked"
```

`HypothesisDirectionOutput` 增加：

```python
compatibility_status: GateAssessment
duplication_status: GateAssessment
safety_status: GateAssessment
```

服务端构造门禁：

```python
incompatible = direction.compatibility_status is GateAssessment.BLOCKED
compatibility_unverified = direction.compatibility_status is GateAssessment.NEEDS_VERIFICATION
duplicate_function = direction.duplication_status is GateAssessment.BLOCKED
safety_blocked = direction.safety_status is GateAssessment.BLOCKED
safety_unverified = direction.safety_status is GateAssessment.NEEDS_VERIFICATION
```

删除 `bool(reason.strip())` 三处硬拒绝触发；理由只用于解释。

- [ ] **Step 5: 运行测试并提交**

Run: `.venv\Scripts\python.exe -m pytest tests/test_prompts.py tests/test_hypothesis_service.py tests/test_stickiness.py tests/test_stickiness_regression.py -q`

Expected: PASS。

```powershell
git add app/domain/pairing_policy.py app/domain/schemas/hypothesis.py app/infrastructure/llm/prompts/hypothesis_a.txt app/services/hypothesis_service.py app/domain/stickiness.py tests/test_prompts.py tests/test_hypothesis_service.py tests/test_stickiness.py tests/test_stickiness_regression.py
git commit -m "fix: use tri-state business gates"
```

### Task 5：增加拒绝可审计性和批量异常校验

**Files:**
- Modify: `backend/application/result_quality.py`
- Modify: `backend/application/analysis_runner.py`
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Test: `backend/tests/test_result_quality.py`
- Test: `backend/tests/test_analysis_runner.py`
- Test: `tests/test_excel_exporter.py`

- [ ] **Step 1: 写无理由拒绝失败测试**

```python
def test_blocked_gate_requires_reason_and_source_fact():
    direction = _direction(
        compatibility_status="blocked",
        incompatibility_reason="",
        source_fact_ids=[],
        rejection_codes=["incompatible"],
    )
    with pytest.raises(ResultQualityError, match="blocked gate lacks evidence"):
        validate_result_payload(_payload(directions=[direction]))
```

- [ ] **Step 2: 写整批同码异常测试**

```python
def test_repeated_multi_rejection_pattern_is_invalid():
    directions = [
        _direction(
            name=f"candidate-{index}",
            rejection_codes=["incompatible", "duplicate_function", "safety_blocked"],
        )
        for index in range(8)
    ]
    with pytest.raises(ResultQualityError, match="suspicious rejection pattern"):
        validate_result_payload(_payload(directions=directions))
```

- [ ] **Step 3: 运行并确认红灯**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_result_quality.py backend/tests/test_analysis_runner.py tests/test_excel_exporter.py -q`

Expected: FAIL，当前质量门禁只校验字段形状和计数。

- [ ] **Step 4: 实现 code→状态→理由→事实映射**

```python
REJECTION_REQUIREMENTS = {
    "incompatible": ("compatibility_status", "incompatibility_reason"),
    "duplicate_function": ("duplication_status", "duplicate_function_reason"),
    "safety_blocked": ("safety_status", "safety_risk"),
}
```

每个业务硬拒绝码要求状态为 `blocked`、理由非空且有有效 `source_fact_ids`。`ingestible_blocked` 要求商品类型为 `ingestible` 和分类理由。

在 runner 与 Excel 中持久化三态状态、中文理由、来源事实和潜力分。

- [ ] **Step 5: 测试并提交**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_result_quality.py backend/tests/test_analysis_runner.py tests/test_excel_exporter.py -q`

Expected: PASS。

```powershell
git add backend/application/result_quality.py backend/application/analysis_runner.py app/infrastructure/storage/excel_exporter.py backend/tests/test_result_quality.py backend/tests/test_analysis_runner.py tests/test_excel_exporter.py
git commit -m "fix: require auditable rejection evidence"
```

### Task 6：修复分数并合并页面状态

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/result-workbench.ts`
- Modify: `frontend/lib/result-labels.ts`
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/components/jobs/direction-list.tsx`
- Test: `frontend/tests/result-workbench.test.ts`
- Test: `frontend/tests/result-workbench-ui.test.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: 写 V2.1 分数红灯测试**

```typescript
expect(directionFinalScore({ stickiness_score: 84 })).toBe(84);
```

- [ ] **Step 2: 写统一状态红灯测试**

```typescript
expect(screen.getByText("待补证据后复核")).toBeInTheDocument();
expect(screen.getByText("粘性潜力：84/100")).toBeInTheDocument();
expect(screen.queryByText("拒绝（reject）")).not.toBeInTheDocument();
expect(screen.queryByText("不建议（not_recommended）")).not.toBeInTheDocument();
```

- [ ] **Step 3: 运行并确认红灯**

Run: `npm test -- --run tests/result-workbench.test.ts tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx`

Working directory: `frontend`

Expected: FAIL，当前分数辅助函数忽略 `stickiness_score` 且页面重复状态。

- [ ] **Step 4: 修复分数读取**

```typescript
export function directionFinalScore(direction: {
  stickiness_score?: number;
  final_score?: number;
  score?: number;
}): number {
  return direction.stickiness_score ?? direction.final_score ?? direction.score ?? 0;
}
```

- [ ] **Step 5: 统一主状态与中文动作**

```typescript
const statusLabel = {
  pass: "可进入测试",
  hold: "待补证据后复核",
  reject: "确认不符合准入条件",
}[direction.execution_status ?? "hold"];
```

主视图显示一个状态、粘性潜力分、商品类型、确认理由或补证清单。英文枚举只允许出现在“原始数据”折叠区。

- [ ] **Step 6: 测试并提交**

Run: `npm test -- --run tests/result-workbench.test.ts tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx`

Working directory: `frontend`

Expected: PASS。

```powershell
git add frontend/lib/api/types.ts frontend/lib/result-workbench.ts frontend/lib/result-labels.ts frontend/components/jobs/direction-detail.tsx frontend/components/jobs/stickiness-scorecard.tsx frontend/components/jobs/direction-list.tsx frontend/tests/result-workbench.test.ts frontend/tests/result-workbench-ui.test.tsx frontend/tests/job-detail.test.tsx
git commit -m "fix: clarify all-category eligibility results"
```

### Task 7：全量回归与跨品类真实验收

**Files:**
- Create: `docs/verification/2026-07-31-all-category-non-ingestible-gates.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Python 全量回归**

Run: `$env:PYTHONUTF8='1'; .venv\Scripts\python.exe -m pytest -q`

Expected: 全部通过，不新增警告。

- [ ] **Step 2: Ruff**

Run: `.venv\Scripts\python.exe -m ruff check app backend tests`

Expected: 退出码 0。

- [ ] **Step 3: 前端全量回归**

Run: `npm test -- --run`

Working directory: `frontend`

Expected: 全部通过。

- [ ] **Step 4: TypeScript 检查**

Run: `npm run typecheck`

Working directory: `frontend`

Expected: 退出码 0。

- [ ] **Step 5: 生产构建**

先停止或隔离正在运行的 `next dev`，再运行：

Run: `npm run build`

Working directory: `frontend`

Expected: 7 个路由构建成功。构建后使用 `启动.ps1` 重启开发实例，避免 `.next` 混用。

- [ ] **Step 6: 跨品类非食品真实任务**

分别创建家居、消费电子、汽车配件、服装/箱包、工具、宠物用品六类新任务。

Expected:

- 主品均判定 `non_food`；
- 辅品没有可摄入商品；
- 未知尺寸/材质/安全条件进入 hold；
- reject 均有确认依据；
- 页面、API、JSON、Excel一致。

- [ ] **Step 7: 可摄入主品反例**

分别使用食品、饮料、药品/维生素、口服保健品、宠物食品新建任务。

Expected: 候选生成前停止，明确返回“不支持可摄入主品”，不调用 LLM 生成辅品。

- [ ] **Step 8: 语义对照验收**

验证：

- `water bottle` 允许，`bottled water` 禁止；
- `vitamin organizer` 允许，`vitamin tablets` 禁止；
- `food storage container` 允许，`dog food` 禁止；
- 标题缺失或冲突进入 unknown。

- [ ] **Step 9: 历史边界**

确认任务 `9bdce5c4-568b-49f9-b173-e4044afab1b7` 未修改。用相同 URL 新建任务验证新规则，不覆盖旧任务。

- [ ] **Step 10: 差异与记录**

Run: `git diff --check`

Expected: 退出码 0。

将每次失败、真实任务 ID、四端一致性、已知限制和回滚方法写入验证报告与中文迭代记录。

- [ ] **Step 11: 提交**

```powershell
git add docs/verification/2026-07-31-all-category-non-ingestible-gates.md docs/优化迭代记录.md
git commit -m "docs: verify all-category non-ingestible gates"
```

## 最终验收标准

1. 所有常规非食品品类使用同一套分类与门禁。
2. 主品和辅品均不能是可摄入商品。
3. 药品、维生素、口服保健品和宠物口服商品全部被排除。
4. 水瓶、饭盒、锅具、餐具等食品接触类非食品不会被误杀。
5. unknown 永远不能 pass；只能暂停或 hold。
6. 普通风险文本不会触发硬拒绝。
7. reject 必须有 blocked 状态、具体理由和来源事实。
8. 非食品 hold/reject 保留真实粘性潜力分。
9. 页面不重复显示“拒绝 / 不建议 / 淘汰”。
10. 异常整批同码结果被质量门禁拦截。
11. API、JSON、Excel、页面四端一致。
12. 历史任务保持只读。

## 回滚

- 分类器、三态门禁、质量校验和前端展示按任务提交独立回滚。
- 回滚不得删除新任务或改写历史任务。
- 若分类器产生跨品类误判，优先回滚对应分类提交，不回滚 V2.1 评分权重或数据库。
