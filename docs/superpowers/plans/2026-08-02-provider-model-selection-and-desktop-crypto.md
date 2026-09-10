# 模型勾选与桌面密钥链路修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复桌面任务密钥解密失败，并以可持久化多选替代默认模型界面。

**Architecture:** 用统一加密工厂消除 API/Worker 分叉；在模型验证记录上持久化选择状态；API 对选择动作执行验证时效约束；前端和工作台只消费已选择且新鲜验证的模型。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy/Alembic、React/Next.js、TanStack Query、Vitest、Electron。

---

### Task 1: 统一桌面加密实现

**Files:** `backend/security/provider_crypto_factory.py`、`backend/api/dependencies.py`、`backend/workers/jobs.py`、`backend/main.py`、后端测试。

- [ ] 写失败测试，断言 desktop 模式的 API 与 Worker 都获得 `WindowsDPAPI`。
- [ ] 运行定向 pytest，确认因 Worker 当前构造 `ProviderCrypto` 而失败。
- [ ] 添加统一工厂并替换三处独立构造。
- [ ] 运行定向与相关加密测试，确认通过。

### Task 2: 持久化模型多选

**Files:** `backend/migrations/versions/0008_add_provider_model_selection.py`、`backend/db/models.py`、`backend/db/provider_repository.py`、`backend/api/schemas/providers.py`、`backend/application/provider_service.py`、`backend/api/routes/providers.py`、后端测试。

- [ ] 写失败测试覆盖选择、取消、未验证/过期禁止选择以及公开 DTO。
- [ ] 运行定向 pytest，确认字段和接口缺失导致预期失败。
- [ ] 添加迁移、仓储更新方法、服务校验与 PATCH 路由。
- [ ] 保留 `default_model` 仅作兼容，不再用其判断工作台模型。
- [ ] 运行数据库迁移、仓储、服务和 API 测试。

### Task 3: 更新设置页与工作台

**Files:** `frontend/lib/api/types.ts`、`frontend/lib/api/providers.ts`、`frontend/lib/model-identity.ts`、`frontend/components/settings/provider-settings-panel.tsx`、`frontend/components/workbench/model-select.tsx`、`frontend/components/workbench/provider-availability.tsx`、相关 Vitest。

- [ ] 写失败测试：设置页无默认模型输入、验证后可多选、工作台过滤未选择模型。
- [ ] 运行定向 Vitest，确认预期失败。
- [ ] 添加选择 API 客户端和复选框交互，验证成功不再隐式改默认模型。
- [ ] 将所有工作台模型过滤改为“新鲜验证且已选择”。
- [ ] 运行前端定向测试和类型检查。

### Task 4: 真实链路与最终安装包

**Files:** `docs/优化迭代记录.md`、`release/组合选品控制台-Setup-0.1.1.exe` 及校验文件。

- [ ] 使用已保存的 DPAPI 凭据验证 OpenAI 与 Maike，确保不打印密钥。
- [ ] 从工作台提交真实测试任务并核验 Worker 不再报密钥重输。
- [ ] 运行后端全量测试、前端全量测试、类型检查和生产构建。
- [ ] 构建 Electron 安装包，启动整包并检查前端、API、Worker 心跳和退出清理。
- [ ] 更新 SHA-256 文件并把成功与失败追加到中文迭代记录。

