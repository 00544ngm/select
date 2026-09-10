from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import (
    BrowserTargetClosedError,
    ModelContractError,
    ProductTypeGateError,
)
from app.domain.dto import (
    DirectionDTO,
    HypothesisDTO,
    HypothesisResultDTO,
    ProductDTO,
)
from backend.application.analysis_runner import (
    AnalysisRunner,
    RunnerResult,
    _build_cross_review_prompt,
    _serialize_b_products,
    _serialize_hypothesis,
)
from backend.application.result_quality import ResultQualityError


class FakeBrowser:
    started = False
    stopped = False
    new_page_called = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def new_page(self):
        self.new_page_called = True


@pytest.mark.asyncio
async def test_scrape_hypothesis_product_closes_browser_after_success():
    browser = FakeBrowser()
    product = ProductDTO(
        url="https://www.walmart.com/ip/example/12345",
        product_id="12345",
        title="Scraped product",
    )

    class ProductServiceStub:
        def __init__(self, _browser):
            pass

        async def get_product(self, _url):
            return product

    result = await AnalysisRunner().scrape_hypothesis_product(
        product.url,
        browser=browser,
        product_service_factory=ProductServiceStub,
    )

    assert result is product
    assert browser.started is True
    assert browser.stopped is True


@pytest.mark.asyncio
async def test_runner_preserves_original_error_when_browser_cleanup_also_fails():
    browser = FakeBrowser()

    async def failing_stop():
        raise RuntimeError("cleanup failed")

    browser.stop = failing_stop

    class ProductServiceStub:
        def __init__(self, _browser):
            pass

        async def get_product(self, _url):
            raise BrowserTargetClosedError()

    with pytest.raises(BrowserTargetClosedError):
        await AnalysisRunner().scrape_hypothesis_product(
            "https://www.walmart.com/ip/example/12345",
            browser=browser,
            product_service_factory=ProductServiceStub,
        )


def test_serialize_b_products_preserves_each_auxiliary_identity():
    products = [
        ProductDTO(
            url="https://www.walmart.com/ip/auxiliary-one/111",
            product_id="111",
            title="Auxiliary One",
            images=["https://images.example/auxiliary-one.jpg"],
        ),
        ProductDTO(
            url="https://www.amazon.com/dp/B0AUX22222",
            title="Auxiliary Two",
            images=[],
        ),
    ]

    assert _serialize_b_products(products) == [
        {
            "title": "Auxiliary One",
            "product_id": "111",
            "product_url": "https://www.walmart.com/ip/auxiliary-one/111",
            "product_image": "https://images.example/auxiliary-one.jpg",
        },
        {
            "title": "Auxiliary Two",
            "product_id": "B0AUX22222",
            "product_url": "https://www.amazon.com/dp/B0AUX22222",
            "product_image": None,
        },
    ]


class FakeLLM:
    def __init__(self, result: dict | None = None) -> None:
        self._result = result or {
            "model_version": "combination_model_v2.0",
            "product_profile": {
                "title_zh": "测试商品",
                "core_purchase_job": "完成测试任务",
                "lifecycle_steps": ["use"],
                "included_items": [],
                "compatibility_constraints": [],
                "safety_constraints": [],
                "primary_search_terms": ["test product"],
            },
            "keyword_pack": [],
            "directions": [],
        }

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        return ""

    async def chat_structured(
        self, messages: list[dict], output_schema: dict, **kwargs: Any
    ) -> dict:
        return self._result


class EvidenceAwareFakeLLM(FakeLLM):
    def __init__(self, judgment_result: dict, evidence_result: dict) -> None:
        super().__init__(judgment_result)
        self._evidence_result = evidence_result

    async def chat_structured(
        self, messages: list[dict], output_schema: dict, **kwargs: Any
    ) -> dict:
        if kwargs.get("schema_name") == "complement_evidence":
            return self._evidence_result
        return self._result


class FakeProductService:
    def __init__(self, browser: object = None) -> None:
        self.browser = browser

    async def get_product(self, url: str) -> Any:
        from app.domain.dto import ProductDTO

        return ProductDTO(url=url, title="Water Bottle", price="$10.00")


