# 工作台分入口模型偏好 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让假设分析、对比审判和批量任务分别显式保存自己的默认供应商与模型，并把任务名称放到链接输入附近随任务提交。

**Architecture:** 使用独立的浏览器偏好模块持久化版本化 `{provider, model}`，UI 只在用户点击保存按钮时写入。模型组件依据最新可用供应商目录恢复或拒绝旧偏好；三个表单通过明确的入口标识隔离状态，任务提交仍使用现有后端请求。

**Tech Stack:** Next.js 15、React 19、TypeScript、React Hook Form、TanStack Query、Vitest、Testing Library。

---

### Task 1: 建立版本化模型偏好存储

**Files:**
- Create: `frontend/lib/workbench-model-preference.ts`
- Test: `frontend/tests/workbench-model-preference.test.ts`

- [ ] **Step 1: 写入失败测试**

覆盖三个入口键、合法 JSON 恢复、损坏 JSON/错误版本/缺字段返回 `null`，以及写入内容只含 `version/provider/model`。

```ts
expect(readWorkbenchModelPreference("hypothesis", storage)).toEqual({
  version: 1,
  provider: "cattoken_claude",
  model: "claude-sonnet-4-6",
});
expect(readWorkbenchModelPreference("judgment", brokenStorage)).toBeNull();
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `npm.cmd test -- --run tests/workbench-model-preference.test.ts`

Expected: FAIL，模块尚不存在。

- [ ] **Step 3: 最小实现纯函数接口**

```ts
export type WorkbenchEntry = "hypothesis" | "judgment" | "batch";
export interface WorkbenchModelPreference {
  version: 1;
  provider: ProviderSlug;
  model: string;
}
export function readWorkbenchModelPreference(entry: WorkbenchEntry, storage = window.localStorage): WorkbenchModelPreference | null;
export function writeWorkbenchModelPreference(entry: WorkbenchEntry, value: Omit<WorkbenchModelPreference, "version">, storage = window.localStorage): void;
```

使用固定前缀和入口后缀；解析时逐字段校验，不抛出本地存储异常。

- [ ] **Step 4: 运行测试并确认 GREEN**

Run: `npm.cmd test -- --run tests/workbench-model-preference.test.ts`

Expected: PASS。

### Task 2: 为 ModelSelect 增加恢复、失效回退和显式保存

**Files:**
- Modify: `frontend/components/workbench/model-select.tsx`
- Modify: `frontend/tests/model-select.test.tsx`

- [ ] **Step 1: 写入失败组件测试**

验证：不同 `preferenceEntry` 恢复不同值；切换下拉框后重新挂载仍是旧默认；点击“保存为此入口默认选择”后重新挂载恢复新值；已保存 identity 不在最新目录时回退并显示失效提示；无供应商时不显示或禁用保存。

```tsx
render(<ModelSelect preferenceEntry="hypothesis" providers={providers} {...registrations} />);
await user.selectOptions(screen.getByLabelText("供应商"), "cattoken_claude");
await user.click(screen.getByRole("button", { name: "保存为此入口默认选择" }));
expect(JSON.parse(localStorage.getItem("workbench-model-preference:hypothesis")!)).toMatchObject({
  provider: "cattoken_claude",
});
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `npm.cmd test -- --run tests/model-select.test.tsx`

Expected: FAIL，组件尚无入口标识和保存按钮。

- [ ] **Step 3: 实现受控选择与保存状态**

给 `ModelSelectProps` 增加 `preferenceEntry: WorkbenchEntry`。目录加载时仅恢复仍存在的 `provider:model`；空模型代表供应商默认模型，校验时解析为 `defaultModelHint(provider)`。恢复、回退和用户切换均同步调用 React Hook Form registration；只有按钮点击时写入本地存储。当前选择与已保存值不一致时显示“尚未保存”，一致时显示“已保存默认”。

- [ ] **Step 4: 运行测试并确认 GREEN**

Run: `npm.cmd test -- --run tests/model-select.test.tsx tests/workbench-model-preference.test.ts`

