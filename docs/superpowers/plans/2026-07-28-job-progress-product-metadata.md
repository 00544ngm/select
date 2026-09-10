# 任务进度与主品元数据 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让任务详情进度实时变化，并在结果工作台显示主品 ID、模型生成的中文标题和可用主图，同时应用 A 字体方案。

**Architecture:** Worker 将进度双写到 Redis 和 `analysis_jobs.progress`，现有 API 读取数据库即可获得持久化进度。商品 ID 从平台 URL 解析，图片由平台抓取器提取并写入现有结果 payload；Hypothesis 使用 `product_analysis.title`，Judgment 增加 `product_title_zh`。前端只扩展结果元数据展示和图片回退，不改分析算法或评分。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, ARQ/Redis, Pydantic, Next.js 15, React, TypeScript, Tailwind, Vitest, Playwright.

---

### Task 1: 商品 URL 元数据解析

**Files:**
- Modify: `app/domain/product_url.py`
- Modify: `app/domain/dto/__init__.py`
- Modify: `app/services/product_service.py`
- Test: `tests/test_product_url.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.domain.product_url import extract_product_id

def test_extracts_walmart_numeric_id():
    assert extract_product_id("https://www.walmart.com/ip/Some-Scale/123456789") == "123456789"

def test_extracts_amazon_asin_from_dp_path():
    assert extract_product_id("https://www.amazon.com/dp/B0FBWG9ZPT") == "B0FBWG9ZPT"

def test_returns_none_for_supported_url_without_product_id():
    assert extract_product_id("https://www.walmart.com/search?q=scale") is None
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.\.venv\Scripts\pytest.exe tests/test_product_url.py -q`

Expected: FAIL because `extract_product_id` is not defined.

- [ ] **Step 3: Implement the parser and DTO field**

Add `extract_product_id(url: str) -> str | None` using `urlparse` and anchored path patterns (`/ip/<slug>/<digits>` for Walmart, `/dp/<ASIN>` or `/gp/product/<ASIN>` for Amazon). Add `product_id: str | None = None` to `ProductDTO`; populate it in `ProductService.get_product` after scraper validation.

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `.\.venv\Scripts\pytest.exe tests/test_product_url.py tests/test_product_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/domain/product_url.py app/domain/dto/__init__.py app/services/product_service.py tests/test_product_url.py tests/test_product_service.py
git commit -m "feat: parse product ids from supported urls"
```

### Task 2: 平台主图抓取与结果序列化

**Files:**
- Modify: `app/infrastructure/walmart/scraper.py`
- Modify: `app/infrastructure/amazon/scraper.py`
- Modify: `backend/application/analysis_runner.py`
- Test: `tests/test_scraper_images.py`
- Test: `backend/tests/test_analysis_runner.py`

- [ ] **Step 1: Write failing extraction tests**

Use a fake page whose read-only `evaluate` returns a list of image URLs. Assert Walmart and Amazon helpers return de-duplicated URLs in document order and ignore blank/data URLs.

```python
@pytest.mark.asyncio
async def test_walmart_extracts_unique_product_images():
    page = FakePage(["https://cdn.example/a.jpg", "", "data:image/png;base64,x", "https://cdn.example/a.jpg", "https://cdn.example/b.jpg"])
    assert await ProductDetailScraper(AsyncMock())._extract_images(page) == [
        "https://cdn.example/a.jpg", "https://cdn.example/b.jpg"
    ]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.\.venv\Scripts\pytest.exe tests/test_scraper_images.py -q`

Expected: FAIL because `_extract_images` is not defined and scrapers leave `ProductDTO.images` empty.

- [ ] **Step 3: Implement extraction and metadata serialization**

Extract `og:image`, product gallery `img` `src`/`data-src`, and JSON-LD image values through one bounded page evaluation. Normalize to absolute HTTP(S) URLs, remove duplicates, cap at 8 images, and assign `dto.images`. In `_serialize_hypothesis`, include `product_id`, `product_title_zh` from `result.product_analysis.get("title")`, and the existing product image list. Add the same metadata to judgment payload from `product_a` and preserve it in `_wrap_models`.

- [ ] **Step 4: Run focused backend tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_scraper_images.py backend/tests/test_analysis_runner.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/infrastructure/walmart/scraper.py app/infrastructure/amazon/scraper.py backend/application/analysis_runner.py tests/test_scraper_images.py backend/tests/test_analysis_runner.py
git commit -m "feat: persist product image and title metadata"
```

### Task 3: Judgment 中文标题字段

**Files:**
- Modify: `app/domain/schemas/judgment.py`
- Modify: `app/services/judgment_service.py`
- Modify: `app/infrastructure/llm/prompts/judgment_b.txt`
- Test: `tests/test_judgment_service.py`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: Write the failing test**

Add a structured-output fixture containing `product_title_zh: "便携式行李秤"`; assert `JudgmentService.judge` exposes it on the DTO and the prompt explicitly requires a Chinese main-product title.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `.\.venv\Scripts\pytest.exe tests/test_judgment_service.py tests/test_prompts.py -q`

Expected: FAIL because the DTO/schema currently drops the field and the prompt does not request it.

- [ ] **Step 3: Implement the optional field**

Add `product_title_zh: str = ""` to `JudgmentOutput` and `JudgmentResultDTO`, copy it after validation, and add it to the required JSON example/prompt as a model-generated translation of product A's title. Keep `extra="ignore"` and the empty fallback for old/provider responses.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\pytest.exe tests/test_judgment_service.py tests/test_prompts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/domain/schemas/judgment.py app/domain/dto/__init__.py app/services/judgment_service.py app/infrastructure/llm/prompts/judgment_b.txt tests/test_judgment_service.py tests/test_prompts.py
git commit -m "feat: save judgment product title translation"
```

