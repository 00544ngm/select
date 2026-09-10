# 第三方 OpenAI 兼容协议接入设计

日期：2026-08-14

## 目标

增强“自定义 API -> OpenAI 兼容”链路，使软件可以通过 OpenAI Python SDK 连接第三方 GPT 服务，并稳定完成连接检测、模型验证和长结构化报告任务。

第三方服务的模型名称不能决定其接口能力。即使模型名为 `gpt-5.5` 或 `gpt-5.6`，也可能只实现 `POST /v1/chat/completions`；反之，某些服务可能只开放 `POST /v1/responses`。软件必须根据真实能力探测结果选择接口，不能继续按模型名硬编码。

本次不改变官方 OpenAI、DeepSeek、Anthropic、商品抓取、历史记录、模型轮换顺序和现有 V2.1 报告质量门。

## 已确认方案

采用“能力探测并持久化”方案：

1. 自定义 OpenAI 模型验证优先探测 Chat Completions。
2. Chat Completions 不可用且错误明确表示接口不支持时，再探测 Responses API。
3. Chat Completions 依次确认 `json_schema`、`json_object` 和提示词约束 JSON 三档结构化输出能力。
4. 把验证成功的传输接口和结构化输出模式与供应商、模型、协议及连接修订号绑定保存。
5. 正式任务只使用已保存的能力组合，不按模型名改路由，也不在一份正式报告中临时切换接口。
6. 地址、API Key 或协议变化后递增连接修订号，使旧能力结果自动失效并要求重新验证。

未采用的方案：

- 仅使用 Chat Completions：兼容面较大，但无法支持只开放 Responses API 的第三方服务。
- 继续按模型名选择接口：改动小，但会延续当前连接测试和正式报告接口不一致的问题。

## 范围

### 包含

- 自定义 OpenAI 服务地址规范化。
- OpenAI SDK 零隐式重试配置。
- Chat Completions 和 Responses API 能力探测。
- 三档 Chat Completions 结构化输出能力探测。
- 探测能力持久化、连接修订失效和运行时固定路由。
- OpenAI SDK 异常到稳定业务错误码的映射。
- 现有模型轮换与 attempt 历史对新错误元数据的复用。
- API 设置页的协议、地址、能力及 Token 消耗说明。
- 自动化测试、桌面整包烟测和 `0.1.14` 安装包。

### 不包含

- 不自动把 OpenAI 协议切换成 Anthropic 协议。
- 不根据 `gpt-*`、`claude-*` 等模型名称猜测接口。
- 不自行实现 OpenAI HTTP 或 SSE 协议，继续使用官方 OpenAI SDK。
- 不在正式报告请求失败后临时换接口重新生成同一份报告。
- 不降低 JSON schema、方向数量、证据绑定或报告质量要求。
- 不记录 API Key、Authorization、完整提示词或完整模型原文。
- 不修改或重新计算已有历史任务。

## 地址规范化

自定义 OpenAI 地址允许填写基础地址、`/v1`、完整 `/v1/chat/completions`、完整 `/v1/responses`，以及带第三方网关前缀的等价地址。

统一规则：

1. 只接受 `http` 或 `https`。
2. 移除查询参数、片段和末尾斜杠。
3. 若末尾为 `/chat/completions` 或 `/responses`，移除该资源路径，保留其前面的 `/v1`。
4. 若地址尚无 `/v1`，追加 `/v1`。
5. 保留 `/v1` 前的第三方网关路径，不截断自定义前缀。
6. 保存边界和客户端构造使用同一规范化函数，避免重复拼接。

官方 OpenAI 和 DeepSeek 的既有地址保持原样，不使用自定义地址迁移规则重写。

## 能力模型

每个自定义 OpenAI 模型的验证记录新增两项可空能力：

- `transport_mode`: `chat_completions` 或 `responses`
- `structured_output_mode`: `json_schema`、`json_object` 或 `prompt_json`

约束：

- `responses` 当前统一使用提示词约束 JSON，因此其 `structured_output_mode` 为 `prompt_json`。
- 能力记录只有在 `status=verified` 且 `connection_revision` 等于当前供应商 `validation_revision` 时有效。
- 旧版验证记录的能力字段为空，继续可展示，但不能直接用于新正式任务；重新验证后补齐能力。
- 官方 OpenAI 和 DeepSeek 不依赖该持久化能力选择改变现有路由。

