# 2026-08-02 桌面安装包验证

- PyInstaller API 冒烟：`/api/v1/health/live` 返回 200，并完成 0001 至 0007 SQLite 迁移。
- PyInstaller Worker 冒烟：进程保持运行并生成有效 Worker 心跳。
- 固定浏览器：安装包包含 Playwright Chromium，headless 本地页面冒烟通过。
- 前端：Next.js production build 通过；打包后的 `server.js` 使用 `runtime_modules` 启动并成功返回首页。
- Electron：类型检查通过；3 项窗口安全与生命周期测试通过。
- 后端桌面聚焦回归：26 项通过，保留 2 项既有异步资源 warning。
- 整包启动：UI、API、Worker、SQLite 数据库五项断言同时通过；仅监听两个随机 `127.0.0.1` 端口。
- 安装器：NSIS x64、非一键安装、允许选择目录、创建桌面和开始菜单快捷方式、卸载默认保留应用数据。
- 严格密钥扫描：`sk-` 加 64 位十六进制格式 0 命中。
- 安装包大小：362.99 MB。
- SHA-256：`6383B52D517A4E8AA06FC2FBFBB741A57F89B111418F9A3F7B58543A9AC99CBF`。

未宣称的范围：未在独立 Windows 11 测试机执行安装矩阵；未执行真实付费模型请求；本次交付为首个本机安装版，首次使用需在桌面版内重新配置 API。
