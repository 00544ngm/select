# CatToken 两个供应商彻底下线验收

- 日期：2026-08-01
- 范围：CatToken OpenAI（`cattoken`）与 CatToken Claude（`cattoken_claude`）
- 结论：通过

## 数据清理

- 清理前精确目标记录：2 条。
- 清理后精确目标记录：0 条。
- 非目标供应商记录：清理前后均为 3 条（OpenAI、DeepSeek、自定义接口）。
- 未解密、未输出、未记录任何 API Key。
- 历史任务和历史结果未删除、未重写。

## 自动化验证

- 后端全量：`509 passed, 9 skipped, 1 warning`。
- 后端目标 Ruff：`All checks passed!`。
- 前端全量：`179 passed, 7 skipped`。
- TypeScript：通过。
- Next.js 生产构建：通过，生成 7 个页面。
- `git diff --check`：通过；仅显示共享工作区既有 LF/CRLF 提示。

跳过项均为 CatToken 仍可配置、仍可选或仍可执行的旧行为用例，已由新的下线契约测试替代。新的保护测试确认：旧客户端直接传入两个退役 slug 时，在读取数据库或发起供应商请求之前返回不可重试的 `PROVIDER_RETIRED`。

## 真实运行验收

- 使用 `启动.ps1` 重启 API、worker 和前端，启动脚本退出码 0。
- `/api/v1/health/live` 返回 `ok`；重启脚本的就绪校验通过。
- API 设置页显示 3 个服务：OpenAI、DeepSeek、claude；CatToken 标签计数为 0。
- 工作台展开模型设置后不含 CatToken 供应商。
- 浏览器中的旧 CatToken 偏好会被自动清除，并回退到当前有效供应商。
- 历史任务 `fd4b7c75-3296-4a2d-b73c-e3abeebaa1e5` 仍可打开，保留原失败状态、65% 进度和原错误摘要；控制台错误为 0。

## 已知限制

- CatToken 的旧协议适配器代码仍保留为历史兼容实现，但已无设置入口、任务 schema 入口或运行时解析入口，且数据库配置与密钥记录已删除，因此不会被新任务调用。
- 被删除的两条配置与密钥不能从软件恢复；若未来重新接入，需要重新实现入口并重新录入密钥。

