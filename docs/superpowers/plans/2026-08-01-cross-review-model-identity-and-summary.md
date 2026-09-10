# 交叉评审模型身份与结构化总结 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让交叉评审明确显示真实的“评审模型 → 被评审模型”，并让新任务生成可快速阅读的六段式评审结论。

**Architecture:** 前端新增无副作用的身份映射与摘要提取函数，依据持久化 `reviewers` 和结果键完成历史兼容，`CrossReviewPanel` 只负责展示。后端仅收紧 `_build_cross_review_prompt` 的输出契约并注入双方真实身份，不改变结果键、持久化、模型调用、重试、评分或供应商路由。

**Tech Stack:** Next.js、React、TypeScript、Vitest、Testing Library、Python、pytest。

---

## 文件结构

- 新建 `frontend/lib/cross-review-identity.ts`：解析结果方向、格式化真实模型身份并提取结论摘要。
- 新建 `frontend/tests/cross-review-identity.test.ts`：覆盖新旧结果键、任意供应商和身份缺失。
- 修改 `frontend/components/jobs/cross-review-panel.tsx`：接入真实标题与展开后的固定身份摘要。
- 修改 `frontend/tests/job-detail.test.tsx`：验证页面方向、历史原文和安全回退。
- 修改 `backend/application/analysis_runner.py`：向提示词传入评审方和被评审方真实身份，并固定六段式输出。
- 修改 `backend/tests/test_analysis_runner.py`：验证提示词结构、身份和禁止项。
- 修改 `docs/优化迭代记录.md`：记录实施结果、失败与验证。

### Task 1: 建立真实模型身份与方向映射

**Files:**
- Create: `frontend/lib/cross-review-identity.ts`
- Create: `frontend/tests/cross-review-identity.test.ts`
- Read: `frontend/lib/api/types.ts`

- [ ] **Step 1: 写失败测试**

在 `frontend/tests/cross-review-identity.test.ts` 覆盖：

```ts
import { describe, expect, it } from "vitest";
import { describeCrossReviewEntry } from "@/lib/cross-review-identity";

const reviewers = [
  { provider: "deepseek", display_name: "DeepSeek", api_protocol: "openai", model: "deepseek-v4-pro" },
  { provider: "claude", display_name: "Claude", api_protocol: "anthropic", model: "claude-opus-5" },
];

describe("describeCrossReviewEntry", () => {
  it("maps reviewer_a to reviewer_b using persisted identities", () => {
    expect(describeCrossReviewEntry("reviewer_a_reviews_reviewer_b", reviewers).title)
      .toBe("DeepSeek（deepseek-v4-pro）评审 Claude（claude-opus-5）");
  });

  it("maps the reverse direction", () => {
    expect(describeCrossReviewEntry("reviewer_b_reviews_reviewer_a", reviewers).title)
      .toBe("Claude（claude-opus-5）评审 DeepSeek（deepseek-v4-pro）");
  });

  it("uses persisted identities for a legacy key", () => {
    expect(describeCrossReviewEntry("gpt_reviews_deepseek", reviewers).title)
      .toBe("DeepSeek（deepseek-v4-pro）评审 Claude（claude-opus-5）");
  });

  it("never exposes internal reviewer keys when identities are absent", () => {
    expect(describeCrossReviewEntry("reviewer_a_reviews_reviewer_b", []).title)
      .toBe("评审模型 A 评审 评审模型 B");
  });

  it("does not guess when reviewer count is invalid", () => {
    expect(describeCrossReviewEntry("reviewer_a_reviews_reviewer_b", reviewers.slice(0, 1)).title)
      .toBe("交叉评审结果");
  });
});
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm.cmd test -- --run tests/cross-review-identity.test.ts`

Working directory: `frontend`

Expected: FAIL，提示 `@/lib/cross-review-identity` 不存在。

- [ ] **Step 3: 写最小身份映射实现**

在 `frontend/lib/cross-review-identity.ts` 定义：

