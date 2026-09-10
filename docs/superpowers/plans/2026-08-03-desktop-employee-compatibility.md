# 员工电脑兼容与故障自诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复员工电脑上的永久“提交中”和无信息 `INTERNAL_ERROR`，建立普通 Windows 用户可运行、可诊断、可验收的桌面安装版。

**Architecture:** Electron 统一创建当前用户可写运行目录并向三个子进程传递路径；进程监督器落盘日志；前端为本地 API 调用增加超时；Worker 保存安全的阶段化错误；后端就绪检查覆盖目录、Worker、浏览器与凭据。所有行为先由单元测试锁定，再构建安装包做只读安装根目录冒烟验收。

**Tech Stack:** Electron、Node.js child_process、TypeScript、Vitest、Next.js、React Query、Python、FastAPI、SQLAlchemy、pytest、Windows DPAPI、Playwright。

---

### Task 1：统一桌面运行目录与子进程工作目录

**Files:**
- Modify: `desktop/src/main.ts`
- Modify: `desktop/src/services/process-supervisor.ts`
- Create: `desktop/src/runtime-paths.ts`
- Create: `desktop/tests/runtime-paths.test.ts`
- Modify: `desktop/tests/process-supervisor.test.ts`
- Modify: `backend/config.py`
- Modify: `backend/tests/test_desktop_paths.py`

- [ ] 写失败测试：断言中文、空格、`#`、`%` 的 LocalAppData 可以生成 data/runtime/logs/artifacts/temp，且每个服务 spawn 都使用显式可写 `cwd`。
- [ ] 运行 `cd desktop; npm.cmd test -- --run`，确认新增测试在实现前失败。
- [ ] 新建 `buildRuntimePaths(baseDir)`，创建全部子目录；向 commonEnv 加入 `DESKTOP_DATA_DIR`、`DESKTOP_LOG_DIR`、`ARTIFACT_DIR`、`TMP`、`TEMP`；向 supervisor 传入 `cwd`。
- [ ] 后端桌面配置从 `ARTIFACT_DIR` 读取绝对路径，测试断言不再使用安装目录相对路径。
- [ ] 重跑桌面和 `backend/tests/test_desktop_paths.py`，预期全部通过。

### Task 2：保存 API、Worker、前端日志

**Files:**
- Modify: `desktop/src/services/process-supervisor.ts`
- Create: `desktop/src/services/service-log.ts`
- Create: `desktop/tests/service-log.test.ts`
- Modify: `desktop/src/main.ts`
- Modify: `backend/desktop/api_entry.py`
- Modify: `backend/desktop/worker_entry.py`

- [ ] 写失败测试：服务 stdout/stderr 写入对应日志，日志路径位于当前用户目录，超过阈值轮转，敏感环境变量不写入日志。
- [ ] 运行桌面测试并确认红灯。
- [ ] 将 `stdio: "ignore"` 改为 pipe，使用 `createServiceLogStreams` 写入 `api.log`、`worker.log`、`frontend.log`；启动和退出只记录服务名、PID、退出码。
- [ ] API 与 Worker 入口初始化 Python logger 到 `DESKTOP_LOG_DIR`，Electron 的“打开日志”打开同一目录。
- [ ] 重跑桌面测试和打包入口测试，预期全部通过。

### Task 3：API 超时并解除永久提交状态

**Files:**
- Modify: `frontend/lib/api/client.ts`
- Modify: `frontend/tests/api-client.test.ts`
- Modify: `frontend/tests/job-forms.test.tsx`

- [ ] 写失败测试：永不 resolve 的 fetch 在 15 秒后抛出 `ApiError("DESKTOP_API_TIMEOUT")`；表单按钮由“提交中”恢复为可提交并显示中文提示。
- [ ] 使用 fake timers 运行相关 Vitest，确认实现前永久 pending。
- [ ] 为 `apiFetch` 增加可测试的 `timeoutMs` 和 `AbortController`；将 AbortError 归一为可重试的 504 错误。
- [ ] 重跑 API client 与 job forms 测试，预期全部通过且无悬挂计时器。

### Task 4：Worker 阶段化错误与 DPAPI 明确提示

**Files:**
- Modify: `backend/workers/jobs.py`
- Modify: `backend/tests/test_worker_jobs.py`
- Modify: `backend/application/provider_clients.py`
- Modify: `backend/tests/test_provider_clients.py`
- Modify: `frontend/lib/job-status.ts`
- Modify: `frontend/tests/job-error.test.tsx`

- [ ] 写失败测试：在 `create_browser`、`resolve_primary_provider`、`run_hypothesis` 注入未知异常，断言错误包含安全阶段和异常类型但不含原始敏感文本。
- [ ] 写失败测试：DPAPI 解密失败映射为 `PROVIDER_CREDENTIAL_REENTRY_REQUIRED`，前端显示“请在当前 Windows 用户下重新输入 API Key”。
- [ ] 运行定向 pytest/Vitest，确认红灯。
- [ ] 实现阶段中文映射与安全错误构造；保持完整堆栈只进入 worker 日志；供应商解析器单独分类凭据重录错误。
- [ ] 重跑定向测试，预期全部通过。

### Task 5：桌面启动/任务预检

**Files:**
- Modify: `backend/api/health.py`
- Modify: `backend/tests/test_readiness.py`
- Modify: `backend/application/job_service.py`
- Modify: `backend/tests/test_job_service.py`
- Modify: `frontend/components/workbench/provider-availability.tsx`
- Modify: `frontend/tests/job-forms.test.tsx`

- [ ] 写失败测试：目录不可写、浏览器缺失、Worker 心跳过期、无可用模型、凭据不可解密分别返回稳定错误码。
- [ ] 运行后端/前端定向测试并确认红灯。
- [ ] 扩展桌面 readiness 结果并在创建任务前执行轻量预检；只阻断确定性失败，网络模型调用仍由任务执行阶段负责。
- [ ] 前端显示具体修复动作和“打开 API 设置/返回工作台”，禁止泛化成 `INTERNAL_ERROR`。
- [ ] 重跑定向测试，预期全部通过。

### Task 6：普通员工环境安装版验收

**Files:**
- Create: `scripts/verify-employee-desktop.ps1`
- Create: `docs/verification/employee-desktop-acceptance.md`
- Modify: `docs/桌面版安装说明.md`
- Modify: `docs/优化迭代记录.md`

- [ ] 脚本创建带中文、空格、`#`、`%` 的临时 LocalAppData，并将模拟安装根目录设为只读。
- [ ] 用打包 API/Worker/前端启动完整桌面服务，断言 readiness 为 200、日志存在、数据库/产物只写当前用户目录、安装根目录零新增。
- [ ] 注入 API 挂起、Worker 退出、浏览器缺失和不可解密凭据，断言 15 秒内解除提交状态并产生明确错误与日志。
- [ ] 运行后端全量 pytest、前端全量 Vitest、Next build/typecheck、桌面全量测试/build/typecheck。
- [ ] 构建新的 Windows 安装包，执行打包冒烟与残留进程检查，记录大小、SHA-256、测试数量和已知外部限制。

## 自检

- 六项设计要求均有对应测试和实现任务。
- 不跨用户共享 DPAPI 密钥，不记录 API Key，不修改业务评分规则。
- 完成标准是打包程序在普通用户等价环境通过，不是开发服务器通过。
- 用户已明确要求当前任务直接执行，因此不派发智能体、不执行 Git 提交。

