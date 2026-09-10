# Verified Model First Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the workbench empty state and move freshly verified provider models to the first catalog page.

**Architecture:** Keep provider validation and persistence unchanged. Add a deterministic front-end ordering helper, reset pagination only after successful verification, and preserve existing query-cache updates.

**Tech Stack:** Next.js, React, TypeScript, TanStack Query, Vitest, Testing Library, Electron Builder.

---

### Task 1: Workbench empty-state regression

**Files:**
- Modify: `frontend/tests/job-forms.test.tsx`
- Modify: `frontend/components/workbench/hypothesis-form.tsx`

- [ ] Run the existing regression asserting that no-provider state displays `请先配置 API` and not `提交中`.
- [ ] Confirm `tests/job-forms.test.tsx` passes without changing the already implemented minimal fix.

### Task 2: Verified-model catalog ordering

**Files:**
- Modify: `frontend/tests/provider-settings.test.tsx`
- Modify: `frontend/components/settings/provider-settings-panel.tsx`

- [ ] Add a failing test with more than ten models where a verified model begins on page two; expect it on page one before unverified models.
- [ ] Run the test and confirm RED because current code preserves directory order.
- [ ] Add a stable ordering helper that ranks fresh verified models first, default models second, and otherwise keeps input order.
- [ ] Add a failing interaction test that starts on page two, verifies a model, and expects pagination to return to page one.
- [ ] Run the test and confirm RED because verification currently leaves the selected page unchanged.
- [ ] Set the catalog page to one only when verification returns `verified`.
- [ ] Run provider settings tests and confirm GREEN.

### Task 3: Verification and desktop release

**Files:**
- Modify: `docs/优化迭代记录.md`
- Generate: `release/组合选品控制台-Setup-0.1.1.exe`
- Generate: `release/组合选品控制台-Setup-0.1.1.exe.sha256`

- [ ] Run `npm.cmd test -- --run tests/job-forms.test.tsx tests/provider-settings.test.tsx` from `frontend/`.
- [ ] Run `npm.cmd run typecheck` and `npm.cmd run build` from `frontend/`.
- [ ] Rebuild packaged services and Electron/NSIS installer with the locked local Electron runtime.
- [ ] Verify the unpacked desktop process tree, API readiness, worker heartbeat, and zero periodic Git focus-stealing processes.
- [ ] Record successes and failures in the Chinese iteration log and calculate the final SHA-256.

No Git commit is included because the user explicitly prohibited Git writes for this workspace.
