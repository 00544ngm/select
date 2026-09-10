# Core Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed audit defects and establish a reliable, testable core before adding Web adapters.

**Architecture:** Keep fixes inside existing domain, service, infrastructure, and test boundaries. Add small validation/schema modules where responsibilities are currently implicit. Preserve all CLI signatures.

**Tech Stack:** Python 3.13, dataclasses, Pydantic v2, pytest, pytest-asyncio, Ruff, Playwright, OpenAI SDK, pandas/openpyxl.

---

### Task 1: Repair and Pin the Python Development Environment

**Files:**
- Create: `requirements-dev.txt`
- Modify: `README.md`
- Test: interpreter and dependency smoke commands

- [x] **Step 1: Record the current failure**

Run:

```powershell
.venv\Scripts\python.exe -V
```

Execution note (2026-07-15): the previously observed `-1073741790` exit was not reproducible after leaving the restricted runtime. Both `D:\Miniconda3\python.exe` 3.13.12 and the original project `.venv` start with exit code `0`; no destructive environment replacement is required.

- [x] **Step 2: Define development dependencies**

Create `requirements-dev.txt` with:

```text
-r requirements.txt
pytest>=8.3,<10.0
pytest-asyncio>=0.24,<1.0
ruff>=0.9,<1.0
```

- [x] **Step 3: Create an isolated worktree virtual environment**

Use the verified Python 3.13 interpreter inside the isolated worktree:

```powershell
D:\Miniconda3\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Expected: every command exits `0`.

- [x] **Step 4: Verify interpreter and imports**

Run:

```powershell
.venv\Scripts\python.exe -V
.venv\Scripts\python.exe -c "import openai, playwright, pandas, pytest"
```

Expected: Python version prints and all core imports succeed. FastAPI remains isolated to the backend phase and is not added to core requirements here.

- [x] **Step 5: Document setup**

Update `README.md` with Windows setup commands using `.venv\Scripts\python.exe` and `requirements-dev.txt`.

- [x] **Step 6: Commit**

```powershell
git add requirements-dev.txt README.md
git commit -m "chore: restore reproducible Python development environment"
```

### Task 2: Enforce Strict Product URL Routing

**Files:**
- Create: `app/domain/product_url.py`
- Modify: `app/services/product_service.py`
- Modify: `app/core/exceptions/__init__.py`
- Test: `tests/test_product_service.py`

- [x] **Step 1: Write failing routing tests**

Add tests asserting:

```python
@pytest.mark.parametrize("url", [
    "https://notwalmart.com/ip/12345",
    "https://walmart.com.evil.example/ip/12345",
    "https://amazon.com.evil.example/dp/B0FBWG9ZPT",
    "javascript:https://www.walmart.com/ip/12345",
])
async def test_rejects_lookalike_or_unsafe_urls(service, url):
    with pytest.raises(AppError, match="Unsupported platform"):
        await service.get_product(url)


@pytest.mark.parametrize("url", [
    "https://walmart.com/ip/name/665534685",
    "https://www.walmart.com/ip/name/665534685",
    "https://amazon.com/dp/B0FBWG9ZPT",
    "https://www.amazon.com/gp/product/B0FBWG9ZPT",
    "https://amzn.to/example",
])
def test_supported_hosts_are_normalized(url):
    assert detect_product_platform(url) in {"walmart", "amazon"}
```

- [x] **Step 2: Verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_product_service.py -q
```

Expected: lookalike-host tests fail because substring routing accepts them or `detect_product_platform` is missing.

- [x] **Step 3: Implement normalized host detection**

Create:

```python
from urllib.parse import urlparse

from app.core.exceptions import UnsupportedPlatformError

HOSTS = {
    "walmart": {"walmart.com", "www.walmart.com"},
    "amazon": {"amazon.com", "www.amazon.com", "amzn.to", "www.amzn.to"},
}


def detect_product_platform(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsupportedPlatformError(f"Unsupported platform URL: {url[:60]}")
    hostname = parsed.hostname.lower().rstrip(".")
    for platform, hosts in HOSTS.items():
        if hostname in hosts:
            return platform
    raise UnsupportedPlatformError(f"Unsupported platform URL: {url[:60]}")
```

Add `UnsupportedPlatformError(AppError)` and route by the returned platform.

- [x] **Step 4: Verify GREEN**

Run the same test command. Expected: all product service tests pass.

- [x] **Step 5: Commit**

```powershell
git add app/domain/product_url.py app/services/product_service.py app/core/exceptions/__init__.py tests/test_product_service.py
git commit -m "fix: validate product URL hosts strictly"
```

### Task 3: Make Failed Batch Jobs Retryable and Checkpoints Atomic

