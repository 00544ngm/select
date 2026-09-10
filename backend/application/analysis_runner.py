from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("analysis_runner")

from app.core.exceptions import ProductTypeGateError
from app.domain.dto import ProductDTO
from app.domain.interfaces import BrowserManager, LLMClient
from app.domain.product_url import extract_product_id
from app.infrastructure.storage import BundleResultStore
from app.infrastructure.storage.excel_exporter import (
    export_hypothesis_to_excel,
    export_judgment_to_excel,
)
from app.services.complement_evidence_service import ComplementEvidenceService
from app.services.hypothesis_service import HypothesisService
from app.services.judgment_service import JudgmentService
from app.services.market_evidence_service import MarketEvidenceService
from app.services.product_service import ProductService
from app.services.product_type_reviewer import (
    ProductTypeReview,
    ProductTypeReviewer,
    ReviewStatus,
)
from backend.application.result_quality import (
    summarize_directions,
    validate_hypothesis_payload,
)


@dataclass
class ArtifactInfo:
    kind: str
    path: str
    size: int = 0
    checksum: str = ""


@dataclass
class RunnerResult:
    result_payload: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactInfo] = field(default_factory=list)


class AnalysisRunner:
    """Orchestrates analysis jobs using existing app/ domain services."""

    def __init__(
        self,
        store: BundleResultStore | None = None,
        excel_dir: str | Path | None = None,
    ) -> None:
        self._store = store or BundleResultStore()
        self._excel_dir = Path(excel_dir) if excel_dir else Path("output/bundling")

    @staticmethod
    async def start_browser(browser: BrowserManager) -> None:
        await browser.start()

    @staticmethod
    async def stop_browser(browser: BrowserManager) -> None:
        try:
            await browser.stop()
        except Exception as error:  # noqa: BLE001 - cleanup must not replace task outcome
            logger.warning("Browser cleanup failed: %s", type(error).__name__)

    async def run_hypothesis(
        self,
        url: str,
        *,
        browser: BrowserManager,
        llm: LLMClient,
        llm_secondary: LLMClient | None = None,
        expected_model_version: str | None = None,
        provider: str = "",
        provider_model: str = "",
        secondary_provider: str = "",
        secondary_provider_model: str = "",
        report_progress: Callable[[int], Awaitable[None]] | None = None,
        product_service_factory: Callable[[BrowserManager], Any] | None = None,
        product: ProductDTO | None = None,
        browser_started: bool = False,
    ) -> RunnerResult:
        factory = product_service_factory or ProductService
        if not browser_started:
            await browser.start()
        try:
            product_service = factory(browser)
            hypothesis_context = "/".join(
                value for value in (provider, provider_model) if value
            )
            hypothesis_service = HypothesisService(
                llm, provider_context=hypothesis_context
            )

            if report_progress:
                await report_progress(5)
            product = product or await product_service.get_product(url)
            product_type_review = await ProductTypeReviewer(llm).review(
                product, role="main product"
            )
            _raise_if_food(product_type_review)
            if report_progress:
                await report_progress(35)

            result, result2 = await self._run_dual(
                hypothesis_service.generate(
                    product,
                    expected_model_version=expected_model_version,
                ),
                (
                    HypothesisService(
                        llm_secondary,
                        provider_context="/".join(
                            value
                            for value in (secondary_provider, secondary_provider_model)
                            if value
                        ),
                    ).generate(
                        product,
                        expected_model_version=expected_model_version,
                    )
                    if llm_secondary
                    else None
                ),
                report_progress,
            )
            result.provider = provider
            result.provider_model = provider_model
            if result2 is not None:
                result2.provider = secondary_provider
                result2.provider_model = secondary_provider_model

            market_evidence = MarketEvidenceService()
            await market_evidence.verify_result(result, browser)
            if result2 is not None:
                await market_evidence.verify_result(result2, browser)

            payload = _serialize_hypothesis(result)
            _apply_quality_fields(result, payload)
            if result2 is not None:
                payload2 = _serialize_hypothesis(result2)
                _apply_quality_fields(result2, payload2)
                payload = _wrap_models(payload, payload2)
                payload["product_summary"] = _build_product_summary(product)
            payload["product_type_review"] = _serialize_product_type_review(
                product_type_review
            )
            validate_hypothesis_payload(
                payload, expected_model_version=expected_model_version
            )
            artifacts = []

            json_path = self._store.save_hypothesis(result)
            excel_name = json_path.stem + ".xlsx"
            excel_path = self._excel_dir / excel_name
            export_hypothesis_to_excel(result, excel_path)
            artifacts.append(ArtifactInfo(kind="json", path=str(json_path)))
            artifacts.append(ArtifactInfo(kind="excel", path=str(excel_path)))

            if result2 is not None:
                json_path2 = self._store.save_hypothesis(result2, suffix="_deepseek")
                excel_name2 = json_path2.stem + ".xlsx"
                excel_path2 = self._excel_dir / excel_name2
                export_hypothesis_to_excel(result2, excel_path2)
                artifacts.append(ArtifactInfo(kind="json_deepseek", path=str(json_path2)))
                artifacts.append(ArtifactInfo(kind="excel_deepseek", path=str(excel_path2)))

            if report_progress:
                await report_progress(100)

            return RunnerResult(result_payload=payload, artifacts=artifacts)
        finally:
            if not browser_started:
                await self.stop_browser(browser)

    async def scrape_hypothesis_product(
        self,
        url: str,
        *,
        browser: BrowserManager,
        product_service_factory: Callable[[BrowserManager], Any] | None = None,
        verification_status: Callable[[bool], Awaitable[None]] | None = None,
        browser_started: bool = False,
    ) -> ProductDTO:
        """Fetch and validate the main product before model attempts begin."""
        products = await self.scrape_products(
            [url],
            browser=browser,
            product_service_factory=product_service_factory,
            verification_status=verification_status,
            browser_started=browser_started,
        )
        return products[0]

    async def scrape_products(
        self,
        urls: list[str],
        *,
        browser: BrowserManager,
        product_service_factory: Callable[[BrowserManager], Any] | None = None,
        verification_status: Callable[[bool], Awaitable[None]] | None = None,
        browser_started: bool = False,
    ) -> list[ProductDTO]:
        """Fetch and validate all product pages before model attempts begin."""
        if not browser_started:
            await browser.start()
        try:
            service = (
                product_service_factory(browser)
                if product_service_factory is not None
                else ProductService(
                    browser,
                    verification_status=verification_status,
                )
            )
            return [await service.get_product(url) for url in urls]
        finally:
            if not browser_started:
                await self.stop_browser(browser)

    async def run_judgment(
        self,
        a_url: str,
        b_urls: list[str],
        *,
        browser: BrowserManager,
        llm: LLMClient,
        llm_secondary: LLMClient | None = None,
        report_progress: Callable[[int], Awaitable[None]] | None = None,
        product_service_factory: Callable[[BrowserManager], Any] | None = None,
        product_a: ProductDTO | None = None,
        products_b: list[ProductDTO] | None = None,
        browser_started: bool = False,
    ) -> RunnerResult:
        factory = product_service_factory or ProductService
        if not browser_started:
            await browser.start()
        try:
            product_service = factory(browser)
            judgment_service = JudgmentService(llm)

            if report_progress:
                await report_progress(5)
            product_a = product_a or await product_service.get_product(a_url)
            reviewer = ProductTypeReviewer(llm)
            product_a_review = await reviewer.review(product_a, role="main product")
            _raise_if_food(product_a_review)
            if report_progress:
                await report_progress(15)

            supplied_products_b = products_b
            products_b = []
            rejected_b_products: list[dict[str, Any]] = []
            for i, url in enumerate(b_urls):
                pb = (
                    supplied_products_b[i]
                    if supplied_products_b is not None
                    else await product_service.get_product(url)
                )
                review = await reviewer.review(pb, role="auxiliary product")
                if review.status is ReviewStatus.CONFIRMED_FOOD:
                    rejected_b_products.append(
                        {
                            "url": pb.url,
                            "title": pb.title,
                            "review": _serialize_product_type_review(review),
                            "action": "rejected_food_product",
                        }
                    )
                else:
                    products_b.append(pb)
                b_progress = 15 + int(50 * (i + 1) / len(b_urls))
                if report_progress:
                    await report_progress(b_progress)

            if not products_b:
                if report_progress:
                    await report_progress(100)
                return RunnerResult(
                    result_payload={
                        "mode": "judgment",
                        "result_status": "completed_no_eligible_b_products",
                        "message": "所有 B 品均被食品准入门槛过滤，未调用审判模型。",
                        "grade": None,
                        "score": None,
                        "product_type_review": _serialize_product_type_review(
                            product_a_review
                        ),
                        "rejected_b_products": rejected_b_products,
                    }
                )

            result, result2 = await self._run_dual(
                judgment_service.judge(product_a, products_b, []),
                JudgmentService(llm_secondary).judge(product_a, products_b, []) if llm_secondary else None,
                report_progress,
                single_progress=90,
            )

            payload = _serialize_judgment(
                result, product_a=product_a, products_b=products_b
            )
            payload["product_type_review"] = _serialize_product_type_review(
                product_a_review
            )
            payload["rejected_b_products"] = rejected_b_products
            evidence_records = await asyncio.gather(
                *(
                    ComplementEvidenceService(llm).analyze(product_a, product_b)
                    for product_b in products_b
                )
            )
            payload["complement_evidence"] = {
                "per_b_product": {
                    record.product_title: record.to_dict()
                    for record in evidence_records
                }
            }
            artifacts = []

            json_path = self._store.save_judgment(
                result, product_a=product_a, products_b=products_b
            )
            excel_name = json_path.stem + ".xlsx"
            excel_path = self._excel_dir / excel_name
            export_judgment_to_excel(result, excel_path)
            artifacts.append(ArtifactInfo(kind="json", path=str(json_path)))
            artifacts.append(ArtifactInfo(kind="excel", path=str(excel_path)))

            if result2 is not None:
                payload2 = _serialize_judgment(
                    result2, product_a=product_a, products_b=products_b
                )
                payload = _wrap_models(payload, payload2)
                payload["product_summary"] = _build_product_summary(product_a, products_b)
                payload["product_type_review"] = _serialize_product_type_review(
                    product_a_review
                )
                payload["rejected_b_products"] = rejected_b_products
                json_path2 = self._store.save_judgment(
                    result2, product_a=product_a, products_b=products_b, suffix="_deepseek"
                )
                excel_name2 = json_path2.stem + ".xlsx"
                excel_path2 = self._excel_dir / excel_name2
                export_judgment_to_excel(result2, excel_path2)
                artifacts.append(ArtifactInfo(kind="json_deepseek", path=str(json_path2)))
                artifacts.append(ArtifactInfo(kind="excel_deepseek", path=str(excel_path2)))

            if report_progress:
                await report_progress(100)

            return RunnerResult(result_payload=payload, artifacts=artifacts)
        finally:
            if not browser_started:
                await self.stop_browser(browser)

    async def run_batch(
        self,
        urls: list[str],
        *,
        browser: BrowserManager,
        llm: LLMClient,
        llm_secondary: LLMClient | None = None,
        expected_model_version: str | None = None,
        provider: str = "",
        provider_model: str = "",
        secondary_provider: str = "",
        secondary_provider_model: str = "",
        report_progress: Callable[[int], Awaitable[None]] | None = None,
        product_service_factory: Callable[[BrowserManager], Any] | None = None,
        products: list[ProductDTO] | None = None,
        browser_started: bool = False,
    ) -> RunnerResult:
        factory = product_service_factory or ProductService
        if not browser_started:
            await browser.start()
        try:
            product_service = factory(browser)
            hypothesis_service = HypothesisService(llm)
            hs2 = HypothesisService(llm_secondary) if llm_secondary else None

            total = len(urls)
            all_results: list[list[RunnerResult]] = []
            food_blocked_count = 0
            review_count = 0

            for i, url in enumerate(urls):
                product = (
                    products[i]
                    if products is not None
                    else await product_service.get_product(url)
                )
                product_type_review = await ProductTypeReviewer(llm).review(
                    product, role="main product"
                )
                if product_type_review.status is ReviewStatus.CONFIRMED_FOOD:
                    food_blocked_count += 1
                    all_results.append(
                        [RunnerResult(result_payload={
                            "mode": "hypothesis",
                            "product": _build_product_summary(product),
                            "product_type_review": _serialize_product_type_review(
                                product_type_review
                            ),
                            "result_status": "food_blocked",
                            "message": f"商品“{product.title}”确认为食品，已跳过分析。",
                        })]
                    )
                    pct = int(100 * (i + 1) / total)
                    if report_progress:
                        await report_progress(pct)
                    continue
                if product_type_review.status in (
                    ReviewStatus.LIKELY_NON_FOOD,
                    ReviewStatus.NEEDS_REVIEW,
                ):
                    review_count += 1

                result, result2 = await self._run_dual(
                    hypothesis_service.generate(
                        product,
                        expected_model_version=expected_model_version,
                    ),
                    (
                        hs2.generate(
                            product,
                            expected_model_version=expected_model_version,
                        )
                        if hs2
                        else None
                    ),
                    None,
                )
                result.provider = provider
                result.provider_model = provider_model
                if result2 is not None:
                    result2.provider = secondary_provider
                    result2.provider_model = secondary_provider_model

                market_evidence = MarketEvidenceService()
                await market_evidence.verify_result(result, browser)
                if result2 is not None:
                    await market_evidence.verify_result(result2, browser)

                batch_items = []
                payload = _serialize_hypothesis(result)
                _apply_quality_fields(result, payload)
                if result2 is not None:
                    payload2 = _serialize_hypothesis(result2)
                    _apply_quality_fields(result2, payload2)
                    payload = _wrap_models(payload, payload2)
                    payload["product_summary"] = _build_product_summary(product)
                payload["product_type_review"] = _serialize_product_type_review(
                    product_type_review
                )
                validate_hypothesis_payload(
                    payload, expected_model_version=expected_model_version
                )
                json_path = self._store.save_hypothesis(result)
                excel_name = json_path.stem + ".xlsx"
                excel_path = self._excel_dir / excel_name
                export_hypothesis_to_excel(result, excel_path)
                batch_items.append(
                    RunnerResult(
                        result_payload=payload,
                        artifacts=[
                            ArtifactInfo(kind="json", path=str(json_path)),
                            ArtifactInfo(kind="excel", path=str(excel_path)),
                        ],
                    )
                )

                if result2 is not None:
                    batch_items[0].result_payload = payload
                    json_path2 = self._store.save_hypothesis(result2, suffix="_deepseek")
                    excel_name2 = json_path2.stem + ".xlsx"
                    excel_path2 = self._excel_dir / excel_name2
                    export_hypothesis_to_excel(result2, excel_path2)
                    batch_items[0].artifacts.append(
                        ArtifactInfo(kind="json_deepseek", path=str(json_path2))
                    )
                    batch_items[0].artifacts.append(
                        ArtifactInfo(kind="excel_deepseek", path=str(excel_path2))
                    )

                all_results.append(batch_items)

                pct = int(100 * (i + 1) / total)
                if report_progress:
                    await report_progress(pct)

            merged_results = []
            all_artifacts = []
            for items in all_results:
                for r in items:
                    merged_results.append(r.result_payload)
                    all_artifacts.extend(r.artifacts)

            return RunnerResult(
                result_payload={
                    "batch_count": total,
                    "results": merged_results,
                    "success_count": total - food_blocked_count,
                    "review_count": review_count,
                    "food_blocked_count": food_blocked_count,
                },
                artifacts=all_artifacts,
            )
        finally:
            if not browser_started:
                await self.stop_browser(browser)

    @staticmethod
    async def _run_dual(coro1, coro2, report_progress, single_progress: int = 80):
        """Run two LLM coroutines concurrently. Returns (result1, result2_or_None).

        Primary model (coro1) errors propagate. Secondary model (coro2) errors
        are swallowed — returns ``None`` for that slot on failure.

        ``single_progress`` — progress % to report when a single model completes
        (used as a heartbeat so the front-end sees movement during LLM wait).
        """
        if coro2 is None:
            result = await coro1
            if report_progress:
                await report_progress(single_progress)
            return result, None

        if report_progress:
            await report_progress(65)

        t1 = asyncio.create_task(coro1)
        t2 = asyncio.create_task(_safe_exec(coro2))
        await asyncio.wait([t1, t2])

        r1 = t1.result()
        r2 = t2.result()
        return r1, r2

    async def run_cross_review(
        self,
        llm: LLMClient,
        llm_secondary: LLMClient,
        product_summary: dict,
        reviewer_a: dict,
        reviewer_b: dict,
        output_a: dict,
        output_b: dict,
        mode: str,
    ) -> dict:
        """Run cross-review between two explicitly selected model identities.

        Each model reviews the other's output given the original product data.
        The generic shape is used for new payloads; the UI can still read legacy
        GPT/DeepSeek keys from historical jobs.
        """
        identity_a = _identity_label(reviewer_a)
        identity_b = _identity_label(reviewer_b)
        prompt_a = _build_cross_review_prompt(
            product_summary, output_b, mode, identity_a, identity_b
        )
        prompt_b = _build_cross_review_prompt(
            product_summary, output_a, mode, identity_b, identity_a
        )

        result1, result2 = await self._run_dual(
            llm.chat([{"role": "user", "content": prompt_a}]),
            llm_secondary.chat([{"role": "user", "content": prompt_b}]),
            None,
        )

        return {
            "reviewer_a": reviewer_a,
            "reviewer_b": reviewer_b,
            "results": {
                "reviewer_a_reviews_reviewer_b": {"raw": result1} if result1 else {"error": f"{identity_a} cross-review failed"},
                "reviewer_b_reviews_reviewer_a": {"raw": result2} if result2 else {"error": f"{identity_b} cross-review failed"},
            },
        }


