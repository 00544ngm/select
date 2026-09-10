# 2026-08-02 桌面版输入焦点与彻底退出修复验证

## 修复内容

- 删除空白托盘图标和“关闭后隐藏到托盘”路径。
- 普通关闭主窗口时允许关闭，最后一个窗口关闭后调用 `app.quit()`。
- `before-quit` 继续停止受管的 API、Worker 和前端子进程。
- `ready-to-show` 监听器改为在 `loadURL()` 之前注册，避免事件被错过后窗口永久隐藏。
- 桌面版本从 0.1.0 提升到 0.1.1。

## TDD 与静态验证

- 第一次 RED：普通关闭期望 `allow-close`，旧实现实际返回 `hide-to-tray`。
- 第二次 RED：源码顺序测试期望先注册 `ready-to-show`，旧实现索引为 3857，晚于 `loadURL` 的 3822。
- GREEN：`desktop/tests/window-options.test.ts` 共 4 项通过。
- `npm.cmd --prefix desktop run typecheck`：通过。
- `npm.cmd --prefix desktop run build`：通过。

## 真整包验证

- 从 `release/win-unpacked/组合选品控制台.exe` 启动。
- 启动后共 7 个目标进程：Electron 主进程/渲染与辅助进程、API、Worker、前端。
- 主进程获得非零窗口句柄，窗口标题为“组合选品控制台”。
- 前端随机回环端口返回 HTTP 200 和 `text/html`。
- API 根路径返回 HTTP 401，符合桌面会话认证要求；未把未授权访问误报为服务失败。
- Worker 心跳文件和 SQLite 数据库存在。
- 对主窗口发送正常关闭消息返回 `true`；随后目标进程数从 7 降为 0，无 Electron、API、Worker 或前端残留。

## 输入验证边界

此前在旧版后台运行时已用记事本成功输入英文和中文，排除了全局键盘钩子。此次 0.1.1 复验时，Windows 自动化在激活最小化记事本时返回 `GetCursorPos failed: 拒绝访问 (0x80070005)`，因此没有伪造人工中文输入“已通过”的结论。已自动验证的软件侧关键条件是：窗口可见、不会周期性自动聚焦、关闭后不再后台驻留。安装后仍需由用户在自己的输入框中完成一次中文连续输入确认。

## 发布产物

- 安装器：`F:\组合品7-31\web-platform-v2.1-work\release\组合选品控制台-Setup-0.1.1.exe`
- 大小：380,709,295 字节（363.07 MiB）
- SHA-256：`5B19CAD3E6272C2EA465D997D90E205DB0FD23ACC43CB2483D535863F94CB696`
- 同目录包含 `.sha256` 校验文件。

## 已知限制与回滚

- 未自动安装覆盖用户当前目录；旧 0.1.0 测试进程已停止。
- 未调用真实供应商或付费模型，未修改历史任务结果。
- 如需回滚，可重新安装 0.1.0；应用数据默认保留在 `%LOCALAPPDATA%\组合选品控制台`。
