# 准入证据链与员工行动指引 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 防止无事实依据的硬拒绝，并把结果页改成员工能理解和执行的单一行动结论。

**Architecture:** 在 `HypothesisService` 进入评分器前规范化门禁：没有理由或有效事实引用的 `blocked` 降级为 `needs_verification`；结果质量层继续拒绝任何绕过规范化的无证据硬拒绝。前端新增纯函数展示适配器，将新任务和历史任务统一转换成“价值判断 + 当前处理建议 + 为什么 + 下一步 + 边界说明”，原始枚举只放入技术详情。

**Tech Stack:** Python 3.12、Pydantic、pytest、FastAPI DTO、TypeScript、React、Next.js 15、Vitest、Testing Library、Tailwind CSS。

---

## 文件职责

- `app/services/hypothesis_service.py`：在构造 `GateSignals` 前执行硬拒绝证据规范化。
- `app/domain/stickiness.py`：保持三态评分与动作派生的单一来源，不加入品类特例。
- `backend/application/result_quality.py`：发布前验证拒绝代码、门禁、理由与事实链一致。
- `app/infrastructure/storage/excel_exporter.py`：导出与员工页面使用一致的中文行动语义。
- `frontend/lib/decision-guidance.ts`：新建纯函数，统一生成员工行动结论、原因、下一步和历史证据完整性。
- `frontend/lib/result-labels.ts`：系统枚举及拒绝代码的中文技术标签。
- `frontend/components/jobs/direction-detail.tsx`：显示价值判断和单一员工行动摘要。
- `frontend/components/jobs/stickiness-scorecard.tsx`：移除重复结论，显示原因、下一步、边界说明及折叠技术详情。
- `frontend/components/jobs/direction-list.tsx`：列表使用同一行动结论。
- `tests/test_hypothesis_service.py`、`backend/tests/test_result_quality.py`：领域与发布门禁回归。
- `tests/test_excel_exporter.py`：导出语义回归。
- `frontend/tests/result-workbench.test.ts`、`frontend/tests/result-labels.test.ts`、`frontend/tests/result-workbench-ui.test.tsx`：展示适配与组件回归。

### Task 1: 无证据 blocked 自动降级为待复核

**Files:**
- Modify: `app/services/hypothesis_service.py`
- Test: `tests/test_hypothesis_service.py`

- [ ] **Step 1: 写无证据不兼容和安全阻断的红灯测试**

在 `tests/test_hypothesis_service.py` 新增两个用例，复用现有 `_direction` / 模型响应夹具：

```python
def test_blocked_gate_without_reason_is_downgraded_to_hold():
    direction = _direction(
        compatibility_status="blocked",
        incompatibility_reason="",
        safety_status="blocked",
        safety_risk="",
        source_fact_ids=["title"],
    )

    hypothesis = _run_single_direction(direction)

    assert hypothesis.execution_status == "hold"
    assert hypothesis.compatibility_status == "needs_verification"
    assert hypothesis.safety_status == "needs_verification"
    assert hypothesis.rejection_codes == []
    assert "兼容性阻断缺少具体理由，需补充证据后复核" in hypothesis.missing_evidence
    assert "安全阻断缺少具体风险，需补充证据后复核" in hypothesis.missing_evidence


def test_blocked_gate_without_valid_fact_reference_is_downgraded_to_hold():
    direction = _direction(
        compatibility_status="blocked",
        incompatibility_reason="候选直径大于主品孔径",
        source_fact_ids=["missing:fact"],
    )

    hypothesis = _run_single_direction(direction)

    assert hypothesis.execution_status == "hold"
    assert hypothesis.compatibility_status == "needs_verification"
    assert hypothesis.rejection_codes == []
```

若现有夹具名称不同，使用文件中真实的最小服务调用夹具，不新建绕过服务层的替代实现。

- [ ] **Step 2: 运行红灯**

Run:

```powershell
python -m pytest tests/test_hypothesis_service.py -k "blocked_gate_without" -q
```

Expected: FAIL，现有实现仍输出 `reject` 或保留 `blocked`。

- [ ] **Step 3: 实现门禁证据规范化函数**

在 `app/services/hypothesis_service.py` 增加文件级纯函数：

