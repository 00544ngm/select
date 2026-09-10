# 补证导航与精准关键词 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把待复核结论变成可直达证据的员工按钮，并把 Amazon 精准词与英文通用词拆成可分别复制、搜索的手风琴。

**Architecture:** 保持既有 `keywords.amazon/en` API 结构，在前端增加纯标准化函数与独立展示组件；`DirectionDetail` 统一协调深度分析展开、目标引用、滚动和焦点。提示词只约束新任务关键词质量，历史任务仅展示适配，不改写数据。

**Tech Stack:** React 19、Next.js 15、TypeScript、Vitest、Testing Library、Python/Pydantic、pytest。

**Execution boundary:** 当前工作区包含大量既有未提交变更。执行时不自动 `git add` 或 `git commit`，只在每项完成后运行精确测试并记录到 `docs/优化迭代记录.md`。

---

## File map

- Create: `frontend/lib/direction-keywords.ts` — 兼容对象、混合字符串和空值的关键词纯函数。
- Create: `frontend/components/jobs/direction-keyword-accordions.tsx` — 两个关键词手风琴、复制按钮和 Amazon 搜索链接。
- Modify: `frontend/components/jobs/direction-detail.tsx` — 替换混合关键词行，并协调补证按钮与深度分析展开。
- Modify: `frontend/components/jobs/platform-search-panel.tsx` — 移除已迁入手风琴的重复 Amazon/复制入口，只保留 Walmart 核验。
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx` — 渲染待复核按钮，接收补证目标引用和点击回调。
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt` — 约束新任务只生成一条精准 Amazon 词和一条通用英文词。
- Modify: `tests/test_prompts.py` — 固化提示词契约。
- Modify: `frontend/tests/result-workbench.test.ts` — 关键词标准化纯函数测试。
- Modify: `frontend/tests/result-workbench-ui.test.tsx` — 跳转、展开、复制、链接与历史兼容组件测试。
- Modify: `docs/优化迭代记录.md` — 记录每次红灯、失败、修复和最终验收。

### Task 1: 关键词标准化纯函数

**Files:**
- Create: `frontend/lib/direction-keywords.ts`
- Test: `frontend/tests/result-workbench.test.ts`

- [ ] **Step 1: 写对象、混合字符串和不可可靠拆分的红灯测试**

```ts
import { normalizeDirectionKeywords } from "@/lib/direction-keywords";

expect(normalizeDirectionKeywords({ amazon: "small torpedo level", en: "level tool for furniture" }))
  .toEqual({ amazon: "small torpedo level", en: "level tool for furniture" });
expect(normalizeDirectionKeywords("amazon: small torpedo level; en: level tool for furniture"))
  .toEqual({ amazon: "small torpedo level", en: "level tool for furniture" });
expect(normalizeDirectionKeywords("level tool for furniture"))
  .toEqual({ amazon: "", en: "level tool for furniture" });
```

- [ ] **Step 2: 运行红灯**

Run: `cd frontend && npm.cmd test -- --run tests/result-workbench.test.ts`

Expected: FAIL，`@/lib/direction-keywords` 尚不存在。

- [ ] **Step 3: 实现最小、无副作用的标准化函数**

```ts
export type DirectionKeywords = { amazon: string; en: string };

export function normalizeDirectionKeywords(value: unknown): DirectionKeywords {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    return {
      amazon: typeof record.amazon === "string" ? record.amazon.trim() : "",
      en: typeof record.en === "string" ? record.en.trim() : "",
    };
  }
  if (typeof value !== "string") return { amazon: "", en: "" };
  const text = value.trim();
  const match = text.match(/^amazon\s*[:：]\s*(.*?)\s*[;；]\s*en\s*[:：]\s*(.+)$/i);
  return match
    ? { amazon: match[1].trim(), en: match[2].trim() }
    : { amazon: "", en: text };
}

export function amazonSearchUrl(query: string): string {
  return `https://www.amazon.com/s?k=${encodeURIComponent(query.trim())}`;
}
```

- [ ] **Step 4: 增加 URL 编码断言并运行绿灯**

```ts
expect(amazonSearchUrl("small torpedo level"))
  .toBe("https://www.amazon.com/s?k=small%20torpedo%20level");
