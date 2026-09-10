# Core Stabilization Verification

**Date:** 2026-07-15  
**Branch:** `feature/web-platform`  
**Python:** 3.13.12

## Commands and Results

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Result: `77 passed in 6.13s`, exit code `0`, no warnings.

```powershell
.venv\Scripts\ruff.exe check app tests
```

Result: `All checks passed!`, exit code `0`.

```powershell
.venv\Scripts\python.exe -m compileall -q app tests
```

Result: exit code `0` with no output.

## Verified Behaviors

- Product routing rejects unsafe schemes and lookalike Walmart/Amazon hosts.
- Batch resume includes failed entries and checkpoint writes use atomic replacement.
- ProductService rejects missing title or price before LLM analysis.
- Structured LLM calls send JSON Schema and validate returned grade/score types.
- Scraped product content is delimited as untrusted prompt data.
- Result filenames are collision-safe and judgment Excel export retains B products without score data.
- Browser cleanup terminates only manager-owned Chrome processes.
- Existing generate, judge, and batch CLI dispatch contracts remain intact.