```python
_BLOCKED_EVIDENCE_RULES = {
    "compatibility_status": (
        "incompatibility_reason",
        "兼容性阻断缺少具体理由或有效事实，需补充证据后复核",
    ),
    "duplication_status": (
        "duplicate_function_reason",
        "重复功能阻断缺少具体理由或有效事实，需补充证据后复核",
    ),
    "safety_status": (
        "safety_risk",
        "安全阻断缺少具体风险或有效事实，需补充证据后复核",
    ),
}


def _normalize_blocked_gate_evidence(
    direction: HypothesisDirectionOutput,
    valid_source_fact_ids: tuple[str, ...],
) -> HypothesisDirectionOutput:
    updates: dict[str, object] = {}
    missing_evidence = list(direction.missing_evidence)
    for status_field, (reason_field, message) in _BLOCKED_EVIDENCE_RULES.items():
        if getattr(direction, status_field) is not GateAssessment.BLOCKED:
            continue
        reason = getattr(direction, reason_field).strip()
        if reason and valid_source_fact_ids:
            continue
        updates[status_field] = GateAssessment.NEEDS_VERIFICATION
        if message not in missing_evidence:
            missing_evidence.append(message)
    if not updates:
        return direction
    updates["missing_evidence"] = missing_evidence
    return direction.model_copy(update=updates)
```

在事实 ID 校验完成之后、构造 `GateSignals` 之前调用：

```python
direction = _normalize_blocked_gate_evidence(direction, valid_ids)
```

禁止根据商品名称或特定品类放行。

- [ ] **Step 4: 运行定向测试转绿**

Run:

```powershell
python -m pytest tests/test_hypothesis_service.py -k "blocked_gate_without" -q
```

Expected: PASS。

- [ ] **Step 5: 运行领域相关回归**

Run:

```powershell
python -m pytest tests/test_hypothesis_service.py tests/test_stickiness.py tests/test_stickiness_regression.py -q
```

Expected: 全部 PASS。

### Task 2: 完整证据硬拒绝与发布质量门禁

**Files:**
- Modify: `backend/application/result_quality.py`
- Test: `tests/test_hypothesis_service.py`
- Test: `backend/tests/test_result_quality.py`

- [ ] **Step 1: 写完整硬拒绝和绕过服务层的红灯测试**

新增：

```python
def test_blocked_gate_with_reason_and_valid_fact_remains_reject():
    direction = _direction(
        compatibility_status="blocked",
        incompatibility_reason="主品孔径 8mm，小于候选笔杆直径 12mm",
        source_fact_ids=["title", "review:10"],
    )

    hypothesis = _run_single_direction(direction)

    assert hypothesis.execution_status == "reject"
    assert hypothesis.rejection_codes == ["incompatible"]
    assert hypothesis.decision_action == "not_recommended"
```

在 `backend/tests/test_result_quality.py` 新增：

```python
def test_reject_without_reason_or_fact_cannot_be_published():
    direction = _direction(
        stickiness_score=94,
        execution_status="reject",
        compatibility_status="blocked",
        incompatibility_reason="",
        source_fact_ids=[],
        rejection_codes=["incompatible"],
    )

    with pytest.raises(ResultQualityError, match="blocked gate lacks evidence"):
        validate_hypothesis_payload(
            _payload([direction]),
            expected_model_version="combination_model_v2.1",
        )
```

- [ ] **Step 2: 运行测试并确认契约现状**

Run:

```powershell
python -m pytest tests/test_hypothesis_service.py -k "blocked_gate_with_reason" backend/tests/test_result_quality.py -k "reject_without_reason_or_fact" -q
```

Expected: 服务层用例在实现前失败；质量门禁用例应通过。如果质量门禁用例失败，修正 `BLOCKED_GATE_CONTRACT` 校验，不放宽断言。

- [ ] **Step 3: 完善发布门禁的错误信息和状态一致性**

保持 `BLOCKED_GATE_CONTRACT`，将通用错误细化为包含代码的稳定信息：

```python
if is_blocked != has_code:
    _fail(f"{code} blocked gate status does not match rejection code")
if is_blocked and (
    not isinstance(direction.get(reason_field), str)
    or not direction[reason_field].strip()
    or not source_fact_ids
):
    _fail(f"{code} blocked gate lacks evidence")
```

再增加：

```python
if direction.get("execution_status") == "reject" and not rejection_codes:
    _fail("Reject candidate must carry at least one rejection code")
if direction.get("execution_status") != "reject" and rejection_codes:
    _fail("Non-reject candidate cannot carry rejection codes")
```

- [ ] **Step 4: 运行质量门禁与 Runner 回归**

Run:

