# 0.1.8 历史任务持久化与模型轮换设计

## 1. 背景与目标

0.1.7 的任务创建已经在排队前写入 `analysis_jobs`。历史页显示为空不是数据库没有保存，而是应用重启恢复任务为 `interrupted` 后，`JobStatus` 仍只允许 `queued/running/completed/failed`，`GET /api/v1/jobs` 在 Pydantic 序列化时返回 500；前端又把查询失败当成空列表展示。

0.1.8 的目标是：

1. 每个用户提交只产生一个历史任务，任务在进入 Worker 前就可见；排队、运行、完成、失败和中断都可查询。
2. 历史列表、详情、重试和错误状态对旧任务兼容，不因一个异常状态隐藏整页历史。
3. 可选启用模型轮换。关闭时严格使用用户选定模型；启用时按任务提交时快照的顺序尝试已通过代表性完整报告验证的模型。
4. 仅技术性失败触发下一个模型；有效且质量通过的报告（包括“没有符合条件的组合”）立即成功，不因业务结论轮换。
5. 保存每次尝试的审计信息和最终成功模型，但只生成一套最终 JSON/Excel 产物。
6. 针对模型差异使用明确的协议、超时和结构化输出适配；不降低 V2.1 schema、证据绑定和结果质量门。

## 2. 非目标与不变量

- 不重算、覆盖或删除 0.1.7 以前的任务和结果。
- 不把每个模型尝试显示成独立历史任务；用户看到的仍是一条用户任务。
- 每个候选模型最多发起一次完整报告请求；不在隐藏层重复付费请求。
- 不把 API Key、原始无效模型输出、请求头或上游响应体写入数据库、日志或迭代记录。
- 不因业务上没有合格方向、食品阻断或 `completed_needs_evidence` 而轮换；这些是结构有效的终态。
- 0.1.8 升级必须保留 0001–0009 数据库内容，并可在升级失败时恢复原数据库备份。

## 3. 领域模型与数据流

### 3.1 用户任务与尝试

`AnalysisJob` 是用户任务根实体。提交 API 先将不可变的请求快照写入任务并提交事务，再入队。快照包含：模式、原始输入、请求模型/provider、`rotation_enabled`、候选顺序、提交时的连接修订号、运行契约版本和提交时间。重试创建新 `AnalysisJob`，通过 `retry_of_id` 指向原任务，并复制原任务快照，不修改原任务。

新增 `JobModelAttempt` 子实体（迁移 `0010`）：

| 字段 | 约束/含义 |
| --- | --- |
| `id` | UUID 主键 |
| `job_id` | `analysis_jobs.id` 外键，级联删除 |
| `ordinal` | 任务内从 1 开始，唯一 |
| `provider` / `api_protocol` / `model` | 本次实际路由身份快照 |
| `status` | `running`、`succeeded`、`failed` |
| `stage` | `prepare`、`request`、`parse`、`schema`、`quality`、`persist` 等固定值 |
| `error_code` / `error_message` | 规范化错误，不含上游原文 |
| `started_at` / `finished_at` / `duration_ms` | UTC 时间和耗时 |
| `created_at` / `updated_at` | 审计时间 |

唯一键为 `(job_id, ordinal)`，索引为 `(job_id, ordinal)` 与 `(job_id, status)`。中断恢复时，将 `running` 尝试标记为 `failed`，错误码 `APP_INTERRUPTED`，保留任务级 `interrupted` 终态；不会凭空把未开始的候选标记为失败。

### 3.2 状态机

```text
queued -> running -> completed
                    -> failed
                    -> interrupted (进程重启恢复)
```

启用轮换时，任务仍保持 `running`：

```text
running -> attempt-1 running -> succeeded -> completed
                         \-> technical failure -> attempt-2 running -> ...
                         \-> terminal failure -> failed
```

只有任务级状态变为 `completed` 后才写入 `result_payload` 和两类 Artifact。任何候选都失败时，任务为 `failed`，错误聚合为稳定错误码，并在详情页展示尝试摘要。

## 4. 历史 API 与兼容性

### 4.1 后端契约