class ReviewedProductService:
    def __init__(self, browser: object = None) -> None:
        self.browser = browser

    async def get_product(self, url: str) -> Any:
        if "/a/" in url:
            return ProductDTO(url=url, title="Water Bottle", price="$20.00")
        return ProductDTO(
            url=url,
            title="Candidate Product",
            price="$10.00",
            attributes={"product type": "camera bag"},
            review_snippets=[
                f"Review {index}: I need a matching holder to use this item properly."
                for index in range(20)
            ],
        )


class CrashingProductService:
    def __init__(self, browser: object = None) -> None:
        self.browser = browser

    async def get_product(self, url: str) -> Any:
        raise RuntimeError("scrape failed")


class TitledProductService:
    title = ""

    def __init__(self, browser: object = None) -> None:
        self.browser = browser

    async def get_product(self, url: str) -> ProductDTO:
        return ProductDTO(url=url, title=self.title, price="$10.00")


class IngestibleProductService(TitledProductService):
    title = "Vitamin Tablets Oral Supplement"


class UnknownProductService(TitledProductService):
    title = "Unclassified Novel Item"


class IngestibleAuxiliaryProductService(TitledProductService):
    async def get_product(self, url: str) -> ProductDTO:
        title = "Water Bottle" if "/a/" in url else "Dog Food"
        return ProductDTO(url=url, title=title, price="$10.00")


class FakeStore:
    def __init__(self) -> None:
        self.saved = []

    def save_hypothesis(self, result: Any, **kwargs: Any) -> Path:
        path = Path("output/bundling/hypothesis_test.json")
        self.saved.append(("hypothesis", result))
        return path

    def save_judgment(self, result: Any, **kwargs: Any) -> Path:
        path = Path("output/bundling/judgment_test.json")
        self.saved.append(("judgment", result))
        return path


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def browser() -> FakeBrowser:
    return FakeBrowser()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service_factory() -> Any:
    return lambda b: FakeProductService(b)


@pytest.mark.asyncio
async def test_runner_blocks_ingestible_main_product_before_llm(
    store: FakeStore,
) -> None:
    browser = FakeBrowser()
    llm = FakeLLM()
    llm.chat_structured = AsyncMock(wraps=llm.chat_structured)
    runner = AnalysisRunner(store=store)

    with pytest.raises(ProductTypeGateError) as caught:
        await runner.run_hypothesis(
            "https://walmart.com/ip/vitamins",
            browser=browser,
            llm=llm,
            product_service_factory=IngestibleProductService,
        )

    assert caught.value.code == "INGESTIBLE_PRODUCT_BLOCKED"
    llm.chat_structured.assert_not_awaited()
    assert browser.stopped is True
    assert store.saved == []


@pytest.mark.asyncio
async def test_runner_unknown_main_product_continues_after_reviewer_fallback(
    store: FakeStore,
) -> None:
    browser = FakeBrowser()
    llm = FakeLLM()
    llm.chat_structured = AsyncMock(wraps=llm.chat_structured)
    runner = AnalysisRunner(store=store)

    result = await runner.run_hypothesis(
        "https://walmart.com/ip/unknown",
        browser=browser,
        llm=llm,
        product_service_factory=UnknownProductService,
    )

    assert result.result_payload["product_type_review"]["status"] == "needs_review"
    assert llm.chat_structured.await_count == 2
    assert browser.stopped is True
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_runner_applies_main_product_gate_to_judgment(
    store: FakeStore,
) -> None:
    runner = AnalysisRunner(store=store)

    with pytest.raises(ProductTypeGateError) as caught:
        await runner.run_judgment(
            a_url="https://walmart.com/ip/vitamins",
            b_urls=["https://walmart.com/ip/camera-bag"],
            browser=FakeBrowser(),
            llm=FakeLLM(),
            product_service_factory=IngestibleProductService,
        )
    assert caught.value.code == "INGESTIBLE_PRODUCT_BLOCKED"


