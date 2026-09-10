# 优化迭代记录

## 使用规则（强制）

1. 每次代码、提示词、评分规则、数据结构、页面展示或部署配置改动前，必须完整阅读本文件，并在本次工作记录中写明读取的最新条目编号。
2. 每次改动必须追加一条记录，内容至少包括：目标、范围、涉及文件、验证命令与结果、已知限制、回滚提交。
3. 任何失败、误判、测试失败、供应商返回异常、采集阻断或数据展示错误都必须追加到“失败案例与防复发规则”，即使最终未修改代码。
4. 不得记录 API Key、Cookie、令牌、用户隐私数据或可复用认证信息。引用外部任务时只记录脱敏链接、任务 ID 或现象。
5. 旧任务结果属于历史快照，除非明确授权，不重新计算、不伪造新证据、不覆盖旧分数。
6. 本文件为追加式记录。更正历史内容时，新增更正条目，不删除原始失败记录。

## 当前基线

- 日期：2026-07-30
- 分支：`codex/stickiness-scoring-v2-1`
- 创建时 HEAD：`af39d69` (`fix: harden food pairing classification`)
- 当前模型契约：`combination_model_v2.0`
- 当前评分：五维粘性分，权重为功能必要性 30、使用连续性 25、场景匹配 20、增强/维护 15、自然联购 10。
- 本轮目标：升级为 V2.1 高精准决策模型；不修改商品数据库、关键词数据库、采集器、利润模块或自定义 Anthropic 兼容协议。

## 历史摘要（由 Git 与既有设计文档回溯）

| 日期 | 迭代 | 已完成或已确认的内容 | 相关提交/文档 |
| --- | --- | --- | --- |
| 2026-07-27 | API 与结果工作台 | 可视化 API 配置、结果工作台、历史记录时间和主品元数据展示。 | `docs/superpowers/specs/2026-07-27-*.md` |
| 2026-07-28 | 供应商兼容与判定展示 | 自定义 Anthropic 风格供应商兼容、任务进度与主品图片修复、否决原因和互补证据展示。 | `docs/superpowers/specs/2026-07-28-*.md` |
| 2026-07-29 | 全品类购买链路 V2.0 | 从类目关联转为购买链路；加入关系类型、食品过滤、五维粘性评分、证据与历史/Excel 透传。 | `0904c48` 至 `af39d69`、`docs/superpowers/specs/2026-07-29-*.md` |
| 2026-07-30 | V2.1 评分诊断与设计 | 确认问题不在算术，而在 AI 输入、分类封顶、硬门槛和证据定义；待实施。 | 本窗口、`2026-07-30-stickiness-scoring-v2.1-design.md` |

## 失败案例与防复发规则

### F-001：所有待验证非食品候选被压成 69 分

- 现象：婴儿安全座椅、颈枕、遮阳帘、玩具、镜面清洁湿巾等不同候选，原始分分别为 100、86、75、75、74，却统一得到最终 69 分。
- 根因：`needs_verification` 同时承担“商品类型未知”和“风险不足”的含义；在 `stickiness.py` 中被当作分数上限 `69`。
- 影响：真实粘性差异被隐藏，排序和解释不可信。
- 防复发：V2.1 必须将“商品类型判断”“安全/兼容待确认”“证据可信度”分离；未知状态只能产生 `hold`，不得直接改写粘性分。

### F-002：购买方向反转仍得到高原始分

- 现象：主品为婴儿车内后视镜时，“婴儿安全座椅”曾得到原始 100 分。
- 根因：模型给出的关系评分未受到“主品是否导致候选需求”的确定性校验约束。
- 影响：把前置主品或更大主品误当作辅品，可能误导采购。
- 防复发：新增 `reverse_dependency` 硬性淘汰；候选必须由拥有/使用主品自然触发需求，不能反向成立。

### F-003：儿童/汽车类安全风险完全依赖模型自报

- 现象：颈枕、车内悬挂玩具等可能涉及儿童乘车安全或制造商适配限制的候选，未必被模型写入 `safety_risk`。
- 根因：当前 `safety_blocked` 只读取模型返回的非空文本。
- 影响：高风险品可能以普通候选进入推荐。
- 防复发：V2.1 建立全品类风险策略表；儿童、汽车、电气、医疗相关候选在安全/合规事实不足时进入 `hold`，明确禁配时直接淘汰。

### F-004：市场证据被标题关键词重合放大

- 现象：沃尔玛搜索结果标题同时含主品和候选词时，系统可标记 E2/E3，但未显示足以证明共同购买、需求或转化的证据。
- 根因：市场验证把标题 token 重合近似当作组合需求。
- 影响：用户无法判断“搜索到商品”与“消费者会一起买”的差别。
- 防复发：证据记录必须保存查询词、来源链接、摘录、计数、时间和证据类型；标题重合只能证明候选存在，不能单独获得高等级。

### F-005：真实供应商运行与自动化测试的边界混淆

- 现象：历史验证中自动化测试通过，但自定义供应商真实任务可能因密钥、Redis、结构化输出或平台限制而无法完成。
- 根因：测试替身和生产供应商能力不同。
- 影响：不能把单元测试通过描述为真实供应商已验证。
- 防复发：每次验证必须分别记录“自动化测试”“真实供应商任务”“基础设施限制”；未实际运行不得标记为已验证。

### F-006：V2.1 初稿存在不可执行或相互矛盾的边界

- 现象：独立文档审阅发现 E3 与“重点开发”定义冲突，`weak_context` 是否允许评分不清晰，婴儿颈枕/普通遮阳帘的回归预期与购买方向规则不一致，证据独立性和分数上限缺少可执行定义。
- 根因：初稿描述了总体方向，但没有穷尽决策动作和服务器裁决矩阵。
- 影响：若直接编码，不同模块或模型供应商可能产生不同解释，测试也无法给出唯一预期。
- 防复发：实施前使用独立读者审阅；规格必须包含穷尽动作矩阵、关系评分上限、证据去重规则和每个歧义案例的唯一预期。

### F-007：V2.1 回归夹具的六维分数手工合计错误

- 现象：新增婴儿颈枕、通用遮阳帘和相机电池回归样本的预期粘性分与按权重换算的实际分数不一致。
- 根因：夹具预期值沿用了人工心算，未逐项按 `30/25/15/15/10/5` 合计。
- 影响：首次回归测试失败，但未改变领域评分代码。
- 防复发：夹具同时断言六维评分结果；新增或修改样本时必须运行评分回归测试，不以手工估算代替测试结果。

### F-008：领域策略提交漏过静态检查

- 现象：评分领域测试通过后，Ruff 仍发现 `Mapping` 导入位置、`__all__` 排序和测试导入格式共四项错误。
- 根因：实现阶段只运行了 pytest，未将静态检查作为提交前必经步骤。
- 防复发：每个 Python 阶段提交前必须运行针对改动文件的 Ruff；测试通过和静态检查通过缺一不可。

### F-009：Ruff 误检查提示词文本

- 现象：验证命令把 `hypothesis_a.txt` 传给 Ruff，产生大量无效 Python 语法错误；Python 测试实际为 `41 passed`。
- 根因：静态检查文件列表未限制为 `.py`。
- 防复发：Ruff 仅接收 Python 文件；提示词使用内容断言和 UTF-8 读取测试验证。

### F-010：前端类型检查在错误目录执行

- 现象：从项目根目录运行 `npm run typecheck`，因根目录没有 `package.json` 而失败；后端测试为 `14 passed`。
- 根因：前端工程位于 `frontend/` 子目录。
- 防复发：所有 npm、Vitest 和 Next.js 命令必须以 `frontend/` 为工作目录。

## 迭代记录

### I-033：统一模型目录与交叉验证实际执行链路收尾

- 日期：2026-07-31
- 修改前已完整阅读：本文件最新条目 `I-032`，并保留 `F-058`、`F-057` 等失败案例与防复发规则。
- 目标：让 API 设置、交叉验证选择器、worker 实际调用、结果页面和历史记录使用同一套供应商/协议/模型身份；不改变评分、采集、商品库、关键词库、利润模块或旧任务结果。
- 修改文件：`backend/application/provider_clients.py`、`backend/application/analysis_runner.py`、`backend/workers/jobs.py`、`backend/application/result_highlights.py`、`backend/api/schemas/jobs.py`、`frontend/app/jobs/[jobId]/page.tsx`、`frontend/components/jobs/cross-review-panel.tsx`、`frontend/components/history/job-table.tsx` 及对应测试。
- 实现：允许任意已启用且通过连接测试的目录供应商作为交叉验证模型；runner 使用 reviewer A/B 身份构造提示词并输出通用结果结构；页面兼容 queued/running/completed/failed 与旧 GPT/DeepSeek 结构；历史列表只显示结果中已持久化的 provider/provider_model，旧任务显示未记录。
- 失败案例：首次回归测试中 resolver 拒绝 DeepSeek 显式选择；runner 仍使用旧参数；前端测试因按钮文案改变失败；历史高亮测试因新增身份字段断言缺失失败。均已通过针对性测试修复。
- 防复发：新增 resolver、runner、历史高亮回归测试；新交叉验证结果禁止依赖 GPT/DeepSeek 固定 key；页面状态判断必须覆盖新状态字段和旧 payload；不得从 request_payload 推断历史实际模型。
- 验证：后端 `210 passed`（1 个既有异步资源警告）；前端交叉验证/结果 UI `41 passed`；`npm.cmd run typecheck` 通过；`npm.cmd run build` 通过；`git diff --check` 通过。
- 回滚：使用本轮提交前的 Git 提交恢复即可，不触碰数据库历史快照；本轮未记录 API Key、Cookie 或 Token。

### I-034：非 GPT 双模型历史高亮兼容

- 日期：2026-07-31
- 修改前已完整阅读：本文件全部 298 行，最新条目 `I-033`。
- 目标：历史任务在双模型 key 不是 `gpt/deepseek` 时仍能显示已持久化的主模型身份和标题；不根据请求参数猜测模型。
- 修改文件：`backend/application/result_highlights.py`、`backend/tests/test_result_highlights.py`。
- 失败案例：首次新增 provider 字段后，既有高亮等值断言失败；随后补齐兼容断言。另发现自定义 reviewer key 无法回退到主模型，新增首个持久化模型回退规则。
- 防复发：优先兼容旧 `gpt` key，其次按 payload 插入顺序读取第一个模型；只读取结果 payload 中的 `provider/provider_model`；旧任务没有身份时返回空值，由前端显示“历史未记录”。
- 验证：`backend/tests/test_result_highlights.py` 通过；前端任务详情/结果工作台 `41 passed`，typecheck 通过；服务健康检查仍为 live/ready 通过。
- 回滚：回退本条提交即可恢复上一版历史高亮逻辑；不删除或重写历史数据。

### I-001：建立 V2.1 评分优化基线与记录制度

- 时间：2026-07-30
- 修改前已阅读：既有 V2.0 设计、link-driven filter 设计与验证记录；本文件为首次建立，无更早的统一历史文件。
- 用户目标：高精准、宁缺毋滥；只依据主品链接推荐高粘性产品；食品必须排除；评分和证据必须可解释，保留 Git 回滚能力。
- 已确认设计：采用“粘性分 + 证据等级 + 可执行状态”三轴决策，替代“单一最终分 + 证据封顶”的表达。
- 本次创建：本文件、`docs/superpowers/specs/2026-07-30-stickiness-scoring-v2.1-design.md`，并在 `CLAUDE.md` 加入强制读取规则。
- 尚未修改：评分逻辑、AI 提示词、数据模型、API、前端或数据库。
- 回滚：删除本文件即可；设计文档提交后记录提交号。

### I-002：V2.1 规格独立审阅与边界修正

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-001`。
- 范围：只修改 V2.1 设计规格与本记录，不改运行代码。
- 修正：E4 才可进入重点开发；E3 为优先测试；`weak_context`/`none` 统一淘汰；补充关系评分上限、证据来源去重、失败证据处理、淘汰记录持久化规则；修正颈枕和普通遮阳帘预期。
- 失败记录：新增 `F-006`，保留初稿歧义及防复发措施。
- 验证：文档占位符、阈值覆盖、术语一致性和 Git diff 检查；不涉及自动化代码测试。
- 回滚基线：`70edc9d`。

### I-003：V2.1 实施计划

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-002`。
- 范围：新增 V2.1 分阶段实施计划；未改运行代码。
- 计划顺序：评分策略和回归矩阵 -> AI 契约与服务门槛 -> 可审计证据 -> 持久化与 Excel/UI -> 全量验证。
- 质量要求：每阶段先写失败测试，测试通过后单独提交；每个失败或基础设施限制必须追加本文件。
- 回滚基线：`bbf1162`。