```powershell
python -m pytest backend/tests/test_result_quality.py backend/tests/test_analysis_runner.py -q
```

Expected: 全部 PASS。

### Task 3: 员工行动指引纯函数与历史兼容

**Files:**
- Create: `frontend/lib/decision-guidance.ts`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/result-labels.ts`
- Test: `frontend/tests/result-workbench.test.ts`
- Test: `frontend/tests/result-labels.test.ts`

- [ ] **Step 1: 写员工行动指引红灯测试**

在 `frontend/tests/result-workbench.test.ts` 新增：

```ts
import { buildDecisionGuidance } from "@/lib/decision-guidance";

it("treats an unsupported historical reject as incomplete evidence", () => {
  expect(buildDecisionGuidance({
    model_version: "combination_model_v2.1",
    stickiness_score: 94,
    execution_status: "reject",
    decision_action: "not_recommended",
    rejection_codes: ["incompatible", "safety_blocked"],
    source_fact_ids: ["title"],
    missing_evidence: ["未提供主品笔夹可容纳的最大笔杆直径。"],
  })).toMatchObject({
    status: "historical_incomplete",
    title: "历史判定证据不完整",
    nextStep: "建议按新规则重新分析，并核对：未提供主品笔夹可容纳的最大笔杆直径。",
  });
});

it("explains hold as evidence work rather than permanent rejection", () => {
  expect(buildDecisionGuidance({
    model_version: "combination_model_v2.1",
    stickiness_score: 94,
    execution_status: "hold",
    missing_evidence: ["核对笔夹最大直径与候选笔杆直径"],
  })).toMatchObject({
    status: "hold",
    title: "补充证据后复核",
    meaning: "当前证据不足，不代表这个辅品不能做。",
  });
});

it("shows a concrete reason for a fully evidenced rejection", () => {
  expect(buildDecisionGuidance({
    model_version: "combination_model_v2.1",
    execution_status: "reject",
    rejection_codes: ["incompatible"],
    compatibility_status: "blocked",
    incompatibility_reason: "主品孔径 8mm，小于候选直径 12mm",
    source_fact_ids: ["spec:main", "spec:candidate"],
  })).toMatchObject({
    status: "reject",
    title: "当前方案暂不进入测试",
    reason: "主品孔径 8mm，小于候选直径 12mm",
  });
});
```

- [ ] **Step 2: 运行红灯**

Run:

```powershell
Set-Location frontend
npm.cmd test -- --run tests/result-workbench.test.ts tests/result-labels.test.ts
```

Expected: FAIL，`decision-guidance` 尚不存在。

- [ ] **Step 3: 扩充前端类型并实现纯函数**

在 `frontend/lib/api/types.ts` 的 `StructuredDirection` 增加或确认：

```ts
compatibility_status?: "clear" | "needs_verification" | "blocked";
duplication_status?: "clear" | "needs_verification" | "blocked";
safety_status?: "clear" | "needs_verification" | "blocked";
incompatibility_reason?: string;
duplicate_function_reason?: string;
safety_risk?: string;
source_fact_ids?: string[];
rejection_codes?: string[];
missing_evidence?: string[];
```

新建 `frontend/lib/decision-guidance.ts`：

```ts
import type { StructuredDirection } from "@/lib/api/types";

export type EmployeeDecisionStatus =
  | "pass"
  | "hold"
  | "reject"
  | "historical_incomplete";

export interface DecisionGuidance {
  status: EmployeeDecisionStatus;
  title: string;
  reason: string;
  nextStep: string;
  meaning: string;
}

const rejectReasonFields = {
  incompatible: ["compatibility_status", "incompatibility_reason"],
  duplicate_function: ["duplication_status", "duplicate_function_reason"],
  safety_blocked: ["safety_status", "safety_risk"],
} as const;

function firstMissingEvidence(direction: StructuredDirection): string {
  return direction.missing_evidence?.find((item) => item.trim()) ?? "";
}

function hasCompleteRejectEvidence(direction: StructuredDirection): boolean {
  const codes = direction.rejection_codes ?? [];
  if (!codes.length) return false;
  if (codes.includes("food_blocked")) return direction.product_type_status === "food"
    || direction.product_type_status === "ingestible";
  return codes.every((code) => {
    const fields = rejectReasonFields[code as keyof typeof rejectReasonFields];
    if (!fields) return true;
    const [statusField, reasonField] = fields;
    return direction[statusField] === "blocked"
      && Boolean(direction[reasonField]?.trim())
      && Boolean(direction.source_fact_ids?.length);
  });
}

