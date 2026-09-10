# Universal Product Stickiness V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AI-authored category-similarity scores with a full-category consumer-lifecycle recommendation model whose hard gates, evidence caps, final scores, rankings, and audit trail are deterministic.

**Architecture:** The selected LLM extracts a source-referenced product profile and candidate relationship hypotheses, but never supplies a final score or recommendation grade. Domain code validates source references, rejects included/incompatible/duplicate candidates, calculates the approved seven-dimension score, applies evidence caps, and persists `combination_model_v2.0` results. A reusable Walmart search service adds conservative E2/E3 market evidence for viable candidates; failures remain explicit and only lower the evidence ceiling. Existing databases, keyword storage, provider selection, product collection, and profit calculation remain unchanged.

**Tech Stack:** Python 3.12, Pydantic 2, dataclasses, Playwright, FastAPI, pandas/openpyxl, React 19, Next.js 15, TypeScript, Tailwind CSS, Vitest, Testing Library, pytest.

**Approved Spec:** `docs/superpowers/specs/2026-07-29-universal-product-stickiness-v2-design.md`

---

## Scope and Delivery Order

This is one end-to-end feature with seven independently testable commits. The deterministic domain and structured LLM contract are completed before orchestration or UI work. Market verification is an additive stage: CAPTCHA, network, or parser failure must not fail the hypothesis task and must never be interpreted as absent demand.

The implementation must not modify the judgment-mode C/B scoring model, the profit calculator, product/keyword databases, provider settings, or historical payloads.

## File Structure

- Create `app/domain/product_facts.py`: build stable source-fact IDs from actual `ProductDTO` fields and validate LLM references.
- Create `app/domain/stickiness.py`: relation/evidence enums, hard gates, score formula, caps, grade derivation, and deterministic ordering.
- Create `app/domain/market_evidence.py`: traceable search evidence records and conservative E2/E3 derivation.
- Modify `app/domain/schemas/hypothesis.py`: replace free-form score fields with the V2 product profile and candidate relationship contract.
- Modify `app/domain/schemas/__init__.py`: export the new schema types.
- Modify `app/domain/dto/__init__.py`: retain legacy fields while adding the V2 audit fields used by storage, API, Excel, and frontend.
- Modify `app/infrastructure/llm/prompts/hypothesis_a.txt`: generate lifecycle candidates without a fixed 8-10 quota and without AI-authored final scores.
- Create `app/infrastructure/walmart/search.py`: reusable Walmart search-page extraction used by both API and workers.
- Modify `backend/api/routes/search.py`: delegate existing on-demand search to the reusable extractor without changing its API contract.
- Create `app/services/market_evidence_service.py`: verify only viable candidate queries, retain raw results, and recompute caps.
- Modify `app/services/hypothesis_service.py`: validate source references, apply hard gates, calculate V2 scores, and sort by final score.
- Modify `backend/application/analysis_runner.py`: run market verification, serialize the V2 report, preserve dual-model and batch behavior, and report monotonic progress.
- Modify `app/infrastructure/storage/__init__.py`: persist the model version and product profile in newly generated JSON artifacts.
- Modify `app/infrastructure/storage/excel_exporter.py`: export final score, component scores, evidence, caps, risks, and rejection reasons.
- Modify `backend/application/result_highlights.py`: select the highest non-rejected final score while preserving legacy payload support.
- Modify `frontend/lib/api/types.ts`: add typed V2 direction, score, evidence, gate, and lifecycle fields.
- Modify `frontend/lib/result-workbench.ts`: add V2 recommendation/evidence labels and stable ordering helpers.
- Create `frontend/components/jobs/stickiness-scorecard.tsx`: render score formula, cap, evidence, four consistencies, chain, risks, and verdict.
- Modify `frontend/components/jobs/direction-list.tsx`: show final score, recommendation level, evidence level, and rejected state.
- Modify `frontend/components/jobs/direction-detail.tsx`: use the V2 scorecard and keep the existing keyword/platform-search controls.
- Modify `frontend/components/jobs/result-analysis-module.tsx`: label V2 results and preserve the old result fallback.
- Modify `frontend/app/jobs/[jobId]/page.tsx` and `frontend/app/results/page.tsx`: pass the same saved V2 payload to task detail and history.
- Add focused tests in existing backend/frontend test files plus new domain/service tests.
- Create `docs/verification/2026-07-29-universal-product-stickiness-v2.md`: record automated and real-provider evidence without secrets.