```

Run: `cd frontend && npm.cmd test -- --run tests/result-workbench.test.ts`

Expected: PASS。

### Task 2: 关键词手风琴组件

**Files:**
- Create: `frontend/components/jobs/direction-keyword-accordions.tsx`
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/platform-search-panel.tsx`
- Test: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: 写分组、默认展开、独立复制和搜索链接红灯测试**

```tsx
expect(screen.getByText("Amazon 精准关键词")).toBeInTheDocument();
expect(screen.getByText("英文通用关键词")).toBeInTheDocument();
expect(screen.queryByText(/amazon:.*en:/i)).not.toBeInTheDocument();
expect(screen.getByRole("link", { name: "打开 Amazon 搜索" }))
  .toHaveAttribute("href", "https://www.amazon.com/s?k=small%20torpedo%20level");
await user.click(screen.getByRole("button", { name: "复制精准词" }));
expect(navigator.clipboard.writeText).toHaveBeenCalledWith("small torpedo level");
```

- [ ] **Step 2: 运行红灯**

Run: `cd frontend && npm.cmd test -- --run tests/result-workbench-ui.test.tsx -t "keyword accordions"`

Expected: FAIL，页面仍显示单行“模型建议关键词”。

- [ ] **Step 3: 实现独立组件并替换旧单行区域**

组件固定接口：

```tsx
type Props = { keywords: unknown };
export default function DirectionKeywordAccordions({ keywords }: Props) { /* ... */ }
```

使用两个原生 `<details>`：Amazon 区域带 `open`，英文区域默认关闭。每个复制按钮只复制自身字段；空字段显示“暂无可用关键词”并禁用相关操作。Amazon 使用普通 `<a target="_blank" rel="noreferrer">`，确保新窗口被阻止时仍可复制或手动打开。

- [ ] **Step 4: 覆盖复制失败状态**

```tsx
await expect(copyButton).toHaveTextContent("复制失败，请手动复制");
```

组件 `try/catch` 捕获 `navigator.clipboard.writeText` 拒绝，并只更新当前手风琴按钮状态。

- [ ] **Step 5: 运行关键词组件回归**

Run: `cd frontend && npm.cmd test -- --run tests/result-workbench-ui.test.tsx tests/result-workbench.test.ts`

Expected: PASS。

### Task 3: 待复核按钮、展开与证据定位

**Files:**
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Test: `frontend/tests/result-workbench-ui.test.tsx`

- [ ] **Step 1: 写当前方向按钮行为红灯测试**

```tsx
await user.click(screen.getByRole("button", { name: "查看待补证据" }));
expect(screen.getByRole("region", { name: "待验证证据" })).toHaveFocus();
expect(screen.getByRole("region", { name: "待验证证据" }))
  .toHaveAttribute("data-highlighted", "true");
expect(screen.getByText("核对主品尺寸与候选规格")).toBeInTheDocument();
```

同时增加：`pass` 不渲染按钮；历史 hold 没有 `missing_evidence` 时焦点落到 `aria-label="处理说明"`。

- [ ] **Step 2: 运行红灯**

Run: `cd frontend && npm.cmd test -- --run tests/result-workbench-ui.test.tsx -t "evidence navigation"`

Expected: FAIL，现有结论为不可点击文本且深度分析未展开。

- [ ] **Step 3: 给评分卡增加明确接口**

```tsx
type StickinessScorecardProps = {
  direction: StructuredDirection;
  evidenceTargetRef?: React.RefObject<HTMLElement | null>;
  guidanceTargetRef?: React.RefObject<HTMLElement | null>;
  highlightedTarget?: "evidence" | "guidance" | null;
  onReviewEvidence?: () => void;
};
```

只有 `guidance.status === "hold"` 时，把“当前处理建议”渲染成 `aria-label="查看待补证据"` 的按钮。待验证证据区使用 `role="region"`、`aria-label="待验证证据"`、`tabIndex={-1}`；行动说明区使用 `aria-label="处理说明"`。

- [ ] **Step 4: 在详情组件协调展开、下一帧定位和高亮**

```tsx
const reviewEvidence = () => {
  setShowDeepAnalysis(true);
  setPendingEvidenceFocus(true);
};

useEffect(() => {
  if (!showDeepAnalysis || !pendingEvidenceFocus) return;
  const target = direction.missing_evidence?.length
    ? evidenceTargetRef.current
    : guidanceTargetRef.current;
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
  target?.focus({ preventScroll: true });
  setHighlightedTarget(direction.missing_evidence?.length ? "evidence" : "guidance");
  setPendingEvidenceFocus(false);
  const timeout = window.setTimeout(() => setHighlightedTarget(null), 1800);
  return () => window.clearTimeout(timeout);
}, [showDeepAnalysis, pendingEvidenceFocus, direction]);
```