### I-004：V2.1 组合决策领域策略

- 时间：2026-07-30
- 修改前已阅读：本文最新条目 `I-003`、`docs/superpowers/plans/2026-07-30-stickiness-scoring-v2.1.md` 与 V2.1 设计规格。
- 目标与范围：实现 Task 1 的领域层决策；新增购买方向、产品类型、执行状态、动作和关系评分上限策略，将 V2.1 粘性分、证据等级与执行状态分离；保留 V2.0 五维和旧六位置参数调用的原有封顶兼容行为。
- 涉及文件：`app/domain/pairing_policy.py`、`app/domain/stickiness.py`、`tests/test_stickiness.py`、`tests/test_stickiness_regression.py`、`tests/fixtures/stickiness_v2_cases.json` 和本文。
- 验证：`.venv\Scripts\python.exe -m pytest tests/test_stickiness.py tests/test_stickiness_regression.py -q`，结果 `33 passed`；首次红灯确认缺少 V2.1 购买方向维度及新 gate 字段，随后修正了三个回归夹具的手工合计。
- 已知限制：本轮只完成领域策略；AI 契约、服务层 gate 注入、证据审计、持久化与 UI 透传留待后续任务。未运行真实供应商任务，自动化测试不代表供应商可用性。
- 回滚基线：`ff54d2c`；本轮提交：`feat: add v2.1 pairing decision policy`。

### I-005：V2.1 候选方向服务接入

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-004`。
- 范围：schema、DTO 和假设生成服务接入 V2.1 模型版本、购买方向、产品类型、执行状态和动作字段。
- 验证：先确认 V2.1 schema 缺失导致测试失败；随后 `tests/test_hypothesis_service.py` 结果 `8 passed`。
- 兼容：V2.0 继续使用原五维评分和 weak-context 排序；只有 V2.1 将 weak-context 视作无有效关系。
- 已知限制：高风险分类、提示词更新、市场证据、持久化和前端展示仍待后续阶段。
- 回滚基线：`458348a`。

### I-006：市场证据降级为可审计候选发现

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-005`。
- 范围：标题关键词重合不再生成 E2/E3，只生成最高 E1 的 `candidate_discovery`；记录查询、来源所有者、平台、链接、标题摘录、时间和状态；提示词升级为 V2.1 并要求购买方向、产品类型和风险字段。
- 验证：红灯阶段 3 个测试按预期失败；修改后市场证据测试 `5 passed`，Ruff 通过；假设服务与提示词测试待合并回归。
- 限制：当前搜索服务只能产出候选发现，无法凭空生成 E2-E4；强证据必须来自后续真实兼容、需求或交易数据源。
- 回滚基线：`03814fb`。

### I-007：V2.1 结果、Excel 与工作台贯通

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-006`。
- 范围：结果 payload、Excel、TypeScript 类型和评分卡透传/展示粘性分、购买方向、执行状态、待验证原因、最终动作和证据记录。
- 展示规则：V2.1 不显示证据封顶，改为粘性评分、执行状态和最终动作三列；V2.0 保留旧展示。
- 验证：后端/Excel/证据相关 `19 passed`；前端工作台 `17 passed`；TypeScript 类型检查通过。
- 失败记录：新增 `F-010`，记录 npm 初次在错误目录运行；更正到 `frontend/` 后通过。
- 回滚基线：`ac9eecb`。

### I-008：V2.1 完整自动化回归

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-007`。
- 验证：后端 `288 passed`（1个既有异步清理警告）；前端 `110 passed`；TypeScript 类型检查通过；Next.js生产构建通过。
- 结论：自动化路径通过，69分聚集、反向依赖和标题重合证据问题均有回归保护。
- 真实供应商边界：本轮未运行真实自定义 Anthropic 供应商任务，不宣称真实供应商已验证。
- 详细记录：`docs/verification/2026-07-30-stickiness-scoring-v2.1.md`。
- 回滚基线：`4b4dca8`。

### F-011：Next.js 开发服务器的资源清单被生产构建覆盖

- 现象：工作台初始 HTML 可以返回，但浏览器请求 `/_next/static/...` 的 CSS 和多个 JavaScript chunk 得到 404；页面只显示服务端骨架，API 配置查询不会执行，提交按钮长期显示“提交中”。
- 根因：同一个 `frontend/.next` 目录被 `next build` 写入生产资源清单，而仍在运行的 `next dev` 进程继续引用先前开发资源版本，造成资源版本不一致。该问题与 V2.1 评分逻辑、API Key 或供应商接口无关。
- 影响：工作台、历史记录和 API 设置等依赖浏览器脚本的页面无法交互，容易被误判为模型或后端故障。
- 防复发：运行中的开发服务器不能与同目录的生产构建共享 `.next` 缓存。执行生产构建后，必须重启开发服务器；验收时应检查页面资源无 404、API 设置已加载、模型选择已启用和 `/api/v1/health/ready` 全部为 `ok`。

### I-009：V2.1 运行态恢复与可用性验收

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-008`，并遵守不记录密钥、令牌或用户隐私数据的规则。
- 范围：仅清理可再生的 `frontend/.next` 开发缓存并重启当前项目的 Next.js 开发服务器；未修改业务代码、评分规则、商品/关键词数据库、采集器、利润模块或供应商协议。
- 根因确认：F-011 所述开发缓存被生产构建覆盖，导致资源 404 和前端脚本不运行。
- 验证：`/`、`/history`、`/settings/api` 和已完成任务详情均返回 200 并在浏览器中完成脚本加载；工作台“高级选项”显示 OpenAI、CatToken 和自定义 Anthropic 供应商及模型选择；API 设置显示 4 个已启用服务；`/api/v1/settings/providers` 返回 200；`/api/v1/health/live` 返回 `ok`；`/api/v1/health/ready` 返回数据库、Redis、Worker 均为 `ok`。
- 已知边界：本次没有新建真实供应商任务，不能把上述基础设施和既有已完成任务的验证描述为“每一个供应商模型都已重新实测”。供应商可用性仍以 API 设置中的“测试连接”结果和实际新任务输出为准。
- 回滚：运行态修复不包含源代码变更；V2.1 代码回滚基线仍为 `dff2ec1`。

### F-012：CatToken 最小真实连接连续返回上游不可用

- 现象：2026-07-30 对 CatToken 使用已保存配置执行两次最小真实连接测试，均返回 HTTP 503、`PROVIDER_UNAVAILABLE`，并标记为可重试；同一时段自定义 Anthropic 供应商连接成功。
- 根因边界：应用已正确调用 CatToken 的 OpenAI-compatible Responses 接口，但 CatToken 返回上游服务不可用。当前证据不能把问题归因于 V2.1 评分、前端、数据库、Redis、Worker 或密钥读取。
- 影响：选择 CatToken 提交的新任务当前可能失败；不能因 API 设置中保存过历史成功状态就宣称 CatToken 此刻可用。
- 防复发：最终可用性报告必须区分应用基础设施、自定义 Anthropic、CatToken 和完整任务输出；供应商当前状态以新鲜连接测试为准，连续 503 时应停止重复调用并提示稍后重试或改用已验证供应商。

### I-010：真实供应商最小连接复核

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-009`。
- 范围：使用已保存、未导出的密钥分别执行 CatToken OpenAI-compatible 和自定义 Anthropic 最小连接测试；测试提示仅为 `Reply OK`，未新建选品任务，未修改供应商配置和业务代码。
- 结果：自定义 Anthropic（`claude-fable-5`）返回 HTTP 200、`Connection successful`；CatToken（`gpt-5.6-sol`）首次及一次复测均返回 HTTP 503、`PROVIDER_UNAVAILABLE`。
- 结论边界：当前软件页面、API、数据库、Redis、Worker 和自定义 Anthropic 连接可用；CatToken 当前不可用；尚未用 V2.1 新建并跑完一条真实供应商选品任务，因此不宣称端到端新任务已验收。
- 回滚：本轮只有追加记录，不含业务代码或配置变更；代码回滚基线仍为 `dff2ec1`。

### F-013：V2.1 更新后旧常驻进程仍生成 V2.0 空结果

- 现象：任务 `719ad217-df31-4202-b0f5-340d4ddd2cf3` 在页面显示“任务已完成”，但 Excel 的“辅品方向”工作表为空，API 原始结果为 `model_version=combination_model_v2.0`、`directions_count=0`、`structured_directions=[]`，没有评分、执行状态或决策动作。
- 根因：后端 Uvicorn 与 ARQ Worker 均于 2026-07-29 深夜启动，而 V2.1 代码在 2026-07-30 凌晨至早晨提交；常驻 Python 进程未重启，不会自动加载 V2.1 提示词和服务代码，因此本任务实际由旧版 V2.0 进程执行。
- 伴随风险一：`HypothesisService._to_hypothesis` 当前仍将候选的 `model_version` 固定写为 `combination_model_v2.0`，即使模型返回 V2.1，也可能让结果层和前端误按旧版本解释。
- 伴随风险二：任务执行器只要 Runner 未抛异常就调用 `complete`；对 `directions=[]` 没有结果质量门槛，导致“成功执行但无可用推荐”被标记为“已完成”。
- 影响：该任务不能作为 V2.1 评分、排序或推荐质量的验收样本，也不能据此判断自行车手机包不存在高粘性辅品。
- 防复发：部署或本地更新业务代码后必须重启 API 与 Worker，并在新任务验收中同时断言进程启动时间晚于目标提交、顶层与候选 `model_version` 均为 V2.1、`directions_count` 与结构化方向一致；空候选必须显示明确的“无合格候选/结果不可用于决策”状态，不得以普通完成态掩盖。

### I-011：自行车手机包空报表只读诊断

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-010`。
- 输入：用户提供的 `719ad217-df31-4202-b0f5-340d4ddd2cf3_gpt.xlsx`、任务页面截图与本机任务 API 原始结果。
- 检查结果：工作簿共 4 张表；“商品信息”有 7 项主品字段，“战略判断”只有购买链路类型与主品使用理由，“关键词包”有 5 个主品搜索词，“辅品方向”有效区域为空；四张表均可渲染且无公式错误，排除 Excel 损坏或前端漏显。
- 结论：这是旧 V2.0 进程生成的空候选结果，不是 V2.1 有效结果。截图中的“历史结果暂无结构化方向”与 Excel/API 完全一致。
- 范围与限制：本轮只做诊断并追加记录，未重启服务、未重算历史任务、未修改评分、提示词、数据库、导出或页面逻辑。
- 回滚：仅撤销本条文档提交；业务代码回滚基线仍为 `dff2ec1`。

### I-012：V2.1 运行与结果可信度方案确认

- 时间：2026-07-30
- 修改前已阅读：本文件最新条目 `I-011`。
- 用户确认：接受“完整可靠性闭环”方案，优先解决版本握手、空结果语义、一次遗漏复核、页面/Excel明示和项目专用重启验收，不继续调整评分权重。
- 设计决策：数据库任务状态保持 `queued/running/completed/failed`；业务结果使用 `completed_with_qualified_candidates`、`completed_needs_evidence`、`completed_no_qualified_candidates` 三种结果状态；旧 Worker 必须拒绝 V2.1 新任务；零方向最多复核一次且不得降低门槛。
- 涉及文件：新增 `docs/superpowers/specs/2026-07-30-v2.1-runtime-result-reliability-design.md`，并追加本记录。
- 范围：本轮只固化设计，不修改运行代码、不重启服务、不重算历史任务。
- 验证：检查规格中的版本、状态、复核、历史兼容、测试和回滚要求无占位符或相互矛盾；使用 `git diff --check` 验证文档差异。
- 已知限制：正式实施计划需在用户审阅本规格后单独编写；真实供应商端到端任务尚未重新验收。
- 回滚：撤销本次设计文档提交；业务代码基线仍为 `dff2ec1`。

### I-013：V2.1 运行与结果可信度实施计划

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-012`；同时复核 `docs/superpowers/specs/2026-07-30-v2.1-runtime-result-reliability-design.md`、当前任务创建/Worker/Runner/Excel/前端实现和相关测试。
- 范围：新增 `docs/superpowers/plans/2026-07-30-v2.1-runtime-result-reliability.md`，把已确认设计拆为四个可独立回滚的 TDD 提交；本轮不修改业务代码、不重启服务、不重算历史任务。
- 计划顺序：版本契约与候选版本透传 -> 结果状态、质量门槛与一次遗漏复核 -> Worker 身份及 API/Excel/UI 一致展示 -> 项目专用重启、全量回归与真实供应商验收。
- 验证要求：每阶段先运行失败测试，再做最小实现；Python 阶段同时运行 Ruff，前端阶段运行 Vitest 和 TypeScript；最终执行全量回归、生产构建后安全重启，并完成至少一条自定义 Anthropic V2.1 真实任务。
- 已知限制：计划文档本身不证明软件已修复或真实供应商端到端可用；CatToken 当前 503 继续视为上游状态，恢复后独立验收。`dump.rdb` 为用户未跟踪文件，继续保留且不提交。
- 回滚：撤销本次纯文档计划提交；业务代码基线仍为 `dff2ec1`，可靠性设计提交为 `6de0d00`。