数据库迁移 `0012` 仅向 `provider_model_validations` 添加上述两个可空字符串字段，不改唯一约束，不删除或重写旧记录。降级时只删除新字段。

## 探测流程

### 连接检测

连接检测验证地址、API Key、模型和基础 OpenAI 响应形状。自定义 OpenAI 使用 Chat Completions 小请求；只有明确的接口不支持错误才尝试 Responses。模型列表发现仍为可选能力，`GET /models` 不可用不能单独判定连接失败。

连接检测会消耗少量 Token。OpenAI SDK 设置 `max_retries=0`，避免 SDK 隐式重试和应用层重试叠加。

### 模型验证

模型验证使用小型严格 schema，按以下顺序执行：

1. Chat Completions + `response_format=json_schema`。
2. 若服务明确不支持该参数，Chat Completions + `response_format=json_object`。
3. 若服务明确不支持 `response_format`，Chat Completions + 提示词约束纯 JSON。
4. 只有 Chat Completions 端点本身明确不可用时，才探测 Responses + 提示词约束纯 JSON。

不会因认证失败、权限不足、模型不存在、请求过大、限流、网络超时或上游 5xx 而切换接口。这些错误不是协议能力证据。

验证成功必须返回非空、可解析、包含必填字段且没有截断状态的 JSON。成功后在同一验证记录保存能力模式与当前连接修订号；失败不保留旧修订号下的可用能力。

### 自动验证

沿用现有“正常使用不重复验证，失败后才重新验证”的策略。地址、Key 或协议变化会主动失效旧结果；运行时若收到明确的端点或结构化能力失效错误，则标记该能力需重新验证，但当前正式报告不会自动换接口再次付费。

## 正式报告路径

`OpenAILLMClient` 接收显式运行模式，而不是在内部根据模型名调用 `_uses_responses_api()`：

- `chat_completions/json_schema`：传递严格 JSON Schema。
- `chat_completions/json_object`：加入 schema 指令并传递 JSON Object 格式。
- `chat_completions/prompt_json`：只加入 schema 指令，不传第三方可能不支持的 `response_format`。
- `responses/prompt_json`：使用 Responses API 和 schema 指令。

正式报告沿用现有模型超时和大输出预算规则，完整解析响应并检测截断。相同模型的一次正式调用只走一个已验证接口。若能力记录缺失或已过期，在付费任务前返回 `PROVIDER_MODEL_NOT_VERIFIED`，由自动验证流程处理，而不是盲目发送正式报告。

官方 OpenAI 保留现有 GPT 5.x Responses 行为；DeepSeek 保留现有 Chat Completions 行为；Anthropic 保留 Messages 流式行为。

## 错误分类与重试

| 条件 | 错误码 | 可重试 |
| --- | --- | --- |
| 401 | `PROVIDER_AUTH_FAILED` | 否 |
| 403 | `PROVIDER_PERMISSION_DENIED` | 否 |
| 404 模型不存在 | `PROVIDER_MODEL_INVALID` | 否 |
| 404/405 端点不存在 | `PROVIDER_PROTOCOL_MISMATCH` | 否 |
| 400 不支持 `response_format` | `PROVIDER_STRUCTURED_OUTPUT_UNSUPPORTED` | 否 |
| 413 | `PROVIDER_REQUEST_TOO_LARGE` | 否 |
| 429 | `PROVIDER_RATE_LIMITED` | 是 |
| 500-599 | `PROVIDER_UPSTREAM_UNAVAILABLE` | 是 |
| 连接失败 | `PROVIDER_CONNECTION_FAILED` | 是 |
| 请求超时 | `PROVIDER_MODEL_TASK_TIMEOUT` | 是 |
| 空响应 | `PROVIDER_EMPTY_RESPONSE` | 是 |
| 截断或非法 JSON | `MODEL_INVALID_JSON` | 是 |

协议探测只在错误可以证明“当前接口或参数不被支持”时进入下一档。应用层对可恢复错误沿用现有有限重试；SDK 始终 `max_retries=0`。模型轮换继续只在现有可轮换技术错误上切换下一个已验证模型，不改变候选顺序。

