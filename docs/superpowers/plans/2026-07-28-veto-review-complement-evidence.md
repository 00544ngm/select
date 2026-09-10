# Veto Review and Complement Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw veto booleans with a clear conclusion card and add traceable, four-level complementary-demand evidence based on actually scraped B-product reviews.

**Architecture:** Add a focused complement-evidence analyzer that classifies indexed review samples through the already selected LLM, validates every returned index against actual input, and derives the display status from fixed server-side thresholds. Store this evidence beside each serialized judgment result without overwriting `g3_validated`, scores, grade, veto flags, or exports. Render structured evidence in one shared judgment component and fall back to clearly labeled legacy initial judgments when evidence is absent.

**Tech Stack:** Python 3.12, Pydantic, existing LLMClient abstraction, FastAPI job result JSON, React 19, Next.js 15, TypeScript, Tailwind CSS, Vitest, Testing Library, pytest.

---

## File Structure

- Create `app/domain/complement_evidence.py`: evidence dataclasses, review normalization, threshold derivation, and model-output validation.
- Create `app/domain/schemas/complement_evidence.py`: strict structured-output schema for one B product's indexed review classification.
- Create `app/services/complement_evidence_service.py`: build a bounded prompt from actual reviews, call the selected LLM, and return a safe evidence record without changing judgment output.
- Modify `app/domain/schemas/__init__.py`: export evidence schema.
- Modify `backend/application/analysis_runner.py`: run evidence analysis after the primary judgment, serialize it into `complement_evidence`, and leave existing result/exports untouched.
- Modify `frontend/lib/api/types.ts`: describe the structured evidence payload.
- Modify `frontend/lib/result-format.ts`: parse legacy veto fields into explicit risk/evidence values without exposing raw booleans.
- Modify `frontend/components/jobs/judgment-analysis.tsx`: render the approved conclusion card, risk group, positive-evidence group, statistics, and expandable quotations.
- Modify job detail/results call sites to pass `complement_evidence` to the shared component.
- Add focused Python and frontend tests for thresholds, index validation, serialization, legacy behavior, and UI states.

### Task 1: Deterministic Evidence Domain

**Files:**
- Create: `app/domain/complement_evidence.py`
- Test: `tests/test_complement_evidence.py`

- [ ] **Step 1: Write failing threshold and normalization tests**

Cover 9/10/19/20 valid reviews, 0/1/2/3 hits, the 10% boundary, duplicate/blank/short review filtering, and source-index validation. Expected status values are `verified`, `signal`, `not_found`, and `insufficient`.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `python -m pytest tests/test_complement_evidence.py -q`

Expected: collection fails because `app.domain.complement_evidence` does not exist.

- [ ] **Step 3: Implement immutable evidence records and threshold derivation**

Implement `normalize_reviews(reviews)`, `validate_hits(raw_hits, indexed_reviews)`, and `derive_evidence_status(valid_count, hit_count, analysis_state)`. Count only actual normalized reviews and reject unknown, duplicated, or non-integer model indexes.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_complement_evidence.py -q`

Expected: all evidence-domain tests pass.

- [ ] **Step 5: Commit deterministic evidence domain**

```powershell
git add app/domain/complement_evidence.py tests/test_complement_evidence.py
git commit -m "feat: add complement evidence rules"
```

### Task 2: Traceable LLM Review Classification

**Files:**
- Create: `app/domain/schemas/complement_evidence.py`
- Create: `app/services/complement_evidence_service.py`
- Modify: `app/domain/schemas/__init__.py`
- Test: `tests/test_complement_evidence_service.py`

- [ ] **Step 1: Write failing service tests**

Verify that the prompt contains stable review indexes and actual review text, accepts only source indexes, retains original text from the server rather than model-repeated text, records Chinese translation/keywords/reason/strength, and returns `analysis_failed` instead of raising when classification fails. Verify zero reviews returns `insufficient` without calling the LLM.

- [ ] **Step 2: Run service tests and confirm failure**

Run: `python -m pytest tests/test_complement_evidence_service.py -q`

Expected: collection fails because the service does not exist.

- [ ] **Step 3: Implement the strict schema and service**

The structured response contains only `review_index`, `is_relevant`, `translation_zh`, `keywords`, `reason`, and `strength`. Build evidence quotations from the server-side indexed review map, never from returned free text. Analyze up to the scraper's retained sample (30 Walmart, 15 Amazon), and derive status through Task 1 helpers.

- [ ] **Step 4: Run service and judgment regression tests**

Run: `python -m pytest tests/test_complement_evidence_service.py tests/test_judgment_service.py -q`

Expected: all tests pass and the existing judgment schema remains unchanged.

- [ ] **Step 5: Commit the classifier**

```powershell
git add app/domain/schemas/complement_evidence.py app/domain/schemas/__init__.py app/services/complement_evidence_service.py tests/test_complement_evidence_service.py
git commit -m "feat: classify traceable complement evidence"
```

### Task 3: Attach Evidence Without Changing Judgment Results

**Files:**
- Modify: `backend/application/analysis_runner.py`
- Modify: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: Write failing runner serialization tests**

Assert a judgment payload contains `complement_evidence.per_b_product`, real B URL/title, counts, ratio, status, timestamp, and evidence quotations. Assert original `sections`, `grade`, `score`, `veto_check` serialization, artifacts, and Excel generation remain identical. Cover classifier failure as a completed judgment with `analysis_failed` evidence.

- [ ] **Step 2: Run runner tests and confirm failure**

Run: `python -m pytest backend/tests/test_analysis_runner.py -q`

Expected: new evidence assertions fail.

- [ ] **Step 3: Integrate the evidence service**

After `JudgmentService.judge` succeeds, call `ComplementEvidenceService` for each B product with the same selected primary LLM. Serialize its records into a top-level `complement_evidence` property. Do not mutate `JudgmentResultDTO.veto_check`, `g3_validated`, score, grade, saved judgment JSON, or Excel exporter inputs. For dual-model tasks, attach primary evidence to the primary model payload; secondary judgment output remains unchanged unless separately classified in a future scoped change.

- [ ] **Step 4: Run runner and API regression tests**

Run: `python -m pytest backend/tests/test_analysis_runner.py backend/tests/test_jobs_api.py tests/test_excel_exporter.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit payload integration**