### F-014：运行契约首轮实现的 Runner 参数落位错误

- 现象：运行包含供应商解析相邻测试的定向回归时结果为 `3 failed, 58 passed`；`run_batch` 已引用 `expected_model_version` 但签名未接收该参数，且 Worker 早拒绝测试对普通 `MagicMock` 使用了仅适用于 `AsyncMock` 的 `assert_not_awaited`。
- 根因：相邻的 `run_hypothesis`、`run_judgment`、`run_batch` 签名形状相似，首轮补丁上下文不够精确，参数曾错误落到 judgment 路径；测试替身断言类型也未与实际 mock 类型对齐。
- 影响：仅发生在实现阶段自动化测试，未运行真实任务、未写数据库、未调用采集器或供应商。
- 防复发：修改相邻同形函数时使用函数名限定补丁上下文，并在定向回归中同时覆盖 hypothesis、batch 和 judgment 边界；普通 mock 使用 `assert_not_called`，协程 mock 才使用 awaited 断言。

### F-015：改动文件 Ruff 检查暴露导入格式和既有宽异常边界

- 现象：首次改动文件 Ruff 检查结果为 `5 errors`，其中 3 个 `I001` 为导入格式问题，2 个 `BLE001` 来自供应商可选模型发现和 Worker 顶层持久化错误边界。
- 根因：新增导入尚未机械排序；两个有意保留的宽异常边界此前没有局部说明，文件进入本阶段 Ruff 清单后被报告。
- 影响：静态检查失败但 Python 定向测试已通过；未改变供应商协议或任务数据。
- 防复发：提交前对全部改动 Python 文件运行 Ruff；机械修复导入，对确需宽异常边界的位置添加局部、带原因的 `noqa`，不得全局关闭规则。

### I-014：V2.1 运行版本契约与候选版本透传

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-013`；同时复核 Task 1 实施计划及当前 JobService、Provider resolver、HypothesisService、Runner、Worker 和相关测试。
- 目标与范围：为新建和重试的 hypothesis/batch 任务固化 `combination_model_v2.1` 与请求 revision；Worker 在浏览器、供应商解析、采集和 LLM 前拒绝版本不匹配；严格校验模型顶层版本并让所有候选继承已校验版本；公开实际解析的 provider/model 元数据但不修改供应商请求协议。judgment 与直接排队的历史缺元数据任务保持兼容；未修改评分权重/阈值、数据库、采集器、利润模块、供应商线协议或旧任务结果。
- 涉及文件：`app/core/runtime_contract.py`、`app/core/exceptions/__init__.py`、`app/services/hypothesis_service.py`、`backend/application/job_service.py`、`backend/application/provider_clients.py`、`backend/application/analysis_runner.py`、`backend/workers/jobs.py`、`tests/test_runtime_contract.py`、`tests/test_hypothesis_service.py`、`backend/tests/test_job_service.py`、`backend/tests/test_provider_clients.py`、`backend/tests/test_worker_jobs.py`、`backend/tests/test_analysis_runner.py` 和本文。
- 红灯：`.venv\Scripts\python.exe -m pytest tests/test_runtime_contract.py tests/test_hypothesis_service.py backend/tests/test_job_service.py backend/tests/test_worker_jobs.py backend/tests/test_analysis_runner.py -q`，结果为 `2 errors during collection`，均因 `ModelContractError`/运行契约尚不存在而导入失败，符合预期红灯。
- 中间失败：加入首轮实现并扩展供应商解析相邻测试后，`.venv\Scripts\python.exe -m pytest tests/test_runtime_contract.py tests/test_hypothesis_service.py backend/tests/test_job_service.py backend/tests/test_worker_jobs.py backend/tests/test_analysis_runner.py backend/tests/test_provider_clients.py -q` 结果为 `3 failed, 58 passed`，详见 `F-014`；首次 Ruff 结果为 `5 errors`，详见 `F-015`。
- 绿灯：`.venv\Scripts\python.exe -m pytest tests/test_runtime_contract.py tests/test_hypothesis_service.py backend/tests/test_job_service.py backend/tests/test_worker_jobs.py backend/tests/test_analysis_runner.py -q` 结果为 `49 passed in 2.01s`；相邻验证 `.venv\Scripts\python.exe -m pytest backend/tests/test_provider_clients.py -q` 结果为 `12 passed in 2.23s`。
- 静态与差异验证：`.venv\Scripts\python.exe -m ruff check app/core/runtime_contract.py app/core/exceptions/__init__.py app/services/hypothesis_service.py backend/application/job_service.py backend/application/provider_clients.py backend/application/analysis_runner.py backend/workers/jobs.py tests/test_runtime_contract.py tests/test_hypothesis_service.py backend/tests/test_job_service.py backend/tests/test_provider_clients.py backend/tests/test_worker_jobs.py backend/tests/test_analysis_runner.py` 结果为 `All checks passed!`；`git diff --check` 通过。
- 已知限制：本阶段未运行真实供应商任务，因此不声明端到端供应商可用；结果状态、质量门槛、一次遗漏复核、Worker 身份和页面/Excel 展示属于后续任务。`dump.rdb` 继续保持未跟踪，未修改、未暂存、未提交。
- 回滚基线：`edffd93`；本轮提交信息为 `fix: enforce v2.1 runtime contract`。

### F-016：空字符串运行契约被误判为历史缺字段

- 现象：规格复核发现 `expected_model_version=""` 在 Worker 与 `HypothesisService` 中都因 Python 真值判断而绕过契约校验；定向红灯结果为 `2 failed, 22 deselected`，服务未抛契约异常，Worker 继续进入外部初始化路径并最终落为 `INTERNAL_ERROR`，而不是提前返回 `MODEL_CONTRACT_MISMATCH`。
- 根因：契约兼容条件使用 `if expected_model_version`，把“字段存在但值为空”与“历史字段缺失/值为 None”合并为同一分支；规格只允许后者走历史兼容路径。
- 影响：构造或损坏的空字符串任务元数据可能绕过 Worker 前置握手；显式传入空期望版本时，模型输出校验也可能被跳过。自动化复现未调用真实供应商、未修改数据库或旧任务。
- 防复发：可选契约字段必须用 `is not None` 判断是否存在；缺失/None 与空字符串分别建立回归测试，Worker 回归同时断言浏览器和供应商 resolver 未调用。

### I-015：收紧空字符串运行契约校验

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-014`，并复核 `F-014`、`F-015`、Task 1 提交 `b8a6cfb` 及 Worker/假设服务当前契约判断。
- 目标与范围：仅修正 `expected_model_version` 的存在性语义；字段缺失或 `None` 继续兼容历史任务，字段存在但为空或任何其他不匹配值统一抛出 `MODEL_CONTRACT_MISMATCH`。未修改评分、数据库、采集器、利润模块、供应商协议、任务创建元数据或历史结果。
- 涉及文件：`backend/workers/jobs.py`、`app/services/hypothesis_service.py`、`backend/tests/test_worker_jobs.py`、`tests/test_hypothesis_service.py` 和本文。
- 红灯：`.venv\Scripts\python.exe -m pytest backend/tests/test_worker_jobs.py tests/test_hypothesis_service.py -k present_empty -q`，结果 `2 failed, 22 deselected`；Worker 得到 `INTERNAL_ERROR` 且服务未抛 `ModelContractError`，准确复现 `F-016`。
- 绿灯：同一命令修正后结果 `2 passed, 22 deselected in 1.13s`；Task 1 定向回归 `.venv\Scripts\python.exe -m pytest tests/test_runtime_contract.py tests/test_hypothesis_service.py backend/tests/test_job_service.py backend/tests/test_worker_jobs.py backend/tests/test_analysis_runner.py -q` 结果 `51 passed in 2.09s`。
- 静态与差异验证：`.venv\Scripts\python.exe -m ruff check app/services/hypothesis_service.py backend/workers/jobs.py tests/test_hypothesis_service.py backend/tests/test_worker_jobs.py` 结果 `All checks passed!`；`git diff --check` 通过。
- 已知限制：本次未运行真实供应商任务，不声明端到端供应商可用；`dump.rdb` 保持未跟踪且不修改、不暂存、不提交。
- 回滚基线：`b8a6cfb`；本轮使用独立修复提交 `fix: reject empty runtime contract versions`。

### F-017：Task 2 质量闭环首轮实现遗漏严格一致性和落盘前门槛

- 现象：新增 Task 2 规格回归时出现 `10 failed, 35 passed`；未知 `execution_status`、不一致 `rejection_summary`、带非法拒绝码的 pass 候选以及缺少完整审计字段的零方向结果仍可通过；Runner 未透传 provider/model，未在 JSON/Excel 写入前调用质量验证器，存储 JSON 也缺少结果状态与审计字段。
- 根因：首轮实现只覆盖了最小状态统计和 Worker 完成前防御性检查，未把规格要求的字段一致性、所有生命周期拒绝关系和文件落盘边界落实到 Runner/Storage。
- 影响：不完整或不一致的 V2.1 结果可能先生成看似可用的文件，且无法审计实际供应商身份；Worker 之后虽可拒绝，但会留下伪完成 artifact。
- 防复发：结果质量验证必须在 Runner 序列化后、任何 JSON/Excel 写入前执行；验证器必须校验状态枚举、计数和拒绝摘要、零方向四字段及 pass 禁止关系/食品/拒绝码；存储层必须保留状态、审计和 provider/model 字段。

### F-018：Task 2 Ruff 检查发现质量字段循环变量遮蔽导入

- 现象：Task 2 定向测试 `105 passed`，但针对改动文件的 Ruff 报告 `F402 Import field shadowed by loop variable`。
- 根因：`_apply_quality_fields` 使用 `field` 作为循环变量，而模块已有 `dataclasses.field` 导入。
- 影响：静态检查失败；运行时当前无功能错误，但增加维护歧义。
- 防复发：新增字段复制循环使用不与模块级导入重名的变量名，并在提交前对所有改动 Python 文件运行 Ruff。

### F-019：V2.1 版本说明回归夹具使用零方向导致无排序文案

- 现象：新增版本说明测试用空方向 DTO，`score_reason` 按既有约定为空，测试错误失败。
- 根因：测试没有提供可排序方向，却断言只有有方向时才生成的排序说明。
- 影响：仅测试夹具错误，未调用供应商、未写任务或改变业务逻辑。
- 防复发：版本说明回归必须使用至少一个方向；零方向只验证结果状态、审计字段和明确消息。