### Task 1: Deterministic Stickiness Domain

**Files:**
- Create: `app/domain/stickiness.py`
- Test: `tests/test_stickiness.py`

- [ ] **Step 1: Write failing score, cap, grade, and hard-gate tests**

Add table-driven tests covering exact arithmetic, category-only cap 49, E0-E4 caps, grade boundaries 69/70/79/80/89/90, included-item rejection, incompatibility rejection, safety rejection, and deterministic tie-break ordering.

```python
from app.domain.stickiness import (
    EvidenceLevel,
    GateSignals,
    ScoreRatings,
    compute_stickiness,
)


def test_e1_caps_an_otherwise_high_score_at_69():
    result = compute_stickiness(
        ScoreRatings(5, 5, 5, 5, 5, 5),
        EvidenceLevel.E1,
        GateSignals(),
    )
    assert result.raw_score == 92.0
    assert result.score_cap == 69
    assert result.final_score == 69
    assert result.recommendation == "not_recommended"


def test_included_item_is_rejected_before_scoring():
    result = compute_stickiness(
        ScoreRatings(5, 5, 5, 5, 5, 5),
        EvidenceLevel.E4,
        GateSignals(included=True),
    )
    assert result.rejected is True
    assert result.final_score == 0
    assert result.rejection_codes == ("included_item",)
```

- [ ] **Step 2: Run the focused tests and confirm the module is missing**

Run: `python -m pytest tests/test_stickiness.py -q`

Expected: collection fails with `ModuleNotFoundError: app.domain.stickiness`.

- [ ] **Step 3: Implement immutable domain types and the approved formula**

Implement these exact public types and mappings. Clamp every rating to `0..5`, round component and total scores to one decimal, apply hard rejection before caps, and keep category/scene-only at 49 even if an evidence level is accidentally supplied.

```python
class EvidenceLevel(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


@dataclass(frozen=True)
class ScoreRatings:
    relation_strength: int
    lifecycle_connection: int
    repeat_value: int
    function_gain: int
    mental_copurchase: int
    user_scene: int


@dataclass(frozen=True)
class GateSignals:
    included: bool = False
    incompatible: bool = False
    duplicate_function: bool = False
    no_valid_relation: bool = False
    safety_blocked: bool = False
    category_or_scene_only: bool = False


WEIGHTS = {
    "relation_strength": 30,
    "lifecycle_connection": 20,
    "repeat_value": 15,
    "function_gain": 10,
    "mental_copurchase": 10,
    "market_evidence": 10,
    "user_scene": 5,
}
MARKET_POINTS = {"E0": 0, "E1": 2, "E2": 5, "E3": 8, "E4": 10}
EVIDENCE_CAPS = {"E0": 59, "E1": 69, "E2": 79, "E3": 89, "E4": 100}
```

Return a `StickinessDecision` containing `breakdown`, `raw_score`, `score_cap`, `final_score`, `recommendation`, `rejected`, and `rejection_codes`. Recommendation values are `focus`, `test_pool`, `observe`, and `not_recommended`.

- [ ] **Step 4: Run the domain tests**

Run: `python -m pytest tests/test_stickiness.py -q`

Expected: all tests pass, including every boundary and table row.

- [ ] **Step 5: Commit the scoring domain**

```powershell
git add app/domain/stickiness.py tests/test_stickiness.py
git commit -m "feat: add deterministic product stickiness scoring"
```

### Task 2: Source-Referenced V2 LLM Contract

**Files:**
- Create: `app/domain/product_facts.py`
- Modify: `app/domain/schemas/hypothesis.py`
- Modify: `app/domain/schemas/__init__.py`
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt`
- Test: `tests/test_product_facts.py`
- Test: `tests/test_hypothesis_service.py`

- [ ] **Step 1: Write failing source-index and schema tests**

Test stable fact IDs for title, each bullet, description, attribute, review, Q&A, and FBT item. Test that unknown model references are removed and reported. Validate relation enums, 0-5 score bounds, A/B/C/D simulation, bilingual names, lifecycle stages, and candidate list length `0..12`. Assert the JSON schema contains no `estimated_score` property.

```python
def test_schema_does_not_let_the_model_author_the_final_score():
    schema = HypothesisOutput.model_json_schema()
    candidate = schema["$defs"]["HypothesisDirectionOutput"]["properties"]
    assert "estimated_score" not in candidate
    assert "evidence_level" not in candidate