export function buildDecisionGuidance(
  direction: StructuredDirection
): DecisionGuidance {
  const missing = firstMissingEvidence(direction);
  if (
    direction.execution_status === "reject"
    && !hasCompleteRejectEvidence(direction)
  ) {
    return {
      status: "historical_incomplete",
      title: "历史判定证据不完整",
      reason: "旧结果包含拒绝代码，但没有保存完整的阻断理由和事实来源。",
      nextStep: `建议按新规则重新分析${missing ? `，并核对：${missing}` : "。"}`,
      meaning: "不能据此判断这个辅品永久不能做。",
    };
  }
  if (direction.execution_status === "reject") {
    const reason = direction.incompatibility_reason
      || direction.duplicate_function_reason
      || direction.safety_risk
      || "已有事实确认当前候选存在阻断。";
    return {
      status: "reject",
      title: "当前方案暂不进入测试",
      reason,
      nextStep: "更换具体候选商品或解除上述阻断后重新分析。",
      meaning: "这是对当前候选方案的判断，不是否定整个辅品品类。",
    };
  }
  if (direction.execution_status === "hold") {
    return {
      status: "hold",
      title: "补充证据后复核",
      reason: missing || "当前兼容、安全或产品信息尚未核实完整。",
      nextStep: missing ? `请核对：${missing}` : "补齐缺失证据后重新评估。",
      meaning: "当前证据不足，不代表这个辅品不能做。",
    };
  }
  return {
    status: "pass",
    title: "可进入测试",
    reason: direction.direction_reason || "当前未发现确定阻断。",
    nextStep: "按最终测试等级执行，并继续核对具体商品规格。",
    meaning: "通过准入不等于保证销售结果，仍需用市场测试验证。",
  };
}
```

在 `result-labels.ts` 新增 `rejectionCodeLabel`，只用于技术详情：

```ts
const rejectionCodeLabels: LabelMap = {
  incompatible: "已确认存在规格冲突",
  duplicate_function: "已确认核心功能重复",
  safety_blocked: "已确认存在具体安全风险",
  food_blocked: "属于禁止的食品或可摄入品",
  reverse_dependency: "购买方向与组合目标相反",
  no_valid_relation: "没有有效的共同购买任务",
};