### I-016：V2.1 结果状态、质量门槛与一次遗漏复核

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新失败条目为 `F-019`；同时复核 Task 2 计划、运行与结果可信度设计规格及 Task 1 提交。
- 目标与范围：为 V2.1 假设结果加入三态业务状态、pass/hold/reject 统计、拒绝摘要、一次零方向遗漏复核、provider/model 与审计字段；在 Runner 写入 JSON/Excel 前及 Worker 完成前执行同一质量验证器；BundleResultStore 保存结果质量与审计字段。保留 V2.0 历史兼容路径，不修改评分权重/门槛、商品/关键词数据库、采集器、利润模块或供应商协议。
- 涉及文件：`app/domain/dto/__init__.py`、`app/infrastructure/llm/prompts/hypothesis_audit.txt`、`app/services/hypothesis_service.py`、`backend/application/result_quality.py`、`backend/application/analysis_runner.py`、`backend/workers/jobs.py`、`app/infrastructure/storage/__init__.py`、对应后端/服务/存储测试及本文。
- 红灯与失败：首轮质量闭环测试结果 `10 failed, 35 passed`，详见 `F-017`；Ruff 首次结果 1 个 F402，详见 `F-018`；版本说明回归夹具误用零方向导致 1 个测试失败，详见 `F-019`。这些失败均未调用真实供应商或修改历史任务。
- 绿灯：Task 2 定向回归（假设服务、质量验证、Runner、Worker、评分回归、存储）`108 passed`；改动 Python 文件 Ruff `All checks passed!`；`git diff --check` 通过。
- 已知限制：尚未运行真实 V2.1 自定义 Anthropic 完整选品任务；自动化通过不代表真实供应商可用。双模型副模型的实际 provider/model 仍依赖后续 Worker 身份与 readiness 阶段补充运行态验收。
- 回滚基线：Task 1 提交 `489e4fd`；本阶段提交信息为 `fix: validate v2.1 result quality`。

### F-020：Task 2 质量验证器边界输入可绕过或泄漏内部异常

- 现象：规格复核新增损坏方向、双模型包装、pass 严格状态和结果文案一致性测试后，定向红灯结果为 `14 failed, 1 passed, 37 deselected`；`structured_directions=[None]` 泄漏 `AttributeError`，`rejection_codes=None` 泄漏 `TypeError`，字符串拒绝码、缺失或多余模型包装、未知商品类型、待验证食品状态、硬拒绝码和矛盾结果文案仍可能通过。
- 根因：验证器在字段形状校验前调用候选 `.get()` 或遍历拒绝码；双模型分支使用宽松的 `payload.get("models")` 和任意字典值遍历；pass 规则只排除部分非法值；结果文案只校验非空，没有与服务器计算出的标准文案逐字一致。
- 影响：损坏的 V2.1 结果可能被映射为 `INTERNAL_ERROR` 或错误完成，双模型结果可能遗漏一侧校验，未验证或带硬拒绝原因的候选可能被错误标记为可执行。
- 防复发：所有外部结果先做容器和字段类型校验，再执行汇总；存在 `models` 时必须严格等于 `gpt/deepseek` 两侧字典；pass 必须同时满足已验证非食品、食品过滤允许且拒绝码为空；`result_message` 必须与服务器根据状态计算的标准文案完全一致；Worker 必须把所有这类损坏载荷稳定落为 `RESULT_QUALITY_INVALID`。

### I-017：收紧 V2.1 结果质量边界

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-020`；同时复核 Task 2 实施计划、运行与结果可信度设计规格及提交 `0f24ee4`。
- 目标与范围：只修正 V2.1 结果质量验证器的输入形状、双模型包装、pass 状态和标准文案一致性；新增对应质量验证与 Worker 错误映射回归。未修改评分权重/门槛、供应商协议、数据库、采集器、利润模块或历史 V2.0 结果。
- 涉及文件：`backend/application/result_quality.py`、`backend/tests/test_result_quality.py`、`backend/tests/test_worker_jobs.py` 和本文。
- 红灯：聚焦命令结果 `14 failed, 1 passed, 37 deselected`，详见 `F-020`。
- 绿灯：同一聚焦命令结果 `15 passed, 37 deselected`；Task 2 完整回归结果 `124 passed`；改动 Python 文件 Ruff 为 `All checks passed!`；`git diff --check` 通过，仅有 Windows 行尾转换提示。
- 已知限制：本轮未运行真实自定义 Anthropic 或 CatToken 完整任务，不声明真实供应商端到端可用；`dump.rdb` 保持未跟踪且不修改、不暂存、不提交。
- 回滚基线：`0f24ee4`；本轮使用独立纠正提交 `fix: harden v2.1 result validation`。

### F-021：独立审查发现决策字段与批量包装仍可泄漏内部错误

- 现象：在 `5e7eb13` 后追加非字符串决策字段、字符串六维分数和损坏 batch 包装测试，聚焦红灯结果为 `6 failed, 9 passed, 49 deselected`；列表型购买方向/主关系泄漏 `TypeError`，列表型证据/动作与字符串分数可通过，`results=None` 的 batch 被 Worker 记录为 `INTERNAL_ERROR`。
- 根因：候选形状检查只覆盖候选字典和拒绝码，没有在汇总与集合成员判断前验证六个决策字段和六维分数值类型；Worker 在 batch 分支先对未经验证的顶层载荷调用 `.get()` 并直接迭代 `results`。
- 影响：部分损坏的供应商结构仍无法稳定归类为结果质量错误，或可能被错误保存为完成结果。
- 防复发：所有必需决策字段必须为非空字符串，六维分数必须为有限数值且排除布尔值；batch 顶层必须为字典、`results` 必须为列表，检查失败统一抛 `ResultQualityError`；保留有效双模型、顶层 primary 和三类标准文案的直接正反回归。

### I-018：补齐候选类型与 batch 质量校验

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-021`；同时复核独立代码审查结论和提交 `5e7eb13`。
- 目标与范围：在结果汇总前验证六个决策字段和六维分数类型；新增统一 batch 载荷验证并让 Worker 使用；补充有效双模型、损坏顶层 primary 和三类标准文案回归。未修改评分权重/门槛、供应商协议、数据库、采集器、利润模块或历史结果。
- 涉及文件：`backend/application/result_quality.py`、`backend/workers/jobs.py`、`backend/tests/test_result_quality.py`、`backend/tests/test_worker_jobs.py` 和本文。
- 红灯：聚焦回归 `6 failed, 9 passed, 49 deselected`，详见 `F-021`。
- 绿灯：同一聚焦回归 `15 passed, 49 deselected`；Task 2 完整回归 `136 passed`；改动 Python 文件 Ruff 为 `All checks passed!`；`git diff --check` 通过，仅有 Windows 行尾转换提示。
- 已知限制：本轮仍未运行真实自定义 Anthropic 或 CatToken 完整任务，不声明真实供应商端到端可用；双模型副模型 provider/model 身份属于后续运行身份任务；`dump.rdb` 保持未跟踪且不修改、不暂存、不提交。
- 回滚基线：`5e7eb13`；本轮使用独立纠正提交 `fix: reject malformed v2.1 batch results`。

### F-022：PowerShell 动态路由目录被当作通配符读取

- 现象：Task 3 只读检查使用 `Get-Content` 读取 `frontend/app/jobs/[jobId]/page.tsx` 时命令失败；PowerShell 将方括号解释为通配符表达式，未正确定位文件。
- 根因：动态路由目录包含 `[` 与 `]`，却使用普通 `-Path` 语义而非 `-LiteralPath`。
- 影响：仅只读检查失败，未修改业务文件、运行进程或历史结果。
- 防复发：PowerShell 读取、复制或检查包含方括号的 Next.js 动态路由路径时必须使用 `-LiteralPath`；不得通过转义不明确的拼接命令处理该路径。

### F-023：Task 3 首轮测试确认运行身份与可靠性展示缺失

- 现象：后端定向红灯在收集阶段出现 2 个导入错误，缺少 `backend.workers.runtime_identity` 与 `check_worker_identity`；前端定向红灯为 `4 failed, 28 passed`，缺少固定可靠性摘要、V2.1 零候选/hold 文案和 V2.0 历史空结果专用文案。
- 根因：Task 2 只建立了结果载荷字段与完成前门禁，尚未实现 Task 3 的 Worker TTL 身份、readiness 契约比较、Excel 摘要和页面展示。
- 影响：自动化准确暴露计划中的未实现功能；未启动或调用真实供应商，未修改历史任务结果。
- 防复发：运行身份、API 健康检查、Excel 和页面必须分别建立定向回归；页面不得根据评分反推业务状态，只能展示持久化的结果字段。

### F-024：FastAPI 无法从字典与 JSONResponse 联合类型生成响应模型

- 现象：Task 3 首轮后端绿灯运行在收集阶段失败，FastAPI 报告 `dict[str, str] | JSONResponse` 不是合法的 Pydantic response field；前端定向测试同期为 `32 passed`。
- 根因：readiness 为支持 200 字典与 503 `JSONResponse` 标注了联合返回类型，FastAPI 默认尝试从该注解生成响应模型。
- 影响：应用路由导入失败，尚未进入健康检查逻辑；自动化未调用真实服务或供应商。
- 防复发：返回多种 Starlette Response/字典形态的 FastAPI 路由必须显式设置 `response_model=None`，或使用框架支持的统一响应类型；新增路由至少执行一次应用导入测试。

### F-025：Task 3 首轮 Ruff 暴露健康探针和 WorkerSettings 静态边界

- 现象：后端定向测试 `16 passed`、前端定向测试 `32 passed`、TypeScript 检查通过后，改动文件 Ruff 报告 9 项错误：导入格式、健康探针宽异常、一个 `Depends` 默认值、重复分支和 WorkerSettings 可变类属性。
- 根因：健康探针的故障降级边界与 WorkerSettings 的框架声明此前没有局部静态说明；新增代码还包含可机械整理的格式和分支问题。
- 影响：运行测试通过但静态检查失败；未调用供应商或修改历史任务。
- 防复发：健康探针确需捕获所有依赖失败时使用带原因的局部 `noqa`；ARQ 类级配置使用 `ClassVar`；每个 Python 阶段在提交前同时运行定向测试和 Ruff。

### F-026：Task 3 规格复核发现结果身份、历史展示和可执行门禁不完整

- 现象：双模型单任务与批量结果把 primary 的 provider/model 同时写入 DeepSeek secondary；V2.0 历史结果缺少持久化身份与计数时，页面用请求配置冒充“实际模型”并把缺失计数显示为 0；Excel 只要存在 pass 动作就标记可采购，未同时要求顶层 `completed_with_qualified_candidates`；readiness 未逐一确定性覆盖数据库、Redis、Worker 不可用的 503，WorkerSettings 测试也未固定 10 秒身份刷新配置。
- 根因：Runner 只接收 primary 解析身份，secondary resolver 只返回裸 client；前端把请求配置当作结果身份回退值；Excel 的 actionable 判定缺少顶层状态条件；运行健康测试侧重字段存在，没有穷举稳定配置行为。
- 红灯证据：后端规格纠正回归为 `5 failed, 64 passed`，分别命中 secondary 身份参数/resolver 缺失、Worker 未传递 secondary 身份和 Excel 顶层状态矛盾；前端详情回归为 `2 failed, 12 passed`，命中历史身份补造和缺失计数显示为 0。readiness 三种 503 与 10 秒 cron 新测试直接通过，说明生产配置已满足、缺口仅在确定性覆盖。
- 影响：双模型结果可能错误归因供应商，历史快照看起来像保存过实际运行身份和精确计数，矛盾载荷的 Excel 可能错误提示进入采购测试；健康配置未来退化时缺少精确回归定位。
- 防复发：provider resolver 必须以结构化结果公开 primary/secondary 的 client、provider、model；结果摘要只展示持久化实际身份，缺失字段明确标为“历史未记录/未记录”；Excel actionable 必须同时满足合格顶层状态和合法 pass 动作；readiness 与 cron 使用确定性参数测试覆盖稳定外部行为。