### Task 4: 进度双写

**Files:**
- Modify: `backend/db/repositories.py`
- Modify: `backend/workers/jobs.py`
- Test: `backend/tests/test_worker_jobs.py`
- Test: `backend/tests/test_job_repository.py`

- [ ] **Step 1: Write the failing tests**

Assert `JobRepository.set_progress(job_id, 35)` updates only a running job and that the worker's `report_progress` callback awaits both repository persistence and Redis persistence.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.\.venv\Scripts\pytest.exe backend/tests/test_worker_jobs.py backend/tests/test_job_repository.py -q`

Expected: FAIL because `set_progress` does not exist and the callback only writes Redis.

- [ ] **Step 3: Implement monotonic database progress**

Add an async repository update that writes `progress=max(existing_progress, max(0,min(100,pct)))` for the target job, commits, and returns the updated row. In `run_analysis_job`, call it from `report_progress` before `_set_progress`; keep Redis writes for queue-side visibility. Do not alter runner progress values.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\pytest.exe backend/tests/test_worker_jobs.py backend/tests/test_job_repository.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/db/repositories.py backend/workers/jobs.py backend/tests/test_worker_jobs.py backend/tests/test_job_repository.py
git commit -m "fix: persist live job progress"
```

### Task 5: API 类型与详情页元数据展示

**Files:**
- Modify: `backend/api/schemas/jobs.py`
- Modify: `backend/application/result_highlights.py`
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/components/jobs/job-progress.tsx`
- Modify: `frontend/components/jobs/result-summary.tsx`
- Modify: `frontend/components/jobs/result-analysis-module.tsx`
- Modify: `frontend/components/jobs/product-media.tsx`
- Modify: `frontend/app/jobs/[jobId]/page.tsx`
- Test: `frontend/tests/job-detail.test.tsx`
- Test: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: Add failing UI assertions**

Extend the mocked job payload with `product_id`, `product_title_zh`, and two `product_images`. Assert the detail page renders the ID, Chinese title, original title, and the image element; assert the progressbar receives a mid-task percentage.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `npm --prefix frontend test -- --run tests/job-detail.test.tsx tests/result-workbench-ui.test.tsx`

Expected: FAIL on missing metadata text and image fallback behavior.

- [ ] **Step 3: Implement typed metadata and rendering**

Add optional metadata fields to backend/frontend job types. Render a compact product identity block below `JobProgress` and inside `ResultSummary` with explicit old-task fallbacks. Update `ResultAnalysisModule` to pass all image candidates to `ProductMedia`; update `ProductMedia` to advance to the next URL after an `onError` before showing the empty state. Keep `aria-valuenow` bound to the API progress.

- [ ] **Step 4: Run focused frontend tests**

Run: `npm --prefix frontend test -- --run tests/job-detail.test.tsx tests/result-workbench-ui.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/api/schemas/jobs.py backend/application/result_highlights.py frontend/lib/api/types.ts frontend/components/jobs/job-progress.tsx frontend/components/jobs/result-summary.tsx frontend/components/jobs/result-analysis-module.tsx frontend/components/jobs/product-media.tsx frontend/app/jobs/[jobId]/page.tsx frontend/tests/job-detail.test.tsx frontend/tests/result-workbench-ui.test.tsx
git commit -m "feat: show product identity and result images"
```

### Task 6: 应用字体 A「清晰商务」

**Files:**
- Modify: `frontend/app/globals.css`
- Test: `frontend/tests/font-style.test.ts`

- [ ] **Step 1: Write the failing style assertion**

Read `frontend/app/globals.css` as UTF-8 and assert it declares `--font-ui` with the A stack and keeps `letter-spacing: 0` in the body rule.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm --prefix frontend test -- --run tests/font-style.test.ts`

Expected: FAIL because the A-specific CSS variable is not present.

- [ ] **Step 3: Implement the A tokenized font stack**

Define `--font-ui: "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", sans-serif` and apply it to body and controls; keep `letter-spacing: 0`, set normal text to 14px/1.65, headings to 600, and use the existing monospace stack only for keywords/IDs.

- [ ] **Step 4: Run the focused test**

Run: `npm --prefix frontend test -- --run frontend/tests/accessibility.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/app/globals.css frontend/tests/font-style.test.ts
git commit -m "style: apply clear business typography"
```

### Task 7: 全量验证与页面检查

**Files:**
- Modify: `docs/verification/job-progress-product-metadata.md`

- [ ] **Step 1: Run backend tests**

Run: `.\.venv\Scripts\pytest.exe backend/tests tests -q`

Expected: all existing and new tests pass; only the documented existing async resource warning may remain.

- [ ] **Step 2: Run frontend checks**

Run: `npm --prefix frontend test -- --run; npm --prefix frontend run typecheck; npm --prefix frontend run build`

Expected: all Vitest tests pass, TypeScript exits 0, and Next.js production build completes.

- [ ] **Step 3: Run browser verification**

Run: `npm --prefix frontend exec playwright test e2e/job-lifecycle.spec.ts e2e/result-workbench.spec.ts --project=desktop --project=mobile`

Expected: desktop and mobile pages show a nonzero mid-task progress bar, product ID/Chinese title, and image or explicit fallback without console errors.

- [ ] **Step 4: Record verification**

Write the command results and any known old-task fallback behavior to `docs/verification/job-progress-product-metadata.md`, then commit the verification record.
