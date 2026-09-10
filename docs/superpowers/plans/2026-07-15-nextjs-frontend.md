# Next.js Operations Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved responsive operations workbench for hypothesis, judgment, batch, status, history, results, and artifact downloads.

**Architecture:** A standalone Next.js App Router client calls `/api/v1` through a typed API module. TanStack Query owns server state and polling; React Hook Form plus Zod owns form state; shadcn/ui provides accessible primitives styled to match the approved layout.

**Tech Stack:** Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, Lucide, TanStack Query, React Hook Form, Zod, Vitest, Testing Library, MSW, Playwright.

---

### Task 1: Scaffold the Frontend and Test Harness

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/components.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/tests/setup.ts`
- Create: `frontend/.env.example`

- [ ] **Step 1: Scaffold Next.js**

Create an App Router TypeScript application with Tailwind, ESLint, `src` disabled, and import alias `@/*`. Add scripts: `dev`, `build`, `start`, `lint`, `typecheck`, `test`, and `test:watch`.

- [ ] **Step 2: Install runtime/test dependencies**

```powershell
npm --prefix frontend install @tanstack/react-query react-hook-form @hookform/resolvers zod lucide-react clsx tailwind-merge class-variance-authority
npm --prefix frontend install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event msw @playwright/test
```

- [ ] **Step 3: Add a failing shell test**

```tsx
render(<RootLayout><div>content</div></RootLayout>)
expect(screen.getByText("组合选品控制台")).toBeInTheDocument()
```

- [ ] **Step 4: Implement root metadata/providers and verify**

Use Chinese metadata, `lang="zh-CN"`, a local font stack, and a query provider. Run `npm --prefix frontend test -- --run`; expected: shell test passes.

- [ ] **Step 5: Commit**

```powershell
git add frontend
git commit -m "feat: scaffold Next.js operations frontend"
```

### Task 2: Build the Responsive Application Shell

**Files:**
- Create: `frontend/components/layout/app-shell.tsx`
- Create: `frontend/components/layout/sidebar.tsx`
- Create: `frontend/components/layout/mobile-nav.tsx`
- Create: `frontend/components/layout/service-status.tsx`
- Modify: `frontend/app/page.tsx`
- Test: `frontend/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing shell behavior tests**

Assert navigation labels, active state, service status, desktop sidebar, mobile menu button, and accessible landmark names.

- [ ] **Step 2: Implement the approved shell**

Desktop uses a 232 px sidebar and flat content region. Mobile uses a menu icon with a shadcn Sheet. Use `LayoutDashboard`, `Sparkles`, `Scale`, `ListChecks`, `History`, `Database`, and `Settings2` icons with tooltips for icon-only controls.

- [ ] **Step 3: Verify and commit**

```powershell
npm --prefix frontend test -- --run frontend/tests/app-shell.test.tsx
git add frontend
git commit -m "feat: add responsive operations shell"
```

### Task 3: Add Typed API Client and Query Contracts

**Files:**
- Create: `frontend/lib/api/types.ts`
- Create: `frontend/lib/api/client.ts`
- Create: `frontend/lib/api/jobs.ts`
- Create: `frontend/lib/query-keys.ts`
- Create: `frontend/lib/job-status.ts`
- Test: `frontend/tests/api-client.test.ts`

- [ ] **Step 1: Write failing client tests**

Use MSW to assert base URL use, JSON request bodies, stable error decoding, artifact blob download, and polling interval behavior.

```ts
expect(getJobPollingInterval({ status: "running" })).toBe(1500)
expect(getJobPollingInterval({ status: "completed" })).toBe(false)
```

- [ ] **Step 2: Implement client/contracts**

Define discriminated `JobMode` and `JobStatus` unions matching backend schemas. `apiFetch<T>` throws `ApiError(code, message, retryable, status)`. Never expose backend environment secrets to client code.

- [ ] **Step 3: Verify and commit**

```powershell
npm --prefix frontend test -- --run frontend/tests/api-client.test.ts
git add frontend/lib frontend/tests/api-client.test.ts
git commit -m "feat: add typed backend API client"
```

### Task 4: Implement Hypothesis and Judgment Forms

**Files:**
- Create: `frontend/components/workbench/workbench-tabs.tsx`
- Create: `frontend/components/workbench/hypothesis-form.tsx`
- Create: `frontend/components/workbench/judgment-form.tsx`
- Create: `frontend/components/workbench/url-field.tsx`
- Create: `frontend/lib/schemas/job-forms.ts`
- Modify: `frontend/app/page.tsx`
- Test: `frontend/tests/job-forms.test.tsx`

- [x] **Step 1: Write failing form tests**

Test required URLs, lookalike-host rejection, add/remove B URL fields, disabled submit during mutation, successful navigation to `/jobs/{id}`, and accessible inline errors.

- [x] **Step 2: Implement forms**

Use shadcn Tabs, Input, Select, Switch, Button, and Form primitives. Match the approved two-column desktop layout and stacked mobile layout. The form submits only documented backend fields; collection switches remain disabled or omitted until backend options exist.

- [x] **Step 3: Verify and commit**

```powershell
npm --prefix frontend test -- --run frontend/tests/job-forms.test.tsx
git add frontend
git commit -m "feat: submit hypothesis and judgment jobs"
```

### Task 5: Implement Task Status and Result Views

**Files:**
- Create: `frontend/app/jobs/[jobId]/page.tsx`
- Create: `frontend/components/jobs/job-progress.tsx`
- Create: `frontend/components/jobs/job-error.tsx`
- Create: `frontend/components/jobs/result-summary.tsx`
- Create: `frontend/components/jobs/result-sections.tsx`
- Create: `frontend/components/jobs/artifact-actions.tsx`
- Test: `frontend/tests/job-detail.test.tsx`

- [x] **Step 1: Write failing state tests**

Cover queued, running progress, completed result, failed retry, unknown job, polling stop, JSON download, and Excel download. Assert no layout shifts when labels change.

- [x] **Step 2: Implement detail view**

Render stable-height progress steps for scrape, analysis, and save. Completed jobs show grade/score/directions and expandable structured sections. Failed jobs show the safe message and retry command without stack traces.

- [x] **Step 3: Verify and commit**

```powershell
npm --prefix frontend test -- --run frontend/tests/job-detail.test.tsx
git add frontend
git commit -m "feat: display live job progress and results"
```

### Task 6: Add Batch Submission and History

**Files:**
- Create: `frontend/components/workbench/batch-form.tsx`
- Create: `frontend/app/history/page.tsx`
- Create: `frontend/components/history/job-table.tsx`
- Create: `frontend/components/history/history-filters.tsx`
- Test: `frontend/tests/batch-history.test.tsx`

- [x] **Step 1: Write failing tests**

Test newline URL parsing/deduplication, invalid row reporting, pagination, mode/status filters, failed retry, empty history, and row navigation.

- [x] **Step 2: Implement batch/history**

Batch input displays accepted and rejected counts before submit. History uses a dense semantic table on desktop and compact rows on mobile. Retry is a RotateCcw icon button with a tooltip and confirmation dialog.

- [x] **Step 3: Verify and commit**

```powershell
npm --prefix frontend test -- --run frontend/tests/batch-history.test.tsx
git add frontend
git commit -m "feat: add batch jobs and task history"
```

### Task 7: Match the Approved Visual System and Accessibility

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: frontend layout/workbench/job components
- Create: `frontend/tests/accessibility.test.tsx`

- [x] **Step 1: Add automated accessibility assertions**

Assert every input has a label, icon-only buttons have accessible names, tab order reaches primary actions, status is not color-only, and text does not overflow at 320 px.

- [x] **Step 2: Implement design tokens**

Define neutral paper, graphite, border, semantic green, amber, and red variables. Keep border radius at 6 px, letter spacing at `0`, fixed control heights, visible focus rings, and no gradient/orb decoration.

- [x] **Step 3: Verify tests and TypeScript**

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

- [x] **Step 4: Commit**

```powershell
git add frontend
git commit -m "style: match approved operations workbench"
```

### Task 8: Playwright Verification and Operations Documentation

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/workbench.spec.ts`
- Create: `frontend/e2e/job-lifecycle.spec.ts`
- Create: `frontend/README.md`
- Create: `docs/verification/frontend.md`

- [x] **Step 1: Add E2E scenarios**

Use API mocking for deterministic UI tests: desktop/mobile workbench, hypothesis submit, judgment B URL management, running-to-complete transition, failure retry, history filters, and downloads.

- [x] **Step 2: Run build and screenshots**

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend exec playwright test
```

Expected: all commands exit `0`; screenshots exist at desktop `1440x900` and mobile `390x844` with no overlap or horizontal overflow.

- [x] **Step 3: Perform browser console check**

Open the production build, submit mocked tasks, and confirm no console errors, hydration warnings, failed assets, or unhandled promise rejections.

- [x] **Step 4: Document and commit**

Record command output, screenshot paths, and known external-service limits in `docs/verification/frontend.md`.

```powershell
git add frontend docs/verification/frontend.md
git commit -m "test: verify frontend workflows and responsive layout"
```

## Phase Completion Gate

The frontend phase is complete only after the production build, component suite, TypeScript checks, Playwright workflows, and desktop/mobile visual inspection all pass using fresh command output.