@pytest.mark.asyncio
async def test_runner_filters_ingestible_auxiliary_before_judgment_llm(
    store: FakeStore,
) -> None:
    llm = FakeLLM()
    llm.chat_structured = AsyncMock(wraps=llm.chat_structured)
    browser = FakeBrowser()

    result = await AnalysisRunner(store=store).run_judgment(
        a_url="https://walmart.com/ip/a/12345",
        b_urls=["https://walmart.com/ip/b/67890"],
        browser=browser,
        llm=llm,
        product_service_factory=IngestibleAuxiliaryProductService,
    )

    assert result.result_payload["rejected_b_products"][0]["title"] == "Dog Food"
    assert result.result_payload["grade"] is None
    llm.chat_structured.assert_not_awaited()
    assert browser.stopped is True


@pytest.mark.asyncio
async def test_runner_judges_only_non_food_b_and_keeps_food_rejection(
    store: FakeStore,
) -> None:
    class MixedBService(TitledProductService):
        async def get_product(self, url: str) -> ProductDTO:
            if "/a/" in url:
                return ProductDTO(url=url, title="Water Bottle", price="$20.00")
            if "food" in url:
                return ProductDTO(url=url, title="Dog Food", price="$10.00")
            return ProductDTO(
                url=url,
                title="Camera Bag",
                price="$10.00",
                attributes={"Product Type": "camera bag"},
            )

    llm = FakeLLM(
        {
            "alignment_review": [],
            "final_grade": "A",
            "priority_score": 80,
        }
    )
    llm.chat_structured = AsyncMock(wraps=llm.chat_structured)

    result = await AnalysisRunner(store=store).run_judgment(
        a_url="https://walmart.com/ip/a/1",
        b_urls=[
            "https://walmart.com/ip/food/2",
            "https://walmart.com/ip/camera/3",
        ],
        browser=FakeBrowser(),
        llm=llm,
        product_service_factory=MixedBService,
    )

    assert [item["title"] for item in result.result_payload["rejected_b_products"]] == [
        "Dog Food"
    ]
    judgment_calls = [
        call
        for call in llm.chat_structured.await_args_list
        if call.kwargs.get("schema_name") == "judgment_output"
    ]
    assert len(judgment_calls) == 1
    prompt = str(judgment_calls[0].kwargs.get("messages", judgment_calls[0].args))
    assert "Camera Bag" in prompt
    assert "Dog Food" not in prompt


@pytest.mark.asyncio
async def test_runner_batch_keeps_running_after_food_item(store: FakeStore) -> None:
    class MixedService(TitledProductService):
        async def get_product(self, url: str) -> ProductDTO:
            title = "Vitamin Tablets Oral Supplement" if "food" in url else "Kitchen Spatula"
            return ProductDTO(url=url, title=title, price="$10.00")

    llm = FakeLLM()
    result = await AnalysisRunner(store=store).run_batch(
        ["https://walmart.com/ip/food", "https://walmart.com/ip/spatula"],
        browser=FakeBrowser(),
        llm=llm,
        product_service_factory=MixedService,
    )

    assert result.result_payload["batch_count"] == 2
    assert result.result_payload["food_blocked_count"] == 1
    assert result.result_payload["success_count"] == 1
    assert result.result_payload["results"][0]["result_status"] == "food_blocked"
    assert result.result_payload["results"][1]["product_type_review"]["status"] in {
        "likely_non_food",
        "needs_review",
        "confirmed_non_food",
    }


