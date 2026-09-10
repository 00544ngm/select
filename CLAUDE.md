# A+B Bundling System

Walmart 跨境组合选品 AI 平台。输入主品链接，自动生成辅品搭配假设（指令A），支持二次验证审判（指令B）。

## 优化迭代纪律（强制）

任何代码、提示词、评分、数据结构、页面展示或部署配置改动前，先完整阅读 `docs/优化迭代记录.md`。每次改动完成后，必须在该文件追加目标、范围、验证结果、失败案例、已知限制和回滚提交；不得删除历史失败记录，也不得写入 API Key、Cookie 或令牌。旧任务结果是历史快照，未经明确授权不得重新计算或覆盖。

## 技术栈

- **核心**: Python 3.13+, Playwright + CDP Chrome, OpenAI GPT
- **后端**: FastAPI, SQLAlchemy Async + PostgreSQL, ARQ + Redis
- **前端**: Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui, React Query, React Hook Form + Zod
- **浏览器**: 本地 Chrome（通过 CDP 远程调试连接），非 Playwright 内置浏览器

## 前置条件

安装以下软件：

- Python 3.13+
- Node.js 20+
- PostgreSQL 17
- Redis 8
- Google Chrome（安装在默认路径 `C:\Program Files\Google\Chrome\Application\chrome.exe`）

### 安装 PostgreSQL（Windows）

1. 下载 https://www.postgresql.org/download/windows/ 并安装
2. 安装时设置密码（记住它），端口保持默认 5432
3. 打开 **SQL Shell (psql)** 或使用 pgAdmin 创建数据库：
```sql
CREATE DATABASE bundling;
CREATE USER bundling WITH PASSWORD 'bundling';
GRANT ALL PRIVILEGES ON DATABASE bundling TO bundling;
```

### 安装 Redis（Windows）

1. 下载 https://github.com/redis-windows/redis-windows/releases（选最新 .msi 或 .zip）
2. 安装后启动 Redis 服务（默认端口 6379）
3. 验证：`redis-cli ping` 返回 `PONG`

### 或用 Docker（如果有）

```powershell
docker compose up -d postgres redis
```

## 完整安装步骤

### 1. 解压并进入项目目录

确保解压后进入项目根目录，路径不含中文/空格。

### 2. 创建虚拟环境并安装 Python 依赖

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

### 3. 创建环境变量文件

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，填入你的 OpenAI API Key：

```
OPENAI_API_KEY=sk-your-real-key-here
```

### 4. 安装前端依赖

```powershell
npm --prefix frontend install
```

### 5. 启动基础设施（PostgreSQL + Redis）

如果安装了 Docker：
```powershell
docker compose up -d postgres redis
```

如果没有 Docker，确保 PostgreSQL 和 Redis 服务已在 Windows 中启动运行。

### 6. 运行数据库迁移

```powershell
.venv\Scripts\alembic.exe -c backend/migrations/alembic.ini upgrade head
```

### 7. 启动 Chrome（用于爬虫）

在任务栏关闭所有 Chrome 窗口后运行：

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$pwd\.chrome-profile" --no-first-run --no-default-browser-check
```

### 8. 启动服务（按顺序）

**终端 1 - 后端 API**:
```powershell
.venv\Scripts\python.exe -c "import asyncio, sys; sys.platform=='win32' and asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy()); import uvicorn; uvicorn.run('backend.main:app', host='127.0.0.1', port=8000)"
```

**终端 2 - Worker**:
```powershell
.venv\Scripts\python.exe -m arq backend.workers.settings.WorkerSettings
```

**终端 3 - 前端**:
```powershell
npm --prefix frontend run dev
```

### 9. 访问

- 前端界面: http://localhost:3000
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 一键启动

也可以用启动脚本（会打开 3 个终端窗口）：

```powershell
.\启动.ps1
```

## 项目结构

```
web-platform/
├── app/                          # 业务核心（不依赖 Web 框架）
│   ├── core/config/settings.py   # 配置（从 .env 读取）
│   ├── domain/                   # DTO + 接口抽象
│   ├── infrastructure/
│   │   ├── browser/              # Playwright + CDP Chrome 管理器
│   │   ├── llm/                  # GPT 客户端 + prompt 模板
│   │   ├── walmart/scraper.py    # 商品详情爬虫（含 CAPTCHA 等待）
│   │   └── storage/              # 结果 JSON/Excel 存储
│   └── services/                 # 业务服务
├── backend/                      # FastAPI 后端
│   ├── api/routes/               # API 路由
│   ├── application/              # 任务编排 + 序列化
│   ├── workers/                  # ARQ Worker
│   └── db/                       # 数据库模型 + 仓库
├── frontend/                     # Next.js 前端
│   ├── app/jobs/[jobId]/         # 任务详情页
│   ├── components/               # UI 组件
│   └── lib/                      # API 客户端 + 工具
├── docs/                         # 设计文档和计划
├── CLAUDE.md                     # 本文件
├── 启动.ps1                      # 一键启动脚本
├── .env.example                   # 环境变量模板
└── docker-compose.yml            # PostgreSQL + Redis
```

## CAPTCHA / 人机验证处理

爬虫遇到 Walmart 人机验证时不会直接失败：

- 检测到 `/blocked` URL 或标题含 "robot" 时进入被动等待
- 不刷新页面，等你手动在浏览器中完成验证
- 配置项（在 `.env` 中）：
  - `CAPTCHA_WAIT_ENABLED=true`
  - `CAPTCHA_WAIT_TIMEOUT_SECONDS=600`
  - `CAPTCHA_CHECK_INTERVAL_SECONDS=5`

## 爬取流程

1. 通过 CDP 连接到本地已打开的 Chrome
2. 自动导航到 Walmart 商品页
3. 遇到人机验证时等待手动处理
4. 提取标题、价格、评分、评论、属性等
5. 自动翻页提取评论（最多 10 页 / 30 条）

## 常见问题

### Python 事件循环错误（Windows）

`NotImplementedError` on Windows Python 3.13 — 启动命令已包含事件循环策略修复：
```python
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

### 端口被占用

```powershell
netstat -ano | Select-String "8000"
taskkill /F /PID <PID>
```

### Worker 没启动

确认 Redis 正在运行：

```powershell
redis-cli ping
# 应返回 PONG
```

如果没有 `redis-cli`，检查 Redis 服务是否在运行（任务管理器 → 服务）。

### 爬虫卡在人机验证

浏览器窗口会停留在验证页面，手动完成验证后继续。如果超时（默认 10 分钟），任务会标记为失败。

## 关键 Commit 记录

- `9b3edbd` — 模型选择、中文映射、用户理性评分
- `3fe173a` — CAPTCHA 等待、判断全字段映射、评级/评分原因说明