GRADE_LABELS: dict[str, str] = {
    "low_cost_value_add": "低成本价值附加",
    "premium_bundle": "高端组合",
    "cross_category": "跨品类搭配",
    "accessory_match": "配件搭配",
    "consumable_refill": "耗材补充",
}

EVIDENCE_CATEGORY_LABELS = {
    "fbt_items": "FBT商品",
    "also_bought": "常一起购买",
    "related_search_terms": "相关搜索词",
    "negative_reviews": "差评",
    "pure_inference": "纯推理",
}

EVIDENCE_LAYER_LABELS = {
    "first_layer": "第一层",
    "second_layer": "第二层",
    "third_layer": "第三层",
}

STICKINESS_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

CATEGORY_TYPE_LABELS: dict[str, str] = {
    "low_cost_value_add": "低成本价值附加",
    "dual_star_bundle": "双爆款捆绑",
    "premium_bundle": "高端组合",
    "cross_category": "跨品类搭配",
    "accessory_match": "配件搭配",
    "consumable_refill": "耗材补充",
}

MOTIVATION_TYPE_LABELS: dict[str, str] = {
    "pain_point": "痛点解决型",
    "convenience": "便利闭环型",
    "cost_effective": "纯性价比型",
    "replacement": "补货换新型",
}

ALIGNMENT_CONCLUSION_LABELS = {
    "alignment": "对齐",
    "mismatch": "不匹配",
}