```ts
import type { CrossReviewState } from "@/lib/api/types";

type Reviewer = NonNullable<CrossReviewState["reviewers"]>[number];

export interface CrossReviewDescription {
  title: string;
  reviewer?: Reviewer;
  reviewed?: Reviewer;
}

function shortIdentity(identity: Reviewer): string {
  const service = identity.display_name?.trim() || identity.provider.trim();
  return `${service}（${identity.model}）`;
}

export function describeCrossReviewEntry(
  key: string,
  reviewers: Reviewer[],
): CrossReviewDescription {
  if (reviewers.length !== 0 && reviewers.length !== 2) return { title: "交叉评审结果" };

  const legacy = key === "gpt_reviews_deepseek";
  const forward = key === "reviewer_a_reviews_reviewer_b" || legacy;
  const reverse = key === "reviewer_b_reviews_reviewer_a";
  if (!forward && !reverse) return { title: "交叉评审结果" };

  if (reviewers.length === 0) {
    return { title: forward ? "评审模型 A 评审 评审模型 B" : "评审模型 B 评审 评审模型 A" };
  }

  const reviewer = forward ? reviewers[0] : reviewers[1];
  const reviewed = forward ? reviewers[1] : reviewers[0];
  return { reviewer, reviewed, title: `${shortIdentity(reviewer)}评审 ${shortIdentity(reviewed)}` };
}
```

- [ ] **Step 4: 运行身份测试确认 GREEN**

Run: `npm.cmd test -- --run tests/cross-review-identity.test.ts`

Working directory: `frontend`

Expected: 5 tests passed。

### Task 2: 提取固定结论摘要并接入页面

**Files:**
- Modify: `frontend/lib/cross-review-identity.ts`
- Modify: `frontend/tests/cross-review-identity.test.ts`
- Modify: `frontend/components/jobs/cross-review-panel.tsx`
- Modify: `frontend/tests/job-detail.test.tsx`

- [ ] **Step 1: 写摘要提取失败测试**

加入以下断言：

```ts
import { extractCrossReviewSummary } from "@/lib/cross-review-identity";

it("extracts the fixed conclusion type and one-line conclusion", () => {
  const raw = "## 结论摘要\n\n结论类型：部分认可\n\n一句话结论：方向合理，但证据不足。\n\n## 认可之处\n- 场景成立";
  expect(extractCrossReviewSummary(raw)).toEqual({
    conclusionType: "部分认可",
    conclusion: "方向合理，但证据不足。",
  });
});

it("falls back safely for historical free-form output", () => {
  expect(extractCrossReviewSummary("旧任务自由文本")).toEqual({
    conclusionType: "无法判断",
    conclusion: "旧任务未提供结构化结论，请查看评审原文。",
  });
});
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `npm.cmd test -- --run tests/cross-review-identity.test.ts`

Working directory: `frontend`

Expected: FAIL，提示 `extractCrossReviewSummary` 未导出。

- [ ] **Step 3: 实现严格、非破坏性的摘要提取**

在 `frontend/lib/cross-review-identity.ts` 增加：

```ts
const CONCLUSION_TYPES = ["认可", "部分认可", "不认可", "无法判断"] as const;

export function extractCrossReviewSummary(raw?: string) {
  const typeMatch = raw?.match(/^结论类型[：:]\s*(认可|部分认可|不认可|无法判断)\s*$/m);
  const conclusionMatch = raw?.match(/^一句话结论[：:]\s*(.+)\s*$/m);
  return {
    conclusionType: CONCLUSION_TYPES.find((value) => value === typeMatch?.[1]) ?? "无法判断",
    conclusion: conclusionMatch?.[1]?.trim() || "旧任务未提供结构化结论，请查看评审原文。",
  };
}
```

- [ ] **Step 4: 在面板接入标题与身份摘要卡**

替换 `key.split("_reviews_")` 标签逻辑，调用 `describeCrossReviewEntry(key, reviewers)`。展开成功结果时，在 `CrossReviewDocument` 前显示：

```tsx
const description = describeCrossReviewEntry(key, reviewers);
const summary = extractCrossReviewSummary(review.raw);

