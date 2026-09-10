# AI Connection Auto-Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically validate AI connections only when configuration changes or a real model call fails, while keeping successful validations indefinitely.

**Architecture:** Reuse connection revision records as the sole staleness signal. Make availability checks read-only, trigger one short real-model probe after changed saves, and run diagnostic probes only for provider-related worker failures. Remove UI page-load probes and the cross-review 24-hour cutoff.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React/Next.js, TanStack Query, Vitest, Electron.

---

### Task 1: Make model availability read-only

**Files:**
- Modify: `backend/application/provider_service.py`
- Test: `backend/tests/test_provider_service.py`

- [ ] Add tests proving a current verified/selected model returns true without invoking the verifier and failed/stale records return false.
- [ ] Run the focused tests and confirm the existing implementation fails the no-call assertion.
- [ ] Remove the unconditional live probe from `is_model_available`.
- [ ] Run the focused provider service tests.

### Task 2: Save and automatically validate changed configuration

**Files:**
- Modify: `frontend/components/settings/provider-settings-panel.tsx`
- Test: `frontend/tests/provider-settings.test.tsx`

- [ ] Add tests proving page load does not verify, changed/new saves verify the default model once, and unchanged saves do not verify.
- [ ] Run the focused frontend tests and confirm the new expectations fail.
- [ ] Remove page-load auto-verification and chain automatic verification from a successful changed save.
- [ ] Update settings copy to explain failure-driven verification and small Token use.
- [ ] Run the focused frontend tests.

### Task 3: Diagnose provider failures in the worker

**Files:**
- Modify: `backend/application/provider_service.py`
- Modify: `backend/workers/jobs.py`
- Test: `backend/tests/test_worker_jobs.py`

- [ ] Add tests proving provider technical failures trigger one automatic diagnostic probe and business/scrape failures do not.
- [ ] Run focused worker tests and confirm failure.
- [ ] Add a provider service diagnostic method that records the short-probe result.
- [ ] Invoke it from the worker only after provider failure classification and before rotation/final failure handling.
- [ ] Run focused worker tests.

### Task 4: Remove time-based validation gates

**Files:**
- Modify: `backend/api/routes/jobs.py`
- Modify: `frontend/components/jobs/job-error.tsx`
- Test: `backend/tests/test_jobs_api.py`
- Test: relevant frontend error tests

- [ ] Add an API test proving an old but current-revision verification remains eligible for cross-review.
- [ ] Run it and confirm the 24-hour cutoff rejects it.
- [ ] Replace the cutoff with status, selection, protocol, and connection-revision checks.
- [ ] Remove 24-hour wording from UI errors.
- [ ] Run focused tests.

### Task 5: Version, full verification, and package

**Files:**
- Modify: `desktop/package.json`
- Modify: `desktop/package-lock.json`
- Modify: `backend/main.py`

- [ ] Set version to `0.1.9`.
- [ ] Run all backend tests.
- [ ] Run all frontend tests, typecheck, and production build.
- [ ] Run desktop tests, typecheck/build, and generate the Windows installer.
- [ ] Verify installer SHA-256 and report its absolute path without changing existing user data.