MARGIN_LABELS = {
    "healthy": "健康",
    "tight": "紧张",
}

DEEP_ARGUMENT_LABELS = {
    "user_rationale": "用户理由",
    "seller_rationale": "卖家理由",
    "urgency": "紧迫性",
    "differentiation": "差异化",
    "risk_mitigation": "风险缓解",
    "scenario_fit": "场景适配",
    "rationale_score": "用户逻辑评分",
}

DELIVERY_CHECKLIST_LABELS = {
    "bundling_display": "捆绑展示",
    "listing_highlights": "Listing亮点",
    "pricing_tactic": "定价策略",
    "launch_actions": "上架行动",
}

PRODUCT_ANALYSIS_LABELS = {
    "title": "标题",
    "price": "价格",
    "rating": "评分",
    "review_count": "评论数",
    "buyer_profile": "买家画像",
    "usage_scenario": "使用场景",
    "whats_included": "包含内容",
}

STRATEGIC_JUDGMENT_KEY_LABELS = {
    "type": "策略类型",
    "rationale": "策略理由",
}

# ── Judgment field key mappings ──────────────────────────────────────────────

ALIGNMENT_REVIEW_LABELS = {
    "product_b": "B品",
    "original_hypothesis": "原假设方向",
    "spec_match": "规格匹配",
    "price_alignment": "价格对齐",
    "function_complement": "功能互补",
    "size_fit": "形态尺寸",
    "overall_verdict": "总体结论",
}