### I-019：V2.1 Worker 身份、可靠性摘要与规格纠正

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-025`；同时复核 V2.1 运行与结果可信度设计、实施计划、provider resolver、Runner、Worker、健康检查、Excel 与前端任务详情实现。
- 目标与范围：完成 Task 3 的 Worker TTL 身份、readiness 契约、Excel 结果摘要、V2.1/V2.0 页面语义，并修正规格复核发现的双模型实际身份、历史缺失字段、Excel 顶层状态门禁和确定性健康配置测试。未修改评分权重/阈值、数据库或关键词存储、采集器、利润模块、供应商请求协议和 V2.0 历史快照。
- 涉及文件：`backend/workers/runtime_identity.py`、`backend/workers/settings.py`、`backend/api/routes/health.py`、`backend/application/provider_clients.py`、`backend/application/analysis_runner.py`、`backend/workers/jobs.py`、`app/infrastructure/storage/excel_exporter.py`、`frontend/components/jobs/result-reliability-summary.tsx`、`frontend/components/jobs/result-analysis-module.tsx`、`frontend/app/jobs/[jobId]/page.tsx`、`frontend/lib/api/types.ts`、对应后端/前端/Excel 测试及本文。
- 红灯与中间失败：Task 3 首轮缺失行为、FastAPI 响应模型和 Ruff 失败分别见 `F-023` 至 `F-025`；规格纠正红灯为后端 `5 failed, 64 passed`、前端 `2 failed, 12 passed`，详见 `F-026`。这些自动化失败均未调用真实供应商、未修改历史任务。
- 绿灯：用户指定后端命令 `62 passed`（伴随 1 个既有异步连接清理警告）；用户指定前端三文件回归 `51 passed`；相邻 resolver/Worker/Runner/readiness/Excel 回归 `69 passed`（伴随 1 个既有异步连接清理警告）；前端 TypeScript 检查通过；全部改动 Python 文件 Ruff 为 `All checks passed!`；`git diff --check` 通过，仅有 Windows 行尾转换提示。
- 已知限制：本阶段未启动或运行真实自定义 Anthropic、DeepSeek 或 CatToken 任务，不声明真实供应商或端到端可用性；真实运行验收属于 Task 4。`dump.rdb` 保持未跟踪且不修改、不暂存、不提交。
- 回滚基线：`5c29a2e`；规格纠正复核已闭合，本轮提交信息为 `feat: expose v2.1 result reliability`。

### F-027：Windows PowerShell 不支持 String.Contains 比较模式重载

- 现象：Task 4 只读进程检查使用 `CommandLine.Contains(path, StringComparison)` 时，对枚举到的每个进程重复报告“Cannot find an overload for Contains and the argument count: 2”。
- 根因：当前环境为 Windows PowerShell/.NET Framework，`System.String.Contains(string, StringComparison)` 重载不可用。
- 影响：只读检查未得到进程列表；未停止任何进程、未删除缓存、未调用供应商。
- 防复发：PowerShell 项目路径与命令标记比较统一使用兼容的 `IndexOf(value, StringComparison) -ge 0`，并加入脚本文本回归。

### F-028：Task 4 首轮安全重启测试确认旧启动器越界

- 现象：`tests/test_restart_script.py` 首次运行结果 `4 failed`；项目专用脚本不存在，旧 `启动.ps1` 仍全局停止所有 Python 进程，并读取配置文件内容。
- 根因：旧启动器为早期手工开发流程设计，没有项目绝对路径进程过滤、缓存路径校验、隐藏日志或运行握手。
- 影响：失败发生在静态测试阶段，未执行旧启动器、未停止进程、未删除文件或调用供应商。
- 防复发：启动器只委托项目专用脚本；脚本必须用绝对路径与明确命令标记筛选进程，验证 `.next` 目标后再清理，不读取或输出配置内容，并提供 `CheckOnly`。

### F-029：Windows PowerShell 5.1 不支持空值合并运算符

- 现象：项目专用脚本首次 `-CheckOnly` 在解析阶段报告 `Unexpected token '??'`，未进入任何运行逻辑。
- 根因：`??` 是 PowerShell 7 语法，当前启动入口使用 Windows PowerShell 5.1。
- 影响：只读检查没有执行；未停止进程、未删除缓存、未启动服务或调用供应商。
- 防复发：项目启动脚本只使用 Windows PowerShell 5.1 兼容语法；空值显示使用显式 `if` 分支，并在真实 `powershell.exe -File ... -CheckOnly` 下验证解析和执行。

### F-030：重启脚本文本测试错误绑定参数顺序

- 现象：实现使用 `Stop-Process -Id ... -Force` 后，测试仍因查找连续文本 `Stop-Process -Force` 而 `1 failed, 3 passed`。
- 根因：测试把 PowerShell 命名参数的书写顺序当成安全行为，未按“明确 PID + Force”分别验证。
- 影响：仅测试夹具错误；脚本未运行变更模式，未停止进程或删除缓存。
- 防复发：静态脚本测试按行为所需标记分开断言，不绑定无语义的参数排列。

### F-031：全量 Ruff 存在历史基线问题

- 现象：全量命令 `.venv\Scripts\python.exe -m ruff check app backend tests` 报告 88 项错误；其中 1 项为本轮新增 `tests/test_restart_script.py` 的空行格式，另 87 项位于既有采集器、LLM、API、迁移与测试文件。
- 根因：项目尚未建立零告警 Ruff 基线；本轮新增文件首次进入全量检查，暴露自身格式问题。
- 影响：全量静态检查当前不能作为通过门槛；未停止进程、未删除缓存、未调用供应商，且未改动既有 87 项无关代码。
- 防复发：本轮先修复新增文件并对所有本轮 Python 改动文件执行 Ruff；后续单独规划既有基线清理，禁止在运行可靠性任务中顺手批量重构。

### F-032：受限会话无法写入原 F 盘仓库

- 现象：会话权限切换后，原项目 `F:` 盘只读；首次本地克隆又触发 Git dubious ownership，后续在不同进程用户下读取镜像仓库也触发相同保护。
- 根因：当前工具进程在 `Administrator` 与受限沙箱用户之间切换，仓库所有者 SID 与执行用户不一致，同时允许写入的根目录仅为 `C:\Users\Administrator\Documents\组合品`。
- 影响：Task 4 暂时不能原地写回或提交到 `F:` 盘；未修改原仓库已提交历史，未复制或触碰 `dump.rdb`。
- 防复发：在允许写入的工作区建立基于 `2295c7f` 的本地副本，只复制 Task 4 文件；Git 操作使用单命令 `safe.directory=*`，不改全局配置。权限恢复后以提交方式同步，禁止手工覆盖原仓库。

### F-033：受限 PowerShell 执行策略拦截 npm.ps1

- 现象：镜像工作区首次并行执行前端测试与类型检查时，PowerShell 报告禁止运行 `C:\Program Files\nodejs\npm.ps1`，聚合命令以非零退出且未可靠展示其他并行项结果。
- 根因：当前 PowerShell 执行策略禁止脚本入口，命令解析优先选择了 `npm.ps1` 而非可执行的 `npm.cmd`。
- 影响：本轮没有得到该次并行前端验证结论；未修改代码、进程、缓存或供应商配置。
- 防复发：Windows 自动化统一显式调用 `npm.cmd`，Python、前端测试与类型检查分别获取完整退出码，不用一个失败的并行聚合替代独立证据。

### F-034：跨盘 node_modules 联接导致 Next.js 构建路径失效

- 现象：镜像工作区 `npm.cmd run build` 在编译阶段无法解析 `./F:/.../node_modules/next/dist/client/next.js` 与 `app-next.js`。
- 根因：镜像位于 `C:`，`frontend/node_modules` Junction 指向 `F:`；Next/Webpack 将解析后的跨盘绝对路径错误当作相对模块路径拼接。
- 影响：本次镜像生产构建失败；前端全量测试 `116 passed` 和 TypeScript 检查已独立通过，原项目依赖与运行进程未修改。
- 防复发：Next.js 构建不得使用跨盘 `node_modules` 联接；移除镜像联接和失败构建生成的 `.next` 后，把现有依赖机械复制到同盘镜像再执行构建。

### F-035：PowerShell 未移除 Junction 导致依赖复制回源目录

- 现象：`Remove-Item` 删除镜像 `node_modules` Junction 时抛出空引用，但命令因非终止错误继续；后续 `Copy-Item` 把源依赖经仍存在的 Junction 复制回自身，生成 `F:\...\frontend\node_modules\node_modules/...` 递归目录并大量报路径不存在，错误命令仍返回 0。
- 根因：Windows PowerShell 对该 Junction 的 `Remove-Item` 失败，组合命令没有为每一步设置终止式检查，也没有在复制前重新断言目标已从联接变为不存在。
- 影响：本次生成了可再生的嵌套依赖目录；未改源码、配置、数据库或 `dump.rdb`。随后使用经过绝对路径与父目录校验的 .NET 目录删除清理了嵌套目录和镜像 Junction，并确认原 `next` 包仍存在。
- 防复发：禁止向刚删除的 Junction 路径直接复制；每个破坏性步骤独立执行并验证后置条件。镜像依赖改用 `npm ci --offline` 在目标盘重新安装，不再复制现有 `node_modules`。

### F-036：重启握手可在静态资源为空或版本字段错误时误通过

- 现象：代码审查新增运行握手断言后，脚本测试为 `1 failed, 3 passed`；脚本未显式检查 `api_model_version/worker_model_version`，静态资源正则零匹配时也会直接返回成功。
- 根因：首轮实现只依赖 `contract_match=ok`，且静态资源循环把空集合视为“没有失败项”，没有证明页面实际引用可加载的 Next.js 资源。
- 影响：极端损坏响应可能被误报为重启验收成功；失败只在静态测试中复现，未启动服务或调用供应商。
- 防复发：运行握手同时断言 API 与 Worker 都为 `combination_model_v2.1`；首页至少发现一个 `/_next/static/` 资源并逐项返回 200；供应商列表至少有一项。

### F-037：受限子 PowerShell 无权查询 Win32_Process

- 现象：镜像脚本通过 `powershell.exe -File ... -CheckOnly` 执行时只返回“拒绝访问”；跟踪定位到 `Get-CimInstance Win32_Process`。外层命令用户为 `Administrator` 且可查询 467 个进程，子 PowerShell 用户为 `CodexSandboxOffline` 并稳定复现 CIM 拒绝。
- 根因：当前工具对显式启动的子 PowerShell 施加受限用户上下文，不是脚本进程过滤逻辑或普通桌面启动权限变化。
- 影响：该子进程方式不能作为当前镜像的 `CheckOnly` 验收通道；未停止任何进程或删除缓存。
- 防复发：镜像验证在当前管理员 PowerShell 内使用进程级执行策略 Bypass 调用脚本；最终仍需在原项目正常桌面用户上下文执行项目专用重启。

### F-038：PowerShell 5.1 的 URI 相对路径回退计算错误

- 现象：手工逐阶段检查发现镜像 `.next` 相对路径被计算为 `web-platform-v2.1-work\frontend\.next`，而不是 `frontend\.next`；新增回退测试为 `1 failed, 3 passed`。
- 根因：Windows PowerShell 5.1 缺少 `Path.GetRelativePath`，原 URI 回退把本地 Windows 根目录构造为不可靠 URI。
- 影响：安全缓存校验会拒绝正确的镜像 `.next`，但不会误删目录；未执行删除。
- 防复发：保留可用时的 `Path.GetRelativePath`，旧运行时改为先验证绝对路径前缀，再用 `Substring` 计算相对路径；禁止 URI 路径回退。

### F-039：重启安全审查发现联接缓存、路径前缀和子进程权限风险

- 现象：新增安全断言后脚本测试为 `3 failed, 1 passed`：未拒绝 `.next` reparse point，项目进程只做路径裸子串匹配，启动器仍通过新 PowerShell 子进程调用脚本。
- 根因：首轮安全边界只校验解析后的路径值，没有检查路径对象类型；进程过滤未固定项目根目录边界；启动器沿用了旧的子进程调用方式。
- 影响：构造的联接缓存可能扩大删除范围，同名前缀兄弟目录可能误匹配；受限工具环境中的子 PowerShell 会失去 CIM 权限。失败只在审查测试中触发，未执行重启或删除。
- 防复发：缓存必须是普通目录且拒绝 reparse point；项目路径同时通过 `IndexOf` 和带边界的转义正则匹配；启动器在当前已授权 PowerShell 进程内直接调用项目脚本。

### F-040：PowerShell 诊断循环后直接接管道产生解析错误

- 现象：两次只读端口/子进程诊断把 `foreach { ... }` 后直接连接 `| Format-List`，PowerShell 报告 `An empty pipe element is not allowed`。
- 根因：语句块不能按该写法直接作为管道输入，诊断命令缺少中间结果集合。
- 影响：只读诊断未执行；未停止进程或修改文件。
- 防复发：复杂 PowerShell 循环先收集到显式数组，再单独输出或格式化，避免把控制语句当作管道表达式。

### F-041：虚拟环境入口的全局 Python 子进程可能逃逸重启

- 现象：端口与父进程链显示，项目 Venv API PID `34824` 的子进程 `43796` 才实际监听 8000；Worker PID `32392` 也有全局 Python 子进程 `35508`。Next 根进程同样派生实际监听 3000 的子进程。新增进程树测试为 `1 failed, 3 passed`。
- 根因：Windows Venv/启动链会派生可执行路径不含项目根目录的子进程，首轮脚本只停止直接满足路径与标记的根进程。
- 影响：重启后旧子进程可能继续占用端口或执行旧 Worker 代码，导致新进程启动失败或再次产生版本漂移。
- 防复发：仍以“项目绝对路径 + 明确启动标记”的根进程确定归属，再递归纳入其 Python/Node/PowerShell 子进程，按子进程优先顺序停止，并在启动前确认所有目标 PID 已退出。

### F-042：真实 Next.js 根进程不含连续 next dev 文本

- 现象：新进程树算法对原实例演练时识别 API/Worker 根与子进程共 4 个，但未识别 Next；实际根命令为 `...\next\dist\bin\next" dev`，新增真实标记测试为 `1 failed, 3 passed`。
- 根因：首轮标记只检查连续字符串 `next dev`，而 npm 启动后的 Node 命令在 `next` 与 `dev` 之间包含完整脚本路径和引号。
- 影响：重启可能留下旧 Next 进程继续占用 3000；演练为只读，未停止进程。
- 防复发：保留人工启动命令标记 `next dev`，同时加入真实 Node CLI 路径标记 `next\dist\bin\next`，再由进程树纳入实际监听子进程。

