# CatToken OpenAI 与 Claude 双供应商设计

## 目标

将现有 CatToken 配置拆成两个可同时启用的独立供应商窗口：

- `CatToken OpenAI`：继续使用 OpenAI Responses API。
- `CatToken Claude`：使用 Anthropic Messages API。

两套配置分别保存 API Key、服务地址、默认模型、模型目录、启用状态和连接测试结果，互不覆盖。历史任务和现有 CatToken OpenAI 配置必须保持兼容。

## 已确认方案

采用固定双槽位架构：保留现有 `cattoken` 槽位并新增 `cattoken_claude` 槽位。界面以两个独立顶部标签展示，不在同一记录中保存两套协议，也不扩展为任意动态供应商系统。

## 供应商定义

### CatToken OpenAI

- Slug：`cattoken`
- 显示名称：`CatToken OpenAI`
- 固定协议：`openai`
- 默认服务地址：`https://www.cattoken.vip/v1`
- 调用方式：OpenAI Responses API
- 数据迁移：保留现有 API Key、默认模型、启用状态、模型目录和测试状态。

### CatToken Claude

- Slug：`cattoken_claude`
- 显示名称：`CatToken Claude`
- 固定协议：`anthropic`
- 默认服务地址：`https://www.cattoken.vip`
- 调用方式：Anthropic Messages API `/v1/messages`
- 初始状态：禁用、API Key 为空、未测试。
- 不从原 CatToken 槽位复制 API Key。

## 数据与兼容性

- 复用现有 `provider_configurations` 表，以新 slug 保存 Claude 配置，不新增明文密钥字段。
- 两套 API Key 继续使用现有加密机制，公开接口只返回掩码。
- 扩展后端与前端的 ProviderSlug 类型以包含 `cattoken_claude`。
- 历史任务中的 `provider=cattoken` 始终代表原 OpenAI 配置，不重写历史数据。
- 新任务保存明确的供应商 slug、显示名称、协议和模型，保证结果页可以区分两个 CatToken 来源。

## API 设置界面

- 顶部供应商标签分别显示 `CatToken OpenAI` 与 `CatToken Claude`。
- 两个窗口均独立提供启用开关、服务地址、默认模型、模型目录、API Key、测试连接与保存配置。
- 固定供应商不显示可编辑协议切换，协议由槽位定义，避免误选。
- 模型目录继续使用每页 10 个的分页组件。
- Claude 未成功测试时不能启用或保存为可用状态。

## 连接测试与错误处理

- CatToken OpenAI 使用 Responses API 发送最小 `Reply OK` 请求。
- CatToken Claude 使用 Messages API 发送最小 `Reply OK` 请求。
- Claude 测试成功后只将实际成功的模型写入可用模型目录；不把未经聊天验证的模型列为可选。
- 错误映射应明确区分：认证失败、模型不存在、协议不兼容、限流、连接超时和上游服务错误。
- 错误信息不得包含 API Key、请求头或完整上游响应中的敏感字段。

## 任务与交叉验证

- 两个 CatToken 槽位可以同时启用。
- 任务与交叉验证的模型选项显示完整身份：
  - `CatToken OpenAI · <模型名>`
  - `CatToken Claude · <模型名>`
- 只展示已启用、最近连接测试成功且模型通过实际聊天验证的选项。
- 同一次交叉验证可以分别选择 CatToken OpenAI 与 CatToken Claude。

## 迁移策略

1. 新版本启动后仍读取原 `cattoken` 记录，不修改其密钥或模型。
2. `cattoken_claude` 没有记录时返回默认的未配置公开对象。
3. 用户手动填写 Claude API Key、测试连接并保存后才创建或更新 Claude 记录。
4. 不自动复制密钥，不改写历史任务，不改变现有 CatToken OpenAI 的可用性。

## 测试与验收

### 自动测试

- 两个槽位独立保存、读取、加密和清除 API Key。
- OpenAI 槽位调用 Responses API；Claude 槽位调用 Messages API。
- 两个槽位的模型目录、测试状态和启用状态互不影响。
- 历史 `cattoken` 任务仍构建原 OpenAI 客户端。
- 前端显示两个标签，并分别管理密钥、模型和测试状态。
- 任务选择器明确区分两套模型身份，未验证模型不可选。

### 实际验收

1. 在 CatToken Claude 窗口填入 Claude API Key。
2. 测试一个真实 Claude 模型并保存。
3. 运行一次最小分析任务，确认软件产生正常输出。
4. 在 CatToken 后台确认 Claude 请求数或消费记录增加。
5. 验证 CatToken OpenAI 原配置仍可用。

## 安全边界

- 不把用户账号、密码或 API Key 写入代码、测试、设计文档、验证报告或迭代记录。
- 浏览器登录只用于读取用户授权范围内的接口信息。
- 日志只记录脱敏状态、错误类别和验证结论。

## 不在本次范围

- 不开发任意数量的动态供应商配置。
- 不自动创建或删除 CatToken 后台密钥。
- 不修改历史任务结论或重新归属历史消费。
- 不改变 OpenAI、DeepSeek 和自定义 API 的现有职责。