def test_serialize_hypothesis_preserves_workbench_fields_without_rescoring():
    result = HypothesisResultDTO(
        product=ProductDTO(
            url="https://www.walmart.com/ip/example/123",
            product_id="123",
            title="Pizza Cutter",
            price="$10.92",
            rating="4.7",
            review_count="414",
            images=["https://images.example/main.jpg"],
        ),
        product_analysis={"title": "披萨刀切割器"},
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
                    food_filter_status="allowed",
                    food_filter_reason="non-food accessory",
                    relation_reasons=["supports the same task"],
                    extended_scenarios=[
                        {"name": "home pizza prep", "assumption": "主品用于家庭烘焙"}
                    ],
                    confidence_level="high",
                    product_type_review={
                        "status": "confirmed_non_food",
                        "source": "model",
                        "confidence": 0.96,
                        "reason": "商品描述明确为非食品配件",
                        "evidence": [
                            {
                                "source_field": "name_zh",
                                "verbatim_quote": "防滑披萨切割垫",
                            }
                        ],
                        "action": "continue",
                    },
                    keywords={
                        "en": "non slip pizza cutting mat",
                        "amazon": "pizza cutting board non slip",
                    },
                ),
                deep_arguments={"user_rationale": "稳定披萨"},
                delivery_checklist={"bundling_display": "展示防滑前后对比"},
            ),
            DirectionDTO(
                hypothesis=HypothesisDTO(
                    direction_name="耐热烤箱手套",
                    estimated_score=80,
                )
            ),
        ],
    )

    payload = _serialize_hypothesis(result)

    assert payload["product_images"] == ["https://images.example/main.jpg"]
    assert payload["product_id"] == "123"
    assert payload["product_title_zh"] == "披萨刀切割器"
    assert payload["product_price"] == "$10.92"
    assert payload["product_rating"] == "4.7"
    assert payload["product_review_count"] == "414"
    assert payload["keyword_pack"] == ["pizza cutter accessories"]
    assert [item["score"] for item in payload["structured_directions"]] == [91, 80]
    first = payload["structured_directions"][0]
    assert first["motivation_evidence"] == "披萨在烤盘上滑动"
    assert first["keywords"]["amazon"] == "pizza cutting board non slip"
    assert first["deep_arguments"] == {"user_rationale": "稳定披萨"}
    assert first["delivery_checklist"] == {
        "bundling_display": "展示防滑前后对比"
    }
    assert first["food_filter_status"] == "allowed"
    assert first["extended_scenarios"][0]["assumption"] == "主品用于家庭烘焙"
    assert first["stickiness_score"] == 91.0
    assert first["market_evidence_status"] == "待验证"
    assert first["product_type_review"]["evidence"] == [
        {
            "source_field": "name_zh",
            "verbatim_quote": "防滑披萨切割垫",
        }
    ]


def test_serialize_hypothesis_reports_actual_model_version_in_score_reason():
    result = HypothesisResultDTO(
        model_version="combination_model_v2.1",
        directions=[
            DirectionDTO(
                hypothesis=HypothesisDTO(direction_name="Filter", estimated_score=80)
            )
        ],
    )

    payload = _serialize_hypothesis(result)

    assert "combination_model_v2.1" in payload["score_reason"]


@pytest.mark.asyncio
async def test_runner_hypothesis_dispatch(
    browser: FakeBrowser, llm: FakeLLM, store: FakeStore, service_factory: Any
):
    runner = AnalysisRunner(store=store)

    result = await runner.run_hypothesis(
        url="https://www.walmart.com/ip/test/12345",
        browser=browser,
        llm=llm,
        product_service_factory=service_factory,
    )

    assert isinstance(result, RunnerResult)
    assert len(result.artifacts) == 2
    assert result.artifacts[0].kind == "json"
    assert result.artifacts[1].kind == "excel"


@pytest.mark.asyncio
async def test_runner_propagates_provider_identity_to_payload_and_storage(
    browser: FakeBrowser, store: FakeStore, service_factory: Any
):
    output = FakeLLM()._result.copy()
    output["model_version"] = "combination_model_v2.1"
    runner = AnalysisRunner(store=store)

    result = await runner.run_hypothesis(
        url="https://www.walmart.com/ip/test/12345",
        browser=browser,
        llm=FakeLLM(result=output),
        expected_model_version="combination_model_v2.1",
        provider="cattoken_claude",
        provider_model="claude-sonnet-4-6",
        product_service_factory=service_factory,
    )

    assert result.result_payload["provider"] == "cattoken_claude"
    assert result.result_payload["provider_model"] == "claude-sonnet-4-6"
    assert store.saved[0][1].provider == "cattoken_claude"
    assert store.saved[0][1].provider_model == "claude-sonnet-4-6"
    assert store.saved[0][1].result_status == "completed_no_qualified_candidates"
    assert store.saved[0][1].audit_outcome == "confirmed_no_candidates"