### F-043：页面握手命令误用 PowerShell 只读 HOME 变量

- 现象：重启后的独立握手已得到 API/Worker V2.1 契约，但命令使用 `$home` 保存首页响应；PowerShell 变量不区分大小写，将其视为只读 `$HOME` 并报 `Cannot overwrite variable HOME`，导致首页状态和静态资源计数无效。
- 根因：诊断变量名与系统选项冲突，且该赋值为非终止错误，后续仍输出了混合有效/无效字段。
- 影响：该次输出只能证明后端 live/readiness，不能证明首页或静态资源；未修改应用状态或配置。
- 防复发：所有脚本和诊断使用任务专用变量名（如 `$frontendHomeResponse`），设置 `$ErrorActionPreference='Stop'`，任何采集失败后不继续输出组合结论。

### F-044：浏览器运行环境不支持 networkidle 等待状态

- 现象：真实任务页面首次浏览器验收调用 `waitForLoadState({state: "networkidle"})` 时，浏览器控制接口明确返回不支持该状态；页面本身已成功打开。
- 根因：当前内置浏览器控制接口只支持其文档列出的有限加载状态，实际后端未实现 `networkidle`。
- 影响：首次页面等待命令失败，但未点击、提交或修改页面数据，也未调用供应商；改用受支持的 `load` 后完成 DOM、图片、资源和控制台验收。
- 防复发：本地页面验收优先使用受支持的 `load`/`domcontentloaded`，随后以明确 DOM 文案、图片自然尺寸、静态资源和控制台错误作为完成信号，不假设完整 Playwright API 均可用。

### F-045：Task 4 单次 CatToken 复核仍返回 503

- 现象：完成真实自定义 Anthropic V2.1 任务后，按验收计划对 CatToken 执行一次最小连接测试，仍返回 HTTP 503、`PROVIDER_UNAVAILABLE`、`retryable=true`。
- 根因边界：应用能够读取已保存配置并进入 CatToken 连接测试，但 CatToken 上游当前不可用；没有证据指向 V2.1 评分、Worker 契约、数据库、Redis 或前端。
- 影响：CatToken 当前不能作为可用供应商验收，也未创建 CatToken 选品任务；自定义 Anthropic 的完整任务与四端结果一致性不受影响。
- 防复发：连续上游 503 时停止重试，最终报告必须明确区分供应商状态；CatToken 恢复后先做一次连接测试，通过后才创建一条完整验收任务。

### F-046：TypeScript 与 Next.js 构建并行争用 `.next`

- 现象：最终验证首次并行执行 `npm.cmd run typecheck` 和 `npm.cmd run build`，TypeScript 报告多个 `.next/types/...` 文件不存在，构建也随聚合命令中断；随后串行执行生产构建和类型检查均通过。
- 根因：`next build` 会清理并重新生成 `.next`，TypeScript 同时按 `tsconfig.json` 读取 `.next/types/**/*.ts`，因此读到半更新目录。
- 影响：只影响该次验证命令，没有改动源码、任务数据或供应商配置；串行生产构建完整生成 7 个路由，随后类型检查退出码为 0。
- 防复发：任何读取 `.next` 的 TypeScript 检查不得与 `next build` 并行；统一先构建、再类型检查，构建后重启开发服务器并验证静态资源。

### F-047：中文镜像路径下的重定向触发 pytest 子进程 GBK 警告

- 现象：最终 Python 全量测试输出重定向到日志时结果为 `389 passed, 9 warnings`；其中 8 条来自子进程读取线程用 GBK 解码包含中文路径的 UTF-8 输出，另 1 条为既有异步连接清理警告。
- 根因：Windows 默认子进程文本编码为 GBK，而测试中的子进程输出包含 UTF-8 中文路径；日志重定向使该边界稳定暴露。
- 影响：测试退出码为 0，389 项均通过；警告不代表业务结果或运行进程失败，但会污染验证信号。
- 防复发：中文工作区运行 Python 回归时显式设置 `PYTHONUTF8=1`，并保留既有异步清理警告的单独记录；不得把警告当作通过结论而忽略。

### F-048：页面 load 事件早于动态任务数据渲染

- 现象：最终重启后浏览器先等待 `load`，随后立即读取 `main.innerText`，六项结果断言暂时均为 false；紧接着取得的 DOM 快照已完整显示任务 ID、V2.1、实际模型及 `1/1/3` 结果计数，控制台无错误。
- 根因：Next.js 页面外壳的 `load` 事件早于客户端任务 API 请求和 React 结果区渲染完成；首次断言使用了错误的完成信号。
- 影响：仅产生一次验收时序误判，没有页面故障、数据丢失、外部提交或供应商调用；同一刷新页面随后显示正确结果。
- 防复发：动态任务页验收必须等待“结果可靠性”区域或任务 ID 等唯一业务元素可见，再读取计数和图片状态；不能只凭顶层 `load` 事件判定客户端数据已完成。

### I-020：V2.1 项目专用重启与真实结果可靠性验收

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-043`；同时复核 Task 4 实施计划、项目进程树、健康握手、真实任务 API、JSON、Excel 和页面。
- 目标与范围：用项目绝对路径和明确进程标记替换全局停止 Python 的旧启动方式；加入子进程逆序停止、`.next` 普通目录校验、隐藏日志、V2.1 readiness 握手、供应商列表和静态资源验证；完成真实自定义 Anthropic V2.1 任务及四端一致性验收。未修改评分权重/阈值、数据库结构、商品/关键词数据库、采集器、利润模块、供应商请求协议或 V2.0 历史结果。
- 涉及文件：`scripts/restart-and-verify.ps1`、`启动.ps1`、`tests/test_restart_script.py`、`docs/verification/2026-07-30-v2.1-runtime-result-reliability.md` 和本文。
- 运行验证：镜像实例 live、数据库、Redis、Worker、契约均为 `ok`；API 与 Worker 均为 `combination_model_v2.1`；4 个供应商配置可见；首页/API 设置页为 200；7 个 Next.js 静态资源全部 200。
- 真实任务：`367c230b-41fa-4e03-8f78-09d2cc1483e5` 由 `custom` / `claude-fable-5` 完成，状态 `completed_with_qualified_candidates`，初次候选 5、合格 1、待补证据 1、淘汰 3；API、JSON、Excel 与任务页面一致，食品候选被 `food_blocked` 淘汰，主品图片真实加载。
- 自动化与中间失败：阶段验证为 Python `389 passed`、前端 `116 passed`、TypeScript 和生产构建通过、Task 4 测试 `4 passed`、改动文件 Ruff 与 `git diff --check` 通过；全项目 Ruff 的 87 个既有问题见 `F-031`。Task 4 过程失败见 `F-027` 至 `F-048`。
- 供应商边界：CatToken 单次最小连接仍为 503，见 `F-045`；本轮不宣称 CatToken、OpenAI 或 DeepSeek 完整选品任务已验收。
- 环境限制：原 `F:` 仓库在当前会话为只读，活动应用与本提交位于 `C:\Users\Administrator\Documents\组合品\web-platform-v2.1-work`；权限恢复后必须以 Git 提交同步，不能手工覆盖。`dump.rdb` 未复制、未修改、未暂存、未提交。
- 回滚基线：`2295c7f`；本轮提交信息为 `ops: verify v2.1 runtime reliability`。

### F-049：自定义 Anthropic V2.1 任务结构化输出失败（Bike Bags）

- 时间：2026-07-30
- 现象：任务 `22e4844d-7dfb-42a2-b962-a6fceb540793` 使用 `custom` 供应商时在 65% 失败，页面只显示 `LLM returned invalid structured output`，没有结果载荷或 artifact。
- 证据：Worker 在 `17:38:47` 同时发起主模型和 DeepSeek 假设请求；到 `17:39:25` 仅记录一条 `Generated 4 hypothesis directions`，随后主任务在 `17:40:25` 以 `LLM_FAILED` 结束。任务 API 确认契约为 `combination_model_v2.1`、供应商为 `custom`。现有 `HypothesisService` 将 Pydantic 字段校验错误统一包装，`_run_dual` 只允许主模型异常传播，因此无法判断具体字段或原始供应商响应。
- 根因判断：主模型返回的 JSON 未通过严格 `HypothesisOutput` 校验，且校验失败没有一次受控修复请求；DeepSeek 的成功结果不能替代主模型结果。GBK 解码警告和 cron 延迟与结构化错误同时出现，但没有证据证明它们是业务根因。
- 本轮范围：保留严格 V2.1 schema、评分、阈值、数据采集和供应商协议；只增加一次契约修复重试、脱敏字段级诊断和主模型供应商上下文。不重算或覆盖旧任务。
- 失败防复发：不得通过放宽 schema、忽略缺失字段或使用 secondary 结果冒充 primary 来“修复”；真实供应商任务仍需单独验收。

### I-021：V2.1 结构化输出失败诊断与受控修复重试

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-049`；同时复核 `HypothesisService`、`AnalysisRunner`、Worker 错误分类、Anthropic 结构化解析和失败任务 API。
- 目标：修复自定义 Anthropic 任务在结构化 JSON 不符合 `HypothesisOutput` 时直接失败且无法定位的问题；保持 V2.1 严格校验，不改变评分、阈值、采集器、数据库、关键词库、利润模块或供应商协议。
- 修改文件：`app/services/hypothesis_service.py`、`backend/application/analysis_runner.py`、`tests/test_hypothesis_service.py`、本文档。
- 实现：首轮 Pydantic 校验失败后最多发起一次明确的完整 JSON 修复请求；修复结果仍必须通过同一 schema 和模型契约校验；失败信息仅记录最多 5 个字段路径与错误类型，并携带主/辅助供应商模型上下文，不记录响应内容、密钥或凭证。
- 验证：定向后端 `54 passed`；Python 全量 `391 passed, 1 warning`；改动文件 Ruff 通过；前端先构建后类型检查均通过；`git diff --check` 通过。
- 真实供应商边界：本轮未重跑旧失败任务，也未用自动化 mock 宣称 custom/DeepSeek 已完成新的真实任务验收；旧任务数据保持不变。

### F-050：前端首次 typecheck 在构建前读取缺失 `.next/types`

- 现象：本轮并行验证中，`npm.cmd run typecheck` 首次因 `.next/types/...` 尚未生成而失败；随后先执行 `npm.cmd run build`，再串行执行 typecheck，均通过。
- 根因与防复发：Next.js 类型检查依赖构建生成的 `.next/types`；继续遵守先 build 后 typecheck，禁止并行执行。