- `JobStatus` 增加 `interrupted`。
- `JobSummary` 保持现有字段，增加 `rotation_enabled`、`attempt_count`、`successful_model`、`last_attempt_status` 等只读摘要字段；缺失字段的旧任务使用 `request_payload` 或空值回退。
- `JobDetail` 增加 `rotation` 快照和 `attempts` 数组；尝试详情只返回规范化字段。
- 新增 `GET /api/v1/jobs/{job_id}/attempts`（或由详情内嵌，二者只实现一个）分页读取审计记录，不能返回原始模型输出。
- `GET /api/v1/jobs` 对未知/旧状态不能整体 500。Repository 保留记录，schema 只允许已知状态；迁移前遗留未知值映射为 `failed` 并使用 `LEGACY_UNKNOWN_STATUS`，同时记录警告。
- `POST /api/v1/jobs/{job_id}/retry` 接受 `failed` 和 `interrupted`，其他状态返回稳定 409。重试创建新任务，不清理旧任务。

### 4.2 前端契约

- `JobStatus` 增加 `interrupted`，状态标签为“已中断”。
- 历史页显示 `isError`、稳定错误文案和带图标的重新加载按钮；查询失败不能渲染“暂无任务记录”。
- 中断任务可打开详情和重新提交；失败任务保留现有重试按钮。运行中显示等待/已运行时长，中断显示最后更新时间。
- 详情页显示任务级轮换摘要和尝试时间线：模型、耗时、阶段、规范化错误；默认折叠技术详情。
- 轮换开关关闭时只显示单模型；开启时显示候选排序编辑器。候选必须来自当前连接且已通过代表性完整报告验证的模型，拖拽/上移下移后保存到本次任务快照，不自动修改全局默认。

## 5. 模型准入与轮换设置

### 5.1 代表性完整报告验证

现有 lightweight probe 只能证明连接和模型存在，不能加入自动轮换。模型目录新增验证结果类型 `full_report_verified`，至少保存：连接修订号、模型、协议、测试时间、测试任务模式、schema 版本、质量门结果和耗时。只有同一连接修订号下最近一次代表性完整报告通过解析、V2.1 schema、证据绑定和 `result_quality` 的模型，才可作为轮换候选。

验证任务使用合成但代表性的最小商品事实，不写入用户历史；必须走与正式任务相同的请求、解析和质量门。验证请求是显式操作或后台队列任务，不在正式任务中隐式额外发起。

### 5.2 提交快照

`rotation_enabled=false` 时，候选列表只含请求模型，Worker 不访问其他模型。

`rotation_enabled=true` 时：

1. 前端提交用户排序后的候选身份；后端重新校验每个身份属于当前连接、已选择且 `full_report_verified`。
2. 后端去重并保留顺序，至少一个候选；失效候选返回 422，不静默替换付费模型。
3. 任务保存候选列表和连接修订号；运行期间即使全局目录变化，也不改变本任务的审计快照。
4. 用户请求模型仍保存为 `requested_model`；成功模型保存为 `successful_model`。

## 6. 失败分类与边界

### 6.1 可轮换技术失败

以下错误结束当前尝试并进入下一个候选：超时、连接断开、429/限流、上游 5xx/不可用、空响应、文本无法提取 JSON、截断 JSON、JSON 解析失败、schema/枚举/字段校验失败、`result_quality` 质量门失败、结构化响应工具不支持且协议适配失败。错误统一为稳定码，例如 `MODEL_TIMEOUT`、`MODEL_RATE_LIMITED`、`MODEL_UPSTREAM_UNAVAILABLE`、`MODEL_EMPTY_RESPONSE`、`MODEL_INVALID_JSON`、`MODEL_SCHEMA_INVALID`、`MODEL_RESULT_QUALITY_INVALID`。

每次尝试只记录失败阶段和规范化摘要。原始异常仅用于内存中的分类，日志只记录 provider、model、stage、稳定码和异常类型。

### 6.2 不轮换的终态

认证失败、模型未授权/不存在、连接配置缺失、URL 不支持、浏览器/抓取失败、主品食品阻断、用户取消、进程被用户主动停止、业务校验不满足但报告结构有效，均直接使任务失败或业务完成，不调用下一个模型。具体错误码由现有错误分类保持兼容。

`completed_no_qualified_candidates`、`completed_needs_evidence`、食品方向过滤后的有效汇总均是成功结果；必须先通过 schema 和质量门，再根据业务结论写入 `completed`。

## 7. Worker 与供应商适配

