# 第三方 Anthropic 兼容协议增强设计

日期：2026-08-13

## 目标

增强“自定义供应商 -> Anthropic 兼容”链路，使软件能够通过官方 Anthropic Python SDK 连接真正实现 Anthropic Messages API 的第三方服务，并稳定完成模型验证与正式结构化报告任务。

本次不改变 OpenAI、DeepSeek、商品抓取、历史记录、模型轮换顺序和现有报告质量门。

## 已确认现状

参考代码使用官方 `anthropic` SDK，将第三方服务地址传给 `base_url`，由 SDK 调用 Anthropic Messages API，并使用流式事件收集完整文本。

当前项目已经具备基础链路：

- API 设置支持“自定义供应商”和 `anthropic` 协议。
- `ProviderClientResolver` 会为该协议创建 `AnthropicLLMClient`。
- 连接检测调用 `messages.create()`。
- 正式结构化报告调用 `messages.stream()` 和 `get_final_message()`。
- API Key 使用桌面端 DPAPI 加密保存。

当前主要缺口不是“没有接入”，而是兼容性判定与错误处理不够完整：

- 特定第三方域名被硬编码禁止正式报告，没有以真实协议能力为准。
- 服务地址需要明确规范化，避免用户填入 `/v1/messages` 后形成错误路径。
- SDK 内部重试和软件外层重试可能叠加。
- 第三方返回的认证、限流、过载、协议不匹配等错误没有全部保留为稳定错误码。
- 轻量结构化验证不足以证明第三方能够流式返回可解析结果。

## 范围

### 包含

- 自定义供应商的 Anthropic Messages API 地址规范化。
- 官方 `anthropic.AsyncAnthropic` 客户端配置。
- 流式文本收集、多个文本块拼接和停止原因检查。
- 结构化 JSON 解析和截断识别。
- Anthropic SDK 类型化异常到稳定业务错误码的映射。
- Anthropic 协议模型验证。
- API 设置与任务失败页面的针对性提示。
- 模型轮换继续把可重试技术错误交给下一个候选模型。
- 自动化测试、桌面整包测试和新版本安装包。

### 不包含

- 不自行实现 Anthropic SSE 协议。
- 不根据 Claude 模型名称自动选择协议。
- 不允许 OpenAI 协议配置自动回退到 Anthropic 协议。
- 不修改 OpenAI、DeepSeek 客户端。
- 不降低 V2.1 报告 schema、方向数量、证据或质量校验要求。
- 不保存聊天历史；本软件仍执行独立的分析任务。
- 不记录 API Key、完整提示词或模型原始报告到错误日志。

## 服务地址规范化

用户可能填写：

- `https://api.example.com`
- `https://api.example.com/`
- `https://api.example.com/v1`
- `https://api.example.com/v1/messages`

保存前统一规范化为 SDK 所需的基础地址：

- 移除查询参数、片段和末尾斜杠。
- 如果末尾是 `/v1/messages`，移除该路径。
- 如果末尾是 `/v1`，保留或按 SDK 实际请求行为转换为等价基础地址。
- 只接受 `http` 或 `https`，生产桌面配置默认要求 `https`；回环测试地址可以使用 `http`。
- 不修改域名中间路径，避免破坏使用前缀路由的第三方服务。

规范化函数必须通过测试确认最终 SDK 请求只包含一次 `/v1/messages`。

## 请求链路

### 连接检测

连接检测用于快速判断：

- 地址可连接；
- API Key 可认证；
- 模型存在且有权限；
- 服务端接受 Anthropic Messages API 请求。

使用小输出请求，不验证完整报告能力。该请求会消耗少量 Token。

### 模型验证

Anthropic 协议的模型验证使用流式小型结构化请求：

1. 构造一个只含少量字段的 JSON schema。
2. 通过 `messages.stream()` 发出请求。
3. 使用 SDK 的 `get_final_message()` 取得完整响应。
4. 合并所有 `text` 类型内容块。
5. 检查 `stop_reason`。
6. 解析 JSON 并验证必填字段。

验证成功表示该模型在当前连接修订号下具备基本流式结构化输出能力，不承诺任何时刻都能生成完整业务报告。

### 正式报告

正式报告继续通过 `AnthropicLLMClient.chat_structured()`：

1. 将原有 system 消息合并到 Anthropic 顶层 `system`。
2. 保留 user/assistant 消息顺序。
3. 添加现有 JSON schema 与紧凑输出指令。
4. 使用流式请求，避免长输出的普通 HTTP 读取超时。
5. 通过最终 Message 合并文本块。
6. `stop_reason=max_tokens` 且 JSON 不完整时返回截断错误。
7. JSON 解析成功后继续走现有 schema 和报告质量校验。

## 重试策略

只保留一层明确的任务重试控制：

