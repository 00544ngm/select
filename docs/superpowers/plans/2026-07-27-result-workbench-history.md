# 结果研究工作台与历史记录实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变抓取、模型输出、评分和任务状态逻辑的前提下，将假设分析结果改造成研究工作台，并为方向增加真实关键词、按需平台核验、主品图片和带时间摘要的历史记录。

**Architecture:** 后端只把领域 DTO 中已经存在的主品和方向字段透传到结果 JSON，并从已保存结果计算只读历史摘要。前端以类型化工具函数分离关键词选择、平台搜索和北京时间计算，以小型组件组成方向列表、方向详情、搜索结果和历史行；旧结果缺字段时继续使用现有 sections。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、pytest、Next.js 15、React 19、TypeScript、TanStack Query、Tailwind CSS、Vitest、Testing Library、MSW、Playwright。

---

## 文件结构

- backend/application/analysis_runner.py：仅扩展假设结果序列化，不改变分析执行。
- backend/application/result_highlights.py：从已保存结果读取历史摘要的纯函数。
- backend/api/schemas/jobs.py、backend/api/routes/jobs.py：给任务列表增加可选摘要。
- frontend/lib/result-workbench.ts：方向查询词、双语名称和最高分选择。
- frontend/lib/job-time.ts：北京时间、耗时和日期分组。
- frontend/lib/api/search.ts：封装现有 POST /api/v1/search。
- frontend/lib/cross-review-format.ts：按保真规则组织交叉验证原文。
- frontend/components/jobs/product-media.tsx：图片稳定尺寸和加载失败回退。
- frontend/components/jobs/direction-list.tsx：左侧固定方向列表。
- frontend/components/jobs/platform-search-panel.tsx：每个方向独立的 Walmart 查询状态和 Amazon 链接。
- frontend/components/jobs/direction-detail.tsx：方向指标、论证与交付清单。
- frontend/components/jobs/result-analysis-module.tsx：组合工作台和旧结果回退。
- frontend/components/history/job-table.tsx：时间、主品、最高方向与现有操作。

## Task 1：透传主品和方向原始字段

**Files:**
- Modify: backend/application/analysis_runner.py:508-595
- Modify: backend/tests/test_analysis_runner.py

- [ ] **Step 1：写失败的序列化测试**

在 backend/tests/test_analysis_runner.py 导入 DTO 与 _serialize_hypothesis，并加入：

    def test_serialize_hypothesis_preserves_workbench_fields_without_rescoring():
        result = HypothesisResultDTO(
            product=ProductDTO(
                url="https://www.walmart.com/ip/example/123",
                title="Pizza Cutter",
                price="$10.92",
                rating="4.7",
                review_count="414",
                images=["https://images.example/main.jpg"],
            ),
            keyword_pack=["pizza cutter accessories"],
            directions=[
                DirectionDTO(
                    hypothesis=HypothesisDTO(
                        direction_name="防滑披萨切割垫 (Non-Slip Pizza Cutting Mat)",
                        category_type="low_cost_value_add",
                        motivation_type="pain_point",
                        motivation_evidence="披萨在烤盘上滑动",
                        evidence_level="2",
                        estimated_cost_1688="¥3-6",
                        price_strategy="组合价 $16.97",
                        stickiness="high",
                        estimated_score=91,
                        keywords={"en": "non slip pizza cutting mat", "amazon": "pizza cutting board non slip"},
                    ),
                    deep_arguments={"user_rationale": "稳定披萨"},
                    delivery_checklist={"bundling_display": "展示防滑前后对比"},
                ),
                DirectionDTO(hypothesis=HypothesisDTO(direction_name="耐热烤箱手套", estimated_score=80)),
            ],
        )
        payload = _serialize_hypothesis(result)
        assert payload["product_images"] == ["https://images.example/main.jpg"]
        assert payload["product_price"] == "$10.92"
        assert payload["product_rating"] == "4.7"
        assert payload["product_review_count"] == "414"
        assert payload["keyword_pack"] == ["pizza cutter accessories"]
        assert [item["score"] for item in payload["structured_directions"]] == [91, 80]
        first = payload["structured_directions"][0]
        assert first["motivation_evidence"] == "披萨在烤盘上滑动"
        assert first["keywords"]["amazon"] == "pizza cutting board non slip"
        assert first["deep_arguments"] == {"user_rationale": "稳定披萨"}
        assert first["delivery_checklist"] == {"bundling_display": "展示防滑前后对比"}

- [ ] **Step 2：运行测试并确认失败**

Run: .venv\Scripts\python -m pytest backend/tests/test_analysis_runner.py::test_serialize_hypothesis_preserves_workbench_fields_without_rescoring -v

Expected: FAIL，缺少 product_images 或方向详细字段。

- [ ] **Step 3：最小扩展序列化**

在 structured_directions 每项加入：

    "motivation_evidence": d.hypothesis.motivation_evidence,
    "keywords": dict(d.hypothesis.keywords),
    "deep_arguments": dict(d.deep_arguments),
    "delivery_checklist": dict(d.delivery_checklist),