MOTIVATION_REVIEW_LABELS = {
    "original_type": "原假设归型",
    "type_still_valid": "归型仍成立",
    "revised_type": "新归型",
    "listing_signals": "Listing信号",
    "motivation_strength": "动机强度",
}

PRICE_CALCULATION_LABELS = {
    "a_price": "A品价格",
    "b_price": "B品价格",
    "combined_price": "组合价格",
    "suggested_bundle_price": "建议捆绑价",
    "b_1688_cost": "1688成本",
    "estimated_margin": "预估毛利",
    "margin_assessment": "毛利评估",
}

VETO_CHECK_LABELS = {
    "g1_rhythm": "节奏不匹配",
    "g2_competition": "竞品冲突",
    "g3_validated": "已验证需求",
    "g4_brand_overshadow": "品牌压制",
    "g5_logistics": "物流问题",
    "g6_legal": "法律风险",
    "g7_bad_reviews": "差评超标",
    "vetoed": "被否决",
    "veto_reason": "否决原因",
}

C_SCORE_LABELS = {
    "complementarity": "互补强度",
    "ticket_lift": "客单价提升",
    "scenario_value": "场景增值",
    "pain_point_coverage": "差评覆盖",
    "total": "总分",
}

B_SCORE_LABELS = {
    "supply_maturity": "供给成熟度",
    "logistics_friendliness": "物流友好",
    "certification_barrier": "认证门槛",
    "season_window": "旺季窗口",
    "total": "总分",
}

DELIVERY_PACKAGE_LABELS = {
    "recommended_bundle_type": "推荐捆绑类型",
    "pricing_tactic": "定价策略",
    "listing_collateral": "Listing联动",
    "launch_priority": "上架优先级",
    "next_steps": "下一步行动",
}

USER_RATIONALITY_LABELS = {
    "score": "评分",
    "analysis": "分析",
    "logical_gaps": "逻辑缺口",
}

# ── Judgment enum value mappings ─────────────────────────────────────────────

MOTIVATION_STRENGTH_LABELS = {
    "strong": "强",
    "moderate": "中",
    "weak": "弱",
}

OVERALL_VERDICT_LABELS = {
    "alignment": "对齐",
    "partial_mismatch": "部分不匹配",
    "mismatch": "不匹配",
}

