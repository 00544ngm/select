# 待补证据跳转与精准关键词展示验证

日期：2026-07-31

## 验证结论

- “补充证据后复核”已改为可操作按钮；点击后展开深度分析，并将当前方向的“待验证证据”滚动到视野、聚焦和短暂高亮。
- 关键词已拆分为“Amazon 精准关键词”和“英文通用关键词”两个折叠区；Amazon 默认展开，英文通用词默认收起。
- Amazon 精准词拥有独立复制和直达搜索；只有通用词的历史数据不会生成 Amazon 搜索链接，避免误标。
- 新分析提示词要求每个方向只生成一条精准 Amazon 检索短语和一条同方向英文通用短语，并禁止无依据品牌词及促销词。
- 历史结果按兼容层展示，不重写原始任务数据。

## 自动验证

- `frontend: npm.cmd run typecheck`：通过。
- `frontend: npm.cmd test -- --run`：19 个测试文件、145 项测试全部通过。
- `.venv\\Scripts\\python.exe -m pytest -q`：448 项通过；保留 1 条既有异步资源清理警告。
- `frontend: npm.cmd run build`：Next.js 生产构建通过。

## 实际页面验证

任务：`0b14fe4f-3459-4fb6-a08c-e9300359befc`

- 页面 HTTP 200，前端服务重新启动后可正常加载。
- “查看待补证据”按钮数量为 1。
- 点击后“待验证证据”区域数量为 1，`document.activeElement` 为该区域，`data-highlighted=true`。
- Amazon 精准关键词折叠区 `open=true`，内容为一条独立查询；英文通用关键词折叠区 `open=false`。
- Amazon 搜索地址对精准词进行了 URL 编码。