切换方向时清除 pending/highlight，防止跳到前一个方向。

- [ ] **Step 5: 运行交互与相关页面回归**

Run: `cd frontend && npm.cmd test -- --run tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx`

Expected: PASS；既有 MSW `/settings/providers` 提示允许存在，但不得有失败测试。

### Task 4: 新任务精准关键词提示词契约

**Files:**
- Modify: `app/infrastructure/llm/prompts/hypothesis_a.txt`
- Modify: `tests/test_prompts.py`

- [ ] **Step 1: 写提示词红灯测试**

```py
assert "keywords.amazon：只输出 1 条 Amazon 精准检索短语" in prompt
assert "keywords.en：只输出 1 条英文通用扩展短语" in prompt
assert "禁止加入 amazon、促销词、无依据品牌词" in prompt
```

- [ ] **Step 2: 运行红灯**

Run: `& '.venv\Scripts\python.exe' -m pytest tests/test_prompts.py -k precise_keyword -q`

Expected: FAIL，现有提示词只要求至少包含两个键。

- [ ] **Step 3: 在现有 keywords 规则后增加全品类约束**

```text
- keywords.amazon：只输出 1 条 Amazon 精准检索短语；必须包含辅品核心品类名，仅在必要时加入规格、用途或适配对象；禁止加入 amazon、促销词、无依据品牌词、完整营销标题和重复近义词。
- keywords.en：只输出 1 条描述同一辅品的英文通用扩展短语，用于跨平台检索。
- 上述关键词是建议检索入口，不得声称已经过平台销量、相关性或商品可用性验证。
```

- [ ] **Step 4: 运行提示词与服务回归**

Run: `& '.venv\Scripts\python.exe' -m pytest tests/test_prompts.py tests/test_hypothesis_service.py -q`

Expected: PASS。

### Task 5: 全量验收、运行态验证与记录

**Files:**
- Create: `docs/verification/2026-07-31-evidence-navigation-and-precise-keywords.md`
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 运行前端完整验证**

Run: `cd frontend && npm.cmd test -- --run`

Expected: 全部 PASS。

Run: `cd frontend && npm.cmd run typecheck`

Expected: `tsc --noEmit` exit 0。

- [ ] **Step 2: 运行 Python 全量与定向 Ruff**

Run: `& '.venv\Scripts\python.exe' -m pytest -q`

Expected: 全部 PASS；记录既有异步数据库清理警告但不隐藏。

Run: `& '.venv\Scripts\python.exe' -m ruff check app/infrastructure/llm/prompts tests/test_prompts.py`

Expected: `All checks passed!`；若文本目录不适用于 Ruff，则只对 Python 测试文件执行并记录命令边界。

- [ ] **Step 3: 无并发开发服务地执行生产构建**

先用 `Get-NetTCPConnection -LocalPort 3000 -State Listen` 和 `Win32_Process.CommandLine` 精确确认本项目 Next dev 父子进程，停止后确认端口释放，再运行：

Run: `cd frontend && npm.cmd run build`

Expected: 编译、类型检查和 7 个页面生成成功。任何停止失败必须中止构建并记为失败，不使用分号继续执行。

- [ ] **Step 4: 重启软件并做 HTTP/API 探活**

隐藏窗口启动 `npm.cmd run dev`，等待 3000 端口监听。

Run: `Invoke-WebRequest http://127.0.0.1:3000/jobs/0b14fe4f-3459-4fb6-a08c-e9300359befc`

Expected: HTTP 200。

Run: `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready`

Expected: database、redis、worker、contract_match 均为 `ok`。

- [ ] **Step 5: 浏览器真实页面验收**

在样本任务上验证：

- “补充证据后复核”为按钮，点击后展开并定位到证据。
- Amazon 精准词默认展开，英文通用词默认收起。
- 两个复制按钮内容互不混淆。
- Amazon 搜索链接只包含精准词。
- 页面不出现 `amazon: ...; en: ...` 混合长句。

- [ ] **Step 6: 写验收文档和最终迭代记录**

记录实际测试数量、构建结果、HTTP/API 状态、浏览器行为、所有失败和已知非阻断提示；不重写历史任务，不自动提交脏工作区。
