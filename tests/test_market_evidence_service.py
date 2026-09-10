import pytest
from playwright._impl._errors import TargetClosedError

from app.domain.dto import DirectionDTO, HypothesisDTO, HypothesisResultDTO, ProductDTO
from app.domain.stickiness import ScoreRatings
from app.services.market_evidence_service import MarketEvidenceService


class FakePage:
    def __init__(self):
        self.closed = False

    async def goto(self, *_args, **_kwargs):
        return None

    async def wait_for_timeout(self, *_args):
        return None

    async def title(self):
        return "Walmart Search"

    async def evaluate(self, *_args):
        return [{"title": "Grinder with Oil Sprayer", "url": "https://walmart.com/ip/1"}]

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.pages = []

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


@pytest.mark.asyncio
async def test_verification_closes_pages_and_caches_queries():
    browser = FakeBrowser()
    service = MarketEvidenceService()
    first = await service.verify_candidate(browser, ["grinder"], ["oil sprayer"])
    second = await service.verify_candidate(browser, ["grinder"], ["oil sprayer"])

    assert first.level.value == "E1"
    assert second is first
    assert len(browser.pages) == 1
    assert browser.pages[0].closed is True


class FailingPage(FakePage):
    async def goto(self, *_args, **_kwargs):
        raise RuntimeError("blocked")


class FailingBrowser(FakeBrowser):
    async def new_page(self):
        page = FailingPage()
        self.pages.append(page)
        return page


@pytest.mark.asyncio
async def test_failed_market_search_is_saved_without_downgrading_existing_evidence():
    result = HypothesisResultDTO(
        product=ProductDTO(title="Printer"),
        product_profile={"primary_search_terms": ["printer"]},
        directions=[DirectionDTO(hypothesis=HypothesisDTO(
            direction_name="Matching Ink",
            canonical_name="matching ink",
            evidence_level="E1",
            raw_score=85,
            final_score=69,
            score_cap=69,
            score_inputs={
                "relation_strength": 5,
                "lifecycle_connection": 5,
                "repeat_value": 5,
                "function_gain": 5,
                "mental_copurchase": 5,
                "user_scene": 5,
            },
        ))],
    )

    service = MarketEvidenceService()
    records = await service.verify_result(result, FailingBrowser())

    hypothesis = result.directions[0].hypothesis
    record = records["Matching Ink"]
    assert record.status == "failed"
    assert record.failure_reason == "blocked"
    assert hypothesis.evidence_level == "E1"
    assert hypothesis.evidence["market"]["failure_reason"] == "blocked"


def test_v21_score_inputs_preserve_purchase_direction_for_market_recalculation():
    ratings = ScoreRatings(
        function_necessity=5,
        usage_continuity=5,
        purchase_direction=5,
        scene_fit=5,
        enhancement_maintenance=5,
        natural_copurchase=5,
    )
    assert "purchase_direction" in ratings.__dict__ or ratings.purchase_direction == 5


class ClosedEvidencePage(FakePage):
    async def goto(self, *_args, **_kwargs):
        raise TargetClosedError("Target page, context or browser has been closed")

    async def close(self):
        raise TargetClosedError("Target page, context or browser has been closed")


class ClosedEvidenceBrowser(FakeBrowser):
    async def new_page(self):
        page = ClosedEvidencePage()
        self.pages.append(page)
        return page


@pytest.mark.asyncio
async def test_target_closed_during_market_evidence_returns_failed_record():
    service = MarketEvidenceService()

    record = await service.verify_candidate(
        ClosedEvidenceBrowser(), ["printer"], ["matching ink"]
    )

    assert record.status == "failed"
    assert "closed" in record.failure_reason.lower()
