# Link-Driven Sticky Product Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make link-driven product pairing recommend only high-粘性 products based on the supplied main-product link, hard-filter edible goods, and present auditable structured results across all output surfaces.

**Architecture:** Keep the existing scraper, provider, product/keyword databases, judgment flow, and profit calculation unchanged. Extend the existing hypothesis DTO and prompt with product-type/filter/relationship fields, apply deterministic food/inclusion/compatibility gates and a five-dimension 粘性 score in the backend, then serialize one final result to JSON/Excel/history and render it with structured frontend sections.

**Tech Stack:** Python 3, Pydantic, pytest, existing LLM client, pandas Excel exporter, Next.js/React/TypeScript, Vitest/Testing Library, Playwright.

---

### Task 1: Add the link-driven product and food-filter contract

**Files:**
- Create: `app/domain/product_pairing_filter.py`
- Modify: `app/domain/schemas/hypothesis.py`
- Modify: `app/domain/dto/__init__.py`
- Test: `tests/test_product_pairing_filter.py`
- Test: `tests/test_hypothesis_service.py`

- [ ] **Step 1: Write failing filter tests**

```python
def test_food_is_rejected_but_non_food_consumable_is_kept():
    assert classify_candidate("Whole Black Peppercorns").status == "food"
    assert classify_candidate("Replacement Ink Cartridge").status == "allowed"

def test_unknown_food_classification_is_not_recommended():
    result = classify_candidate("Natural refill product")
    assert result.status == "needs_verification"
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `py -m pytest tests/test_product_pairing_filter.py -q`

Expected: FAIL because `app.domain.product_pairing_filter` and `classify_candidate` do not exist.

- [ ] **Step 3: Implement deterministic classification**

Create an immutable result with `status`, `reason`, and `matched_terms`. Normalize title, keywords, product type, and description; match edible categories and explicit terms such as food, seasoning, spice, peppercorn, beverage, snack, ingredient, edible, and supplement. Match non-food consumables such as ink, filter, battery, blade, and cartridge as allowed. Treat ambiguous matches as `needs_verification`; only `allowed` can be scored.

Extend `ProductProfileOutput` with `source_url`, `product_type`, and `source_collected_at`. Extend `HypothesisDirectionOutput` with `food_filter_status`, `food_filter_reason`, `relation_reasons`, `extended_scenarios`, `assumptions`, and `confidence_level`, all with backward-compatible defaults.

- [ ] **Step 4: Run the tests and update schema fixtures**

Run: `py -m pytest tests/test_product_pairing_filter.py tests/test_hypothesis_service.py -q`

Expected: PASS, including existing schema validation fixtures.

- [ ] **Step 5: Commit the contract changes**

```bash
git add app/domain/product_pairing_filter.py app/domain/schemas/hypothesis.py app/domain/dto/__init__.py tests/test_product_pairing_filter.py tests/test_hypothesis_service.py
git commit -m "feat: add link-driven product filter contract"
```

### Task 2: Replace the core hypothesis scoring with link-driven粘性 scoring

**Files:**
- Modify: `app/domain/stickiness.py`
- Modify: `app/services/hypothesis_service.py`
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt`
- Test: `tests/test_stickiness.py`
- Test: `tests/test_hypothesis_service.py`
- Test: `tests/fixtures/stickiness_link_driven_cases.json`

- [ ] **Step 1: Add failing scoring and gate tests**

```python
def test_link_driven_weights_ignore_market_and_explosive_labels():
    result = compute_stickiness(
        StickyRatings(function_necessity=5, usage_continuity=5,
                      scene_fit=5, enhancement_maintenance=4,
                      natural_copurchase=5),
        GateSignals(),
    )
    assert result.final_score == 96

def test_food_candidate_is_hard_rejected_before_scoring():
    result = compute_stickiness(
        StickyRatings(function_necessity=5, usage_continuity=5,
                      scene_fit=5, enhancement_maintenance=5,
                      natural_copurchase=5),
        GateSignals(food_blocked=True),
    )
    assert result.rejected is True
    assert "food_blocked" in result.rejection_codes
```

- [ ] **Step 2: Run the focused tests and confirm the old contract fails**

Run: `py -m pytest tests/test_stickiness.py -q`

Expected: FAIL because the current `ScoreRatings` still uses market evidence and legacy relation weights.

- [ ] **Step 3: Implement the five-dimension deterministic score**

Use weights `{function_necessity: 30, usage_continuity: 25, scene_fit: 20, enhancement_maintenance: 15, natural_copurchase: 10}`. Keep evidence level as a separate confidence/cap signal only when evidence is missing; remove market points from the 粘性 sum. Add `food_blocked`, `needs_verification`, and existing inclusion/incompatibility/duplicate/safety/no-relation gates. Preserve `final_score`, `recommendation`, and rejection compatibility for historical records.