@pytest.mark.asyncio
async def test_dual_hypothesis_persists_distinct_secondary_provider_identity(
    browser: FakeBrowser, store: FakeStore, service_factory: Any
):
    output = {**FakeLLM()._result, "model_version": "combination_model_v2.1"}
    runner = AnalysisRunner(store=store)

    result = await runner.run_hypothesis(
        url="https://www.walmart.com/ip/test/12345",
        browser=browser,
        llm=FakeLLM(result=output),
        llm_secondary=FakeLLM(result=output),
        expected_model_version="combination_model_v2.1",
        provider="custom",
        provider_model="claude-test",
        secondary_provider="deepseek",
        secondary_provider_model="deepseek-chat",
        product_service_factory=service_factory,
    )

    primary = result.result_payload["models"]["gpt"]
    secondary = result.result_payload["models"]["deepseek"]
    assert (primary["provider"], primary["provider_model"]) == (
        "custom",
        "claude-test",
    )
    assert (secondary["provider"], secondary["provider_model"]) == (
        "deepseek",
        "deepseek-chat",
    )
    assert (store.saved[1][1].provider, store.saved[1][1].provider_model) == (
        "deepseek",
        "deepseek-chat",
    )


@pytest.mark.asyncio
async def test_dual_batch_persists_distinct_secondary_provider_identity(
    browser: FakeBrowser, store: FakeStore, service_factory: Any
):
    output = {**FakeLLM()._result, "model_version": "combination_model_v2.1"}
    runner = AnalysisRunner(store=store)

    result = await runner.run_batch(
        urls=["https://www.walmart.com/ip/test/12345"],
        browser=browser,
        llm=FakeLLM(result=output),
        llm_secondary=FakeLLM(result=output),
        expected_model_version="combination_model_v2.1",
        provider="cattoken",
        provider_model="gpt-test",
        secondary_provider="deepseek",
        secondary_provider_model="deepseek-reasoner",
        product_service_factory=service_factory,
    )

    models = result.result_payload["results"][0]["models"]
    assert (models["gpt"]["provider"], models["gpt"]["provider_model"]) == (
        "cattoken",
        "gpt-test",
    )
    assert (
        models["deepseek"]["provider"],
        models["deepseek"]["provider_model"],
    ) == ("deepseek", "deepseek-reasoner")
    assert (store.saved[1][1].provider, store.saved[1][1].provider_model) == (
        "deepseek",
        "deepseek-reasoner",
    )


@pytest.mark.asyncio
async def test_runner_validates_before_writing_artifacts(
    browser: FakeBrowser, store: FakeStore, service_factory: Any, monkeypatch
):
    output = FakeLLM()._result.copy()
    output["model_version"] = "combination_model_v2.1"
    runner = AnalysisRunner(store=store)

    def reject(_payload, *, expected_model_version):
        raise ResultQualityError("invalid result")

    monkeypatch.setattr(
        "backend.application.analysis_runner.validate_hypothesis_payload", reject
    )

    with pytest.raises(ResultQualityError):
        await runner.run_hypothesis(
            url="https://www.walmart.com/ip/test/12345",
            browser=browser,
            llm=FakeLLM(result=output),
            expected_model_version="combination_model_v2.1",
            product_service_factory=service_factory,
        )

    assert store.saved == []


@pytest.mark.asyncio
async def test_runner_judgment_dispatch(
    browser: FakeBrowser, store: FakeStore, service_factory: Any
):
    judgment_llm = FakeLLM(
        result={
            "alignment_review": [],
            "motivation_review": {},
            "price_calculation": {},
            "veto_check": {},
            "c_score": {},
            "b_score": {},
            "final_grade": "A",
            "delivery_package": {},
            "priority_score": 0.85,
        }
    )
    runner = AnalysisRunner(store=store)

    result = await runner.run_judgment(
        a_url="https://www.walmart.com/ip/a/12345",
        b_urls=["https://www.amazon.com/dp/B000000001"],
        browser=browser,
        llm=judgment_llm,
        product_service_factory=service_factory,
    )

    assert isinstance(result, RunnerResult)
    assert len(result.artifacts) == 2