JUDGMENT_GRADE_LABELS = {
    "S": "S级 - 强烈推荐",
    "A": "A级 - 推荐",
    "B": "B级 - 可行",
    "C": "C级 - 不推荐",
}


def _raise_if_food(review: ProductTypeReview) -> None:
    if review.status is ReviewStatus.CONFIRMED_FOOD:
        raise ProductTypeGateError(
            code="INGESTIBLE_PRODUCT_BLOCKED",
            message=f"{review.role} 确认为食品，已阻止分析：{review.reason}",
        )


def _serialize_product_type_review(review: ProductTypeReview) -> dict[str, Any]:
    def json_value(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, tuple):
            return [json_value(item) for item in value]
        return value

    return {key: json_value(value) for key, value in asdict(review).items()}


def _map_dict_keys(d: dict, key_map: dict[str, str]) -> dict:
    """Remap top-level keys of a dict using key_map."""
    return {key_map.get(k, k): v for k, v in d.items()}


def _fmt(d: Any) -> str:
    """Format a dict/object as human-readable Chinese text."""
    if isinstance(d, dict):
        return "\n".join(f"• {k}: {_fmt(v)}" for k, v in d.items())
    if isinstance(d, list):
        return "\n".join(f"  - {_fmt(item)}" for item in d)
    return str(d)