- [ ] **Step 4: Make hypothesis generation link-first and filter deterministically**

Update the prompt to require: facts only from `<untrusted-product-data>`, candidates tied to required/continuous/enhancement/maintenance/protection/storage relations, explicit `extended_scenarios` with assumptions, no model-authored final score, and no edible candidates. In `HypothesisService._parse_directions`, run `classify_candidate` before scoring, add the food rejection gate, retain non-food consumables, and map the five ratings into the new score inputs. Candidates without a relationship reason or with an ambiguous food classification must not reach the high-粘性 output.

- [ ] **Step 5: Add cross-category regression fixtures**

Create fixture cases for printer+ink (high), camera+lens (high), grinder+pepper (food rejected), grinder+cleaning brush (medium/high), scissors+measuring cup (weak/rejected), included accessory (rejected), incompatible accessory (rejected), and filter/battery/blade (allowed consumables).

- [ ] **Step 6: Run backend scoring and service tests**

Run: `py -m pytest tests/test_stickiness.py tests/test_hypothesis_service.py -q`

Expected: PASS with all legacy V2 tests updated only where their assertions describe the replaced market-weighted score.

- [ ] **Step 7: Commit the scoring changes**

```bash
git add app/domain/stickiness.py app/services/hypothesis_service.py app/infrastructure/llm/prompts/hypothesis_a.txt tests/test_stickiness.py tests/test_hypothesis_service.py tests/fixtures/stickiness_link_driven_cases.json
git commit -m "feat: score link-driven product stickiness"
```

### Task 3: Persist one auditable result through API, history, and Excel

**Files:**
- Modify: `app/services/market_evidence_service.py`
- Modify: `backend/application/analysis_runner.py`
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Modify: `frontend/lib/api/types.ts`
- Test: `backend/tests/test_analysis_runner.py`
- Test: `backend/tests/test_result_highlights.py`

- [ ] **Step 1: Write failing serialization tests**

```python
def test_structured_direction_persists_filter_status_and_extended_scenarios():
    payload = build_result_payload({
        "structured_directions": [{
            "food_filter_status": "allowed",
            "extended_scenarios": [{"name": "home office", "assumption": "主品用于固定办公场景"}],
            "score_breakdown": {"function_necessity": 30},
        }]
    })
    direction = payload["structured_directions"][0]
    assert direction["food_filter_status"] == "allowed"
    assert direction["extended_scenarios"][0]["assumption"]
    assert direction["score_breakdown"]["function_necessity"] == 30
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `py -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py -q`

Expected: FAIL because the payload/exporter do not expose the new fields.

- [ ] **Step 3: Serialize the final backend DTO once**

Add the new fields to the `HypothesisDTO`/direction payload mapping in `backend/application/analysis_runner.py`. Preserve legacy aliases (`score`, `stickiness`, `evidence_level`) while adding `stickiness_score`, `relation_reasons`, `extended_scenarios`, `assumptions`, `food_filter_status`, `confidence_level`, `market_evidence_status`, and readable `rejection_reason`. Ensure history highlights sort by `final_score` and ignore rejected directions.

- [ ] **Step 4: Export readable Excel columns**

Update `app/infrastructure/storage/excel_exporter.py` to export one row per candidate with separate columns for粘性 dimensions, chain, food status, extended scenario, assumption, risk, evidence status, and rejection reason. Keep raw JSON in a separate optional sheet/column; do not replace existing product, keyword, or profit columns.

- [ ] **Step 5: Extend TypeScript API types**

Add typed interfaces for `RelationReasons`, `ExtendedScenario`, `FoodFilterStatus`, and `MarketEvidenceStatus`; add optional fields to `StructuredDirection` and `ModelResult` so historical payloads remain valid.

- [ ] **Step 6: Run serialization and type checks**

Run: `py -m pytest backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py -q` and `npm run typecheck`.

Expected: PASS.

- [ ] **Step 7: Commit the persistence changes**

```bash
git add app/services/market_evidence_service.py backend/application/analysis_runner.py app/infrastructure/storage/excel_exporter.py frontend/lib/api/types.ts backend/tests/test_analysis_runner.py backend/tests/test_result_highlights.py
git commit -m "feat: persist auditable sticky pairing results"
```

### Task 4: Replace raw JSON evidence and deep-analysis rendering

**Files:**
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/result-analysis-module.tsx`
- Modify: `frontend/lib/result-workbench.ts`
- Test: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: Add failing UI assertions**

