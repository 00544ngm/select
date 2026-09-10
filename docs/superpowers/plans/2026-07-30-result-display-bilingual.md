# 结果页中英双语展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将结果页机器字段和枚举转换为清晰的中文主标签加英文原值展示。

**Architecture:** 新增纯函数 formatter 模块，由结果列表、详情和评分卡共享；组件继续消费原始 `StructuredDirection`，不改变 API 类型或后端数据。

**Tech Stack:** Next.js、React、TypeScript、Vitest、Testing Library。

---

### Task 1: 集中展示映射

**Files:**
- Create: `frontend/lib/result-labels.ts`
- Test: `frontend/tests/result-labels.test.ts`

- [x] 编写枚举、字段键、策略和关键词 formatter 的失败测试。
- [x] 实现纯函数并覆盖未知值回退为原文。
- [x] 运行定向测试确认通过。

### Task 2: 接入结果组件

**Files:**
- Modify: `frontend/components/jobs/direction-detail.tsx`
- Modify: `frontend/components/jobs/direction-drawer.tsx`
- Modify: `frontend/components/jobs/direction-list.tsx`
- Modify: `frontend/components/jobs/stickiness-scorecard.tsx`
- Test: `frontend/tests/result-workbench-ui.test.tsx`

- [x] 先增加组件断言，固定双语枚举、策略、深度字段和证据关键词显示。
- [x] 将组件中的裸映射替换为集中 formatter，递归格式化深度分析。
- [x] 运行组件测试并修复类型错误。

### Task 3: 记录与全量验证

**Files:**
- Modify: `docs/优化迭代记录.md`

- [x] 记录本轮目标、范围、验证命令、已知限制和回滚提交。
- [x] 运行 `npm.cmd run build`、`npm.cmd run typecheck`、前端测试和 `git diff --check`。
- [x] 通过组件测试检查双语显示与数据不变性；真实浏览器核对因当前会话无浏览器绑定未执行，已记录限制。
