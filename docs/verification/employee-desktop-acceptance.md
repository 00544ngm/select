# 员工电脑桌面版验收

## 自动验收

运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-employee-desktop.ps1
```

通过条件：

- 用户数据路径同时包含中文、空格、`#`、`%`，SQLite 仍使用完整文件路径。
- 数据库迁移成功，异步连接 `SELECT 1` 成功。
- 运行时没有向模拟安装目录写入文件。
- 内置 Chromium 文件存在。
- 输出 `employee-desktop-acceptance-ok`。

## 新员工首次使用

API Key 使用 Windows DPAPI 按当前用户加密。每位员工第一次安装后必须在自己的 Windows 账户内输入 API Key、测试连接、验证并勾选模型。复制其他用户的数据目录不能代替这一步。

## 外部阻断

网站 CAPTCHA、企业代理、杀毒软件阻止 Chromium 或网络访问时，软件会结束提交/任务等待并保存日志；这类外部策略仍需管理员按日志放行，软件不会绕过系统安全策略。