@pytest.mark.asyncio
async def test_runner_attaches_evidence_without_mutating_judgment_fields(
    browser: FakeBrowser, store: FakeStore
):
    original_veto = {
        "per_b_product": {
            "Candidate Product": {
                "g1_rhythm": False,
                "g2_competition": False,
                "g3_validated": False,
                "g4_brand_overshadow": False,
                "g5_logistics": False,
                "g6_legal": False,
                "g7_bad_reviews": False,
                "vetoed": False,
                "veto_reason": "",
            }
        }
    }
    llm = EvidenceAwareFakeLLM(
        judgment_result={
            "veto_check": original_veto,
            "c_score": {"per_b_product": {"Candidate Product": {"total": 84}}},
            "b_score": {"per_b_product": {"Candidate Product": {"total": 78}}},
            "final_grade": "A",
            "priority_score": 82,
        },
        evidence_result={
            "reviews": [
                {
                    "review_index": index,
                    "is_relevant": index < 3,
                    "translation_zh": f"评论 {index} 需要配套支架",
                    "keywords": ["matching holder"] if index < 3 else [],
                    "reason": "明确表达配套需求" if index < 3 else "无关",
                    "strength": "explicit" if index < 3 else "none",
                }
                for index in range(20)
            ]
        },
    )
    runner = AnalysisRunner(store=store)

    result = await runner.run_judgment(
        a_url="https://www.walmart.com/ip/a/12345",
        b_urls=["https://www.walmart.com/ip/b/67890"],
        browser=browser,
        llm=llm,
        product_service_factory=lambda value: ReviewedProductService(value),
    )

    payload = result.result_payload
    evidence = payload["complement_evidence"]["per_b_product"]["Candidate Product"]
    assert evidence["status"] == "verified"
    assert evidence["valid_review_count"] == 20
    assert evidence["relevant_review_count"] == 3
    assert evidence["hit_rate"] == 0.15
    assert evidence["evidence"][0]["original_text"].startswith("Review 0:")
    assert payload["grade"] == "A级 - 推荐"
    assert payload["score"] == 82

    saved_judgment = next(value for kind, value in store.saved if kind == "judgment")
    assert saved_judgment.veto_check == original_veto
    assert saved_judgment.veto_check["per_b_product"]["Candidate Product"]["g3_validated"] is False


@pytest.mark.asyncio
async def test_dual_judgment_keeps_evidence_on_primary_model_only(
    browser: FakeBrowser, store: FakeStore
):
    judgment_result = {
        "veto_check": {
            "per_b_product": {
                "Candidate Product": {"g3_validated": False, "vetoed": False}
            }
        },
        "final_grade": "A",
        "priority_score": 80,
    }
    primary = EvidenceAwareFakeLLM(
        judgment_result=judgment_result,
        evidence_result={"reviews": []},
    )
    secondary = FakeLLM(judgment_result)
    runner = AnalysisRunner(store=store)

    result = await runner.run_judgment(
        a_url="https://www.walmart.com/ip/a/12345",
        b_urls=["https://www.walmart.com/ip/b/67890"],
        browser=browser,
        llm=primary,
        llm_secondary=secondary,
        product_service_factory=lambda value: ReviewedProductService(value),
    )

    assert "complement_evidence" in result.result_payload["models"]["gpt"]
    assert "complement_evidence" not in result.result_payload["models"]["deepseek"]


@pytest.mark.asyncio
async def test_runner_batch_dispatch(
    browser: FakeBrowser, llm: FakeLLM, store: FakeStore, service_factory: Any
):
    runner = AnalysisRunner(store=store)

    result = await runner.run_batch(
        urls=[
            "https://www.walmart.com/ip/a/12345",
            "https://www.walmart.com/ip/b/67890",
        ],
        browser=browser,
        llm=llm,
        product_service_factory=service_factory,
    )

    assert isinstance(result, RunnerResult)
    assert len(result.artifacts) >= 2