Expected: PASS。

### Task 3: 接入假设分析并移动任务名称

**Files:**
- Modify: `frontend/components/workbench/hypothesis-form.tsx`
- Modify: `frontend/tests/job-forms.test.tsx`

- [ ] **Step 1: 写入失败测试**

验证任务名称输入位于商品链接输入之前且不在“模型设置”折叠区；提交 payload 同时包含 `name/url/provider/model`；保存 hypothesis 偏好后不改变 judgment/batch 键。

- [ ] **Step 2: 运行并确认 RED**

Run: `npm.cmd test -- --run tests/job-forms.test.tsx`

Expected: FAIL，任务名称仍位于高级选项且组件未传入口标识。

- [ ] **Step 3: 最小修改表单**

把 `register("name")` 区块移到 URL 主输入区上方，将折叠按钮文案改为“模型设置”，并传入：

```tsx
<ModelSelect preferenceEntry="hypothesis" ... />
```

保持 `submitHypothesis({ name: data.name || undefined, ... })` 不变。

- [ ] **Step 4: 运行并确认 GREEN**

Run: `npm.cmd test -- --run tests/job-forms.test.tsx`

Expected: PASS。

### Task 4: 接入对比审判和批量任务

**Files:**
- Modify: `frontend/components/workbench/judgment-form.tsx`
- Modify: `frontend/components/workbench/batch-form.tsx`
- Modify: `frontend/tests/job-forms.test.tsx`
- Modify: `frontend/tests/batch-history.test.tsx`

- [ ] **Step 1: 写入失败测试**

对比审判验证 `preferenceEntry="judgment"` 的保存与重新挂载；批量任务验证 `batch` 独立保存、临时切换不持久化、失效偏好回退。两个入口提交 payload 都必须包含当前任务名称和当前选择。

- [ ] **Step 2: 运行并确认 RED**

Run: `npm.cmd test -- --run tests/job-forms.test.tsx tests/batch-history.test.tsx`

Expected: FAIL，对比审判未传入口标识，批量任务仍有重复的模型选择实现且无保存按钮。

- [ ] **Step 3: 复用 ModelSelect**

对比审判传 `preferenceEntry="judgment"`。批量任务新增仅管理模型字段的 React Hook Form：

```tsx
const { register, getValues } = useForm<{ provider: ProviderSlug | ""; model: string }>({
  defaultValues: { provider: "", model: "" },
});

<ModelSelect
  preferenceEntry="batch"
  providers={providerQuery.providers}
  providerRegistration={register("provider")}
  modelRegistration={register("model")}
/>
```

`submitBatch` 使用 `getValues()` 读取当前 provider/model，删除批量表单内重复的下拉逻辑；保留现有 URL 解析、名称输入和提交状态。

- [ ] **Step 4: 运行并确认 GREEN**

Run: `npm.cmd test -- --run tests/job-forms.test.tsx tests/batch-history.test.tsx tests/model-select.test.tsx`

Expected: PASS。

### Task 5: 回归、构建、运行验收和记录

**Files:**
- Modify: `docs/优化迭代记录.md`

- [ ] **Step 1: 运行前端全套测试**

Run: `npm.cmd test -- --run`

Expected: 全部 PASS；任何失败先记录到中文迭代记录再修复。

- [ ] **Step 2: 运行类型检查与生产构建**

Run: `npm.cmd run typecheck`

Run: `npm.cmd run build`

Expected: 两者退出码 0。

- [ ] **Step 3: 运行差异检查**

Run: `git diff --check`

Expected: 退出码 0；仅允许既有 LF/CRLF 提示。

- [ ] **Step 4: 重启并进行浏览器验收**

Run: `powershell -ExecutionPolicy Bypass -File .\启动.ps1`

验证三个入口分别保存并恢复默认选择，任务名称位于链接附近，临时切换不会覆盖长期默认，失效模型不会被提交。

- [ ] **Step 5: 更新中文迭代记录**

记录每轮 RED、GREEN、失败、回归结果、已知限制和安全边界；不得写入真实凭据。