export function rejectionCodeLabel(value: string): string {
  return withOriginal(value, rejectionCodeLabels[value]);
}
```

- [ ] **Step 4: 运行纯函数测试转绿和类型检查**

Run:

```powershell
npm.cmd test -- --run tests/result-workbench.test.ts tests/result-labels.test.ts
npm.cmd run typecheck
```

Expected: 全部 PASS。

### Task 4: 结果页改为单一员工行动结论

**Files:**
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/components/jobs/direction-list.tsx`
- Test: `frontend/tests/result-workbench-ui.test.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: 写页面红灯测试**

在 `frontend/tests/result-workbench-ui.test.tsx` 扩展现有
`shows one Chinese eligibility status...` 用例：

```ts
expect(screen.getAllByText("补充证据后复核")).toHaveLength(1);
expect(screen.getByText("为什么")).toBeInTheDocument();
expect(screen.getByText("下一步")).toBeInTheDocument();
expect(
  screen.getByText("当前证据不足，不代表这个辅品不能做。")
).toBeInTheDocument();
expect(screen.queryByText("执行状态")).not.toBeInTheDocument();
expect(screen.queryByText("最终动作")).not.toBeInTheDocument();
```

再新增历史样本用例：

```ts
it("does not present an unsupported historical rejection as a confirmed fact", () => {
  render(<ResultAnalysisModule structuredDirections={[{
    ...directions[0],
    model_version: "combination_model_v2.1",
    stickiness_score: 94,
    execution_status: "reject",
    decision_action: "not_recommended",
    rejection_codes: ["incompatible", "safety_blocked"],
    source_fact_ids: ["title"],
    missing_evidence: ["未提供主品笔夹可容纳的最大笔杆直径。"],
  }]} />);

  expect(screen.getAllByText("历史判定证据不完整")).toHaveLength(1);
  expect(screen.getByText("不能据此判断这个辅品永久不能做。")).toBeInTheDocument();
  expect(screen.queryByText("确认不符合准入条件")).not.toBeInTheDocument();
  expect(screen.queryByText("不建议（not_recommended）")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: 运行红灯**

Run:

```powershell
npm.cmd test -- --run tests/result-workbench-ui.test.tsx -t "Chinese eligibility|historical rejection"
```

Expected: FAIL，旧组件仍显示重复状态。

- [ ] **Step 3: 改造 `DirectionDetail` 摘要**

使用：

```ts
const guidance = buildDecisionGuidance(direction);
```

摘要卡只显示：

```tsx
<Badge variant={guidance.status === "reject" ? "destructive" : "default"}>
  {guidance.title}
</Badge>
<span>粘性潜力：{directionFinalScore(direction)}/100</span>
```

保留核心理由和购买链路，但不再从 `executionStatusLabel` /
`recommendationDisplayLabel` 生成第二套结论。

- [ ] **Step 4: 改造 `StickinessScorecard`**

把三列网格替换为两列：

```tsx
<div className="grid gap-4 border-b p-4 lg:grid-cols-2">
  <section>
    <span className="text-xs text-muted-foreground">价值判断</span>
    <strong className="mt-1 block text-2xl">
      粘性潜力：{directionFinalScore(direction)}/100
    </strong>
  </section>
  <section>
    <span className="text-xs text-muted-foreground">当前处理建议</span>
    <strong className="mt-1 block text-xl">{guidance.title}</strong>
  </section>
</div>
<div className="grid gap-4 border-b p-4 lg:grid-cols-3">
  <GuidanceItem label="为什么" value={guidance.reason} />
  <GuidanceItem label="下一步" value={guidance.nextStep} />
  <GuidanceItem label="这意味着" value={guidance.meaning} />
</div>
```

删除顶部重复“已淘汰”横幅和底部“推荐等级”行。新增默认收起技术详情：

```tsx
<details className="border-t px-4 py-3 text-xs text-muted-foreground">
  <summary className="cursor-pointer font-medium text-foreground">技术详情</summary>
  <dl className="mt-3 grid gap-2 sm:grid-cols-[140px_minmax(0,1fr)]">
    <dt>执行状态</dt><dd>{direction.execution_status ?? "-"}</dd>
    <dt>最终动作</dt><dd>{direction.decision_action ?? "-"}</dd>
    <dt>拒绝代码</dt>
    <dd>{direction.rejection_codes?.map(rejectionCodeLabel).join("、") || "-"}</dd>
  </dl>
</details>
```

- [ ] **Step 5: 统一方向列表状态**

`direction-list.tsx` 使用 `buildDecisionGuidance(direction).title`，不直接映射
`execution_status` 或 `recommendation_level`。

- [ ] **Step 6: 运行组件回归与类型检查**

Run:

```powershell
npm.cmd test -- --run tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx
npm.cmd run typecheck
```

Expected: 全部 PASS。

### Task 5: Excel 导出使用一致行动语义

**Files:**
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Test: `tests/test_excel_exporter.py`

- [ ] **Step 1: 写导出红灯测试**

新增：

```python
def test_excel_uses_employee_action_language_for_hold_and_reject():
    hold_row = _export_direction_row(
        execution_status="hold",
        missing_evidence=["核对笔夹与笔杆直径"],
    )
    reject_row = _export_direction_row(
        execution_status="reject",
        compatibility_status="blocked",
        incompatibility_reason="主品孔径小于候选直径",
        source_fact_ids=["spec:main", "spec:candidate"],
        rejection_codes=["incompatible"],
    )

    assert hold_row["当前处理建议"] == "补充证据后复核"
    assert hold_row["下一步"] == "请核对：核对笔夹与笔杆直径"
    assert reject_row["当前处理建议"] == "当前方案暂不进入测试"
    assert reject_row["具体原因"] == "主品孔径小于候选直径"
```

- [ ] **Step 2: 运行红灯**

Run:

```powershell
python -m pytest tests/test_excel_exporter.py -k "employee_action_language" -q
```

Expected: FAIL，新列尚不存在。

- [ ] **Step 3: 新增 Python 侧员工行动映射**

在 `excel_exporter.py` 增加局部纯函数，保持与前端相同顺序：

```python
def _employee_guidance(hypothesis: HypothesisDTO) -> tuple[str, str, str]:
    if hypothesis.execution_status == "hold":
        reason = next(iter(hypothesis.missing_evidence), "当前证据尚未核实完整")
        return "补充证据后复核", reason, f"请核对：{reason}"
    if hypothesis.execution_status == "reject":
        reason = (
            hypothesis.incompatibility_reason
            or hypothesis.duplicate_function_reason
            or hypothesis.safety_risk
            or "历史判定证据不完整，建议重新分析"
        )
        title = (
            "当前方案暂不进入测试"
            if reason != "历史判定证据不完整，建议重新分析"
            else "历史判定证据不完整"
        )
        return title, reason, "解除阻断或更换候选后重新分析"
    return "可进入测试", hypothesis.direction_reason or "当前未发现确定阻断", "按测试等级执行"
```

在候选导出列加入 `当前处理建议`、`具体原因`、`下一步`；原始执行状态和拒绝码保留为审计列。

- [ ] **Step 4: 运行导出与 Runner 回归**

Run:

```powershell
python -m pytest tests/test_excel_exporter.py backend/tests/test_analysis_runner.py -q
```

Expected: 全部 PASS。

### Task 6: 全量验证、运行态与记录

**Files:**
- Modify: `docs/优化迭代记录.md`
- Create: `docs/verification/2026-07-31-decision-evidence-and-employee-guidance.md`

- [ ] **Step 1: 运行 Python 定向质量检查**

Run:

```powershell
python -m pytest tests/test_hypothesis_service.py tests/test_stickiness.py tests/test_stickiness_regression.py tests/test_excel_exporter.py backend/tests/test_result_quality.py backend/tests/test_analysis_runner.py -q
python -m ruff check app/services/hypothesis_service.py backend/application/result_quality.py app/infrastructure/storage/excel_exporter.py tests/test_hypothesis_service.py tests/test_excel_exporter.py backend/tests/test_result_quality.py
```

Expected: 全部 PASS，Ruff 0 errors。

- [ ] **Step 2: 运行 Python 全量回归**

Run:

```powershell
python -m pytest -q
```

Expected: 0 failures。既有异步清理 warning 单独记录，不把 warning 误报为失败。

- [ ] **Step 3: 运行前端全量回归**

Run:

```powershell
Set-Location frontend
npm.cmd test -- --run
npm.cmd run typecheck
```

Expected: 0 failures；既有 MSW `/settings/providers` 未匹配提示记录为测试噪声。

- [ ] **Step 4: 确认 Next dev 进程后安全停止**

先通过端口和命令行确认 PID 属于
`F:\组合品7-31\web-platform-v2.1-work\frontend`，再执行：

```powershell
$nextDevPid = <已核对的父进程 PID>
Stop-Process -Id $nextDevPid -Force -ErrorAction Stop
if (Get-Process -Id $nextDevPid -ErrorAction SilentlyContinue) {
    throw "Next dev process is still running"
}
if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 3000 is still listening"
}
```

不得把停止和构建用普通分号连接；停止失败必须终止。

- [ ] **Step 5: 生产构建并重启开发服务**

Run:

```powershell
npm.cmd run build
```

Expected: Next.js build exit 0。随后用隐藏窗口启动 `npm.cmd run dev`，日志写入项目
`frontend` 下的验证日志，不输出或记录 API Key。

- [ ] **Step 6: HTTP 与浏览器验收**

验证：

```powershell
Invoke-WebRequest http://127.0.0.1:3000/jobs/01dd4c75-c84f-49b9-8eca-29d61fdc6e7a -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health/ready -UseBasicParsing
```

Expected: 两者 HTTP 200；ready 中 database、redis、worker、contract_match 均为 `ok`。

浏览器检查样本历史任务：

- 只显示一个“历史判定证据不完整”；
- 保留 94/100；
- 显示原因、下一步和“不能据此判断永久不能做”；
- 主视图不再显示“不建议（not_recommended）”或“确认不符合准入条件”；
- 技术详情仍可查看原始拒绝代码。

- [ ] **Step 7: 写验证报告和迭代记录**

`docs/verification/2026-07-31-decision-evidence-and-employee-guidance.md` 记录：

- 修改范围；
- RED→GREEN 证据；
- 定向及全量测试计数；
- Ruff、TypeScript、构建和探活结果；
- 历史任务只读边界；
- 已知基线 warning；
- 回滚文件清单。

把所有预期红灯、意外失败和最终成功分别追加到
`docs/优化迭代记录.md`，每次操作前继续先读取该文件。

## 提交说明

计划中的“频繁提交”不在当前脏工作区自动执行。只有用户明确要求提交时，才按任务
边界精确暂存本次文件；不得把用户和前序任务的无关修改混入提交。