def test_unknown_source_references_are_reported():
    facts = build_product_facts(ProductDTO(title="Camera", bullet_points=["Includes battery"]))
    valid, invalid = validate_fact_ids(["title", "bullet:0", "bullet:99"], facts)
    assert valid == ("title", "bullet:0")
    assert invalid == ("bullet:99",)
```

- [ ] **Step 2: Run focused tests and confirm missing V2 types/functions**

Run: `python -m pytest tests/test_product_facts.py tests/test_hypothesis_service.py -q`

Expected: failures identify the absent fact builder and V2 schema properties.

- [ ] **Step 3: Implement stable source facts**

`build_product_facts(product)` must return immutable facts with IDs such as `title`, `bullet:0`, `attribute:Color`, `description`, `review:0`, `qa:0`, and `fbt:0`. Empty values are omitted. `validate_fact_ids(ids, facts)` returns `(valid_ids, invalid_ids)` without accepting a model-supplied quote as source truth.

```python
@dataclass(frozen=True)
class ProductFact:
    fact_id: str
    field: str
    text: str


def render_product_facts(facts: Sequence[ProductFact]) -> str:
    return "\n".join(f"[{fact.fact_id}] {fact.field}: {fact.text}" for fact in facts)
```

- [ ] **Step 4: Replace the free-score schema with the V2 contract**

Define strict Pydantic models for:

```python
RelationType = Literal[
    "required_dependency", "spec_compatibility", "consumable_refill",
    "continuous_task", "protection_maintenance", "effect_enhancement",
    "storage_transport", "style_occasion", "weak_context", "none",
]

class RatedReason(BaseModel):
    score: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1)

class ConsistencyOutput(BaseModel):
    user: RatedReason
    scenario: RatedReason
    lifecycle: RatedReason
    mental: RatedReason

class IndependentRatingsOutput(BaseModel):
    relation_strength: int = Field(ge=0, le=5)
    repeat_value: int = Field(ge=0, le=5)
    function_gain: int = Field(ge=0, le=5)

class IncludedItemOutput(BaseModel):
    canonical_name: str
    source_fact_ids: list[str]

class ProductProfileOutput(BaseModel):
    title_zh: str
    core_purchase_job: str
    lifecycle_steps: list[str]
    included_items: list[IncludedItemOutput]
    compatibility_constraints: list[str]
    safety_constraints: list[str]
    primary_search_terms: list[str]

class HypothesisDirectionOutput(BaseModel):
    name_zh: str
    name_en: str
    canonical_name: str
    primary_relation: RelationType
    secondary_relations: list[RelationType]
    purchase_chain: dict[str, str]
    lifecycle_stage: str
    consistency: ConsistencyOutput
    consumer_simulation: Literal["A", "B", "C", "D"]
    consumer_simulation_reason: str
    independent_ratings: IndependentRatingsOutput
    source_fact_ids: list[str]
    incompatibility_reason: str
    duplicate_function_reason: str
    safety_risk: str
    risk_analysis: str
    missing_evidence: list[str]
    keywords: dict[str, str]
    estimated_cost_1688: str
    price_strategy: str
    delivery_checklist: dict[str, Any]

class HypothesisOutput(BaseModel):
    model_version: Literal["combination_model_v2.0"]
    product_profile: ProductProfileOutput
    directions: list[HypothesisDirectionOutput] = Field(max_length=12)
    keyword_pack: list[str]
