# Walmart 导航超时恢复验证

日期：2026-08-14

## 结果

- Walmart 抓取单元测试：16 passed。
- Worker、模型轮换及 Walmart 回归：68 passed。
- Python 全量测试：787 passed，9 skipped，1 个既有异步清理 warning。
- 前端错误提示测试：20 passed。
- 前端全量测试：254 passed，7 skipped；保留既有 MSW 未匹配请求提示。
- 前端 TypeScript 类型检查通过。
- Next.js 生产构建通过。
- Windows 安装包 `组合选品控制台-Setup-0.1.15.exe` 构建通过，SHA-256：`86BE51925C84532E7D7FB66993BB402172E42055FA64A3C4F36EF744982AC1F3`。

## 本轮行为

- 初始 `page.goto` 超时后，只读取 URL、标题和最多 4000 个字符的页面文本判断是否为 Walmart 验证页。
- 验证页会复用已有可见浏览器流程，员工完成验证后继续同一商品抓取。
- 普通导航超时返回 `WALMART_NAVIGATION_TIMEOUT`。
- 代理、连接重置、域名解析等传输失败返回 `WALMART_NETWORK_FAILED`。
- 两类抓取错误都在模型 attempt 创建前结束，不会触发模型轮换或报告 Token 消耗。
- 前端稳定错误提示不显示 `Page.goto` 原始日志、完整 URL 或浏览器内部信息。

## 边界

本轮没有绕过或自动破解 Walmart 验证，没有伪造商品数据，也没有访问真实用户数据库、API Key、Cookie 或第三方模型端点。旧版 `0.1.14` 安装包未覆盖。