### F-051：真实 custom 任务返回截断/非法 JSON

- 时间：2026-07-30
- 任务：新建验证任务 `bdc7283e-178e-43d9-9441-bd69d5a808f8`，供应商 `custom`，模型 `claude-fable-5`，同一 Bike Bags 商品；未修改旧任务 `22e4844d-7dfb-42a2-b962-a6fceb540793`。
- 现象：任务抓取完成并进入 65% 双模型阶段；DeepSeek 方向生成 3 条，主 custom 请求最终失败，错误为 `Anthropic structured output failed: invalid JSON: Unterminated string starting at`。
- 根因：模型响应在 JSON 解析前已不完整/非法，尚未进入 Pydantic 字段校验；此前仅对 Pydantic 校验失败做修复重试，因此该路径直接映射为 `LLM_FAILED`。
- 防复发：结构化响应出现 `invalid JSON`、`response truncated` 或空响应时，最多进行一次明确要求完整 JSON 的修复请求；修复仍必须通过原始 V2.1 schema 和模型版本契约，不能接收片段、宽松解析或 secondary 冒充 primary。

### F-052：前端验证命令在仓库根目录执行

- 现象：本轮组合命令先在仓库根目录运行 `npm.cmd run build` 和 `npm.cmd run typecheck`，因根目录没有 `package.json` 返回 `ENOENT`。
- 根因：前端工程位于 `frontend/`；与历史 `F-010`、`F-050` 相同，属于验证命令工作目录错误，不是前端源码故障。
- 结果：后端 `392 passed, 1 warning`；前端命令将从 `frontend/` 单独串行执行并记录最终结果。

### F-053：custom 真实任务通过 JSON 后触发 V2.1 质量门禁

- 时间：2026-07-30
- 任务：`e1f28c63-f49d-4f56-8d94-efc00a8db061`，`custom/claude-fable-5`，Bike Bags 商品。
- 现象：两条模型方向均生成（日志分别为 5 条和 8 条），但任务最终以 `RESULT_QUALITY_INVALID` 失败，错误为 `Candidate is missing the six V2.1 score dimensions`。
- 判断：该失败发生在供应商 JSON 解析和 Pydantic 校验之后的应用质量门禁，不能通过放宽门禁或用 secondary 结果替代 primary 解决。当前旧错误未标明具体模型和缺失字段，无法据此安全修改序列化或评分逻辑。
- 本轮处理：增强 `result_quality` 诊断，错误现在会标明 `gpt/deepseek` 和缺失维度；保留六维完整性硬门禁。旧任务不重算、不覆盖。

### I-022：修复市场证据重算丢失 V2.1 purchase_direction

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-053`；同时复核 `HypothesisService._to_hypothesis`、`MarketEvidenceService._apply_record`、`ScoreRatings` 和质量门禁调用链。
- 根因：V2.1 初始 `StickinessDecision.breakdown` 有六维，但 `_to_hypothesis()` 保存 `score_inputs` 时漏掉 `purchase_direction`。市场证据升级后 `_apply_record()` 用这五维输入重新计算，`ScoreRatings` 退回旧模式，最终 `structured_directions` 缺少 V2.1 维度并被硬门禁拒绝。
- 修改文件：`app/services/hypothesis_service.py`、`tests/test_hypothesis_service.py`、`tests/test_market_evidence_service.py`、本文档。
- 修复：V2.1 DTO 持久化 `purchase_direction` 输入（forward=5，其它=3），市场证据重算继续走六维 V2.1 权重；没有改变权重、阈值或门禁。
- 防复发：任何影响评分重算的 DTO 输入必须覆盖 V2.1 六维回归；质量门禁继续拒绝缺维度结果。

### F-054：最终 custom 真实验收仍返回非法 JSON

- 时间：2026-07-30
- 任务：`9adf577a-80d9-4872-9837-dec4ec5d25eb`，`custom/claude-fable-5`，Bike Bags 商品。
- 结果：主模型首轮返回 `invalid JSON: Unterminated string starting at`；受控修复请求后仍返回同类非法 JSON，任务以 `LLM_FAILED` 结束，进度 65%。新版错误已明确显示 `custom/claude-fable-5`，没有生成伪结果或覆盖历史任务。
- 结论：程序侧结构化重试和 V2.1 六维重算修复已生效，但该供应商/模型当前真实输出仍不稳定，不能宣称 custom 已完成稳定供应商验收。后续应优先检查模型端 max token/代理截断或更换已验证模型，不得放宽本地 schema 门禁。

### I-023：结果页中英双语展示与关键词可读性优化

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `F-054`；同时复核结果详情、方向列表、抽屉、评分卡及现有前端测试。
- 目标：将 `required_dependency`、`bundled at $8-15`、`E1`、深度分析机器键名和证据搜索词改为中文主标签加英文原值，保留完整原始数据，不改变评分或后端协议。
- 修改文件：`frontend/lib/result-labels.ts`、`frontend/components/jobs/direction-detail.tsx`、`frontend/components/jobs/direction-drawer.tsx`、`frontend/components/jobs/direction-list.tsx`、`frontend/components/jobs/stickiness-scorecard.tsx`、`frontend/tests/result-labels.test.ts`、`frontend/tests/result-workbench-ui.test.tsx`；设计与计划记录在 `docs/superpowers/specs/2026-07-30-result-display-bilingual-design.md` 和 `docs/superpowers/plans/2026-07-30-result-display-bilingual.md`。
- 实现：集中 formatter 仅作用于渲染层；枚举显示为“中文（英文）”，定价保留价格区间，关键词按字段稳定排序并用 `；` 分隔，对已识别短语提供有限中文释义，未知内容保留英文；深度对象递归显示键名，原始 JSON 折叠区继续保留。
- 验证：`npm.cmd run build` 通过；随后 `npm.cmd run typecheck` 通过；前端全量测试 `19 files / 120 passed`；`git diff --check` 通过。浏览器自动化本轮未执行，原因是当前 Node 浏览器连接未提供 `agent` 绑定；代码层测试覆盖真实组件输出。
- 失败案例与防复发：首次定向测试因 formatter 文件尚不存在而按预期失败；接入后旧测试仍查找裸标签“使用前/使用辅品”，实际双语输出导致断言失败，已将断言固定为完整双语标签。以后新增显示映射必须同时更新 formatter 测试和组件断言；不得通过修改原始 payload 来迎合界面。
- 回滚：保留 Git 工作区和本轮独立文件；回滚本轮只需撤销上述前端文件及本条记录，不涉及历史任务数据。

### I-024：双语展示更新后的服务重启复核

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-023`；确认本次只做运行重启和验证，不修改业务代码或历史任务数据。
- 执行：运行 `启动.ps1` 调用 `scripts/restart-and-verify.ps1`，按项目进程树停止旧 API、Worker、Next.js，清理并重新生成受校验的 `frontend/.next`，再启动三项服务。
- 结果：运行时校验通过；API live、API ready、首页、历史页、任务详情页和 API 设置页均返回 200；ready 检查确认 database、redis、worker 为 `ok`，API/Worker 契约为 `combination_model_v2.1`。
- 回归：重启后在 `frontend/` 运行 `npm.cmd test -- --run`，结果为 `19 files / 120 passed`。
- 已知限制：当前会话没有可用的浏览器控制绑定，因此未执行截图级浏览器操作；HTTP、构建产物资产检查和组件测试均已执行。未调用供应商 API，未产生新任务或覆盖历史结果。
- 回滚：本次仅重启进程和重建前端缓存，不改变源代码；如需恢复代码，使用上一条 Git 提交 `d7ea4e0` 及其父提交即可。

### I-025：安装 shadcn/ui 官方基础组件

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-024`；同时检查 `frontend/components.json`、Tailwind 配置、全局 CSS、现有 Radix 依赖和 Git 工作区。
- 目标：从 shadcn/ui 官方 registry 补齐可复用 UI 基础组件，为后续排版优化提供一致组件基础；本轮不替换现有业务页面，不改变评分、API、数据或历史结果。
- 执行：在 `frontend/` 运行 `npm.cmd exec --yes shadcn@latest add button card badge separator tabs tooltip --yes`。
- 新增：`frontend/components/ui/button.tsx`、`card.tsx`、`badge.tsx`、`separator.tsx`、`tabs.tsx`、`tooltip.tsx`、`frontend/lib/utils.ts`；依赖补充 `@radix-ui/react-separator`，并更新 `package.json`/`package-lock.json`。
- 验证：`npm.cmd run build` 通过；`npm.cmd run typecheck` 通过；前端全量测试 `19 files / 120 passed`；安装后未自动改动现有页面。
- 已知限制：组件目前仅作为基础库安装，尚未应用到具体工作台排版；后续 UI 改版需单独设计、确认和回归测试。
- 回滚：撤销本条提交即可移除新增组件和依赖，不影响此前结果页双语展示版本。

### I-026：结论优先结果工作台（实施中）

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-025`；同时复核已确认的 `conclusion-first-workbench.html` 样板、结果详情页、方向列表、评分卡和前端回归测试。
- 用户目标：解决字段堆叠、结论不突出、中英文标题混排、评分/理由/场景重复和分析层级不清；采用“先结论、后依据”的结果阅读顺序。
- 范围：仅调整 React 展示层和 UI 回归测试，使用已安装 shadcn/ui 基础组件；不修改评分逻辑、权重、阈值、AI 提示词、商品/关键词数据库、采集器、利润模块、供应商协议或历史任务快照。
- 计划：先新增结论优先、深度分析折叠和购买链路层级测试；再把结果摘要、方向详情和粘性评分卡调整为三层阅读结构；最后执行构建、类型检查、全量测试和 `git diff --check`。
- 已知限制：当前会话不保证有浏览器控制绑定；若无法执行截图级验收，必须以组件测试、构建产物和可访问文本验收，并如实记录。
- 回滚：本轮仅涉及后续列出的前端组件、测试和本条记录；可用本轮 Git 提交的父提交恢复。

### F-055：结论优先改版初始回归断言可能保留旧版重复文案

- 预防记录：本轮测试必须同时断言结论区存在、深度依据默认折叠、方向列表只显示中文主标题；旧版字段如果仍在首屏重复出现，应先修复组件而不是删改原始 payload。
- 防复发：展示层重排只能通过 formatter 和组件结构完成；原始 `StructuredDirection`、评分字段和历史结果不做迁移或重算。

### F-056：结论优先 UI 定向测试首次使用错误过滤路径

- 时间：2026-07-30
- 现象：在 `frontend/` 工作目录运行 `npm.cmd test -- --run frontend/tests/result-workbench-ui.test.tsx`，Vitest 返回 `No test files found`。
- 根因：测试过滤参数仍带仓库根相对前缀，导致与 `frontend/` 下的 include 规则不匹配；不是组件或测试实现错误。
- 处理：改用 `npm.cmd test -- --run tests/result-workbench-ui.test.tsx`；前端所有验证命令继续固定以 `frontend/` 为工作目录。
- 防复发：执行前确认命令工作目录与测试路径基准一致，并把命令失败与源码失败分开记录。