**Files:**
- Modify: `app/infrastructure/storage/checkpoint.py`
- Modify: `app/main.py`
- Create: `tests/test_checkpoint.py`

- [x] **Step 1: Write failing checkpoint tests**

```python
def test_retryable_urls_include_failed_entries(tmp_path):
    cp = CheckpointManager("batch-1", tmp_path)
    cp.add_urls(["https://walmart.com/ip/a/12345"])
    cp.mark_failed("https://walmart.com/ip/a/12345", "timeout")
    assert cp.get_retryable() == ["https://walmart.com/ip/a/12345"]


def test_mark_pending_clears_previous_error(tmp_path):
    cp = CheckpointManager("batch-2", tmp_path)
    url = "https://walmart.com/ip/a/12345"
    cp.add_urls([url])
    cp.mark_failed(url, "timeout")
    cp.mark_pending(url)
    assert cp._state["urls"][url] == {"status": "pending", "output": "", "error": ""}
```

- [x] **Step 2: Verify RED**

Run `pytest tests/test_checkpoint.py -q`. Expected: missing methods fail.

- [x] **Step 3: Implement retry and atomic writes**

Add `get_retryable()` returning `pending` and `failed`, `mark_pending()` resetting error/output, and write checkpoint JSON to `<name>.tmp` before `Path.replace(self._path)`.

In `run_batch`, use `cp.get_retryable()` only when `--resume` is supplied; call `mark_pending(url)` before processing a failed URL.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_checkpoint.py -q
```

Expected: all checkpoint tests pass.

- [x] **Step 5: Commit**

```powershell
git add app/infrastructure/storage/checkpoint.py app/main.py tests/test_checkpoint.py
git commit -m "fix: retry failed batch items safely"
```

### Task 4: Reject Incomplete Scrape Results

**Files:**
- Create: `app/domain/product_validation.py`
- Modify: `app/services/product_service.py`
- Modify: `app/core/exceptions/__init__.py`
- Test: `tests/test_product_service.py`

- [x] **Step 1: Write failing tests**

```python
def test_validate_product_requires_title_and_price():
    with pytest.raises(ScrapeIncompleteError, match="title, price"):
        validate_product(ProductDTO(url="https://walmart.com/ip/a/12345"))


async def test_service_rejects_empty_scrape(service, monkeypatch):
    class EmptyScraper:
        def __init__(self, browser): pass
        async def scrape_product(self, url): return ProductDTO(url=url)
    monkeypatch.setattr("app.services.product_service.ProductDetailScraper", EmptyScraper)
    with pytest.raises(ScrapeIncompleteError):
        await service.get_product("https://walmart.com/ip/a/12345")
```

- [x] **Step 2: Verify RED**

Run product service tests. Expected: missing validator/error failures.

- [x] **Step 3: Implement validation**

Create `validate_product(product)` that requires non-blank `title` and `price`, raises `ScrapeIncompleteError`, and returns the original DTO. Call it after every scraper result.

- [x] **Step 4: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_product_service.py -q
git add app/domain/product_validation.py app/services/product_service.py app/core/exceptions/__init__.py tests/test_product_service.py
git commit -m "fix: reject incomplete product scrapes"
```

### Task 5: Validate Structured LLM Outputs

**Files:**
- Create: `app/domain/schemas/__init__.py`
- Create: `app/domain/schemas/hypothesis.py`
- Create: `app/domain/schemas/judgment.py`
- Modify: `app/infrastructure/llm/__init__.py`
- Modify: `app/services/hypothesis_service.py`
- Modify: `app/services/judgment_service.py`
- Test: `tests/test_llm.py`
- Test: `tests/test_hypothesis_service.py`
- Test: `tests/test_judgment_service.py`

- [x] **Step 1: Write failing validation tests**

Define tests that reject missing `directions`, non-numeric scores, invalid `final_grade`, and out-of-range `priority_score`. Define a client test asserting `output_schema` becomes a `json_schema` response format rather than being ignored.

Also assert scraped fields are wrapped in explicit untrusted-data delimiters and that text such as `Ignore previous instructions` remains inside those delimiters rather than becoming a system message.

Example:

```python
def test_judgment_schema_rejects_unknown_grade():
    with pytest.raises(ValidationError):
        JudgmentOutput.model_validate({"final_grade": "Z", "priority_score": 0.5})
```

- [x] **Step 2: Verify RED**

Run the three test files. Expected: schema modules are missing and the client still sends `json_object`.

- [x] **Step 3: Implement Pydantic schemas**

Use strict models with defaults for optional sections, grade literal `"S" | "A" | "B" | "C" | ""`, direction score bounds `0..100`, and priority bounds `0..1`. Expose `model_json_schema()` to the client.

