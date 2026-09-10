from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from playwright._impl._errors import TargetClosedError

from app.core.exceptions import ScrapeError
from app.infrastructure.amazon.scraper import AmazonProductDetailScraper


class FakePage:
    url = "https://www.amazon.com/dp/B012345678"

    def __init__(self) -> None:
        self.goto = AsyncMock()
        self.close = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.evaluate = AsyncMock()


class RecoveringBrowser:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages
        self.new_page_calls = 0
        self.restart_calls = 0

    async def new_page(self) -> FakePage:
        page = self.pages[self.new_page_calls]
        self.new_page_calls += 1
        return page

    async def restart(self) -> None:
        self.restart_calls += 1


def stub_successful_extractors(monkeypatch, scraper) -> None:
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(side_effect=["Recovered product", "Description"]),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_price", AsyncMock(return_value="$19.99"))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_reviews",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))


@pytest.mark.asyncio
async def test_target_closed_during_navigation_restarts_browser_once(monkeypatch):
    first = FakePage()
    first.goto.side_effect = TargetClosedError(
        "Target page, context or browser has been closed"
    )
    second = FakePage()
    browser = RecoveringBrowser([first, second])
    scraper = AmazonProductDetailScraper(browser)
    stub_successful_extractors(monkeypatch, scraper)

    result = await scraper.scrape_product("https://www.amazon.com/dp/B012345678")

    assert result.title == "Recovered product"
    assert browser.new_page_calls == 2
    assert browser.restart_calls == 1


@pytest.mark.asyncio
async def test_target_closed_during_field_extraction_restarts_browser(monkeypatch):
    first = FakePage()
    second = FakePage()
    browser = RecoveringBrowser([first, second])
    scraper = AmazonProductDetailScraper(browser)
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(
            side_effect=[
                TargetClosedError("Target page, context or browser has been closed"),
                "Recovered product",
                "Description",
            ]
        ),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_price", AsyncMock(return_value="$19.99"))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_reviews",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    result = await scraper.scrape_product("https://www.amazon.com/dp/B012345678")

    assert result.title == "Recovered product"
    assert browser.restart_calls == 1


@pytest.mark.asyncio
async def test_optional_field_extractors_propagate_target_closed():
    page = FakePage()
    error = TargetClosedError("Target page, context or browser has been closed")
    page.evaluate.side_effect = error
    scraper = AmazonProductDetailScraper(RecoveringBrowser([page]))

    extractors = [
        scraper._extract_images(page),
        scraper._extract_text(page, "#productTitle"),
        scraper._extract_price(page),
        scraper._extract_rating_and_reviews(page),
        scraper._extract_bullet_points(page),
    ]
    for extraction in extractors:
        with pytest.raises(TargetClosedError):
            await extraction


@pytest.mark.asyncio
async def test_review_extractor_propagates_target_closed():
    page = FakePage()
    page.goto.side_effect = TargetClosedError(
        "Target page, context or browser has been closed"
    )
    scraper = AmazonProductDetailScraper(RecoveringBrowser([page]))

    with pytest.raises(TargetClosedError):
        await scraper._extract_reviews(
            page, "https://www.amazon.com/dp/B012345678"
        )


@pytest.mark.asyncio
async def test_page_cleanup_does_not_override_original_amazon_failure():
    page = FakePage()
    page.goto.side_effect = RuntimeError("original scrape failure")
    page.close.side_effect = RuntimeError("browser already closed")
    scraper = AmazonProductDetailScraper(RecoveringBrowser([page]))

    with pytest.raises(ScrapeError, match="original scrape failure"):
        await scraper.scrape_product("https://www.amazon.com/dp/B012345678")

    page.close.assert_awaited_once()
