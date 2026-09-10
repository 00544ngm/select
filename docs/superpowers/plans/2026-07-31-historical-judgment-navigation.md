# Historical Judgment Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the historical-incomplete status open the current direction's deep analysis and focus the historical processing explanation without rewriting historical data.

**Architecture:** Reuse `DirectionDetail`'s existing deep-analysis state, guidance ref, scroll, focus, and highlight behavior. Replace the evidence-specific boolean pending state with an explicit target (`evidence` or `guidance`) so hold and historical-incomplete actions route to different regions through one effect.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Next.js 15.

---

### Task 1: Add the historical navigation regression test

**Files:**
- Modify: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: Write the failing test**

Add a test that renders `ResultAnalysisModule` with an evidence-incomplete historical rejection, clicks the uniquely named historical button, and checks that the guidance region receives focus, highlight, and scroll:

```tsx
it("opens and focuses the explanation for incomplete historical judgments", async () => {
  const user = userEvent.setup();
  const scrollIntoView = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoView,
  });
  render(
    <ResultAnalysisModule structuredDirections={[{
      ...directions[0],
      model_version: "combination_model_v2.1",
      execution_status: "reject",
      rejected: true,
      rejection_codes: ["incompatible"],
      source_fact_ids: ["title"],
      missing_evidence: ["核对具体兼容条件"],
    }]} />
  );

  await user.click(screen.getByRole("button", { name: "查看历史判定说明" }));

  const target = screen.getByRole("region", { name: "处理说明" });
  expect(target).toHaveFocus();
  expect(target).toHaveAttribute("data-highlighted", "true");
  expect(scrollIntoView).toHaveBeenCalled();
  expect(screen.getByRole("region", { name: "待验证证据" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
cd frontend
npm.cmd test -- --run tests/result-workbench-ui.test.tsx -t "opens and focuses the explanation for incomplete historical judgments"
```

Expected: FAIL because no button named “查看历史判定说明” exists.

### Task 2: Implement explicit navigation targets

**Files:**
- Modify: `frontend/components/jobs/direction-detail.tsx`

- [ ] **Step 1: Replace the evidence-only pending state**

Use an explicit pending target:

```tsx
const [pendingFocusTarget, setPendingFocusTarget] = useState<"evidence" | "guidance" | null>(null);

const reviewEvidence = () => {
  setShowDeepAnalysis(true);
  setPendingFocusTarget(direction.missing_evidence?.length ? "evidence" : "guidance");
};

const reviewHistoricalGuidance = () => {
  setShowDeepAnalysis(true);
  setPendingFocusTarget("guidance");
};
```

- [ ] **Step 2: Route the shared focus effect by target**

```tsx
useEffect(() => {
  if (!showDeepAnalysis || !pendingFocusTarget) return;
  const target = pendingFocusTarget === "evidence"
    ? evidenceTargetRef.current
    : guidanceTargetRef.current;
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
  target?.focus({ preventScroll: true });
  setHighlightedTarget(pendingFocusTarget);
  setPendingFocusTarget(null);
}, [pendingFocusTarget, showDeepAnalysis]);
```

Reset `pendingFocusTarget` when `direction.name` changes.

- [ ] **Step 3: Render the historical action button**

Keep the hold button unchanged. For `historical_incomplete`, render:

```tsx
<button
  type="button"
  aria-label="查看历史判定说明"
  onClick={reviewHistoricalGuidance}
  className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
>
  <Badge variant="default" className="cursor-pointer">{guidance.title}</Badge>
</button>
```

Do not make `pass` or complete `reject` badges interactive.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run:

```powershell
cd frontend
npm.cmd test -- --run tests/result-workbench-ui.test.tsx -t "opens and focuses"
```

Expected: the new historical navigation test and existing hold navigation test pass.

### Task 3: Verify and document

**Files:**
- Modify: `docs/优化迭代记录.md`
- Create: `docs/verification/2026-07-31-historical-judgment-navigation.md`

- [ ] **Step 1: Run frontend verification**

```powershell
cd frontend
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
```

Expected: typecheck, all frontend tests, and production build pass.

- [ ] **Step 2: Restart the exact workspace frontend service**

Verify the process listening on port 3000 belongs to `F:\组合品7-31\web-platform-v2.1-work\frontend`, stop only that process tree, then start `npm.cmd run dev` hidden with workspace-local logs. This avoids `.next` development/production cache mismatch after `next build`.

- [ ] **Step 3: Verify the real historical page**

On `/jobs/0b14fe4f-3459-4fb6-a08c-e9300359befc`, select a historical-incomplete direction and verify:

- one “查看历史判定说明” button exists;
- clicking it opens deep analysis;
- “处理说明” is focused and has `data-highlighted=true`;
- “待验证证据” remains visible when present;
- the original task result is unchanged.

- [ ] **Step 4: Record success and every failure**

Write command results, browser evidence, and any failure/root cause/fix to the Chinese iteration log and verification report. Do not commit or stage because the shared worktree contains unrelated user changes.