### I-027：结论优先结果工作台落地完成

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-025`；本轮中途新增并保留 `F-055`、`F-056`。
- 目标：让用户先看到辅品结论、粘性分和核心理由，再按需查看购买链路、评分依据、证据和深度分析，解决字段堆叠与阅读层级不清。
- 修改文件：`frontend/components/jobs/direction-detail.tsx`、`frontend/lib/result-labels.ts`、`frontend/tests/result-workbench-ui.test.tsx`、本文档。
- 实现：方向详情顶部新增 shadcn/ui `Card`、`Badge` 风格的“结论摘要”；保留分数和原始英文值，不改 payload；将核心理由与最多三步购买链路置于首屏；将评分卡、结构化分析、深度字段和原始 JSON 收入默认折叠的“深度分析（点击展开）”；推荐等级 formatter 修正为 `focus/test_pool/observe/not_recommended` 映射，避免与执行动作混用。
- 业务边界：未修改评分权重、阈值、推荐排序、AI 提示词、API 协议、数据库、关键词库、采集器、利润模块、历史任务或供应商配置。
- 验证：定向 UI `21 passed`；生产构建 `next build` 通过；TypeScript `npm.cmd run typecheck` 通过；前端全量 `19 files / 121 passed`；`git diff --check` 通过。
- 失败与修复：首次定向命令路径错误见 `F-056`；新增断言初期命中旧版重复字段及双语重复文本，已改为验证折叠交互和允许展示层重复来源，不修改业务数据。
- 已知限制：当前会话未执行截图级浏览器验收；需重启运行中的 Next.js 开发服务器后，在真实任务详情页确认折叠交互和移动端布局。构建与组件测试未调用供应商 API，不代表供应商端到端状态变化。
- 回滚：本轮提交的父提交可完整恢复；不涉及历史结果数据回滚。

### I-028：结论优先版本重启复核

- 时间：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-027`；本次只做运行重启与健康检查。
- 执行：运行 `启动.ps1`，重启 API、Worker 和 Next.js，并重建前端运行缓存；未创建新任务、未调用供应商、未重算历史结果。
- 验证：首页、历史页、API 设置页均返回 HTTP 200；API live/ready 返回 200；ready 显示 database、redis、worker 均为 `ok`，API/Worker 均为 `combination_model_v2.1`，契约匹配为 `ok`，运行 revision 为 `8a1468c`。
- 已知限制：未执行截图级浏览器验收；真实任务详情需要在浏览器打开后点击“深度分析（点击展开）”确认视觉效果。
- 回滚：运行态无源代码变更；代码回滚使用 `8a1468c` 的父提交。
### F-057：深度分析分组与交叉验证按钮回归测试首轮失败

- 日期：2026-07-30
- 修改前已阅读：本文件全部内容，最新完成条目为 `I-028`；本轮仅限展示层与 UI 测试。
- 现象：深度分析测试找不到“深度分析分组”；交叉验证 mock 报 `Expected ")" but found ";"`。
- 原因：生产组件尚未提供分组标题；新增 MSW mock 闭合括号遗漏。
- 防复发：保持 payload/评分/供应商流程不变；MSW mock 必须完整闭合；所有失败保留在此记录。

### I-029：深度分析分组与交叉验证主操作视觉优化（进行中）

- 日期：2026-07-30
- 修改前已阅读：本文件全部内容，最新条目为 `I-028`，并保留 `F-057` 失败记录。
- 目标：整理深度分析阅读层级，并将交叉验证操作变成明确主按钮。
- 范围：仅修改前端展示层与 UI 测试，不创建任务、不请求供应商、不改评分或数据。
- 修改文件：`frontend/components/jobs/direction-detail.tsx`、`frontend/app/jobs/[jobId]/page.tsx`、`frontend/tests/result-workbench-ui.test.tsx`、`frontend/tests/job-detail.test.tsx`。
- 实现：深度依据按分析假设、一致性评分、购买链路、关系依据、扩展场景、交付检查和深度依据分组，以双列卡片减少堆叠；交叉验证增加图标、说明和高对比主按钮，保留原 mutation 与 API 调用。
- 验证：定向 UI `37 passed`；全量前端 `19 files / 123 passed`；`npm.cmd run build` 通过；`npm.cmd run typecheck` 通过。
- 已知限制：未进行截图级浏览器验收；本轮未触发真实供应商请求，不代表供应商状态已重新验证。
- 回滚：撤销本轮提交即可恢复上一版；不涉及历史任务结果。
- 重启复核：`启动.ps1` 执行完成；前端 `/` 返回 200，`/api/v1/health/live` 返回 200，`/api/v1/health/ready` 显示 database/redis/worker 均为 `ok`、API/Worker 均为 `combination_model_v2.1`、`contract_match=ok`，revision 为 `5806069`。误用 `/health/live` 得到 404，已按项目实际路由复核，不是服务故障。
- 状态：已完成。

### I-030：深度依据中英双语与扩展场景排版优化

- 日期：2026-07-30
- 修改前已阅读：本文件全部内容，最新完成条目为 `I-029`，并保留 `F-057` 失败记录。
- 用户问题：`user`/`score`/`reason`/`mental`/`scenario`/`lifecycle` 仅显示英文，一致性评分与深度依据字段堆叠，扩展场景难以扫读。
- 修改文件：`frontend/components/jobs/direction-detail.tsx`、`frontend/lib/result-labels.ts`、`frontend/tests/result-workbench-ui.test.tsx`。
- 实施：展示层将一致性评分转为独立卡片，以“中文名称（英文原值）”、“评分（score）”、“成立理由（reason）”展示；扩展场景按场景名、理由、假设分开卡片化；深度依据中已分组字段从残余 JSON 展示中过滤，避免重复。保留英文原值以便追溯，未修改 payload、评分、阈值或历史任务。
- 失败案例与防复发：已将 `F-057` 中的分组标题缺失、mock 语法错误以及双语标签断言不匹配作为本轮回归警示；新增扩展场景卡片测试，后续修改必须同时保持中英标签和分组去重。
- 验证：定向 UI 测试 `23 passed`；前端全量 `19 files / 124 passed`；`npm.cmd run typecheck`、`npm.cmd run build`、`git diff --check` 均通过。本轮未调用真实供应商 API，未创建新任务、未覆盖历史结果。
- 回滚：回退本轮提交即可恢复上一版展示，不影响任务数据。
- 状态：已完成。

### I-031：双语标签去重、证据字段网格与深度分析主按钮

- 日期：2026-07-30
- 修改前已阅读：本文件全部内容，最新完成条目为 `I-030`，并保留 `F-057` 以及 `I-030` 的失败和防复发记录。
- 用户反馈：一致性卡片显示 `用户一致性（user）（user）`、`评分（score）（score）`；证据来源的搜索词与双语释义被挤在右对齐字段；深度分析操作不够醒目。
- 根因：`deepArgumentKeyLabel()` 已返回“中文（英文原值）”，组件又额外拼接英文原值；证据区沿用左右对齐的 flex 布局，不适合较长的搜索词；深度分析仅是文字按钮。
- 修改文件：`frontend/components/jobs/direction-detail.tsx`、`frontend/components/jobs/stickiness-scorecard.tsx`、`frontend/tests/result-workbench-ui.test.tsx`。
- 实施：去掉已由 formatter 提供的重复英文原值；证据来源改为响应式字段网格，搜索词可换行；深度分析使用主色按钮、焦点环和图标。不改变 payload、评分、证据原始值或历史任务。
- 失败案例与防复发：新增回归时曾因复制受损的中文字面量导致测试语法错误，已改用结构化选择器和正则断言；一次用宽泛 `/20/` 断言与日期匹配产生歧义，已改为 `^20$`；后续 UI 测试必须避免宽泛文本匹配。
- 验证：定向 UI `26 passed`；顺序执行 `npm.cmd run build` 、`npm.cmd run typecheck` 、前端全量 `19 files / 127 passed`均通过。之前并行运行 build/typecheck 出现 `.next/types` 暂时缺失，已确认为构建竞5争，改为顺序验证后通过。
- 回滚：回退本轮 Git 提交即可恢复上一版展示，不影响任务数据。
- 状态：已完成。

### F-058：统一模型目录设计阶段的检索命令语法错误

- 日期：2026-07-31
- 现象：设计阶段第一次使用 PowerShell 管道输出检索结果时出现空管道语法错误。
- 原因：在 `foreach` 表达式外直接追加管道，命令结构不完整；与业务代码和供应商状态无关。
- 处理：改为先将循环结果赋值给变量，再单独输出；后续命令正常完成。
- 防复发：PowerShell 多文件诊断命令先验证语法，再执行；将工具命令失败与源码测试失败分开记录。

### I-032：API 模型目录与交叉验证统一设计

- 日期：2026-07-31
- 修改前已阅读：本文件全部内容，最新完成条目为 `I-031`，并保留 `F-058` 记录。
- 用户目标：API 设置必须明确显示实际使用的供应商、协议和模型；交叉验证模型选择与 API 设置保持一致。
- 本轮范围：新增设计规格 `docs/superpowers/specs/2026-07-31-provider-model-catalog-cross-review-design.md`；尚未修改业务代码、数据库、评分逻辑或历史结果。
- 设计结论：采用统一模型目录方案 A；仅允许选择已启用且连接测试通过的两个不同模型；新任务保存脱敏模型身份快照；结果和历史显示实际模型；旧 GPT/DeepSeek payload 保持兼容读取。
- 验证：完成代码结构核对和设计自检；未调用供应商 API，未创建任务，未重算或覆盖历史结果。
- 已知限制：规格等待用户审阅；用户批准规格后才进入实施计划和代码修改。
- 回滚：删除本轮设计文档并回退本条记录即可恢复本轮文档状态；无运行态或数据变更。

### I-035：供应商模型测试状态与旧目录失效回归

- 日期：2026-07-31
- 修改前已完整阅读：本文件最新条目为 `I-032`，并保留既有 `F-058` 及此前失败案例与防复发规则。
- 现象：页面同时显示 `Connection successful` 和 `The configured model was not found or is unavailable`。根因不是评分算法，而是旧成功状态与当前模型不可用失败状态并存。
- 失败案例：本轮回归初次运行 9 个测试时 2 个失败：新增测试使用了乱码标签；未测试的 custom 供应商仍沿用 `supported_models`，导致启用后保存未被锁定。
- 根因：供应商初始化和 tab 切换直接读取 `supported_models`，没有检查 `last_test_status`；因此 `untested` 或失败状态也会展示旧模型目录，`requiresRetest` 无法形成门禁。
- 修改文件：`frontend/components/settings/provider-settings-panel.tsx`、`frontend/tests/provider-settings.test.tsx`。
- 实施：仅在 `last_test_status === "success"` 时加载 `supported_models`；未测试、失败或服务地址/协议变化时清空目录、测试签名和成功提示，并禁止保存，要求重新测试。
- 验证：`npm.cmd test -- --run tests/provider-settings.test.tsx` 通过，`9 passed`。本次单元测试不代表真实供应商可用性，真实 API 仍需用用户自己的 Key 和已确认存在的模型测试。
- 回滚：撤销本轮提交即可恢复旧目录展示逻辑；不修改商品数据库、评分逻辑、历史任务或 API Key。
- 防复发：以后新增供应商状态测试必须覆盖 `success`、`untested`、`failed` 三种状态；失败只记录 `PROVIDER_MODEL_INVALID` 等错误类型，不记录任何 API Key、Cookie 或 Token。

### I-036：测试失败后清空持久化目录与页面旧下拉框

- 日期：2026-07-31
- 修改前已完整阅读：本文件最新条目为 `I-035`，并保留此前供应商状态、模型目录和接口失败记录。
- 用户现象：OpenAI 显示“尚未发现可用模型”，Claude 同时显示旧的 `Connection successful`、一个旧模型和当前 `PROVIDER_MODEL_INVALID` 错误；用户无法切换到不存在或未验证的模型。
- 根因：测试接口异常只返回 HTTP 错误，没有把现有供应商记录标记为 `failed`；前端失败分支也没有清空当前 `availableModels`，导致旧模型下拉框继续可选。OpenAI/DeepSeek 的环境导入状态本来就是 `untested`，没有可切换目录；Claude 本次实际只发现一个模型，没有第二个可选项。
- 修改文件：`backend/db/provider_repository.py`、`backend/application/provider_service.py`、`frontend/components/settings/provider-settings-panel.tsx`、对应 provider 测试文件。
- 实施：新增 `record_test_failure`，失败时清空数据库 `supported_models`、写入 `failed` 状态和错误信息；前端 `onError` 清空模型目录、测试签名和成功提示，保存按钮重新进入“必须测试”门禁。成功测试仍只展示本次返回的模型。
- 验证：后端供应商服务/仓储回归通过；前端 provider 设置回归 `10 passed`。完整验证和服务重启在本轮代码完成后执行。
- 失败案例与防复发：实现初次缺少 `ProviderConnectionError` 导入，已立即补齐；新增测试必须覆盖“旧成功目录 + 当前模型无效”的失败路径，且不能只验证 HTTP 错误，还要断言目录被清空、状态变为 `failed`。
- 回滚：撤销本轮提交即可恢复旧的失败不落库行为；不修改商品数据库、评分逻辑、历史任务或任何密钥内容。