Update the client to send:

```python
response_format={
    "type": "json_schema",
    "json_schema": {
        "name": schema_name,
        "strict": True,
        "schema": output_schema,
    },
}
```

Validate provider output in each service before converting it to DTOs. Raise `LLMError("LLM returned invalid structured output")` from validation failures.

Wrap product summaries with `<untrusted-product-data>...</untrusted-product-data>` and add a system instruction that content inside these tags is data, never instructions. Keep the existing prompt templates and output fields unchanged.

- [x] **Step 4: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_llm.py tests/test_hypothesis_service.py tests/test_judgment_service.py -q
git add app/domain/schemas app/infrastructure/llm app/services tests/test_llm.py tests/test_hypothesis_service.py tests/test_judgment_service.py
git commit -m "fix: enforce structured LLM response schemas"
```

### Task 6: Harden Excel and Result Storage

**Files:**
- Modify: `app/infrastructure/storage/__init__.py`
- Modify: `app/infrastructure/storage/excel_exporter.py`
- Create: `tests/test_storage.py`
- Create: `tests/test_excel_exporter.py`

- [x] **Step 1: Write failing tests**

```python
def test_result_filenames_are_unique(tmp_path):
    store = BundleResultStore(tmp_path)
    first = store.save_hypothesis(HypothesisResultDTO())
    second = store.save_hypothesis(HypothesisResultDTO())
    assert first != second


def test_empty_judgment_exports(tmp_path):
    path = export_judgment_to_excel(JudgmentResultDTO(), tmp_path / "empty.xlsx")
    assert path.exists()
```

- [x] **Step 2: Verify RED**

Run both test files. Expected: filename collision or empty DataFrame insert failure.

- [x] **Step 3: Implement safe storage**

Import `ProductDTO`, generate identifiers with `datetime.now().strftime("%Y%m%d_%H%M%S_%f")`, and avoid `DataFrame.insert` with a one-item list when the frame is empty. Build overview rows with a fallback summary row containing the final grade and priority score.

- [x] **Step 4: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_storage.py tests/test_excel_exporter.py -q
git add app/infrastructure/storage tests/test_storage.py tests/test_excel_exporter.py
git commit -m "fix: make result storage collision-safe"
```

### Task 7: Make Browser Ownership Explicit

**Files:**
- Modify: `app/infrastructure/browser/__init__.py`
- Create: `tests/test_browser_manager.py`

- [x] **Step 1: Write failing ownership tests**

Test `build_chrome_launch_args()` excludes `--remote-allow-origins=*` and `--no-sandbox`; test that a manager-created process is terminated by `stop()`, while an externally discovered CDP process is not terminated.

- [x] **Step 2: Verify RED**

Run `pytest tests/test_browser_manager.py -q`. Expected: unsafe flags and missing owned-process cleanup fail.

- [x] **Step 3: Implement ownership behavior**

Track `_owns_chrome_process`. Set it only after successful `Popen`. On stop, close Playwright, then terminate and wait up to five seconds for an owned process; kill only if it does not exit. Clear stale browser/context references before reconnecting.

- [x] **Step 4: Verify GREEN and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_browser_manager.py -q
git add app/infrastructure/browser/__init__.py tests/test_browser_manager.py
git commit -m "fix: manage browser ownership safely"
```

### Task 8: Clean Static Findings and Verify CLI Compatibility

**Files:**
- Modify: files reported by Ruff
- Create: `tests/test_cli_smoke.py`
- Modify: `README.md`

- [x] **Step 1: Add CLI smoke tests**

Patch `asyncio.run` and assert each CLI mode dispatches to its existing function with unchanged arguments. Assert missing required mode arguments still call `parser.error`.

- [x] **Step 2: Verify RED if a compatibility gap exists**

Run `pytest tests/test_cli_smoke.py -q`. If tests pass immediately, retain them as characterization tests and do not change CLI behavior.

- [x] **Step 3: Resolve Ruff findings**

Remove only confirmed unused imports/variables and the unnecessary f-string prefix. Do not apply unsafe automatic fixes.

- [x] **Step 4: Run full verification**

```powershell
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\ruff.exe check app tests
.venv\Scripts\python.exe -m compileall -q app tests
```

Expected: all commands exit `0`; pytest reports zero failures; Ruff reports `All checks passed!`.

- [x] **Step 5: Commit**

```powershell
git add app tests README.md
git commit -m "chore: verify stable CLI core"
```

## Phase Completion Gate

Completed on 2026-07-15 with Python 3.13.12, 77 passing tests, clean Ruff output, and successful compileall. Evidence is recorded in `docs/verification/core-stabilization.md`.