```

- [ ] **Step 5: Rewrite the prompt around consumer lifecycle and traceable facts**

The prompt must explicitly state:

```text
只输出结构化 JSON。不要输出最终分、推荐等级、证据等级或市场销量结论。
只能引用输入中存在的 source_fact_id；无法验证时写入 missing_evidence。
先识别消费者核心任务和商品生命周期，再按真实关系生成 0-12 个候选。
没有合格候选时允许返回空数组，禁止为了数量生成同类目或同场景弱关联商品。
主品已包含、规格不兼容、功能重复、安全风险商品必须明确标识。
类目相同、用户相同、地点相同不能作为高粘性依据。
所有解释使用中文；name_en 与搜索关键词使用英文。
```

Include the exact relation enum, four-consistency questions, three independent 0-5 ratings, A/B/C/D meanings, lifecycle stages, and required JSON property list from the schema. State that the server derives lifecycle connection from `consistency.lifecycle`, mental co-purchase from `consistency.mental`, and user/scene consistency from the lower of `consistency.user` and `consistency.scenario`; the model must not output those three values a second time.

- [ ] **Step 6: Run schema and fact tests**

Run: `python -m pytest tests/test_product_facts.py tests/test_hypothesis_service.py -q`

Expected: all tests pass and prompt assertions confirm there is no fixed 8-10 quota or AI-authored score.

- [ ] **Step 7: Commit the V2 contract**

```powershell
git add app/domain/product_facts.py app/domain/schemas/hypothesis.py app/domain/schemas/__init__.py app/infrastructure/llm/prompts/hypothesis_a.txt tests/test_product_facts.py tests/test_hypothesis_service.py
git commit -m "feat: define source-referenced stickiness model contract"
```

### Task 3: V2 Candidate Service and DTO Compatibility

**Files:**
- Modify: `app/domain/dto/__init__.py`
- Modify: `app/services/hypothesis_service.py`
- Test: `tests/test_dto.py`
- Test: `tests/test_hypothesis_service.py`

- [ ] **Step 1: Write failing DTO and service behavior tests**

Use an LLM fixture that returns Oil Sprayer, Kitchen Scissors, and the already included Spice Funnel. Assert:

- the funnel has `rejected=True`, `final_score=0`, and `included_item`;
- scissors cannot exceed 49 when marked category/scene-only;
- Oil Sprayer uses the program-computed score instead of any ignored extra `estimated_score` returned by a provider;
- invalid source IDs appear in `invalid_source_fact_ids` and do not upgrade evidence;
- output is sorted by non-rejected final score, with rejected candidates last;
- empty candidate arrays complete normally.

```python
assert result.model_version == "combination_model_v2.0"
assert result.directions[0].hypothesis.direction_name == "喷油壶 (Oil Sprayer)"
assert result.directions[-1].hypothesis.rejected is True
assert "included_item" in result.directions[-1].hypothesis.rejection_codes
```

- [ ] **Step 2: Run focused tests and confirm the legacy DTO lacks V2 fields**

Run: `python -m pytest tests/test_dto.py tests/test_hypothesis_service.py -q`

Expected: V2 field assertions fail.

- [ ] **Step 3: Extend DTOs without deleting legacy fields**

Keep `direction_name`, `category_type`, `motivation_type`, `estimated_cost_1688`, `price_strategy`, `stickiness`, `estimated_score`, and `keywords`. Add:

```python
model_version: str = "combination_model_v2.0"
canonical_name: str = ""
primary_relation: str = ""
secondary_relations: list[str] = field(default_factory=list)
purchase_chain: dict[str, str] = field(default_factory=dict)
lifecycle_stage: str = ""
consistency: dict[str, Any] = field(default_factory=dict)
consumer_simulation: str = ""
consumer_simulation_reason: str = ""
score_breakdown: dict[str, float] = field(default_factory=dict)
raw_score: float = 0.0
score_cap: int = 0
final_score: float = 0.0
recommendation_level: str = "not_recommended"
evidence: dict[str, Any] = field(default_factory=dict)
rejected: bool = False
rejection_codes: list[str] = field(default_factory=list)
invalid_source_fact_ids: list[str] = field(default_factory=list)
risk_analysis: str = ""
missing_evidence: list[str] = field(default_factory=list)
```

Set legacy `estimated_score = final_score`; derive legacy `stickiness` and `category_type` from the deterministic recommendation and primary relationship. Add `model_version` and `product_profile` to `HypothesisResultDTO`.

- [ ] **Step 4: Implement service mapping, included-item comparison, gates, and deterministic scoring**

Use normalized case-folded alphanumeric tokens for exact/canonical included-item comparisons. Do not use substring matching shorter than three characters. Derive gates as follows:

```python
gates = GateSignals(
    included=is_included(candidate.canonical_name, profile.included_items),
    incompatible=bool(candidate.incompatibility_reason.strip()),
    duplicate_function=bool(candidate.duplicate_function_reason.strip()),
    no_valid_relation=candidate.primary_relation == "none",
    safety_blocked=bool(candidate.safety_risk.strip()),
    category_or_scene_only=candidate.primary_relation == "weak_context",
)
```

Set initial evidence to E1 only when at least one valid source fact supports the candidate; otherwise E0. Build `ScoreRatings` without duplicate semantic inputs:

```python
ratings = ScoreRatings(
    relation_strength=candidate.independent_ratings.relation_strength,
    lifecycle_connection=candidate.consistency.lifecycle.score,
    repeat_value=candidate.independent_ratings.repeat_value,
    function_gain=candidate.independent_ratings.function_gain,
    mental_copurchase=candidate.consistency.mental.score,
    user_scene=min(candidate.consistency.user.score, candidate.consistency.scenario.score),
)
```

Call `compute_stickiness`, populate all audit fields, and sort with the domain ordering helper.

- [ ] **Step 5: Run service and DTO tests**

Run: `python -m pytest tests/test_dto.py tests/test_hypothesis_service.py tests/test_stickiness.py -q`

Expected: all tests pass and legacy fields contain computed rather than model-authored values.

- [ ] **Step 6: Commit candidate generation**

```powershell
git add app/domain/dto/__init__.py app/services/hypothesis_service.py tests/test_dto.py tests/test_hypothesis_service.py
git commit -m "feat: score lifecycle candidates with hard gates"
```

### Task 4: Traceable Walmart Market Evidence

**Files:**
- Create: `app/domain/market_evidence.py`
- Create: `app/infrastructure/walmart/search.py`
- Create: `app/services/market_evidence_service.py`
- Modify: `backend/api/routes/search.py`
- Test: `tests/test_market_evidence.py`
- Test: `tests/test_market_evidence_service.py`
- Modify test: `backend/tests/test_search_api.py`

- [ ] **Step 1: Write failing evidence-classification tests**

Cover these fixed outcomes:

```python
assert derive_market_level([], matched_count=0, bundle_count=0) == EvidenceLevel.E0
assert derive_market_level(results, matched_count=1, bundle_count=0) == EvidenceLevel.E2
assert derive_market_level(results, matched_count=2, bundle_count=2) == EvidenceLevel.E3
```

Also assert that unrelated search results stay at the candidate's existing E0/E1 level, distinct URLs are deduplicated, token matching requires both primary and candidate term groups, blocked searches retain `failure_reason`, and no code path produces E4 without transaction input.

- [ ] **Step 2: Run focused tests and confirm the evidence modules are missing**

Run: `python -m pytest tests/test_market_evidence.py tests/test_market_evidence_service.py backend/tests/test_search_api.py -q`

Expected: collection fails for the new modules.

- [ ] **Step 3: Extract the existing Walmart page search without changing the endpoint response**

Move `EXTRACT_JS` and navigation into:

```python
async def search_walmart_page(page: Any, keyword: str) -> list[dict[str, str]]:
    query = quote_plus(keyword.strip())
    await page.goto(
        f"https://www.walmart.com/search?q={query}",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    await page.wait_for_timeout(3000)
    if "robot" in (await page.title()).lower():
        raise RuntimeError("Walmart blocked the request (bot detection)")
    return list(await page.evaluate(EXTRACT_JS) or [])[:20]
```

The API route still creates/closes its own context, validates blank keywords as HTTP 400, returns the same `SearchResponse`, and maps search failures to the existing structured HTTP 502 response.

- [ ] **Step 4: Implement conservative evidence records and matching**

`MarketEvidenceRecord` must store `level`, `platform`, `query`, `verified_at`, `status`, raw returned items, matched item URLs/titles, matched count, bundle count, and failure reason. Normalize English tokens, remove a fixed stopword set, and require at least one primary-product token and one candidate-product token in the same result title. Bundle intent is recognized only when that matched title also contains one of `bundle`, `kit`, `with`, `compatible`, `replacement`, `refill`, or `accessory`.

- [ ] **Step 5: Implement bounded verification and rescoring**

`MarketEvidenceService.verify(result, browser)` must:

1. skip rejected and raw-score-below-70 candidates;
2. verify at most five candidates per model result;
3. cache identical normalized queries within the task;
4. always close each worker page;
5. preserve the candidate's E1 level when search fails or results are unrelated;
6. promote only to E2/E3 using actual results;
7. call the deterministic scorer again with unchanged ratings/gates and the new evidence level;
8. re-sort after caps change.

Use `" ".join(product_profile["primary_search_terms"][:2] + [candidate_keyword])` as the combined query, preferring `keywords.amazon`, then `keywords.en`, then `name_en`.

- [ ] **Step 6: Run evidence and API tests**

Run: `python -m pytest tests/test_market_evidence.py tests/test_market_evidence_service.py backend/tests/test_search_api.py -q`

Expected: all tests pass; existing `/api/v1/search` JSON is byte-for-byte equivalent for the same fake results.

- [ ] **Step 7: Commit market verification**

```powershell
git add app/domain/market_evidence.py app/infrastructure/walmart/search.py app/services/market_evidence_service.py backend/api/routes/search.py tests/test_market_evidence.py tests/test_market_evidence_service.py backend/tests/test_search_api.py
git commit -m "feat: verify candidate market evidence"
```

### Task 5: Runner, Persistence, Serialization, Highlights, and Excel

**Files:**
- Modify: `backend/application/analysis_runner.py`
- Modify: `app/infrastructure/storage/__init__.py`
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Modify: `backend/application/result_highlights.py`
- Modify: `backend/tests/test_analysis_runner.py`
- Modify: `backend/tests/test_result_highlights.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_excel_exporter.py`

- [ ] **Step 1: Write failing end-to-end serialization tests**

Build a `HypothesisResultDTO` containing one accepted and one rejected V2 direction. Assert payload and saved JSON include `model_version`, product profile, relation, chain, consistency, evidence, raw score, cap, final score, recommendation, risks, and rejection codes. Assert the top highlight ignores rejected directions and reads `final_score` with a legacy `score` fallback.

For Excel, assert the `辅品方向` sheet contains these columns:

```text
模型版本, 最终评分, 原始计算分, 分数上限, 推荐等级, 主要关系,
消费者模拟, 证据等级, 证据查询, 证据来源, 淘汰状态, 淘汰原因,
关系强度, 生命周期连接, 持续使用或复购, 功能增益, 自然联购,
市场证据, 用户与场景
```

- [ ] **Step 2: Run focused integration tests and confirm missing serialized fields**

Run: `python -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py tests/test_storage.py tests/test_excel_exporter.py -q`

Expected: V2 payload, storage, highlight, and Excel assertions fail.

- [ ] **Step 3: Integrate verification into hypothesis and batch runners**

After `_run_dual` returns model-generated results, call `MarketEvidenceService().verify(result, browser)` before serialization and artifact creation. Verify primary and secondary results separately but share one per-job query cache. Keep progress monotonic with milestones `5` product start, `35` product loaded, `65` model output ready, `70..90` evidence candidates, `95` artifacts, `100` complete. Search failures must remain candidate evidence failures, not job failures.

- [ ] **Step 4: Serialize the V2 audit structure and retain legacy payload keys**

Each `structured_directions` item must keep `name`, `score`, `type`, `motivation`, `evidence_level`, `cost`, `strategy`, `stickiness`, `keywords`, `deep_arguments`, and `delivery_checklist`. Add the V2 fields listed in Task 3. Set top-level `score` to the highest non-rejected final score rather than the average, and make `score_reason` identify the rule version and evidence cap. Add top-level `model_version` and `product_profile`.

- [ ] **Step 5: Persist and export only actual saved values**

Add `model_version` and `product_profile` to new JSON artifacts; `directions` already uses `asdict` and must preserve the new fields. Extend Excel rows from DTO fields without recomputing scores. No formulas, LLM calls, or searches run during export.

- [ ] **Step 6: Preserve dual-model, batch, and legacy highlights**

`extract_result_highlights` must choose the highest direction where `rejected is not True`, preferring numeric `final_score` and falling back to numeric `score`. Old payload behavior remains unchanged. Add dual-model tests proving each model retains its own candidate analysis and evidence.

- [ ] **Step 7: Run runner, storage, exporter, API, and worker tests**

Run: `python -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py backend/tests/test_jobs_api.py backend/tests/test_worker_jobs.py tests/test_storage.py tests/test_excel_exporter.py -q`

Expected: all tests pass with unchanged judgment-mode assertions.

- [ ] **Step 8: Commit backend integration**

```powershell
git add backend/application/analysis_runner.py app/infrastructure/storage/__init__.py app/infrastructure/storage/excel_exporter.py backend/application/result_highlights.py backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py backend/tests/test_jobs_api.py backend/tests/test_worker_jobs.py tests/test_storage.py tests/test_excel_exporter.py
git commit -m "feat: persist stickiness v2 recommendation reports"
```

### Task 6: V2 Result Workbench

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/result-workbench.ts`
- Create: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/components/jobs/direction-list.tsx`
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/result-analysis-module.tsx`
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Modify: `frontend/app/results/page.tsx`
- Modify: `frontend/tests/result-workbench.test.ts`
- Modify: `frontend/tests/result-workbench-ui.test.tsx`
- Modify: `frontend/tests/job-detail.test.tsx`
- Modify: `frontend/tests/results-page.test.tsx`

- [ ] **Step 1: Write failing type-helper and component tests**

Use one accepted E3 direction, one E1 capped direction, and one included-item rejection. Assert:

- list sorting uses `final_score` and places rejected items last;
- labels are `重点开发`, `测试池`, `观察验证`, and `不推荐`;
- raw score, cap, final score, and cap reason are all visible;
- hard rejection reason is visible and not represented as a misleading score;
- consumer chain, four consistencies, A/B/C/D simulation, seven components, evidence source/query/time, risks, and missing evidence render;
- verified facts, AI judgment, and pending validation are separate sections;
- task detail and history render the same saved values;
- old directions with only `score` still render without fabricated V2 fields.

- [ ] **Step 2: Run focused frontend tests and confirm V2 UI is absent**

Run from `frontend`:

```powershell
npm test -- --run tests/result-workbench.test.ts tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx tests/results-page.test.tsx
```

Expected: V2 type/helper/component assertions fail.

- [ ] **Step 3: Extend frontend types and deterministic view helpers**

Add optional V2 fields to `StructuredDirection` so legacy tasks remain valid. Define exact union types:

```typescript
export type EvidenceLevel = "E0" | "E1" | "E2" | "E3" | "E4";
export type RecommendationLevel = "focus" | "test_pool" | "observe" | "not_recommended";
export interface ScoreBreakdown {
  relation_strength: number;
  lifecycle_connection: number;
  repeat_value: number;
  function_gain: number;
  mental_copurchase: number;
  market_evidence: number;
  user_scene: number;
}
```

`directionFinalScore(direction)` returns `direction.final_score ?? direction.score ?? 0`. `rankDirections` creates a copy, orders accepted candidates by final score descending, and always moves `rejected === true` after accepted candidates.

- [ ] **Step 4: Build the unframed scorecard report**

`StickinessScorecard` renders compact full-width sections separated by borders, not nested cards. Use `CheckCircle2`, `XCircle`, `Link2`, `Clock3`, `ShieldAlert`, and `Search` from Lucide. Use a seven-row table for component scores, a four-column consistency grid on desktop that becomes a single column on mobile, and an explicit banner for caps or hard rejection. Do not show a 0 score badge for rejected items; show `已淘汰` and its exact reasons.

- [ ] **Step 5: Integrate the scorecard and preserve current workflow controls**

Keep product image, precise keyword, Walmart verification, Amazon link, model switcher, historical selection, raw sections, and cross-review. Add a `V2.0 全品类购买链路` label only when `model_version === "combination_model_v2.0"`. Legacy results continue to use their existing detail groups and score display.

- [ ] **Step 6: Run focused UI tests, typecheck, and production build**

Run from `frontend`:

```powershell
npm test -- --run tests/result-workbench.test.ts tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx tests/results-page.test.tsx
npm run typecheck
npm run build
```

Expected: all focused tests pass, TypeScript reports no errors, and Next.js production build succeeds.

- [ ] **Step 7: Commit the V2 workbench**

```powershell
git add frontend/lib/api/types.ts frontend/lib/result-workbench.ts frontend/components/jobs/stickiness-scorecard.tsx frontend/components/jobs/direction-list.tsx frontend/components/jobs/direction-detail.tsx frontend/components/jobs/result-analysis-module.tsx 'frontend/app/jobs/[jobId]/page.tsx' frontend/app/results/page.tsx frontend/tests/result-workbench.test.ts frontend/tests/result-workbench-ui.test.tsx frontend/tests/job-detail.test.tsx frontend/tests/results-page.test.tsx
git commit -m "feat: show auditable stickiness v2 results"
```

### Task 7: Full-Category Regression and Real Provider Verification

**Files:**
- Create: `tests/fixtures/stickiness_v2_cases.json`
- Create: `tests/test_stickiness_regression.py`
- Modify only when a scoped failure is found: files from Tasks 1-6
- Create: `docs/verification/2026-07-29-universal-product-stickiness-v2.md`

- [ ] **Step 1: Add the approved full-category fixture matrix**

The fixture must include positive and negative pairs for kitchen, printing, oral care, cameras, bedding, automotive, and apparel. Each case contains `main_product`, `candidate`, `relation`, `evidence_level`, `ratings`, `gates`, and expected `rejected`, `minimum_score`, `maximum_score`, and `recommendation`.

Required invariants:

```python
assert score("matching printer ink") > score("desk organizer")
assert score("matching toothbrush head") > score("hair dryer")
assert score("compatible camera battery") > score("incompatible lens")
assert score("matching mattress protector") > score("bedroom lamp")
assert rejected("included spice funnel")
assert rejected("wrong-year automotive part")
```

- [ ] **Step 2: Run the complete Python suite**

Run: `python -m pytest -q`

Expected: all tests pass with no skipped V2 regression cases.

- [ ] **Step 3: Run all frontend verification**

Run from `frontend`:

```powershell
npm test -- --run
npm run typecheck
npm run build
```

Expected: all tests pass, typecheck reports no errors, and production build succeeds.

- [ ] **Step 4: Run the Electric Salt Pepper Grinder regression fixture**

Use the saved source facts representing the verified Moreblue listing. Assert Oil Sprayer ranks above Kitchen Scissors, Measuring Cups, and Silicone Baking Mat; Kitchen Scissors, Measuring Cups, and Silicone Baking Mat do not enter the test pool; Spice Funnel is rejected because the main product includes a bonus funnel; Spice Rack is capped according to its actual evidence.

- [ ] **Step 5: Run one real primary-provider task through the UI**

Use the currently saved custom Anthropic-style provider and the Walmart grinder URL. Do not print or store the API key. Confirm:

- the task reaches 100% and artifacts are downloadable;
- the provider returns the V2 structured contract;
- the server, not the provider, calculates final scores;
- every stored source ID exists in the scraped input;
- market search failures show a reason and lower the evidence cap without failing the job;
- task detail, history, and Excel contain the same final scores and rejection states;
- no direction claims E4 unless real transaction input exists.

- [ ] **Step 6: Perform desktop and mobile visual checks**

Use Playwright at `1440x900` and `390x844`. Verify no overlapping text, no horizontal page overflow, stable direction selection, readable Chinese typography, visible cap/rejection status, and accessible controls. Keep existing services on ports `3100` and `3017` untouched; use the project's current `3000` and `8000` services or unused ports.

- [ ] **Step 7: Record exact verification results**

Write commands, pass counts, provider/model names without credentials, task ID, evidence levels, final ordered candidates, rejected candidates, screenshots, and any residual platform-data limitations to `docs/verification/2026-07-29-universal-product-stickiness-v2.md`.

- [ ] **Step 8: Commit regression evidence**

```powershell
git add tests/fixtures/stickiness_v2_cases.json tests/test_stickiness_regression.py docs/verification/2026-07-29-universal-product-stickiness-v2.md
git commit -m "test: verify universal stickiness model v2"
```

## Final Acceptance Gate

Before claiming completion, confirm all of the following from fresh command output:

- Git working tree contains no unintended files or secrets.
- Python suite passes.
- Frontend suite, typecheck, and production build pass.
- The full-category fixture matrix passes.
- The real custom-provider grinder task completes and its evidence is traceable.
- No AI output field controls final score, evidence grade, cap, ranking, or recommendation level.
- No E4 claim exists without transaction evidence.
- Judgment mode, databases, keyword storage, product collection, and profit calculation retain their prior behavior.
- Every implementation stage is available as a separate Git commit for rollback.
