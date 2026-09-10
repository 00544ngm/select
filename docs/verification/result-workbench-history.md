# 结果研究工作台与历史记录验收

验收日期：2026-07-28（Asia/Shanghai）

## 自动化验证

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量测试 | `.\.venv\Scripts\python.exe -m pytest backend/tests tests -q` | PASS，174 passed，1 warning |
| 前端单元测试 | `npm test -- --run` | PASS，17 个文件、94 个测试 |
| TypeScript | `npm run typecheck` | PASS，exit 0 |
| 生产构建 | `npm run build` | PASS，7 个页面生成成功 |
| 桌面与移动端 E2E | `npx playwright test e2e/result-workbench.spec.ts --project=desktop --project=mobile` | PASS，4 passed |

后端警告来自 `backend/tests/test_search_api.py::test_returns_structured_failure_and_closes_resources`：Starlette 异常处理路径报告 `Connection._cancel` coroutine 未 await。该警告在本轮功能前已存在，未造成测试失败。

生产构建首次完成后，仍在运行的 Next.js 开发服务继续读取同一个 `.next` 目录，导致一次 E2E 环境失败，日志为 `Cannot find module './vendor-chunks/next.js'`。停止旧开发服务、清理可再生的 `.next` 缓存并重启后，原样重跑 E2E，最终 4 项全部通过。此问题不涉及业务数据或源代码。

## E2E 截图

- `frontend/test-results/result-workbench-uses-the--378fb-atform-candidates-on-demand-desktop/workbench-desktop.png`
- `frontend/test-results/result-workbench-uses-the--378fb-atform-candidates-on-demand-mobile/workbench-mobile.png`
- `frontend/test-results/result-workbench-shows-Bei-3688b-and-saved-direction-summary-desktop/history-desktop.png`
- `frontend/test-results/result-workbench-shows-Bei-3688b-and-saved-direction-summary-mobile/history-mobile.png`

E2E 使用固定响应验证：默认选择最高分方向、按需 Walmart 查询、`平台已返回` 与 `相似候选（未确认精准）` 标签、真实图片槽位、方向切换、北京时间摘要，以及桌面和移动端无页面级横向溢出。移动端额外断言切换后的方向详情标题位于可视窗口内。

## 真实任务只读核验

任务：`ff03dd2a-7a22-4c79-9d36-e62f150b37fa`

- API 返回 HTTP 200，任务状态为 `completed`。
- 主品：`BUSATIA Blade Guard Pizza Cutter Rocker with Wooden Handles & Stainless Steel Pizza Knife`。
- 综合评分：77.6。
- 已保存最高分方向：`Non-Slip Pizza Cutting Mat` / 防滑披萨切割垫，方向分 91。
- 北京时间：2026-07-27 21:37 开始，22:09 完成；页面显示耗时约 32 分钟。
- 任务详情的研究工作台可打开，方向按分数固定排序，最高分方向默认选中。
- 历史页按北京时间分组，并展示开始、完成、耗时、主品、最高分方向、方向分与综合分。

该任务是在新字段写入逻辑上线前保存的旧任务，因此结果中没有 `product_images`、方向关键词、深度论证和交付清单。真实核验只确认旧数据的降级展示：主图明确显示“历史无图”，查询词使用已保存名称的确定性回退；不能据此声称新任务字段已由该旧任务验证。新字段及平台查询交互由单元测试和固定响应 E2E 覆盖。

## 运行地址

- 前端：`http://localhost:3000`
- 后端：`http://127.0.0.1:8000`
- 就绪检查：`GET /api/v1/health/ready` 返回 `database=ok`、`redis=ok`、`worker=ok`。

前端必须使用 `localhost:3000` 打开。后端 CORS 当前允许来源为 `http://localhost:3000`；若改用 `http://127.0.0.1:3000` 打开前端，浏览器会拒绝跨域请求。