def _serialize_hypothesis(result: Any) -> dict[str, Any]:
    accepted_scores = [
        _direction_final_score(d.hypothesis)
        for d in result.directions
        if not d.hypothesis.rejected
    ]
    top_score = max(accepted_scores) if accepted_scores else None

    directions_summary = "、".join(
        d.hypothesis.direction_name for d in result.directions[:5] if d.hypothesis.direction_name
    )
    if len(result.directions) > 5:
        directions_summary += f" 等共{len(result.directions)}个方向"

    sections = []
    if result.product_analysis:
        sections.append({"title": "商品分析", "content": _fmt(_map_dict_keys(result.product_analysis, PRODUCT_ANALYSIS_LABELS))})
    if result.evidence_table:
        mapped = {}
        for layer_key, categories in result.evidence_table.items():
            layer_label = EVIDENCE_LAYER_LABELS.get(layer_key, layer_key)
            if isinstance(categories, dict):
                mapped[layer_label] = _map_dict_keys(categories, EVIDENCE_CATEGORY_LABELS)
            else:
                mapped[layer_label] = categories
        sections.append({"title": "证据表", "content": _fmt(mapped)})
    if result.strategic_judgment:
        sj = dict(result.strategic_judgment)
        if "type" in sj and sj["type"] in GRADE_LABELS:
            sj["type"] = GRADE_LABELS[sj["type"]]
        sj = _map_dict_keys(sj, STRATEGIC_JUDGMENT_KEY_LABELS)
        sections.append({"title": "策略判断", "content": _fmt(sj)})
    if result.directions:
        direction_items = []
        for i, d in enumerate(result.directions):
            dir_header = (
                f"类型: {CATEGORY_TYPE_LABELS.get(d.hypothesis.category_type, d.hypothesis.category_type)} | "
                f"动机: {MOTIVATION_TYPE_LABELS.get(d.hypothesis.motivation_type, d.hypothesis.motivation_type)} - {d.hypothesis.motivation_evidence}\n"
                f"证据级: {EVIDENCE_LAYER_LABELS.get(d.hypothesis.evidence_level, d.hypothesis.evidence_level)} | "
                f"1688成本: {d.hypothesis.estimated_cost_1688} | "
                f"定价策略: {d.hypothesis.price_strategy} | "
                f"粘性: {STICKINESS_LABELS.get(d.hypothesis.stickiness, d.hypothesis.stickiness)}\n"
                f"评分: {d.hypothesis.estimated_score}"
            )
            sub_items = []
            if d.deep_arguments:
                sub_items.append({
                    "title": "深度论证",
                    "content": _fmt(_map_dict_keys(d.deep_arguments, DEEP_ARGUMENT_LABELS)),
                })
            if d.delivery_checklist:
                sub_items.append({
                    "title": "交付清单",
                    "content": _fmt(_map_dict_keys(d.delivery_checklist, DELIVERY_CHECKLIST_LABELS)),
                })
            direction_items.append({
                "title": f"方向{i+1}: {d.hypothesis.direction_name}",
                "content": dir_header,
                "children": sub_items if sub_items else None,
            })
        sections.append({"title": "假设方向", "children": direction_items})
    if result.keyword_pack:
        sections.append({"title": "关键词包", "content": "、".join(result.keyword_pack)})

    raw_grade = result.strategic_judgment.get("type", "") if result.strategic_judgment else ""
    dir_scores = [
        _direction_final_score(d.hypothesis)
        for d in result.directions
        if _direction_final_score(d.hypothesis)
    ]
    structured_directions = [
        {
            "name": d.hypothesis.direction_name,
            "score": _direction_final_score(d.hypothesis),
            "type": CATEGORY_TYPE_LABELS.get(d.hypothesis.category_type, d.hypothesis.category_type),
            "motivation": MOTIVATION_TYPE_LABELS.get(d.hypothesis.motivation_type, d.hypothesis.motivation_type),
            "motivation_evidence": d.hypothesis.motivation_evidence,
            "evidence_level": EVIDENCE_LAYER_LABELS.get(d.hypothesis.evidence_level, d.hypothesis.evidence_level),
            "cost": d.hypothesis.estimated_cost_1688,
            "strategy": d.hypothesis.price_strategy,
            "stickiness": STICKINESS_LABELS.get(d.hypothesis.stickiness, d.hypothesis.stickiness),
            "keywords": dict(d.hypothesis.keywords),
            "deep_arguments": dict(d.deep_arguments),
            "delivery_checklist": dict(d.delivery_checklist),
            "model_version": d.hypothesis.model_version,
            "canonical_name": d.hypothesis.canonical_name,
            "primary_relation": d.hypothesis.primary_relation,
            "secondary_relations": list(d.hypothesis.secondary_relations),
            "purchase_chain": dict(d.hypothesis.purchase_chain),
            "lifecycle_stage": d.hypothesis.lifecycle_stage,
            "consistency": dict(d.hypothesis.consistency),
            "consumer_simulation": d.hypothesis.consumer_simulation,
            "consumer_simulation_reason": d.hypothesis.consumer_simulation_reason,
            "score_breakdown": dict(d.hypothesis.score_breakdown),
            "score_inputs": dict(d.hypothesis.score_inputs),
            "raw_score": d.hypothesis.raw_score,
            "score_cap": d.hypothesis.score_cap,
            "final_score": _direction_final_score(d.hypothesis),
            "recommendation_level": d.hypothesis.recommendation_level,
            "evidence": dict(d.hypothesis.evidence),
            "rejected": d.hypothesis.rejected,
            "rejection_codes": list(d.hypothesis.rejection_codes),
            "invalid_source_fact_ids": list(d.hypothesis.invalid_source_fact_ids),
            "source_fact_ids": list(d.hypothesis.source_fact_ids),
            "incompatibility_reason": d.hypothesis.incompatibility_reason,
            "duplicate_function_reason": d.hypothesis.duplicate_function_reason,
            "safety_risk": d.hypothesis.safety_risk,
            "risk_analysis": d.hypothesis.risk_analysis,
            "missing_evidence": list(d.hypothesis.missing_evidence),
            "food_filter_status": d.hypothesis.food_filter_status,
            "food_filter_reason": d.hypothesis.food_filter_reason,
            "relation_reasons": list(d.hypothesis.relation_reasons),
            "extended_scenarios": list(d.hypothesis.extended_scenarios),
            "assumptions": list(d.hypothesis.assumptions),
            "confidence_level": d.hypothesis.confidence_level,
            "stickiness_score": d.hypothesis.stickiness_score or _direction_final_score(d.hypothesis),
            "purchase_direction": d.hypothesis.purchase_direction,
            "direction_reason": d.hypothesis.direction_reason,
            "product_type_status": d.hypothesis.product_type_status,
            "product_type_review": (
                dict(d.hypothesis.product_type_review)
                if d.hypothesis.product_type_review is not None
                else None
            ),
            "compatibility_status": d.hypothesis.compatibility_status,
            "duplication_status": d.hypothesis.duplication_status,
            "safety_status": d.hypothesis.safety_status,
            "execution_status": d.hypothesis.execution_status,
            "hold_reasons": list(d.hypothesis.hold_reasons),
            "decision_action": d.hypothesis.decision_action,
            "evidence_records": list(d.hypothesis.evidence.get("market", {}).get("records", [])),
            "market_evidence_status": _market_evidence_status(d.hypothesis.evidence),
            "rejection_reason": _rejection_reason(d.hypothesis),
        }
        for d in result.directions
    ]
    quality = summarize_directions(structured_directions)
    return {
        "mode": "hypothesis",
        "grade": GRADE_LABELS.get(raw_grade, raw_grade),
        "grade_reason": result.strategic_judgment.get("rationale", "") if result.strategic_judgment else "",
        "score": top_score,
        "score_reason": (
            f"{result.model_version}，按最终分排序；各方向分数: "
            f"{', '.join(str(s) for s in dir_scores)}"
            if dir_scores
            else ""
        ),
        "directions": directions_summary,
        "sections": sections,
        "directions_count": len(result.directions),
        "structured_directions": structured_directions,
        "result_status": quality.result_status,
        "result_message": quality.result_message,
        "raw_direction_count": quality.raw_direction_count,
        "qualified_direction_count": quality.qualified_direction_count,
        "hold_direction_count": quality.hold_direction_count,
        "rejected_direction_count": quality.rejected_direction_count,
        "rejection_summary": quality.rejection_summary,
        "audit_performed": result.audit_performed,
        "audit_reason": result.audit_reason,
        "initial_raw_direction_count": result.initial_raw_direction_count,
        "audit_raw_direction_count": result.audit_raw_direction_count,
        "audit_outcome": result.audit_outcome,
        "provider": result.provider,
        "provider_model": result.provider_model,
        "product_id": result.product.product_id or extract_product_id(result.product.url),
        "product_title_zh": (
            result.product_analysis.get("title", "")
            if isinstance(result.product_analysis.get("title", ""), str)
            else ""
        ),
        "product_title": result.product.title,
        "product_url": result.product.url,
        "product_images": list(result.product.images),
        "product_price": result.product.price,
        "product_rating": result.product.rating,
        "product_review_count": result.product.review_count,
        "keyword_pack": list(result.keyword_pack),
        "model_version": result.model_version,
        "product_profile": dict(result.product_profile),
    }


def _apply_quality_fields(result: Any, payload: dict[str, Any]) -> None:
    """Copy the serialized quality summary into the DTO before persistence."""
    for quality_field in (
        "result_status",
        "result_message",
        "raw_direction_count",
        "qualified_direction_count",
        "hold_direction_count",
        "rejected_direction_count",
        "rejection_summary",
    ):
        setattr(result, quality_field, payload[quality_field])


def _direction_final_score(hypothesis: Any) -> float:
    """Use V2 final score and fall back to the legacy score-only field."""
    final_score = getattr(hypothesis, "final_score", 0.0)
    if isinstance(final_score, (int, float)) and (
        final_score > 0 or getattr(hypothesis, "rejected", False)
    ):
        return float(final_score)
    legacy_score = getattr(hypothesis, "estimated_score", 0.0)
    return float(legacy_score) if isinstance(legacy_score, (int, float)) else 0.0