新增任务编排器负责：读取任务快照、创建尝试、选择协议客户端、调用一次完整报告、解析/校验/质量检查、写入尝试结果，并在需要时切换候选。现有 `AnalysisRunner` 继续负责单模型业务流程；不在业务服务内复制轮换循环。

每个模型使用显式运行配置：协议、请求超时、最大输出、结构化响应能力和错误分类器。GPT-5.5 及有真实证据的版本化后缀默认允许较长单次超时；5.4 和其他模型保持各自经过验证的上限。超时值必须配置化并在尝试审计中记录实际耗时，不用一个全局值掩盖模型差异。

优先使用供应商支持的结构化输出/JSON schema；文本回退必须经过严格 JSON 提取、解析、V2.1 schema 和质量门，不能因为轮换而放宽字段、枚举、证据或业务一致性要求。

## 8. 产物与事务边界

每个任务最多写一套 JSON 和 Excel。候选尝试的中间内存结果不写 Artifact；只有最终质量通过后，先持久化 `result_payload`，再原子写入两类产物并登记 checksum。产物写入失败是任务级 `ARTIFACT_PERSIST_FAILED`，不再向其他模型收费轮换，因为报告本身已经成功。

任务创建事务与入队保持现有语义：数据库提交成功后入队失败，任务仍在历史中并标记 `QUEUE_UNAVAILABLE`。尝试记录与任务终态在同一个任务会话中按阶段提交，进程崩溃后恢复器依据状态补齐 `interrupted`，不伪造成功。

## 9. 数据迁移与升级

迁移 `0010_add_job_model_attempts_and_rotation.py` 只新增 `job_model_attempts` 表和必要索引，不回填旧尝试。旧 `analysis_jobs` 的 `request_payload` 缺失轮换字段时按关闭处理，`attempt_count` 从 0 或已有 provider/model 摘要回退。

升级验收包括：0009 -> 0010、空库全迁移、已有 4 completed/8 failed/1 interrupted 的混合数据、WAL/SQLite 备份恢复、Windows 中文/空格/#/% 路径。迁移失败必须保留 live 数据库和现有备份，不执行替换。

版本号更新到 0.1.8；覆盖安装沿用现有 LocalAppData 数据目录，不能把数据库放回只读安装目录。

## 10. TDD 与验收标准

先写红灯，再做最小实现，至少覆盖：

1. `JobStatus` 序列化 interrupted；混合状态列表/详情返回 200；前端查询失败显示错误和重试，而非空状态。
2. 提交后立即存在 queued 历史行；队列失败仍有 failed 行；重启恢复 running 为 interrupted；中断可重试。
3. 轮换关闭只调用请求模型；开启按快照顺序调用；技术失败才切换；业务成功/无合格组合不切换；候选最多一次完整请求。
4. 每次尝试写入开始/结束/耗时/阶段/规范化错误；任务只生成一套 Artifact；最终模型正确显示。
5. 空响应、截断 JSON、非法枚举、schema 失败、质量门失败和上游 429/5xx 均可分类；认证、抓取、业务阻断不轮换。
6. 代表性完整报告验证通过模型才能加入轮换；lightweight probe 不能绕过准入；连接修订号变化使旧验证失效但保留历史。
7. 后端定向/全量 pytest、Ruff（改动文件）、前端 Vitest、TypeScript、Next 构建、桌面测试、`git diff --check`；停止 dev 服务后串行构建。
8. 用新的合成任务和至少一次真实端到端报告验证 5.4/5.5/5.6 中已配置模型；真实模型响应不进入日志或文档，质量通过的“无合格组合”视为成功。

## 11. 回滚与风险

若 0.1.8 运行异常，停止 Worker 后恢复 0.1.7 应用文件，保留新增数据库表和任务数据；0.1.7 读取未知表不受影响。只有在备份校验成功后才允许恢复数据库副本。回滚不删除用户在 0.1.8 期间创建的任务；通过迁移脚本和兼容读取保留可审计性。

主要风险是上游模型行为仍可能变化、长超时占用 Worker、以及轮换导致费用增加。通过候选快照、每候选一次、代表性准入、明确超时、审计和用户可见状态控制风险；不以自动轮换掩盖模型 5.6 的根本不稳定，仍需用代表性任务持续收集证据并针对协议/提示/结构化输出修复。
