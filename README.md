# A+B Bundling System

Walmart 跨境组合选品 AI 系统。输入主品链接，自动生成辅品搭配假设，支持二次验证审判。

## 快速开始

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m playwright install chromium

# 复制 .env 并填入你的 API Key
Copy-Item .env.example .env
```

运行测试和静态检查：

```powershell
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\ruff.exe check app tests
```

## 使用方式

### 模式A：生成辅品假设

```bash
python -m app.main --mode generate --url "https://www.walmart.com/ip/..."
```

### 模式B：审判辅品假设

```bash
python -m app.main --mode judge --a-url "https://..." --b-urls "url1" "url2"
```

## 项目结构

```
app/
├── main.py                     # 入口
├── core/                       # 配置、日志、异常
├── domain/                     # DTO + 接口抽象
├── infrastructure/
│   ├── browser/                # Playwright + CDP 浏览器
│   ├── llm/                    # GPT 客户端 + prompt 模板
│   ├── walmart/scraper.py      # 商品详情爬虫
│   └── storage/                # 结果存储
└── services/
    ├── product_service.py      # 商品数据
    ├── hypothesis_service.py   # 指令A：假设生成
    └── judgment_service.py     # 指令B：假设审判
```

## 输出

结果保存在 `output/bundling/` 目录，JSON 格式。
