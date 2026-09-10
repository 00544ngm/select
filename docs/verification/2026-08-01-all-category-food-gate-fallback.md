# 全品类食品门禁回退：全量与真实样例验收

- 验收时间：2026-08-01 03:57–04:10（Asia/Shanghai）
- 结论：`DONE`
- 日志基线：操作前均完整读取 `docs/优化迭代记录.md`，开始时最新成功条目为 `I-116`；本轮失败记录为 `F-183` 至 `F-187`。
- 安全边界：未读取或记录 API Key、账号、密码、Cookie、Token、隐私数据或模型原始响应；仅记录本地 job UUID、结构化状态和安全错误码。

## Fresh 自动化证据

1. 后端全量：`.\.venv\Scripts\python.exe -m pytest -q`
   - 退出码 0；`520 passed, 1 warning in 15.87s`。
   - warning：readiness 测试中的未等待协程资源警告。
2. 前端（工作目录 `frontend`）：
   - `npm.cmd test -- --run`：退出码 0；`20 passed` 测试文件，`182 passed` 测试，11.15s。
   - 有既有 Vite CJS 弃用提示及一项 MSW provider 请求未匹配 stderr，不影响断言或退出码。
   - `npm.cmd run typecheck`：退出码 0。
   - `npm.cmd run build`：退出码 0；Next.js 15.5.20 编译、类型检查及 7 个静态页面生成通过。
3. Ruff：对共享工作区实际改动或新增的 27 个 Python 文件运行 `.\.venv\Scripts\python.exe -m ruff check -- <files>`，退出码 1，5 项错误：
   - `app/core/exceptions/__init__.py`
   - `app/domain/dto/__init__.py`
   - `app/domain/pairing_policy.py`
   - `app/domain/schemas/hypothesis.py`
   - `app/domain/stickiness.py`
   - `app/infrastructure/storage/excel_exporter.py`
   - `app/services/hypothesis_service.py`
   - `app/services/market_evidence_service.py`
   - `backend/api/schemas/jobs.py`
   - `backend/api/schemas/providers.py`
   - `backend/application/analysis_runner.py`
   - `backend/application/provider_clients.py`
   - `backend/application/provider_service.py`
   - `backend/application/result_quality.py`
   - `backend/tests/test_analysis_runner.py`
   - `backend/tests/test_job_service.py`
   - `backend/tests/test_provider_clients.py`
   - `backend/tests/test_provider_service.py`
   - `backend/tests/test_providers_api.py`
   - `backend/tests/test_result_quality.py`
   - `tests/test_excel_exporter.py`
   - `tests/test_hypothesis_service.py`
   - `tests/test_prompts.py`
   - `app/domain/ingestible_classifier.py`
   - `app/services/product_type_reviewer.py`
   - `tests/test_ingestible_classifier.py`
   - `tests/test_product_type_reviewer.py`
   - 错误集中于 `backend/api/schemas/providers.py`（导入排序、两项 UP037、`__all__` 排序，共 4）及 `backend/tests/test_provider_service.py`（导入格式，共 1）。未自动修复。
4. `git diff --check`：退出码 0，无空白错误；仅共享工作区 LF→CRLF warnings。

## 重启与健康

- `& '.\启动.ps1'`：退出码 0，25.2s。
- `http://127.0.0.1:3000/`：HTTP 200。
- `http://127.0.0.1:8000/api/v1/health/live`：HTTP 200。
- 启动脚本声明并实际使用 `/api/v1/health/ready`；fresh 响应中 database、redis、worker、contract_match 均为 `ok`，API 与 worker 模型版本均为 `combination_model_v2.1`。
- 首次组合检查误用 PowerShell `$home`，与只读 `$HOME` 冲突；该次前端状态作废，已用任务专用变量重跑得到 HTTP 200（`F-184`）。

## 真实 Walmart 样例

- 商品 ID：`5818883652`。
- 新 hypothesis job：`c0c8c912-41f8-45aa-bd66-ade06a0a244a`；未修改历史任务。
- 提交：仅传正常 Walmart 商品 URL，未覆盖 provider/model，复用后端当前默认配置。
- 状态：queued → running 5% → running 65% → completed 100%；约 5 分钟，无终态错误码。首段 121 秒窗口未终态，已记 `F-185` 后继续轮询。
- 结构化结果：`product_type_review.status=confirmed_non_food`、`source=rule`、`action=continue`，依据 2 条；结果存在后续模型/方向分析。
- 验收判断：不再于 5% 以 `PRODUCT_TYPE_VERIFICATION_REQUIRED` 失败，食品类型回退最低运行门槛通过。

## 运行时 UI

- Playwright headless 打开真实 job 结果页：HTTP 200、console error 0、page error 0。
- 首次中文常量受 PowerShell stdin 编码影响，断言无效，已记 `F-186` 并以 Unicode 转义重跑。
- Unicode 重验：仅找到通用“结论”；未找到“商品类型复核”“来源”“依据”“处理”或“非食品”。真实结果页未满足中文商品类型卡四栏验收，记 `F-187`。

## UI 缺陷修复后的最终复验

- 根因：双模型结果的主品 `product_type_review` 位于任务 wrapper 顶层；页面切换到模型子结果后只读取子结果，导致任务级判断卡丢失。
- 修复：任务详情优先继承 wrapper 顶层主品复核，flat 单模型安全回退；卡片移至结果视图切换之外，默认页、模型切换和方案分析均只显示一份。
- 自动化：前端全量 `20 passed` 测试文件、`183 passed` 测试；TypeScript 通过；Next.js 生产构建成功并生成 7 个页面；`git diff --check` 退出码 0，仅有既有 LF/CRLF 提示。
- 真实页面：任务 `debf9aa1-cc43-4132-9e4e-2c0dffcb9577` 中“确认非食品”“规则判断”“判断依据”“允许继续分析”各出现 1 次；浏览器控制台 error 为 0。

## 最终判定

- 后端食品门禁、模型输出、结果持久化与前端中文解释卡均已通过自动化和真实样例验证。
- 早期 Ruff 失败在后续修正后，目标 Python 文件复跑为 `All checks passed!`；早期 UI concern 已由上述 wrapper 顶层回退修复关闭。
- 本轮未提交 commit，未记录凭据、隐私数据或模型原始响应。