```powershell
git add backend/application/analysis_runner.py backend/tests/test_analysis_runner.py
git commit -m "feat: attach complement evidence to judgments"
```

### Task 4: Structured Veto Presentation

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/result-format.ts`
- Modify: `frontend/components/jobs/judgment-analysis.tsx`
- Test: `frontend/tests/result-workbench.test.ts`
- Test: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: Write failing parser and component tests**

Cover these assertions: `vetoed=false` shows “通过”; each false risk shows “未触发”; true risks show “已触发”; G3 is absent from risk checks; empty veto reason is hidden; verified/signal/not-found/insufficient/analysis-failed evidence states have distinct wording; quotations reveal original/translation/keywords/reason; legacy false displays “旧任务初判：暂未确认” and no invented counts.

- [ ] **Step 2: Run focused frontend tests and confirm failure**

Run: `npm test -- --run tests/result-workbench.test.ts tests/result-workbench-ui.test.tsx` from `frontend`.

Expected: new UI assertions fail.

- [ ] **Step 3: Implement typed parsing and approved card UI**

Extend `PerBProduct` with individual G1/G2/G4-G7 values and legacy G3. Add `ComplementEvidencePayload` types. Update the drawer to use a conclusion header, six risk rows, and a separate positive-evidence section. Evidence details are collapsed by default and use accessible buttons. Never render literal `True` or `False` in this card.

- [ ] **Step 4: Run focused frontend tests**

Run: `npm test -- --run tests/result-workbench.test.ts tests/result-workbench-ui.test.tsx` from `frontend`.

Expected: all focused tests pass.

- [ ] **Step 5: Commit shared UI**

```powershell
git add frontend/lib/api/types.ts frontend/lib/result-format.ts frontend/components/jobs/judgment-analysis.tsx frontend/tests/result-workbench.test.ts frontend/tests/result-workbench-ui.test.tsx
git commit -m "feat: clarify veto and complement evidence UI"
```

### Task 5: Use the Shared Judgment View Everywhere

**Files:**
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Modify: `frontend/app/results/page.tsx`
- Modify: `frontend/components/jobs/batch-leaderboard.tsx` if judgment batches expose the same payload
- Test: `frontend/tests/job-detail.test.tsx`
- Test: `frontend/tests/results-page.test.tsx`

- [ ] **Step 1: Write failing integration tests**

Assert task detail and historical results both pass active-model evidence into `JudgmentAnalysis` and show the same status/counts. Assert switching models does not display evidence from a different model payload.

- [ ] **Step 2: Run page tests and confirm failure**

Run: `npm test -- --run tests/job-detail.test.tsx tests/results-page.test.tsx` from `frontend`.

Expected: evidence is missing from at least one page.

- [ ] **Step 3: Wire the shared component into all judgment result surfaces**

Pass `activeResult.complement_evidence` alongside sections and grade. On the historical results page, select `JudgmentAnalysis` for judgment mode instead of the hypothesis-only direction workbench. Preserve current artifact actions and model switcher behavior.

- [ ] **Step 4: Run page and accessibility tests**

Run: `npm test -- --run tests/job-detail.test.tsx tests/results-page.test.tsx tests/accessibility.test.tsx` from `frontend`.

Expected: all tests pass.

- [ ] **Step 5: Commit page integration**

```powershell
git add 'frontend/app/jobs/[jobId]/page.tsx' frontend/app/results/page.tsx frontend/components/jobs/batch-leaderboard.tsx frontend/tests/job-detail.test.tsx frontend/tests/results-page.test.tsx
git commit -m "feat: share judgment evidence across results"
```

### Task 6: Full Verification and Real Provider Check

**Files:**
- Modify only if verification finds a scoped defect.
- Create: `docs/verification/2026-07-28-veto-review-complement-evidence.md`

- [ ] **Step 1: Run all backend and domain tests**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run all frontend checks**

Run from `frontend`:

```powershell
npm test -- --run
npm run typecheck
npm run build
```

Expected: tests, TypeScript, and production build pass.

- [ ] **Step 3: Run a real custom Anthropic judgment task**

Use the existing saved custom provider and a valid A/B URL pair. Confirm the job reaches 100%, its original grade/score/veto values remain present, evidence sample counts match saved quotations, and every quotation can be found verbatim in the collected input sample. Do not include API keys in logs or verification notes.

- [ ] **Step 4: Verify desktop and mobile UI in the local browser**

Check task detail and history at desktop and mobile widths. Confirm no text overlap, no literal booleans, correct pass/fail colors, expandable evidence, and understandable legacy fallback.

- [ ] **Step 5: Record verification and commit**

```powershell
git add docs/verification/2026-07-28-veto-review-complement-evidence.md
git commit -m "docs: verify complement evidence workflow"
```