<div className="mb-4 grid gap-3 rounded-md bg-muted/30 p-3 text-sm sm:grid-cols-2">
  <div><span className="text-muted-foreground">评审模型</span><strong className="mt-1 block">{formatFullIdentity(description.reviewer)}</strong></div>
  <div><span className="text-muted-foreground">被评审模型</span><strong className="mt-1 block">{formatFullIdentity(description.reviewed)}</strong></div>
  <div><span className="text-muted-foreground">结论类型</span><strong className="mt-1 block">{summary.conclusionType}</strong></div>
  <div><span className="text-muted-foreground">一句话结论</span><strong className="mt-1 block">{summary.conclusion}</strong></div>
</div>
```

`formatFullIdentity` 对有效身份返回 `服务名 · 协议 · 模型`，缺失身份返回“历史任务未记录”；错误结果仍显示真实方向标题和原有脱敏错误。

- [ ] **Step 5: 写页面回归测试**

在 `frontend/tests/job-detail.test.tsx` 的任务 payload 中加入两个 reviewers 和两个方向结果，断言：

```ts
expect(screen.getByRole("button", { name: /DeepSeek（deepseek-v4-pro）评审 Claude（claude-opus-5）/ })).toBeInTheDocument();
expect(screen.getByRole("button", { name: /Claude（claude-opus-5）评审 DeepSeek（deepseek-v4-pro）/ })).toBeInTheDocument();
expect(screen.getByText("部分认可")).toBeInTheDocument();
expect(screen.getByText("方向合理，但证据不足。")).toBeInTheDocument();
expect(screen.queryByText(/reviewer_a|reviewer_b/)).not.toBeInTheDocument();
```

保留现有 `raw` 字节内容断言，另加缺失 reviewers 时显示“评审模型 A 评审 评审模型 B”的历史兼容用例。

- [ ] **Step 6: 运行前端聚焦测试**

Run: `npm.cmd test -- --run tests/cross-review-identity.test.ts tests/job-detail.test.tsx tests/result-workbench-ui.test.tsx`

Working directory: `frontend`

Expected: 全部通过；旧任务原文断言保持不变。

### Task 3: 收紧新交叉评审提示词契约

**Files:**
- Modify: `backend/application/analysis_runner.py:466-505`
- Modify: `backend/application/analysis_runner.py:1102-1135`
- Modify: `backend/tests/test_analysis_runner.py:793-816`

- [ ] **Step 1: 写提示词契约失败测试**

扩展 `test_runner_cross_review_uses_selected_model_identities`，检查两个 FakeLLM 收到的提示词，并新增纯函数测试：

```py
def test_cross_review_prompt_requires_structured_sections_and_real_identities():
    prompt = _build_cross_review_prompt(
        {"title": "Primary"},
        {"score": 70},
        "hypothesis",
        reviewer_model="DeepSeek (openai) / deepseek-v4-pro",
        reviewed_model="Claude (anthropic) / claude-opus-5",
    )
    for heading in ("## 结论摘要", "## 认可之处", "## 存在的问题", "## 关键分歧", "## 修正建议", "## 最终推荐"):
        assert heading in prompt
    assert "结论类型：认可 / 部分认可 / 不认可 / 无法判断" in prompt
    assert "一句话结论：" in prompt
    assert "DeepSeek (openai) / deepseek-v4-pro" in prompt
    assert "Claude (anthropic) / claude-opus-5" in prompt
    assert "不要输出寒暄" in prompt
    assert "不得虚构证据" in prompt
```

- [ ] **Step 2: 运行后端测试确认 RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -k "cross_review" -q`

Expected: FAIL，提示 `_build_cross_review_prompt` 参数或六段契约不匹配。

- [ ] **Step 3: 向提示词传入双方真实身份**

在 `run_cross_review` 中改为：

```py
prompt_a = _build_cross_review_prompt(product_summary, output_b, mode, identity_a, identity_b)
prompt_b = _build_cross_review_prompt(product_summary, output_a, mode, identity_b, identity_a)
```

保持 `results` 的两个现有键不变，避免迁移历史数据。

- [ ] **Step 4: 实现六段式提示词**

将函数签名改为：