@pytest.mark.asyncio
async def test_runner_passes_expected_model_version_for_hypothesis_and_batch(
    browser: FakeBrowser, store: FakeStore, service_factory: Any
):
    llm = FakeLLM({**FakeLLM()._result, "model_version": "combination_model_v2.0"})
    runner = AnalysisRunner(store=store)

    with pytest.raises(ModelContractError) as hypothesis_error:
        await runner.run_hypothesis(
            url="https://www.walmart.com/ip/test/12345",
            browser=browser,
            llm=llm,
            expected_model_version="combination_model_v2.1",
            provider="custom",
            provider_model="model-x",
            product_service_factory=service_factory,
        )

    assert hypothesis_error.value.code == "MODEL_CONTRACT_MISMATCH"

    batch_browser = FakeBrowser()
    with pytest.raises(ModelContractError) as batch_error:
        await runner.run_batch(
            urls=["https://www.walmart.com/ip/test/12345"],
            browser=batch_browser,
            llm=llm,
            expected_model_version="combination_model_v2.1",
            provider="custom",
            provider_model="model-x",
            product_service_factory=service_factory,
        )

    assert batch_error.value.code == "MODEL_CONTRACT_MISMATCH"


@pytest.mark.asyncio
async def test_runner_reports_monotonic_progress(
    browser: FakeBrowser, llm: FakeLLM, store: FakeStore, service_factory: Any
):
    runner = AnalysisRunner(store=store)
    progress_values: list[int] = []

    async def report(pct: int) -> None:
        progress_values.append(pct)

    await runner.run_hypothesis(
        url="https://www.walmart.com/ip/test/12345",
        browser=browser,
        llm=llm,
        report_progress=report,
        product_service_factory=service_factory,
    )

    assert len(progress_values) >= 4
    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1]


@pytest.mark.asyncio
async def test_runner_cross_review_uses_selected_model_identities():
    runner = AnalysisRunner()
    first = FakeLLM()
    second = FakeLLM()

    result = await runner.run_cross_review(
        llm=first,
        llm_secondary=second,
        product_summary={"title": "Primary"},
        reviewer_a={"provider": "custom", "display_name": "供应商A", "api_protocol": "anthropic", "model": "model-a"},
        reviewer_b={"provider": "deepseek", "display_name": "DeepSeek", "api_protocol": "openai", "model": "deepseek-chat"},
        output_a={"score": 80},
        output_b={"score": 70},
        mode="hypothesis",
    )

    assert result["reviewer_a"]["provider"] == "custom"
    assert result["reviewer_b"]["model"] == "deepseek-chat"
    assert "reviewer_a_reviews_reviewer_b" in result["results"]


def test_cross_review_prompt_requires_structured_sections_and_real_identities():
    prompt = _build_cross_review_prompt(
        {"title": "Primary"},
        {"score": 70},
        "hypothesis",
        reviewer_model="DeepSeek (openai) / deepseek-v4-pro",
        reviewed_model="Claude (anthropic) / claude-opus-5",
    )

    for heading in (
        "## 结论摘要",
        "## 认可之处",
        "## 存在的问题",
        "## 关键分歧",
        "## 修正建议",
        "## 最终推荐",
    ):
        assert heading in prompt
    assert "结论类型：认可 / 部分认可 / 不认可 / 无法判断" in prompt
    assert "一句话结论：" in prompt
    assert "DeepSeek (openai) / deepseek-v4-pro" in prompt
    assert "Claude (anthropic) / claude-opus-5" in prompt
    assert "不要输出寒暄" in prompt
    assert "不得虚构证据" in prompt


@pytest.mark.asyncio
async def test_runner_stops_browser_after_success(
    browser: FakeBrowser, llm: FakeLLM, store: FakeStore, service_factory: Any
):
    runner = AnalysisRunner(store=store)

    await runner.run_hypothesis(
        url="https://www.walmart.com/ip/test/12345",
        browser=browser,
        llm=llm,
        product_service_factory=service_factory,
    )

    assert browser.started
    assert browser.stopped