def _map_per_product_fields(
    section: dict,
    key_map: dict[str, str],
    value_map: dict[str, dict[str, str]] | None = None,
) -> dict:
    """Map field keys and enum values in each per_b_product entry of a judgment section."""
    if not isinstance(section, dict):
        return section
    per_b = section.get("per_b_product", {})
    if not isinstance(per_b, dict):
        return section
    mapped_per_b = {}
    for product_name, fields in per_b.items():
        if isinstance(fields, dict):
            fields = dict(fields)
            renamed = _map_dict_keys(fields, key_map)
            if value_map:
                for orig_key, val_labels in value_map.items():
                    if orig_key in fields and str(fields[orig_key]) in val_labels:
                        new_key = key_map.get(orig_key, orig_key)
                        renamed[new_key] = val_labels[str(fields[orig_key])]
            mapped_per_b[product_name] = renamed
        else:
            mapped_per_b[product_name] = fields
    return {"各B品详情": mapped_per_b}


def _translate_alignment_item(item: dict[str, Any]) -> dict[str, Any]:
    """Translate keys and enum values in an alignment review item."""
    translated = {}
    for k, v in item.items():
        new_key = ALIGNMENT_REVIEW_LABELS.get(k, k)
        translated[new_key] = v
    for orig_key, new_key in [("overall_verdict", "总体结论")]:
        if orig_key in item and str(item[orig_key]) in OVERALL_VERDICT_LABELS:
            translated[new_key] = OVERALL_VERDICT_LABELS[str(item[orig_key])]
    for key in ("conclusion", "alignment", "result"):
        if key in item and str(item[key]) in ALIGNMENT_CONCLUSION_LABELS:
            new_key = ALIGNMENT_REVIEW_LABELS.get(key, key)
            translated[new_key] = ALIGNMENT_CONCLUSION_LABELS[str(item[key])]
    for key in ("margin", "margin_assessment", "margin_health"):
        if key in item and str(item[key]) in MARGIN_LABELS:
            new_key = ALIGNMENT_REVIEW_LABELS.get(key, key)
            translated[new_key] = MARGIN_LABELS[str(item[key])]
    return translated


def _serialize_b_products(products_b: list[ProductDTO]) -> list[dict[str, Any]]:
    """Persist the real identity of every auxiliary product used in judgment."""
    return [
        {
            "title": product.title,
            "product_id": product.product_id or extract_product_id(product.url),
            "product_url": product.url,
            "product_image": product.images[0] if product.images else None,
        }
        for product in products_b
    ]


def _serialize_judgment(
    result: Any,
    product_a: ProductDTO | None = None,
    products_b: list[ProductDTO] | None = None,
) -> dict[str, Any]:
    sections = []
    if hasattr(result, "alignment_review") and result.alignment_review:
        mapped = [_translate_alignment_item(item) for item in result.alignment_review]
        sections.append({"title": "对比分析", "content": _fmt(mapped)})
    if hasattr(result, "motivation_review") and result.motivation_review:
        mapped = _map_per_product_fields(result.motivation_review, MOTIVATION_REVIEW_LABELS,
                                          value_map={"motivation_strength": MOTIVATION_STRENGTH_LABELS})
        sections.append({"title": "动机审查（消费者心理）", "content": _fmt(mapped)})
    if hasattr(result, "price_calculation") and result.price_calculation:
        mapped = _map_per_product_fields(result.price_calculation, PRICE_CALCULATION_LABELS,
                                          value_map={"margin_assessment": MARGIN_LABELS})
        sections.append({"title": "价格计算", "content": _fmt(mapped)})
    if hasattr(result, "veto_check") and result.veto_check:
        mapped = _map_per_product_fields(result.veto_check, VETO_CHECK_LABELS)
        sections.append({"title": "否决审查", "content": _fmt(mapped)})
    if hasattr(result, "c_score") and result.c_score:
        mapped = _map_per_product_fields(result.c_score, C_SCORE_LABELS)
        sections.append({"title": "C组合价值分", "content": _fmt(mapped)})
    if hasattr(result, "b_score") and result.b_score:
        mapped = _map_per_product_fields(result.b_score, B_SCORE_LABELS)
        sections.append({"title": "B跨境执行分", "content": _fmt(mapped)})
    if hasattr(result, "delivery_package") and result.delivery_package:
        mapped = _map_per_product_fields(result.delivery_package, DELIVERY_PACKAGE_LABELS)
        sections.append({"title": "交付方案", "content": _fmt(mapped)})
    if hasattr(result, "user_rationality") and result.user_rationality:
        mapped = _map_per_product_fields(result.user_rationality, USER_RATIONALITY_LABELS)
        sections.append({"title": "用户理性评分", "content": _fmt(mapped)})

    # Derive grade/score reason from c_score, b_score and veto_check
    grade_reason = ""
    score_reason = ""
    veto_parts: list[str] = []
    c_avg: int | None = None
    b_avg: int | None = None

    vc = getattr(result, "veto_check", None) or {}
    if isinstance(vc, dict):
        per_b = vc.get("per_b_product", {})
        if isinstance(per_b, dict):
            for b_name, check in per_b.items():
                if isinstance(check, dict) and check.get("vetoed"):
                    veto_parts.append(f"{b_name}: {check.get('veto_reason', '') or ''}")

    def _avg_total(section: Any) -> int | None:
        if not isinstance(section, dict):
            return None
        per_b = section.get("per_b_product", {})
        if not isinstance(per_b, dict):
            return None
        totals = []
        for scores in per_b.values():
            if isinstance(scores, dict) and "total" in scores:
                try:
                    totals.append(float(scores["total"]))
                except (ValueError, TypeError):
                    pass
        return round(sum(totals) / len(totals)) if totals else None

    c_avg = _avg_total(getattr(result, "c_score", None))
    b_avg = _avg_total(getattr(result, "b_score", None))

    if veto_parts:
        grade_reason = f"触发否决：{'；'.join(veto_parts)}"
    elif c_avg is not None and b_avg is not None:
        grade_reason = f"C组合价值分{c_avg}、B跨境执行分{b_avg}"
    else:
        grade_reason = ""

    if c_avg is not None and b_avg is not None:
        score_reason = f"综合C组合价值分({c_avg})和B跨境执行分({b_avg})"

    payload = {
        "mode": "judgment",
        "grade": JUDGMENT_GRADE_LABELS.get(result.final_grade, result.final_grade),
        "grade_reason": grade_reason,
        "score": result.priority_score,
        "score_reason": score_reason,
        "directions": "",
        "sections": sections,
    }
    if product_a is not None:
        payload.update(
            {
                "product_id": product_a.product_id or extract_product_id(product_a.url),
                "product_title": product_a.title,
                "product_title_zh": getattr(result, "product_title_zh", "") or "",
                "product_url": product_a.url,
                "product_images": list(product_a.images),
                "product_price": product_a.price,
                "product_rating": product_a.rating,
                "product_review_count": product_a.review_count,
            }
        )
    if products_b is not None:
        payload["b_products"] = _serialize_b_products(products_b)
    return payload








