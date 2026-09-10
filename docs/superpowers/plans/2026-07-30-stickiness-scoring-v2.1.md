# 高精准组合粘性评分 V2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将证据封顶评分替换为粘性分、证据等级和执行状态三轴决策。

**Architecture:** 在领域层集中购买方向、风险、评分上限和动作矩阵；候选服务、证据、持久化和前端只消费该领域决定。V2.0 历史结果只读兼容。

**Tech Stack:** Python 3.13、Pydantic、pytest、FastAPI、pandas、Next.js 15、TypeScript、Vitest。

---

### Task 1: V2.1 领域策略与回归矩阵

**Files:**
- Create: `app/domain/pairing_policy.py`
- Modify: `app/domain/stickiness.py`
- Modify: `tests/test_stickiness.py`
- Modify: `tests/fixtures/stickiness_v2_cases.json`
- Modify: `tests/test_stickiness_regression.py`

- [ ] **Step 1: 写失败测试**

```python
def test_unknown_type_is_hold_not_69_cap():
    result = compute_stickiness(V21_RATINGS, EvidenceLevel.E1,
                                GateSignals(product_type_unknown=True))
    assert result.stickiness_score == 100
    assert result.execution_status == "hold"

def test_reverse_dependency_is_rejected():
    result = compute_stickiness(V21_RATINGS, EvidenceLevel.E4,
                                GateSignals(reverse_dependency=True))
    assert result.rejection_codes == ("reverse_dependency",)
```

- [ ] **Step 2: 运行 `.venv\Scripts\python.exe -m pytest tests/test_stickiness.py -q`，确认因缺少 V2.1 字段而失败。**
- [ ] **Step 3: 在 `pairing_policy.py` 定义购买方向、产品类型、执行状态、动作枚举和关系评分上限；将评分改为 `30/25/15/15/10/5` 六维。**
- [ ] **Step 4: `compute_stickiness` 保留粘性原分，硬门槛只产生 reject，未知、安全和兼容不足只产生 hold，证据只参与动作。**
- [ ] **Step 5: 加入打印机/墨盒、研磨器/喷油壶、婴儿镜/安全座椅、颈枕、遮阳帘、食品、相机电池和汽车不兼容件案例。**
- [ ] **Step 6: 运行 `.venv\Scripts\python.exe -m pytest tests/test_stickiness.py tests/test_stickiness_regression.py -q`，预期全部通过且无69分聚集。**
- [ ] **Step 7: 更新 `docs/优化迭代记录.md`，提交 `feat: add v2.1 pairing decision policy`。**

### Task 2: AI 契约、购买方向和风险门槛

**Files:**
- Modify: `app/domain/schemas/hypothesis.py`
- Modify: `app/domain/dto/__init__.py`
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt`
- Modify: `app/services/hypothesis_service.py`
- Modify: `tests/test_hypothesis_service.py`

- [ ] **Step 1: 写失败测试，断言 `purchase_direction`、`execution_status`、`hold_reasons` 被保存，`weak_context`/`none`/模拟 D 被淘汰。**
- [ ] **Step 2: 运行 `.venv\Scripts\python.exe -m pytest tests/test_hypothesis_service.py -q`，确认 schema 缺字段而失败。**
- [ ] **Step 3: 给 schema/DTO 添加向后兼容字段；提示词只允许模型返回事实、方向、理由和不确定项，不允许返回最终分、证据等级或动作。**
- [ ] **Step 4: 服务端确定性处理食品、包含项、不兼容、重复、反向依赖和高风险 hold，并在评分前应用关系维度上限。**
- [ ] **Step 5: 运行 `.venv\Scripts\python.exe -m pytest tests/test_hypothesis_service.py tests/test_product_pairing_filter.py -q`，预期全部通过且 V2.0 fixture 可读。**
- [ ] **Step 6: 更新迭代记录，提交 `feat: constrain v2.1 pairing direction inputs`。**

### Task 3: 可审计市场证据

**Files:**
- Modify: `app/domain/market_evidence.py`
- Modify: `app/services/market_evidence_service.py`
- Modify: `tests/test_market_evidence.py`
- Modify: `tests/test_market_evidence_service.py`

- [ ] **Step 1: 写失败测试：标题 token 重合只能是 `candidate_discovery` 且不超过 E1；关系事实加独立需求证据才达到 E3。**
- [ ] **Step 2: 运行 `.venv\Scripts\python.exe -m pytest tests/test_market_evidence.py tests/test_market_evidence_service.py -q`，确认 V2.0 错误提升 E2/E3。**
- [ ] **Step 3: 保存来源类型、所有者、平台、查询、URL/ID、摘录、支持方向、计数、时间、状态和失败原因，并按来源所有者/类型/规范 ID 去重。**
- [ ] **Step 4: 证据更新只改变证据等级、动作和排序，绝不改变粘性分。**
- [ ] **Step 5: 运行上述证据测试及 `tests/test_stickiness.py`，预期全部通过。**
- [ ] **Step 6: 更新迭代记录，提交 `feat: make pairing evidence auditable`。**

### Task 4: API、历史、Excel 和工作台统一展示

**Files:**
- Modify: `backend/application/analysis_runner.py`
- Modify: `backend/application/result_highlights.py`
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Modify: `backend/tests/test_analysis_runner.py`
- Modify: `backend/tests/test_result_highlights.py`
- Modify: `tests/test_excel_exporter.py`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/result-workbench.ts`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/tests/result-workbench.test.ts`
- Modify: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: 写失败测试，断言 `stickiness_score`、购买方向、执行状态、动作和结构化证据贯穿 API/Excel/UI，且页面不出现 `[object Object]`。**
- [ ] **Step 2: 运行后端序列化测试和 `frontend/tests/result-workbench-ui.test.tsx`，确认缺字段和旧封顶文案导致失败。**
- [ ] **Step 3: 透传一个后端权威结果；拒绝项保存审计但不进入推荐亮点；前端用类型化区块展示六维分数、方向、状态、证据和原因。**
- [ ] **Step 4: 运行 `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py tests/test_excel_exporter.py -q`。**
- [ ] **Step 5: 运行 `npm test -- --run frontend/tests/result-workbench.test.ts frontend/tests/result-workbench-ui.test.tsx` 和 `npm run typecheck`。**
- [ ] **Step 6: 更新迭代记录，提交 `feat: persist and show v2.1 pairing decisions`。**

### Task 5: 完整验证与真实供应商边界

**Files:**
- Create: `docs/verification/2026-07-30-stickiness-scoring-v2.1.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 运行 `.venv\Scripts\python.exe -m pytest -q`，记录通过数、失败和既有警告。**
- [ ] **Step 2: 运行 `npm test -- --run`、`npm run typecheck`、`npm run build`，记录精确结果。**
- [ ] **Step 3: 仅在 Redis 和用户已配置 Anthropic 兼容供应商可用时跑真实任务；不记录密钥，不把自动化测试冒充真实供应商验证。**
- [ ] **Step 4: 写验证文档和最终迭代记录，提交 `test: verify v2.1 pairing scoring`。**

## Plan self-review

- Task 1-2 覆盖评分、方向、食品和风险；Task 3 覆盖证据；Task 4 贯通历史、Excel 与 UI；Task 5 负责完整验证。
- V2.1 字段对 V2.0 任务可选；商品、关键词、采集器、供应商协议、审判和利润模块不在改动范围。
- 69 分聚集、反向依赖、高风险、标题重合证据和真实供应商边界都有明确回归步骤。