```py
def _build_cross_review_prompt(
    product_summary: dict,
    other_output: dict,
    mode: str,
    reviewer_model: str,
    reviewed_model: str,
) -> str:
```

提示词明确：评审方与被评审方身份；只使用真实名称的第三人称；禁止 `reviewer_a`、`reviewer_b`、“GPT”和“对方模型”；不寒暄、不复述任务；不得虚构评论、市场或商品事实；证据不足时写明无法判断。要求原样输出以下骨架：

```md
## 结论摘要
结论类型：认可 / 部分认可 / 不认可 / 无法判断
一句话结论：用一句话概括判断和最关键理由

## 认可之处
- 只列有原始商品数据或被评审结果支持的判断

## 存在的问题
- 分别指出逻辑、证据、市场需求或场景匹配问题

## 关键分歧
- 明确写出两个真实模型名称、分歧对象和评审方判断

## 修正建议
- 给出可直接修改原分析的动作

## 最终推荐
- 按优先级列出保留、降级或新增方向
```

- [ ] **Step 5: 运行后端聚焦测试并静态检查**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_analysis_runner.py -k "cross_review" -q`

Expected: 全部通过。

Run: `.venv\Scripts\python.exe -m ruff check backend/application/analysis_runner.py backend/tests/test_analysis_runner.py`

Expected: `All checks passed!`

### Task 4: 全量验证、运行验收与记录

**Files:**
- Modify: `docs/优化迭代记录.md`
- Verify only: existing source and test files

- [ ] **Step 1: 运行前端全量测试**

Run: `npm.cmd test -- --run`

Working directory: `frontend`

Expected baseline: 不少于当前 `183 passed, 7 skipped`，且无失败。

- [ ] **Step 2: 运行 TypeScript 与生产构建**

Run: `npm.cmd run typecheck`

Working directory: `frontend`

Expected: exit code 0。

Run: `npm.cmd run build`

Working directory: `frontend`

Expected: Next.js production build 成功。

- [ ] **Step 3: 运行后端全量回归**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected baseline: 不少于当前 `521 passed, 9 skipped`，且无失败。

- [ ] **Step 4: 检查差异与历史兼容边界**

Run: `git diff --check -- backend/application/analysis_runner.py backend/tests/test_analysis_runner.py frontend/lib/cross-review-identity.ts frontend/components/jobs/cross-review-panel.tsx frontend/tests/cross-review-identity.test.ts frontend/tests/job-detail.test.tsx docs/优化迭代记录.md`

Expected: 无空白错误。确认没有数据库迁移、历史 payload 改写、模型自动调用、评分或供应商路由变更。

- [ ] **Step 5: 重启并做本地只读验收**

Run: `powershell -ExecutionPolicy Bypass -File .\启动.ps1`

Expected: `/api/v1/health/ready` 的 database、redis、worker、contract_match 均为 `ok`，`http://127.0.0.1:3000/jobs/aadd62cb-f4d7-4bc6-9abf-953a5af49ea5` 返回 200。历史任务刷新后标题显示真实方向，原始评审正文不变；不触发重新评审和 Token 消耗。

- [ ] **Step 6: 追加中文迭代记录**

写明：读取的最新条目、目标、精确文件、RED/GREEN 失败、全量验证数字、运行健康状态、历史兼容、已知限制和回滚方式。不得记录 API Key、Cookie、Token 或模型回复全文。

- [ ] **Step 7: 保留共享脏工作区，不提交**

本目录已有大量用户改动。完成后只报告本计划涉及的文件，不执行 `git add`、`git commit`、重置、清理或覆盖无关文件。

## 自检结果

- 规格覆盖：真实双向标题、协议身份卡、六段式新输出、四种结论、历史键、安全回退、失败方向、原文保留和非目标均有对应任务。
- 占位符扫描：无 TODO、TBD、“稍后实现”或未定义的测试动作。
- 类型一致性：统一使用现有 `CrossReviewState["reviewers"]`；结果键和持久化结构不变；前端摘要字段只由原始 Markdown 派生。
- 范围拆分：前端展示和后端提示词可分别测试，但共同构成一个用户可见功能，无需拆成两个独立项目。