在结果级加入：

    "product_images": list(result.product.images),
    "product_price": result.product.price,
    "product_rating": result.product.rating,
    "product_review_count": result.product.review_count,
    "keyword_pack": list(result.keyword_pack),

不得修改 scores、avg_score、directions_summary、sections 或方向数组顺序。

- [ ] **Step 4：运行序列化测试**

Run: .venv\Scripts\python -m pytest backend/tests/test_analysis_runner.py -v

Expected: PASS。

- [ ] **Step 5：提交**

    git add backend/application/analysis_runner.py backend/tests/test_analysis_runner.py
    git commit -m "feat: expose result workbench fields"

## Task 2：生成只读历史摘要

**Files:**
- Create: backend/application/result_highlights.py
- Create: backend/tests/test_result_highlights.py
- Modify: backend/api/schemas/jobs.py:66-82
- Modify: backend/api/routes/jobs.py:101-137
- Modify: backend/tests/test_jobs_api.py

- [ ] **Step 1：写摘要纯函数失败测试**

创建 backend/tests/test_result_highlights.py：

    from backend.application.result_highlights import extract_result_highlights

    def test_extracts_actual_highest_scoring_direction():
        payload = {
            "product_title": "Pizza Cutter",
            "product_images": ["https://images.example/main.jpg"],
            "structured_directions": [
                {"name": "方向甲", "score": 70, "type": "便利型", "keywords": {}},
                {"name": "防滑披萨切割垫", "score": 91, "type": "低成本附加", "keywords": {"en": "non slip pizza cutting mat"}},
            ],
        }
        result = extract_result_highlights(payload)
        assert result["product_title"] == "Pizza Cutter"
        assert result["product_image"] == "https://images.example/main.jpg"
        assert result["top_direction_name"] == "防滑披萨切割垫"
        assert result["top_direction_score"] == 91.0
        assert result["top_direction_keywords"] == {"en": "non slip pizza cutting mat"}

    def test_uses_primary_model_when_only_nested_payload_has_highlights():
        payload = {"models": {
            "gpt": {"product_title": "Primary", "structured_directions": [{"name": "Primary Direction", "score": 88}]},
            "deepseek": {"product_title": "Secondary", "structured_directions": [{"name": "Secondary Direction", "score": 99}]},
        }}
        result = extract_result_highlights(payload)
        assert result["product_title"] == "Primary"
        assert result["top_direction_name"] == "Primary Direction"

    def test_returns_empty_highlights_for_old_payload():
        assert extract_result_highlights(None) == {}
        result = extract_result_highlights({"grade": "A"})
        assert result["product_title"] is None
        assert result["top_direction_name"] is None
        assert result["top_direction_keywords"] == {}

- [ ] **Step 2：运行测试并确认模块不存在**

Run: .venv\Scripts\python -m pytest backend/tests/test_result_highlights.py -v

Expected: FAIL，result_highlights 模块尚不存在。

- [ ] **Step 3：实现确定性摘要提取**