- Anthropic SDK 客户端设置 `max_retries=0`，避免隐藏重试。
- 适配器对 429、529、网络错误和 5xx 最多按当前软件配置重试。
- 等待时间优先读取 `retry-after`，否则使用带随机抖动的指数退避。
- 认证失败、权限不足、模型不存在、400 参数错误和协议不兼容不重试。
- 每一次正式模型调用仍记录为当前候选模型的一次 attempt；同一候选内部的传输重试不新增历史 attempt。
- 模型轮换开启时，当前候选最终失败后按现有顺序切换下一个候选。
- 模型轮换关闭时，不自动换成其他付费模型。

## 错误分类

| 条件 | 稳定错误码 | 可重试 |
| --- | --- | --- |
| 401 | `PROVIDER_AUTH_FAILED` | 否 |
| 403 | `PROVIDER_PERMISSION_DENIED` | 否 |
| 404 | `PROVIDER_MODEL_INVALID` | 否 |
| 400 请求结构不兼容 | `PROVIDER_PROTOCOL_MISMATCH` | 否 |
| 413 | `PROVIDER_REQUEST_TOO_LARGE` | 否 |
| 429 | `PROVIDER_RATE_LIMITED` | 是 |
| 500-599（含 529） | `PROVIDER_UPSTREAM_UNAVAILABLE` | 是 |
| 连接失败 | `PROVIDER_CONNECTION_FAILED` | 是 |
| 请求超时 | `PROVIDER_MODEL_TASK_TIMEOUT` | 是 |
| 无文本内容 | `PROVIDER_EMPTY_RESPONSE` | 是 |
| `max_tokens` 截断 | `MODEL_INVALID_JSON` | 是 |
| JSON 或 schema 无效 | 现有模型结构错误码 | 是 |

日志只记录供应商标识、协议、模型、阶段、HTTP 状态、SDK 异常类型、请求 ID 和安全错误摘要。不得记录 API Key、Authorization、x-api-key、完整请求体或模型完整原文。

## 配置与界面

- “自定义供应商”继续显示协议分段选择：OpenAI 兼容 / Anthropic 兼容。
- 选择 Anthropic 后提示服务必须支持 `POST /v1/messages`。
- 服务地址允许用户粘贴基础地址或完整 `/v1/messages` 地址，保存时自动规范化。
- 连接检测和模型验证结果区分认证、权限、模型不存在、协议不兼容、限流、过载和网络错误。
- 正式任务错误页面显示针对性处理建议。
- 不显示或记录 API Key。

## 数据兼容

- 复用现有 `api_protocol`、`base_url`、模型验证和连接修订号字段。
- 不新增数据库表，不需要迁移。
- 修改协议、地址或 API Key 后继续增加连接修订号，并要求重新验证模型。
- 已保存的 OpenAI、DeepSeek 和自定义 OpenAI 配置保持原样。

## 测试

### 适配器

- 第三方 `base_url` 传给官方 SDK。
- 基础地址与 `/v1/messages` 输入规范化。
- system 消息分离和多文本块拼接。
- 流式结构化响应解析。
- `max_tokens` 截断识别。
- 401、403、404、400、413、429、529、5xx、超时和网络错误分类。
- `retry-after` 与退避策略。
- SDK 不执行隐藏重试。

### 服务与 Worker

- Anthropic 模型验证走流式结构化请求。
- 连接修订号改变后要求重新验证。
- 可重试 Anthropic 错误参与现有模型轮换。
- 不可重试错误立即结束，不错误切换付费模型。
- attempt 保存真实 `api_protocol=anthropic` 和稳定错误码。

### 前端

- Anthropic 协议选择、地址说明和保存请求。
- 各稳定错误码显示明确中文建议。
- 不影响现有 OpenAI、DeepSeek 配置和模型选择。

### 发布

- Python、前端、桌面全量测试与类型检查。
- Ruff 本次涉及文件检查和 `git diff --check`。
- 构建 Windows 安装包。
- 使用独立临时 `LOCALAPPDATA` 启动整包，不接触真实用户数据库。
- 校验安装包版本、SHA-256 和上一版本安装包不变。

## 回滚

回滚只需要恢复：

- Anthropic 地址规范化；
- Anthropic 适配器重试与异常分类；
- Anthropic 模型验证；
- 前端 Anthropic 提示与错误说明；
- 对应测试。

由于不新增数据库迁移，回滚不会改变历史任务或已保存凭据。已有配置仍可由旧版本读取。

## 验收标准

- 一个真实支持 Anthropic Messages API 的第三方地址、API Key 和模型能够完成连接检测、模型验证和正式报告任务。
- 长报告通过流式响应完整收集。
- 技术失败具有准确、稳定且不泄密的错误码。
- 模型轮换开启和关闭时均保持当前既定行为。
- OpenAI、DeepSeek 和自定义 OpenAI 链路无回归。
- 安装版在员工电脑环境可启动、保存配置并执行任务。