日志只记录供应商标识、协议、模型、能力模式、阶段、HTTP 状态、SDK 异常类型、请求 ID 和脱敏错误摘要。

## 配置界面

选择“自定义 API -> OpenAI 兼容”后：

- 说明服务至少需要支持 `POST /v1/chat/completions` 或 `POST /v1/responses` 之一。
- 说明可粘贴基础地址、`/v1` 或完整接口地址，保存时会自动规范化。
- 说明连接检测和模型验证会产生少量 Token；验证成功且配置不变时不会按固定时长重复验证。
- 展示模型已验证的接口模式和结构化输出模式，便于定位第三方兼容程度。
- 对认证、模型、端点、结构化格式、限流、上游和网络错误显示针对性的中文处理建议。

不显示或记录 API Key 明文。

## 数据流

1. 用户保存自定义 OpenAI 地址、API Key 和模型名。
2. 服务规范化地址，并在配置变化时递增连接修订号。
3. 连接检测发送极小请求并确认基础协议。
4. 模型验证按能力矩阵探测，保存成功模式及连接修订号。
5. 用户勾选通过验证的模型。
6. 创建任务时将供应商、协议、模型和连接修订号写入现有任务/轮换快照。
7. Resolver 读取当前有效能力并构造固定模式的 OpenAI 客户端。
8. 正式报告按固定模式执行，结果继续经过现有 schema 和质量门。
9. attempt 历史保存实际供应商、协议、模型、阶段和稳定错误码；不保存密钥和模型原文。

## 测试与发布

- 地址各种形式和网关前缀规范化。
- OpenAI SDK 使用规范化地址并设置 `max_retries=0`。
- Chat 三档结构化能力和 Responses 回退探测。
- 认证、限流、超时或 5xx 不误触发接口切换。
- 能力模式随连接修订号持久化和失效。
- 自定义 `gpt-5.5/5.6` 不再因名称强制走 Responses。
- 正式任务只调用一个已验证接口。
- 空响应、截断、非法 JSON 和响应形状异常映射稳定错误码。
- 官方 OpenAI、DeepSeek、Anthropic 回归测试。
- 前端地址/Token 说明、能力展示和错误引导测试。
- Python、前端、Electron 全量测试，双方 TypeScript 检查，目标 Ruff、`git diff --check` 和前端生产构建。
- 构建 Windows 安装包，使用独立临时 `LOCALAPPDATA` 启动，验证数据库迁移至 `0012`、API、Worker、首页、历史页、设置页及员工中文、空格、`#`、`%` 路径。
- 校验 `0.1.14` 文件版本和 SHA-256，并确认 `0.1.12`、`0.1.13` 安装包未改变。

真实第三方供应商只有在用户提供可用配置并明确执行真实测试时才能声明通过；自动化 mock 测试不能替代真实供应商验收。

## 安全、兼容与回滚

- API Key 继续使用现有桌面 DPAPI/加密存储。
- 不把密钥、Authorization、完整请求或模型完整原文写入日志、数据库验证消息或安装包。
- `0012` 只增加可空字段，旧数据库可前向迁移，旧历史任务不被修改。
- 回滚生产代码时，旧版本可忽略新字段；若执行数据库降级，仅删除两个能力字段，不删除模型验证或任务历史。
- 不覆盖既有安装包；新版本使用 `0.1.14`。

## 验收标准

- 第三方 OpenAI 兼容服务可填写地址、API Key 和任意模型名称完成配置。
- 模型名为 `gpt-5.5/5.6` 时不会被硬编码到 Responses API。
- 仅支持 Chat Completions 或仅支持 Responses 的服务都能按真实能力完成验证和正式长报告。
- 正式报告只调用已验证接口一次，不因接口回退产生双倍 Token 消耗。
- 配置不变且能力有效时不按固定时长重复验证；配置变化或明确能力失效后重新验证。
- 技术失败产生准确、稳定、脱敏的错误码，并继续遵守现有模型轮换规则。
- 官方 OpenAI、DeepSeek、Anthropic、历史记录、抓取流程和报告质量门无行为回归。
- `0.1.14` 安装包在隔离员工路径环境可启动并完成迁移与页面烟测。