创建 backend/application/result_highlights.py：

    from __future__ import annotations
    from typing import Any

    def _primary(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("structured_directions") or payload.get("product_title"):
            return payload
        models = payload.get("models")
        if isinstance(models, dict) and isinstance(models.get("gpt"), dict):
            return models["gpt"]
        return payload

    def _number(value: Any) -> float | None:
        return float(value) if isinstance(value, (int, float)) else None

    def extract_result_highlights(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        source = _primary(payload)
        images = source.get("product_images")
        product_image = images[0] if isinstance(images, list) and images and isinstance(images[0], str) else None
        raw = source.get("structured_directions")
        directions = [item for item in raw or [] if isinstance(item, dict)]
        scored = [item for item in directions if _number(item.get("score")) is not None]
        top = max(scored, key=lambda item: _number(item.get("score")) or 0) if scored else {}
        keywords = top.get("keywords")
        return {
            "product_title": source.get("product_title") or None,
            "product_image": product_image,
            "top_direction_name": top.get("name") or None,
            "top_direction_keywords": dict(keywords) if isinstance(keywords, dict) else {},
            "top_direction_score": _number(top.get("score")),
            "top_direction_type": top.get("type") or None,
        }

    __all__ = ["extract_result_highlights"]

- [ ] **Step 4：扩展列表 Schema 和路由**

向 JobSummary 加入：

    product_title: str | None = None
    product_image: str | None = None
    top_direction_name: str | None = None
    top_direction_keywords: dict[str, str] = Field(default_factory=dict)
    top_direction_score: float | None = None
    top_direction_type: str | None = None

在 jobs.py 导入 extract_result_highlights；现有 grade/score 逻辑之后执行：

    for field, value in extract_result_highlights(result_payload).items():
        setattr(summary, field, value)

- [ ] **Step 5：写列表 API 测试**

在 backend/tests/test_jobs_api.py 构造 completed job，result_payload 含 product_images 和一个 91 分方向，断言 items[0] 的 product_title、product_image、top_direction_name、top_direction_score、top_direction_keywords 与原值一致。另构造 failed/None payload，断言响应成功且摘要为空。

- [ ] **Step 6：运行摘要和 API 测试**

Run: .venv\Scripts\python -m pytest backend/tests/test_result_highlights.py backend/tests/test_jobs_api.py -v

Expected: PASS。

- [ ] **Step 7：提交**

    git add backend/application/result_highlights.py backend/api/schemas/jobs.py backend/api/routes/jobs.py backend/tests/test_result_highlights.py backend/tests/test_jobs_api.py
    git commit -m "feat: expose job history highlights"

## Task 3：建立前端类型、查询词、搜索和时间工具

**Files:**
- Modify: frontend/lib/api/types.ts
- Create: frontend/lib/api/search.ts
- Create: frontend/lib/result-workbench.ts
- Create: frontend/lib/job-time.ts
- Create: frontend/tests/search-api-client.test.ts
- Create: frontend/tests/result-workbench.test.ts
- Create: frontend/tests/job-time.test.ts

- [ ] **Step 1：写查询词与最高分失败测试**

创建 frontend/tests/result-workbench.test.ts：

    import { expect, it } from "vitest";
    import { directionQuery, highestDirection, splitDirectionName } from "@/lib/result-workbench";

    it("prefers saved amazon keyword and keeps deterministic fallbacks", () => {
      expect(directionQuery({ name: "防滑垫 (Non-Slip Mat)", keywords: { en: "non slip mat", amazon: "pizza cutting board non slip" } })).toBe("pizza cutting board non slip");
      expect(directionQuery({ name: "防滑垫 (Non-Slip Mat)", keywords: { en: "non slip mat" } })).toBe("non slip mat");
      expect(directionQuery({ name: "防滑垫 (Non-Slip Mat)", keywords: {} })).toBe("Non-Slip Mat");
    });

    it("selects highest score without mutating input", () => {
      const input = [{ name: "A", score: 70 }, { name: "B", score: 91 }];
      expect(highestDirection(input)?.name).toBe("B");
      expect(input.map((item) => item.name)).toEqual(["A", "B"]);
    });

    it("splits an existing bilingual name", () => {
      expect(splitDirectionName("防滑垫 (Non-Slip Mat)")).toEqual({ zh: "防滑垫", en: "Non-Slip Mat" });
    });

- [ ] **Step 2：写北京时间失败测试**

创建 frontend/tests/job-time.test.ts：

    import { expect, it } from "vitest";
    import { beijingDateKey, formatBeijingTime, formatDuration } from "@/lib/job-time";

    it("uses Asia/Shanghai for display and date grouping", () => {
      expect(formatBeijingTime("2026-07-27T13:37:06Z")).toBe("21:37");
      expect(beijingDateKey("2026-07-27T16:30:00Z")).toBe("2026-07-28");
    });

    it("formats duration and invalid values explicitly", () => {
      expect(formatDuration("2026-07-27T13:37:06Z", "2026-07-27T14:09:23Z")).toBe("32分17秒");
      expect(formatDuration("invalid", "2026-07-27T14:09:23Z")).toBe("时间不可用");
    });

- [ ] **Step 3：运行测试并确认失败**

Run: npm test -- --run tests/result-workbench.test.ts tests/job-time.test.ts（工作目录 frontend）

Expected: FAIL，工具模块尚不存在。

- [ ] **Step 4：扩展类型并实现工具**

StructuredDirection 新增可选 motivation_evidence、keywords、deep_arguments、delivery_checklist。ModelResult 和 JobResultPayload 新增可选 product_url、product_images、product_price、product_rating、product_review_count、keyword_pack。JobSummary 新增 Task 2 六个可选字段。新增 SearchProduct 与 SearchResponse 类型，对应后端 search.py 的 title、url、price、rating、review_count、image。

frontend/lib/result-workbench.ts 的确定性实现：

    export function splitDirectionName(name: string) {
      const match = name.trim().match(/^(.*?)\s*[（(]([A-Za-z][^()（）]*)[)）]\s*$/);
      return match ? { zh: match[1].trim(), en: match[2].trim() } : { zh: name.trim(), en: "" };
    }

    export function directionQuery(direction: { name: string; keywords?: Record<string, string> }) {
      return direction.keywords?.amazon?.trim()
        || direction.keywords?.en?.trim()
        || splitDirectionName(direction.name).en;
    }

    export function highestDirection<T extends { score?: number }>(directions: T[]) {
      return directions.reduce<T | undefined>((best, item) =>
        !best || (item.score ?? -Infinity) > (best.score ?? -Infinity) ? item : best, undefined);
    }

frontend/lib/job-time.ts 使用 Intl.DateTimeFormat 的 timeZone: "Asia/Shanghai" 与 formatToParts 构造 HH:mm 和 YYYY-MM-DD；formatDuration 用两个有效时间戳的毫秒差返回 X分Y秒 或 X小时Y分Z秒，非法或负差值返回 时间不可用。

- [ ] **Step 5：写并实现搜索客户端**

测试 mock global fetch，断言 searchWalmart("pizza cutting board non slip") 请求 http://localhost:8000/api/v1/search、method POST、JSON body 精确为 keyword。实现：

    import { apiFetch } from "./client";
    import type { SearchResponse } from "./types";

    export function searchWalmart(keyword: string): Promise<SearchResponse> {
      return apiFetch<SearchResponse>("/search", { method: "POST", body: { keyword } });
    }

- [ ] **Step 6：运行新前端基础测试**

Run: npm test -- --run tests/result-workbench.test.ts tests/job-time.test.ts tests/search-api-client.test.ts（工作目录 frontend）

Expected: PASS。

- [ ] **Step 7：提交**

    git add frontend/lib/api/types.ts frontend/lib/api/search.ts frontend/lib/result-workbench.ts frontend/lib/job-time.ts frontend/tests/search-api-client.test.ts frontend/tests/result-workbench.test.ts frontend/tests/job-time.test.ts
    git commit -m "feat: add workbench data helpers"

## Task 4：实现方向研究工作台和主品展示

**Files:**
- Create: frontend/components/jobs/product-media.tsx
- Create: frontend/components/jobs/direction-list.tsx
- Create: frontend/components/jobs/direction-detail.tsx
- Modify: frontend/components/jobs/result-analysis-module.tsx
- Modify: frontend/app/jobs/[jobId]/page.tsx
- Modify: frontend/app/results/page.tsx
- Create: frontend/tests/result-workbench-ui.test.tsx
- Modify: frontend/tests/job-detail.test.tsx

- [ ] **Step 1：写工作台交互失败测试**

创建 frontend/tests/result-workbench-ui.test.tsx，构造 70 分方向甲和 91 分方向乙，渲染 ResultAnalysisModule 后断言：

    expect(screen.getByRole("button", { name: /方向乙/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("heading", { name: "方向乙" })).toBeInTheDocument();
    expect(screen.getByText("模型建议关键词")).toBeInTheDocument();

点击方向甲后断言方向甲成为当前项、右侧标题和深度论证切换，且两个方向仍各出现一次于列表中。加入旧数据测试：structuredDirections 为空但 sections 存在时，显示“历史结果暂无结构化方向”和现有 ResultSections 内容，而不是抛异常。

- [ ] **Step 2：写主品媒体失败测试**

在同一测试文件渲染有图片和无图片的 ProductMedia：

    expect(screen.getByRole("img", { name: "Pizza Cutter" })).toHaveAttribute("src", "https://images.example/main.jpg");

触发图片 error 后断言“图片加载失败”；无 src 时根据 emptyLabel 断言“历史无图”。

- [ ] **Step 3：运行测试并确认组件缺失**

Run: npm test -- --run tests/result-workbench-ui.test.tsx（工作目录 frontend）

Expected: FAIL，ProductMedia、DirectionList 或新工作台行为尚不存在。

- [ ] **Step 4：实现稳定图片区域**

frontend/components/jobs/product-media.tsx 接受 src、alt、emptyLabel、className。用 useState 记录加载失败；容器使用固定 aspect-square 或明确 width/height，img 使用 object-contain。无 src 显示 emptyLabel，onError 后显示“图片加载失败”。不要用假图或其他商品图回填。

- [ ] **Step 5：实现左侧方向列表**

DirectionList props：directions、activeName、onSelect。使用副本按 score 降序排序，按钮内显示两位排名、splitDirectionName(name).zh、type、motivation、evidence_level、score；当前项设置 aria-current="true"。桌面端容器使用 max-height 与 overflow-y-auto，移动端使用横向 overflow-x-auto。列表不得写回或重排传入数组。

- [ ] **Step 6：实现方向详情**

DirectionDetail props：direction、sections。标题同时显示 splitDirectionName 的 zh 与 en；指标网格显示 type、motivation、cost、strategy、stickiness、evidence_level。deep_arguments 和 delivery_checklist 用 Object.entries 保持原对象顺序，数组值用列表显示，其他值转为字符串。motivation_evidence 单独标记为“原始动机证据”。字段缺失显示“-”，不得生成文案。

- [ ] **Step 7：重组 ResultAnalysisModule**

扩展 props：

    interface ResultAnalysisModuleProps {
      sections?: Section[];
      structuredDirections?: StructuredDirection[];
      productTitle?: string;
      productUrl?: string;
      productImages?: string[];
      productPrice?: string;
      productRating?: string;
      productReviewCount?: string;
      keywordPack?: string[];
    }

初始化 activeName 为 highestDirection(structuredDirections)?.name，并在模型切换导致方向集合改变时，如果原 activeName 不存在则选择新最高分。页面顺序为主品带、四个标签按钮、双栏方向研究区。

方向研究区由 DirectionList + DirectionDetail 组成。商品与证据标签使用现有 sections 中“商品分析”“证据表”“策略判断”章节；关键词包逐项显示 keywordPack，空数组显示“当前结果没有保存关键词包”。旧数据无 structuredDirections 时渲染现有 ResultSections。四个标签为“方向研究”“商品与证据”“关键词包”“交叉验证”；前三个标签按上述规则显示，“交叉验证”在 Task 6 接入真实原文，在此之前显示“当前任务没有交叉验证结果”。

- [ ] **Step 8：把结果字段传入两个入口**

在 frontend/app/jobs/[jobId]/page.tsx 与 frontend/app/results/page.tsx 的 ResultAnalysisModule 调用处传入 activeResult 对应的 product_title、product_url、product_images、product_price、product_rating、product_review_count、keyword_pack。主品字段必须取 activeResult，顶层 payload 只作为旧双模型兼容回退。将任务详情主容器从 max-w-2xl 改为 max-w-[1500px]，但 judgment 与 batch 现有模块保持原组件和行为。

- [ ] **Step 9：运行工作台和详情页测试**

Run: npm test -- --run tests/result-workbench-ui.test.tsx tests/job-detail.test.tsx（工作目录 frontend）

Expected: PASS，既有排队、失败、下载和旧结果测试仍通过。

- [ ] **Step 10：提交**

    git add frontend/components/jobs/product-media.tsx frontend/components/jobs/direction-list.tsx frontend/components/jobs/direction-detail.tsx frontend/components/jobs/result-analysis-module.tsx frontend/app/jobs/[jobId]/page.tsx frontend/app/results/page.tsx frontend/tests/result-workbench-ui.test.tsx frontend/tests/job-detail.test.tsx
    git commit -m "feat: build result research workbench"

## Task 5：实现按方向的平台核验

**Files:**
- Create: frontend/components/jobs/platform-search-panel.tsx
- Modify: frontend/components/jobs/direction-detail.tsx
- Modify: frontend/components/jobs/result-analysis-module.tsx
- Modify: frontend/tests/result-workbench-ui.test.tsx

- [ ] **Step 1：写四种搜索状态失败测试**

在 result-workbench-ui.test.tsx 使用 MSW 处理 POST /api/v1/search，验证初始显示“待核验”；点击“核验 Walmart”后显示加载态，成功后显示“平台已返回”和“相似候选（未确认精准）”，并展示真实标题、URL 与图片。返回 results: [] 时显示“无结果”；返回 502 detail 时显示“搜索失败”和可读错误。断言页面中不存在“精准匹配”。

加入方向隔离测试：搜索方向乙后切到方向甲，方向甲仍是“待核验”；再切回方向乙，已有结果仍在。

- [ ] **Step 2：写关键词操作失败测试**

mock navigator.clipboard.writeText，点击“复制关键词”后断言收到 directionQuery 的值。断言 Amazon 链接为：

    https://www.amazon.com/s?k=pizza%20cutting%20board%20non%20slip

无查询词方向的按钮 disabled，并显示“暂无可核验关键词”。

- [ ] **Step 3：运行测试并确认失败**

Run: npm test -- --run tests/result-workbench-ui.test.tsx（工作目录 frontend）

Expected: FAIL，PlatformSearchPanel 尚不存在。

- [ ] **Step 4：实现搜索面板**

PlatformSearchPanel 接受 direction。用 direction.name 作为 Map key，在组件父级保存：

    type SearchState =
      | { status: "idle" }
      | { status: "loading" }
      | { status: "success"; results: SearchProduct[] }
      | { status: "empty" }
      | { status: "error"; message: string };

点击时只调用 searchWalmart(directionQuery(direction))。成功非空显示“平台已返回”；每张商品卡固定图片尺寸，标签固定为“平台实际返回”“相似候选（未确认精准）”。空数组显示“无结果”，异常显示“搜索失败”。不得自动分析标题或写“精准匹配”。

Amazon 只使用 encodeURIComponent(query) 构建链接并 target="_blank"、rel="noreferrer"。复制按钮调用 navigator.clipboard.writeText(query)，提供 aria-label 和短暂“已复制”状态。

- [ ] **Step 5：在 DirectionDetail 接入面板**

将 searchStates 和 setSearchState 提升到 ResultAnalysisModule，使切换方向时状态保留；将当前方向状态和更新回调传给 DirectionDetail，再传给 PlatformSearchPanel。方向或模型集合变化时只保留仍存在方向的 Map 项，不触发自动搜索。

- [ ] **Step 6：运行搜索交互测试**

Run: npm test -- --run tests/result-workbench-ui.test.tsx tests/search-api-client.test.ts（工作目录 frontend）

Expected: PASS。

- [ ] **Step 7：提交**

    git add frontend/components/jobs/platform-search-panel.tsx frontend/components/jobs/direction-detail.tsx frontend/components/jobs/result-analysis-module.tsx frontend/tests/result-workbench-ui.test.tsx
    git commit -m "feat: add on-demand platform verification"

## Task 6：保真排版交叉验证原文

**Files:**
- Create: frontend/lib/cross-review-format.ts
- Create: frontend/tests/cross-review-format.test.ts
- Modify: frontend/components/jobs/cross-review-panel.tsx
- Modify: frontend/components/jobs/result-analysis-module.tsx
- Modify: frontend/app/jobs/[jobId]/page.tsx
- Modify: frontend/app/results/page.tsx
- Modify: frontend/tests/job-detail.test.tsx

- [ ] **Step 1：写保真解析失败测试**

创建 frontend/tests/cross-review-format.test.ts：

    import { expect, it } from "vitest";
    import { formatCrossReview, joinCrossReviewBlocks } from "@/lib/cross-review-format";

    it("preserves every original character while grouping blocks", () => {
      const raw = "结论\n1. 优点\n原始说明\n\n- 风险一\n- 风险二";
      const blocks = formatCrossReview(raw);
      expect(joinCrossReviewBlocks(blocks)).toBe(raw);
      expect(blocks.some((block) => block.kind === "heading")).toBe(true);
      expect(blocks.some((block) => block.kind === "list")).toBe(true);
    });

    it("falls back to one text block for unstructured content", () => {
      const raw = "没有结构但必须原样保留";
      expect(formatCrossReview(raw)).toEqual([{ kind: "text", raw }]);
    });

- [ ] **Step 2：运行并确认工具缺失**

Run: npm test -- --run tests/cross-review-format.test.ts（工作目录 frontend）

Expected: FAIL。

- [ ] **Step 3：实现可逆分块**

CrossReviewBlock 只保存 kind 与 raw，不 cleanLabel、不 trim、不替换字符。按换行及空行扫描，识别 Markdown 标题行、数字编号行和以短横线或项目符号开头的行为 heading/list，其余为 text；分隔换行必须保存在前一块 raw 或独立 text 块。joinCrossReviewBlocks 只执行 blocks.map(b => b.raw).join("")，测试保证完全等于输入。

- [ ] **Step 4：改造 CrossReviewPanel 和结果页复用**

ReviewText 使用 formatCrossReview 渲染，不再调用 cleanLabel。heading 使用 font-medium，list 使用 whitespace-pre-wrap，text 使用 whitespace-pre-wrap leading-relaxed。错误项仍直接展示 review.error。向 ResultAnalysisModule 增加 crossReview、models 可选 props；“交叉验证”标签在有数据时渲染 CrossReviewPanel，无数据时显示明确空状态。任务详情页和独立结果页删除外部重复展示及 CROSS_REVIEW_LABELS/手写展示，统一把原 crossReview、models 传入 ResultAnalysisModule。触发交叉验证按钮仍保留在任务详情顶部，行为不变。

- [ ] **Step 5：增加组件保真断言并运行**

在 job-detail.test.tsx 构造包含双换行、编号和项目符号的 raw，展开交叉验证后断言完整片段都存在，并通过容器 textContent 与原 raw 做只忽略 DOM 标签、不忽略字符的拼接比较。

Run: npm test -- --run tests/cross-review-format.test.ts tests/job-detail.test.tsx（工作目录 frontend）

Expected: PASS。

- [ ] **Step 6：提交**

    git add frontend/lib/cross-review-format.ts frontend/tests/cross-review-format.test.ts frontend/components/jobs/cross-review-panel.tsx frontend/components/jobs/result-analysis-module.tsx frontend/app/jobs/[jobId]/page.tsx frontend/app/results/page.tsx frontend/tests/job-detail.test.tsx
    git commit -m "feat: format cross review without rewriting"

## Task 7：锁定现有 Walmart 搜索接口行为

**Files:**
- Create: backend/tests/test_search_api.py
- Modify only if a test exposes a defect: backend/api/routes/search.py

- [ ] **Step 1：写请求校验测试**

用 create_app 和 ASGITransport 请求 POST /api/v1/search，body 为 {"keyword": "   "}，断言 400 且 detail.code 为 INVALID_KEYWORD。此测试不启动浏览器，因为校验应先于 new_context。

- [ ] **Step 2：写成功映射测试**

创建 FakeBrowser、FakeContext、FakePage。FakePage.evaluate 返回一个包含 title、url、price、rating、review_count、image 的商品列表；断言 API 原样返回，并断言 page.goto URL 为 https://www.walmart.com/search?q=non+slip+mat、page.close 和 context.close 均执行。

- [ ] **Step 3：写失败和无结果测试**

让 FakePage.evaluate 返回 []，断言响应 200 且 JSON 为 {"results": []}，以便前端显示“无结果”。再让 goto 抛 RuntimeError("network down")，断言响应 502、detail.code 为 SEARCH_FAILED，且 message 可读；两种情况都断言 finally 关闭 page/context。另让 page.title 返回包含 robot 的标题，验证反爬失败走相同结构化错误。

- [ ] **Step 4：运行搜索路由测试**

Run: .venv\Scripts\python -m pytest backend/tests/test_search_api.py -v

Expected: 初次运行时空结果测试 FAIL，因为现有路由把空数组转换成 502；其余测试用于确认现有行为。

- [ ] **Step 5：让正常空结果保持正常响应**

在 backend/api/routes/search.py 删除以下分支：

    if not results:
        raise Exception("No products found on the page")

保留 SearchResponse(results=results) 的正常返回，因此空数组成为 200。不得改变搜索 URL、EXTRACT_JS、返回字段或网络异常的 502 处理。重新运行：

Run: .venv\Scripts\python -m pytest backend/tests/test_search_api.py -v

Expected: PASS。

- [ ] **Step 6：提交搜索回归保护**

    git add backend/tests/test_search_api.py backend/api/routes/search.py
    git commit -m "test: cover walmart search states"

如果 search.py 未修改，git add 只暂存测试文件。

## Task 8：重构历史记录为时间与匹配摘要视图

**Files:**
- Modify: frontend/components/history/job-table.tsx
- Modify: frontend/app/history/page.tsx
- Modify: frontend/tests/batch-history.test.tsx

- [ ] **Step 1：扩展历史测试夹具**

在 frontend/tests/batch-history.test.tsx 的成功任务中加入：

    created_at: "2026-07-27T13:37:06Z",
    updated_at: "2026-07-27T14:09:23Z",
    product_title: "BUSATIA Blade Guard Pizza Cutter Rocker",
    product_image: null,
    top_direction_name: "防滑披萨切割垫 (Non-Slip Pizza Cutting Mat)",
    top_direction_keywords: { en: "non slip pizza cutting mat" },
    top_direction_score: 91,
    top_direction_type: "低成本价值附加",
    score: 77.6,

失败任务使用不同 created_at/updated_at，摘要字段为空。

- [ ] **Step 2：写历史摘要失败测试**

渲染 HistoryPage 后断言成功任务显示“21:37 开始”“22:09 完成”“32分17秒”“BUSATIA Blade Guard Pizza Cutter Rocker”“防滑披萨切割垫”“non slip pizza cutting mat”“方向分 91”“综合 77.6”和“历史无图”。失败任务显示“结束”时间、错误摘要和“没有评分”，不捏造方向。

- [ ] **Step 3：写日期分组与现有操作测试**

用 vi.setSystemTime 固定北京时间 2026-07-27 23:00，构造今天、昨天和更早任务，断言组标题分别为“今天 · 2026年7月27日”“昨天 · 2026年7月26日”“2026年7月25日”。保留并继续断言分页、模式/状态筛选、失败重试、批量选择和下载按钮行为。

- [ ] **Step 4：运行历史测试并确认失败**

Run: npm test -- --run tests/batch-history.test.tsx（工作目录 frontend）

Expected: FAIL，现有表格没有时间与摘要列。

- [ ] **Step 5：实现按北京时间分组**

JobTable 使用 beijingDateKey(job.created_at) 分组；组内保持 API 返回顺序，scoreSort 启用时只对当前页全量排序后再分组。显示标签用当前北京时间 dateKey 比较，今天/昨天使用固定前缀，否则只显示完整日期。不得通过字符串截断 UTC 时间实现分组。

- [ ] **Step 6：重建桌面行与移动布局**

桌面列固定为：选择、匹配时间、任务与主品、最高分辅品方向、结果、状态、操作。

- 匹配时间：created_at 为开始，completed/failed 的 updated_at 为完成/结束，并显示 formatDuration；running 显示“已运行”，queued 不显示虚假结束。
- 任务与主品：ProductMedia 使用 44x44 稳定尺寸；product_image 为空显示“历史无图”；旁边显示 job.name 与 product_title。
- 方向：top_direction_name、directionQuery({name, keywords})；空值显示“未生成匹配结果”。
- 结果：top_direction_score 标为“方向分”，score 标为“综合”，top_direction_type 为辅助文字。
- 操作：保留现有查看、重试、批量 JSON/Excel 下载和分页。

在小于 lg 断点时隐藏表头，每行用 CSS grid 自动转为单列/双列语义块；不复制第二套数据或事件处理。每个值设置 min-w-0、break-words 或 line-clamp，不能依赖横向滚动阅读。

- [ ] **Step 7：更新历史页标题区**

frontend/app/history/page.tsx 保留 HistoryFilters 与现有查询参数，标题下加入“按匹配时间回看主品、最高分辅品方向和任务结果”，右侧明确“时间显示：北京时间 UTC+8”。页面最大宽度 1500px。

- [ ] **Step 8：运行历史回归测试**

Run: npm test -- --run tests/batch-history.test.tsx tests/accessibility.test.tsx（工作目录 frontend）

Expected: PASS。

- [ ] **Step 9：提交**

    git add frontend/components/history/job-table.tsx frontend/app/history/page.tsx frontend/tests/batch-history.test.tsx
    git commit -m "feat: show timed match history"

## Task 9：应用排版并完成全量和视觉验收

**Files:**
- Modify: frontend/app/globals.css
- Modify: frontend/tests/accessibility.test.tsx
- Create: frontend/e2e/result-workbench.spec.ts
- Create: docs/verification/result-workbench-history.md

- [ ] **Step 1：写全局排版失败断言**

在 frontend/tests/accessibility.test.tsx 读取 document.body 计算样式或直接渲染 app shell，断言 font-family 包含 Microsoft YaHei UI，body font-size 为 14px 或更大，letter-spacing 为 0px。工作台测试补充仅图标按钮都有 aria-label，所有商品 img 有非空 alt。

- [ ] **Step 2：应用已批准的排版规则**

在 globals.css 的 body 加入：

    font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif;
    font-size: 14px;
    letter-spacing: 0;
    line-height: 1.6;

新增 .analysis-copy { line-height: 1.7; } 与 .keyword-text { font-family: Consolas, "SFMono-Regular", monospace; font-size: 13px; }。保留现有颜色变量和 --radius: 6px；新组件不得使用 rounded-xl/2xl。

- [ ] **Step 3：写桌面与移动 Playwright 场景**

frontend/e2e/result-workbench.spec.ts 用 page.route mock：

- 完成任务 ff03dd2a-7a22-4c79-9d36-e62f150b37fa，21:37:06Z 至 22:09:23Z。
- 主品 BUSATIA Blade Guard Pizza Cutter Rocker，真实测试图片 URL。
- 两个方向，最高为防滑披萨切割垫 / Non-Slip Pizza Cutting Mat，方向分 91，综合分 77.6。
- Walmart search 返回 Silicone Baking Pastry Dough Mat。
- 历史列表返回同一任务。

测试：打开任务详情，默认方向为 91 分项；主品图、关键词和指标可见；点击核验后只出现“平台已返回”“相似候选（未确认精准）”，页面不存在“精准匹配”；切换方向正常。打开历史页验证北京时间、32分17秒、主品到方向摘要和历史无图状态。

每个页面断言：

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow).toBe(false);

同一文件在 desktop 与 mobile 项目运行；移动端额外点击方向横向选择器并确认详情标题可见。

- [ ] **Step 4：运行后端全量测试**

Run: .venv\Scripts\python -m pytest backend/tests tests -v（项目根目录）

Expected: PASS，0 failed。

- [ ] **Step 5：运行前端单元测试、类型检查和构建**

工作目录 frontend，依次运行：

    npm test -- --run
    npm run typecheck
    npm run build

Expected: 三条命令均 exit 0；Vitest 0 failed；TypeScript 0 errors；Next.js production build 成功。

- [ ] **Step 6：运行桌面和移动 E2E**

Run: npx playwright test e2e/result-workbench.spec.ts --project=desktop --project=mobile（工作目录 frontend）

Expected: 两个项目全部 PASS。失败时查看 test-results 的截图/trace，修复重叠、溢出、不可点击或图片回退问题后重跑完整命令。

- [ ] **Step 7：连接当前本地服务做真实任务只读核验**

确认 http://localhost:8000/api/v1/jobs/ff03dd2a-7a22-4c79-9d36-e62f150b37fa 返回 completed。打开 http://localhost:3000/jobs/ff03dd2a-7a22-4c79-9d36-e62f150b37fa，核对主品标题、最高方向、方向分 91、综合分 77.6、北京时间 21:37 至 22:09。手动点击 Walmart 核验；返回商品时只确认真实标题/图/链接与未确认精准标签，不把是否有返回当成精准判定。

若该本地数据库中任务已不存在，在验证文档记录“真实任务不可用”，但不得用虚构数据声称真实验证通过；mock E2E 仍作为确定性回归证据。

- [ ] **Step 8：记录验证证据**

创建 docs/verification/result-workbench-history.md，逐项记录实际执行命令、日期、退出码、测试数量、真实任务是否可用，以及 Playwright 截图/trace 路径。不得预填通过；只有命令实际成功后写 PASS。

- [ ] **Step 9：检查最终差异和敏感文件**

    git status --short
    git diff --check
    git check-ignore -v .env backend/.env backend/.api-config.key logs output .venv frontend/node_modules .superpowers

Expected: 只有本计划列出的源代码、测试和验证文档变更；敏感与生成目录继续被忽略。既有基线文件的旧尾随空白不作为本功能新增问题，但所有本轮新增差异必须通过 diff --check。

- [ ] **Step 10：提交最终排版与验证**

    git add frontend/app/globals.css frontend/tests/accessibility.test.tsx frontend/e2e/result-workbench.spec.ts docs/verification/result-workbench-history.md
    git commit -m "test: verify result workbench and history"

## 验收映射

- 数据不改写：Task 1、2、6。
- 主品真实图片和缺图状态：Task 1、4、8。
- 原始方向关键词与平台核验边界：Task 1、3、5、7。
- 双栏工作台与减少纵向展开：Task 4。
- 交叉验证原文完整：Task 6。
- 北京时间、耗时和主品到辅品摘要：Task 2、3、8。
- 中文字体、低眩光界面和移动端无重叠：Task 9。
- Git 分阶段回滚：每个 Task 的独立提交步骤。
