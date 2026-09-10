# 供应商重复保存保留模型验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复员工端验证并勾选模型后再次保存配置导致验证记录被删除的问题，并重新生成通过真实验收的安装包。

**Architecture:** 前端在保存成功后用服务端返回配置重置表单与密钥输入状态，使后续保存不再携带旧明文；后端使用常量时间比较识别“同一密钥重复提交”，仅在密钥真实变化时删除模型验证。模型选择接口继续即时持久化选择状态。

**Tech Stack:** React、React Hook Form、TanStack Query、Vitest、Testing Library、Python、FastAPI、SQLAlchemy repository、pytest、Electron/Next.js。

---

## 文件结构

- 修改 `frontend/components/settings/provider-settings-panel.tsx`：保存成功后重置表单，向密钥组件传递稳定的重置身份，并显示模型选择已自动保存。
- 修改 `frontend/components/settings/secret-input.tsx`：已保存密钥变化后同步退出替换状态并清空可见性。
- 修改 `frontend/tests/provider-settings.test.tsx`：覆盖二次保存不携带密钥、掩码恢复和模型选择提示。
- 修改 `backend/application/provider_service.py`：同一密钥重复提交不使模型验证失效。
- 修改 `backend/tests/test_provider_service.py`：覆盖同密钥保留与不同密钥失效。
- 修改 `docs/优化迭代记录.md`：记录红灯、修复、测试、真实验收和安装包信息。

### Task 1：前端保存后清除临时密钥

- [ ] **Step 1：写失败测试**

在 `frontend/tests/provider-settings.test.tsx` 新增用例：初始供应商未配置，输入 API Key 并保存；服务端返回 `masked_api_key`。再次点击保存，断言第二次 PUT 的 `api_key` 为 `undefined`，界面显示掩码而不是“新 API Key”输入框。

- [ ] **Step 2：确认红灯**

运行：

```powershell
cd frontend
npm.cmd test -- --run tests/provider-settings.test.tsx
```

预期：第二次请求仍含第一次输入的密钥，或密钥输入框未恢复掩码，新增用例失败。

- [ ] **Step 3：最小实现**

`saveMutation.onSuccess` 使用 `reset(valuesFor(updatedProvider))`；`SecretInput` 接收 `maskedValue` 变化时，用 effect 将 `replacing` 设为 `false`、`visible` 设为 `false`。仅保存成功后清除表单密钥，保存失败保持原输入。

- [ ] **Step 4：验证绿灯**

运行同一 Vitest 文件，预期全部通过。

### Task 2：模型选择即时保存提示

- [ ] **Step 1：写失败测试**

扩展现有“verified models can be selected”用例：选择接口成功后，断言页面出现“模型选择已自动保存”，且不需要再点击“保存配置”。

- [ ] **Step 2：确认红灯**

运行 `frontend/tests/provider-settings.test.tsx`，预期找不到提示文本。

- [ ] **Step 3：最小实现**

在 `selectionMutation.onSuccess` 更新查询缓存后设置成功提示 `模型选择已自动保存`；`onError` 清空成功提示并保留 API 错误。

- [ ] **Step 4：验证绿灯**

运行前端设置测试，预期全部通过。

### Task 3：后端同密钥重复保存防御

- [ ] **Step 1：写失败测试**

在 `backend/tests/test_provider_service.py` 新增两个用例：已有供应商与验证记录时重复提交相同 API Key，断言不调用 `delete_model_validations`；提交不同 API Key 时断言调用一次。测试使用内存加密器或现有 fixture，不输出密钥。

- [ ] **Step 2：确认红灯**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_provider_service.py -k "same_key or changed_key" -q
```

预期：同密钥用例失败，因为当前实现只要 `update.api_key is not None` 就删除验证记录。

- [ ] **Step 3：最小实现**

在 `ProviderService.save` 解析 runtime 后，使用 `hmac.compare_digest` 比较新密钥与已解密旧密钥；`invalidates_models` 仅在协议变化、地址变化或密钥内容真实变化时为真。清除密钥仍按现有逻辑处理。

- [ ] **Step 4：验证绿灯**

运行 `backend/tests/test_provider_service.py`，预期全部通过。

### Task 4：全量验证、真实验收与安装包

- [ ] **Step 1：运行全量回归**

顺序运行后端 `pytest backend/tests -q`、前端 `npm test -- --run`、Next build 后再单独 typecheck、桌面测试和 typecheck。不得并发争用 `.next/types`。

- [ ] **Step 2：真实员工链路验收**

使用受控桌面会话执行“保存配置 → 测试连接 → 验证模型 → 勾选使用 → 再保存”，随后重新读取供应商目录，断言模型仍为 `verified` 且 `is_selected=true`；再从工作台确认该模型可选。不得在输出中显示 API Key。

- [ ] **Step 3：重新构建安装包**

运行项目现有 `scripts/build-windows-installer.ps1`，等待完整父进程退出；核对安装包路径、大小、SHA-256 与整包进程健康，不复用旧安装包校验值。

- [ ] **Step 4：安全扫描与记录**

对发布目录执行本轮临时密钥精确匹配扫描，只输出命中数量；把所有失败、修复、测试数量、真实验收和安装包信息写入中文迭代记录。

## 自检

- 规格中的前端明文清理、后端同密钥防御、真实变化失效、即时选择提示、错误边界和真实验收均有对应任务。
- 无 TBD/TODO 或未定义接口；字段名与现有 `api_key`、`masked_api_key`、`is_selected`、`delete_model_validations` 一致。
- 不需要数据库迁移，不改写旧任务；工作区由用户持有，本计划不执行 Git 提交、合并或清理。