```tsx
it("shows structured relation, filter, scenario, and evidence sections", () => {
  const direction = {
    name: "打印机墨盒 (Printer Ink Cartridge)", score: 96, type: "required_dependency",
    motivation: "replacement", evidence_level: "E1", cost: "-", strategy: "-",
    stickiness: "high", model_version: "combination_model_v2.0",
    food_filter_status: "allowed", food_filter_reason: "不可食用耗材",
    relation_reasons: { function: "主品打印必须使用墨盒" },
    extended_scenarios: [{ name: "home office", assumption: "主品用于固定办公场景" }],
    purchase_chain: { before: "准备打印任务", primary_use: "打印文件", auxiliary_use: "补充墨水" },
  } as StructuredDirection;
  render(<StickinessScorecard direction={direction} />);
  expect(screen.getByText("功能关系")).toBeInTheDocument();
  expect(screen.getByText("食品过滤：已通过")).toBeInTheDocument();
  expect(screen.getByText("拓展场景")).toBeInTheDocument();
  expect(screen.queryByText(/\"purchase_chain\"/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the UI test and confirm failure**

Run: `npm test -- --run frontend/tests/result-workbench-ui.test.tsx`

Expected: FAIL because the current components stringify nested objects and show raw URL arrays.

- [ ] **Step 3: Build structured display helpers**

In `result-workbench.ts`, add pure helpers that normalize old/new payloads into `relationReasons`, `chainSteps`, `extendedScenarios`, `evidenceSummary`, and `rejectionSummary`. Each helper must return empty arrays/`待验证` for absent historical fields and never call `JSON.stringify` for user-facing content.

- [ ] **Step 4: Refactor the scorecard**

Render five粘性 rows, final score/level, purchase chain, relation reasons, food filter status, extended scenarios with assumptions, risks, and a compact evidence summary showing platform/query/matched count/verified time. Put raw URLs and raw fields under a collapsed “查看原始数据” control.

- [ ] **Step 5: Refactor deep analysis**

Replace `DisplayValue` JSON serialization in `direction-detail.tsx` with typed sections for purchase chain, relation reasons, four-consistency output, scenarios, evidence, risks, and delivery checklist. Keep unknown legacy fields in the collapsed raw-data section.

- [ ] **Step 6: Run frontend tests and typecheck**

Run: `npm test -- --run frontend/tests/result-workbench-ui.test.tsx` and `npm run typecheck`.

Expected: PASS with existing history/result-workbench tests unchanged or updated only for the new visible labels.

- [ ] **Step 7: Commit the UI changes**

```bash
git add frontend/components/jobs/stickiness-scorecard.tsx frontend/components/jobs/direction-detail.tsx frontend/components/jobs/result-analysis-module.tsx frontend/lib/result-workbench.ts frontend/tests/result-workbench-ui.test.tsx
git commit -m "feat: render structured sticky pairing analysis"
```

### Task 5: Run full regression and document verification

**Files:**
- Modify: `docs/verification/2026-07-29-universal-product-stickiness-v2.md`
- Test: `tests/test_stickiness_regression.py`
- Test: `frontend/tests/batch-history.test.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: Run the full backend suite**

Run: `py -m pytest -q`

Expected: all backend tests pass with no new failures. Redis must be available at `127.0.0.1:6379` for integration tests.

- [ ] **Step 2: Run the full frontend suite**

Run: `npm test -- --run`

Expected: all frontend tests pass, including historical payloads without the new fields.

- [ ] **Step 3: Build and typecheck production artifacts**

Run: `npm run typecheck` and `npm run build`

Expected: both commands exit 0.

- [ ] **Step 4: Update verification evidence**

Record the exact test counts, link-driven regression cases, food-filter behavior, non-food consumable behavior, and any provider/Redis limitations in `docs/verification/2026-07-29-universal-product-stickiness-v2.md`. Do not write API keys or claim a real provider run without configured credentials.

- [ ] **Step 5: Commit the verified implementation**

```bash
git add docs/verification/2026-07-29-universal-product-stickiness-v2.md tests/test_stickiness_regression.py frontend/tests/batch-history.test.tsx frontend/tests/job-detail.test.tsx
git commit -m "test: verify link-driven sticky pairing behavior"
```

## Self-review checklist

- The plan removes 爆品 status from the core score and never filters non-food consumables merely because they are consumable.
- Every design requirement has a task: link-only main product, edible-food hard filter, five-dimensional stickiness, extension scenarios, separate market evidence, structured JSON/Excel/history/UI, and cross-category regression.
- Existing storage and provider boundaries remain unchanged; only DTO mapping and presentation are extended.
- Historical payloads remain compatible through optional fields and legacy aliases.
- No placeholder steps or unspecified error-handling tasks remain.
