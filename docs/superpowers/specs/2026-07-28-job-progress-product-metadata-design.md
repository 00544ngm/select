# 任务进度与主品元数据展示设计

## 目标

修复任务详情页进度条不随任务执行变化、主品商品 ID 与中文标题缺失、结果图片不显示的问题，并应用已选择的 A「清晰商务」字体方案。分析评分、方向生成、队列编排和结果内容保持不变。

## 已确认的设计决策

- 进度采用方案 3：Worker 保留 Redis 进度，同时把同一百分比写入 `analysis_jobs.progress`；详情接口继续读取数据库，数据库是页面展示和重启后的兜底来源。
- 主品 ID 从 Walmart/Amazon 商品 URL 解析，不修改原始 URL。
- Hypothesis 复用模型已输出的 `product_analysis.title` 作为中文标题；Judgment 在结构化输出中增加 `product_title_zh`，由当前模型生成并保存。
- 抓取器提取主图 URL，去重后写入 `ProductDTO.images`；前端图片组件保留加载失败降级，并按候选图片顺序回退。
- 字体 A 使用本机可用的清晰中文字体栈、明确字重和更高文字对比度，不引入必须联网下载的字体，也不改变现有布局和颜色体系。

## 数据流

1. `AnalysisRunner` 抓取商品时获得标题、URL、图片和模型分析结果。
2. `run_analysis_job` 的进度回调同时更新 Redis 和数据库进度字段。
3. `AnalysisRunner` 序列化结果时补充 `product_id`、`product_title_zh`、`product_images` 等元数据；双模型结果在顶层和各模型结果中保持一致。
4. FastAPI 详情/列表响应透传这些字段，旧任务缺失字段时返回空值，不影响历史数据读取。
5. 任务详情页在进度区、结果摘要和结果工作台显示商品 ID、原文标题、中文标题和主图；图片失败显示明确降级文案。

## 文件边界

- 后端进度：`backend/workers/jobs.py`、`backend/db/repositories.py`。
- 商品元数据：`app/domain/product_url.py`、Walmart/Amazon scraper、`backend/application/analysis_runner.py`、Judgment schema/prompt。
- API 类型：`backend/api/schemas/jobs.py`、`frontend/lib/api/types.ts`。
- 前端展示：`frontend/components/jobs/job-progress.tsx`、`result-summary.tsx`、`result-analysis-module.tsx`、`product-media.tsx`、`frontend/app/globals.css`。

## 错误处理与兼容性

- 进度写入失败不能吞掉任务主流程；Redis 失败时数据库进度仍可展示，数据库更新失败按现有 Worker 异常处理记录失败。
- 无法从 URL 解析商品 ID 时显示“未识别”，不猜测 ID。
- 抓取不到图片、图片 URL 失效或旧任务没有图片时显示“暂无图片/历史无图”，不伪造图片。
- 旧任务没有中文标题时显示“未保存中文标题”，原始英文标题继续保留。
- Judgment 模型不返回新增字段时使用空值兼容，不改变已有评分结果。

## 验证范围

- 后端单元测试：进度回调双写、URL 商品 ID 解析、Walmart/Amazon 图片提取、Hypothesis/Judgment 元数据序列化。
- 前端单元测试：进度从 0/中间值/100 正确渲染、ID 与中英文标题展示、多图失败回退、旧任务降级文案、字体变量生效。
- 类型检查、全量前后端测试、生产构建和桌面/移动端 Playwright 页面验证。

