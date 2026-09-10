# Cross-Review Markdown Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render cross-review model responses as safe, readable Markdown documents while preserving the exact raw response for audit.

**Architecture:** Extend the existing dependency-free cross-review formatter into a whitelist parser that produces typed document blocks and inline emphasis nodes. Render those nodes through React semantic elements in a focused component; retain the original string in a collapsed raw-text panel.

**Tech Stack:** TypeScript, React 19, Next.js 15, Tailwind CSS, Vitest, Testing Library.

---

### Task 1: Parse Block-Level Markdown

**Files:**
- Modify: `frontend/lib/cross-review-format.ts`
- Modify: `frontend/tests/cross-review-format.test.ts`

- [ ] **Step 1: Write failing parser tests**

Add tests that request typed blocks for headings, paragraphs, ordered/unordered lists, and Markdown tables:

```ts
const document = parseCrossReviewMarkdown([
  "## 合理之处",
  "",
  "正文 **重点**。",
  "",
  "- 风险一",
  "- 风险二",
  "",
  "| 方向 | 判断 |",
  "| --- | --- |",
  "| 笔 | 合理 |",
].join("\n"));

expect(document.map((block) => block.kind)).toEqual([
  "heading", "paragraph", "unordered-list", "table",
]);
```

Add a malformed-table test asserting it falls back to paragraph text.

- [ ] **Step 2: Run parser tests and verify RED**

Run: `npm.cmd test -- --run tests/cross-review-format.test.ts`

Working directory: `frontend`

Expected: FAIL because `parseCrossReviewMarkdown` and document block types do not exist.

- [ ] **Step 3: Implement the minimal whitelist parser**

Define:

```ts
export type CrossReviewInline =
  | { kind: "text"; value: string }
  | { kind: "strong"; value: string };

export type CrossReviewDocumentBlock =
  | { kind: "heading"; level: number; content: CrossReviewInline[] }
  | { kind: "paragraph"; content: CrossReviewInline[] }
  | { kind: "unordered-list"; items: CrossReviewInline[][] }
  | { kind: "ordered-list"; items: CrossReviewInline[][] }
  | { kind: "table"; headers: CrossReviewInline[][]; rows: CrossReviewInline[][][] };
```

Implement `parseCrossReviewMarkdown(raw)` with normalized line scanning. Recognize only ATX headings, list prefixes, valid pipe tables, paragraphs, blank-line boundaries, and `**strong**`. Do not parse HTML or links into executable markup. Keep existing `formatCrossReview` and `joinCrossReviewBlocks` exports for backward compatibility.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `npm.cmd test -- --run tests/cross-review-format.test.ts`

Expected: PASS.

### Task 2: Render a Semantic Review Document

**Files:**
- Create: `frontend/components/jobs/cross-review-document.tsx`
- Modify: `frontend/components/jobs/cross-review-panel.tsx`
- Modify: `frontend/tests/result-workbench-ui.test.tsx`
- Modify: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: Write failing component tests**

Add a cross-review payload containing:

```md
## 合理之处
### 核心场景
正文包含 **评论证据**。

- 结实耐用
- 便于携带

| 搭配方向 | 判断 |
| --- | --- |
| 笔 | 合理 |
```

Assert:

```ts
expect(screen.getByRole("heading", { name: "合理之处", level: 2 })).toBeInTheDocument();
expect(screen.getByRole("list")).toBeInTheDocument();
expect(screen.getByRole("table")).toBeInTheDocument();
expect(screen.getByText("评论证据").tagName).toBe("STRONG");
expect(screen.queryByText("## 合理之处")).not.toBeInTheDocument();
```

Assert the raw string is available only after opening “查看模型原文” and that the raw `textContent` is exactly unchanged.

- [ ] **Step 2: Run UI tests and verify RED**

Run: `npm.cmd test -- --run tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx`

Working directory: `frontend`

Expected: FAIL because Markdown markers are still rendered as plain text and no raw-text disclosure exists.

- [ ] **Step 3: Implement semantic rendering**

Create `CrossReviewDocument` that maps only typed parser output to:

- headings: `h2`–`h6`
- paragraphs: `p`
- lists: `ul/ol/li`
- tables: `table/thead/tbody/tr/th/td` inside `overflow-x-auto`
- emphasis: `strong`

Use React text nodes for every model-supplied value. Do not use `dangerouslySetInnerHTML`.

Replace `ReviewText` in `cross-review-panel.tsx` with:

```tsx
<CrossReviewDocument raw={review.raw} />
<details className="mt-5 border-t pt-3">
  <summary>查看模型原文</summary>
  <pre data-testid={`cross-review-raw-${key}`} className="whitespace-pre-wrap">
    {review.raw}
  </pre>
</details>
```

- [ ] **Step 4: Run UI tests and verify GREEN**

Run: `npm.cmd test -- --run tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx`

Expected: PASS.

### Task 3: Full Verification and Runtime Restart

**Files:**
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: Run focused tests**

Run:

```powershell
npm.cmd test -- --run tests/cross-review-format.test.ts tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx
```

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 2: Run full frontend regression**

Run: `npm.cmd test -- --run`

Working directory: `frontend`

Expected: all test files pass.

- [ ] **Step 3: Run type checking**

Run: `npm.cmd run typecheck`

Working directory: `frontend`

Expected: exit code 0.

- [ ] **Step 4: Build without concurrent Next dev**

Identify the exact `web-platform-v2.1-work` Next dev PID. Stop only that PID and verify it is gone.

Run: `npm.cmd run build`

Working directory: `frontend`

Expected: optimized production build succeeds.

- [ ] **Step 5: Restart and probe**

Restart `npm.cmd run dev` in a hidden window. Verify:

- `http://127.0.0.1:3000/` returns HTTP 200.
- `http://127.0.0.1:8000/api/v1/health/ready` returns HTTP 200.

- [ ] **Step 6: Record results**

Append success and every encountered failure to `docs/优化迭代记录.md`. Do not log API keys, cookies, tokens, or other reusable credentials.