def _build_product_summary(product_a, products_b: list | None = None) -> dict:
    """Build a product summary dict from ProductDTO(s) for cross-review."""
    summary = {
        "title": product_a.title,
        "price": product_a.price,
        "rating": product_a.rating,
        "review_count": product_a.review_count,
        "bullet_points": product_a.bullet_points[:5] if product_a.bullet_points else [],
        "description": (product_a.description or "")[:500],
        "review_snippets": product_a.review_snippets[:8] if product_a.review_snippets else [],
        "attributes": dict(product_a.attributes) if product_a.attributes else {},
    }
    if products_b:
        summary["b_products"] = [
            {
                "title": p.title,
                "price": p.price,
                "rating": p.rating,
                "review_count": p.review_count,
                "bullet_points": p.bullet_points[:5] if p.bullet_points else [],
            }
            for p in products_b
        ]
    return summary


def _identity_label(identity: dict) -> str:
    display_name = str(identity.get("display_name") or identity.get("provider") or "selected provider")
    protocol = str(identity.get("api_protocol") or "openai")
    model = str(identity.get("model") or "unknown model")
    return f"{display_name} ({protocol}) / {model}"


def _build_cross_review_prompt(
    product_summary: dict,
    other_output: dict,
    mode: str,
    reviewer_model: str,
    reviewed_model: str,
) -> str:
    """Build a prompt asking a model to review the other model's analysis."""
    import json

    product_str = json.dumps(product_summary, ensure_ascii=False, indent=2)
    other_str = json.dumps(other_output, ensure_ascii=False, indent=2)

    mode_label = "假设分析（A+B 捆绑搭配）" if mode == "hypothesis" else "对比判断（验证 B 品搭配假设）"

    return f"""请对一份 Walmart 跨境电商{mode_label}结果进行交叉评审。

评审模型：{reviewer_model}
被评审模型：{reviewed_model}

请用中文和第三人称真实模型名称作答。不要输出寒暄、角色声明或任务复述；禁止使用 reviewer_a、reviewer_b、GPT、“对方模型”等模糊代称。只依据下方原始商品数据和被评审结果，不得虚构证据、评论、市场需求或商品事实；证据不足时必须明确写“无法判断”。避免重复论述，每一项只保留最关键的依据和动作。

必须严格使用以下 Markdown 结构：

## 结论摘要
结论类型：认可 / 部分认可 / 不认可 / 无法判断
一句话结论：用一句话概括判断和最关键理由

## 认可之处
- 只列有原始商品数据或被评审结果支持的判断

## 存在的问题
- 分别指出逻辑、证据、市场需求或场景匹配问题

## 关键分歧
- 明确写出 {reviewer_model} 与 {reviewed_model} 的分歧对象和评审方判断

## 修正建议
- 给出可直接修改原分析的动作

## 最终推荐
- 按优先级列出保留、降级或新增方向

===== 原始商品数据 =====
{product_str}

===== {reviewed_model} 的分析结果 =====
{other_str}"""


async def _safe_exec(coro):
    """Run a coroutine and return None on failure instead of raising."""
    try:
        return await coro
    except BaseException as exc:
        logger.exception("Secondary model failed: %s", type(exc).__name__)
        return None


def _market_evidence_status(evidence: dict) -> str:
    market = evidence.get("market") if isinstance(evidence, dict) else None
    if not isinstance(market, dict):
        return "待验证"
    status = str(market.get("status", "")).strip()
    if status == "completed" and int(market.get("matched_count", 0) or 0) > 0:
        return "已验证"
    if status == "completed":
        return "部分验证"
    return "待验证"


def _rejection_reason(hypothesis: Any) -> str:
    if not hypothesis.rejected:
        return ""
    reasons = list(hypothesis.rejection_codes)
    if hypothesis.food_filter_reason:
        reasons.append(hypothesis.food_filter_reason)
    return "；".join(dict.fromkeys(reasons))


def _wrap_models(primary: dict, secondary: dict) -> dict:
    """Wrap two model results into a dual-model payload.

    The primary (GPT) result keeps its top-level keys for backward compat,
    and both results are stored under ``models``.
    """
    title = primary.get("product_title") or secondary.get("product_title", "")
    return {
        "mode": primary.get("mode", ""),
        "product_title": title,
        "product_url": primary.get("product_url") or secondary.get("product_url", ""),
        **primary,
        "models": {
            "gpt": primary,
            "deepseek": secondary,
        },
    }


__all__ = ["AnalysisRunner", "ArtifactInfo", "RunnerResult"]