def test_serialize_hypothesis_uses_v2_scores_and_excludes_rejected_top_score():
    result = HypothesisResultDTO(
        model_version="combination_model_v2.0",
        product_profile={"core_purchase_job": "print"},
        directions=[
            DirectionDTO(hypothesis=HypothesisDTO(
                direction_name="Matching Ink",
                estimated_score=88,
                raw_score=91,
                score_cap=89,
                final_score=89,
                recommendation_level="focus",
                evidence={"level": "E3", "market": {"matched_count": 2}},
            )),
            DirectionDTO(hypothesis=HypothesisDTO(
                direction_name="Included Funnel",
                estimated_score=100,
                raw_score=100,
                score_cap=100,
                final_score=0,
                rejected=True,
                rejection_codes=["included_item"],
            )),
        ],
    )

    payload = _serialize_hypothesis(result)

    assert payload["model_version"] == "combination_model_v2.0"
    assert payload["product_profile"] == {"core_purchase_job": "print"}
    assert payload["score"] == 89
    assert payload["structured_directions"][0]["final_score"] == 89
    assert payload["structured_directions"][1]["rejected"] is True
    assert payload["structured_directions"][1]["rejection_codes"] == ["included_item"]


def test_serialize_hypothesis_falls_back_to_legacy_score_when_v2_score_is_unset():
    result = HypothesisResultDTO(
        directions=[DirectionDTO(hypothesis=HypothesisDTO(
            direction_name="Legacy Direction",
            estimated_score=76,
        ))]
    )

    assert _serialize_hypothesis(result)["score"] == 76


@pytest.mark.parametrize(
    ("statuses", "expected_status", "expected_counts"),
    [
        (
            ["pass", "hold", "reject"],
            "completed_with_qualified_candidates",
            (1, 1, 1),
        ),
        (
            ["hold", "reject"],
            "completed_needs_evidence",
            (0, 1, 1),
        ),
        (
            ["reject"],
            "completed_no_qualified_candidates",
            (0, 0, 1),
        ),
        ([], "completed_no_qualified_candidates", (0, 0, 0)),
    ],
)
def test_serialize_hypothesis_adds_v21_result_status_and_counts(
    statuses, expected_status, expected_counts
):
    directions = []
    for index, status in enumerate(statuses):
        rejected = status == "reject"
        directions.append(
            DirectionDTO(
                hypothesis=HypothesisDTO(
                    direction_name=f"Direction {index}",
                    model_version="combination_model_v2.1",
                    primary_relation=("none" if rejected else "continuous_task"),
                    purchase_direction=("none" if rejected else "forward_dependency"),
                    product_type_status="non_food",
                    food_filter_status="allowed",
                    execution_status=status,
                    decision_action=(
                        "not_recommended" if rejected else "needs_evidence"
                    ),
                    rejected=rejected,
                    rejection_codes=["no_valid_relation"] if rejected else [],
                )
            )
        )
    result = HypothesisResultDTO(
        model_version="combination_model_v2.1",
        directions=directions,
        audit_performed=not directions,
        audit_reason="initial_v2.1_directions_empty" if not directions else "",
        initial_raw_direction_count=len(directions),
        audit_raw_direction_count=0,
        audit_outcome="confirmed_no_candidates" if not directions else "",
    )

    payload = _serialize_hypothesis(result)

    assert payload["result_status"] == expected_status
    assert (
        payload["qualified_direction_count"],
        payload["hold_direction_count"],
        payload["rejected_direction_count"],
    ) == expected_counts
    assert payload["raw_direction_count"] == len(directions)
    assert payload["directions_count"] == len(directions)
    assert payload["result_message"]


@pytest.mark.asyncio
async def test_runner_stops_browser_after_failure(
    browser: FakeBrowser, llm: FakeLLM, store: FakeStore
):
    runner = AnalysisRunner(store=store)

    with pytest.raises(RuntimeError):
        await runner.run_hypothesis(
            url="https://www.walmart.com/ip/test/12345",
            browser=browser,
            llm=llm,
            product_service_factory=lambda b: CrashingProductService(b),
        )

    assert browser.stopped
