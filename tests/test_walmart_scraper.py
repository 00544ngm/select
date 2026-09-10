from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest
from playwright._impl._errors import TargetClosedError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.exceptions import (
    BrowserTargetClosedError,
    ScrapeError,
    WalmartNavigationTimeoutError,
    WalmartNetworkError,
)
from app.infrastructure.walmart.scraper import ProductDetailScraper


class BlockedPage:
    url = "https://www.walmart.com/blocked?url=L3"

    def __init__(self) -> None:
        self.goto = AsyncMock()
        self.close = AsyncMock()
        self.set_content = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.evaluate = AsyncMock()

    async def title(self) -> str:
        return "Robot or human?"


class FakeBrowser:
    def __init__(self, page: BlockedPage) -> None:
        self.page = page

    async def new_page(self) -> BlockedPage:
        return self.page


class RecoveringBrowser:
    def __init__(self, pages: list[BlockedPage]) -> None:
        self.pages = pages
        self.new_page_calls = 0
        self.restart_calls = 0
        self.restart_visible_calls = 0

    async def new_page(self) -> BlockedPage:
        page = self.pages[self.new_page_calls]
        self.new_page_calls += 1
        return page

    async def restart(self) -> None:
        self.restart_calls += 1

    async def restart_visible(self) -> None:
        self.restart_visible_calls += 1


def test_captcha_default_wait_is_short_enough_for_an_invisible_desktop_browser():
    timeout = inspect.signature(ProductDetailScraper._wait_for_captcha).parameters[
        "timeout"
    ].default

    assert timeout <= 10


@pytest.mark.asyncio
async def test_blocked_product_explains_that_scrape_failed_before_model_call(
    monkeypatch,
):
    page = BlockedPage()
    scraper = ProductDetailScraper(FakeBrowser(page))
    monkeypatch.setattr(scraper, "_wait_for_captcha", AsyncMock(return_value=False))

    with pytest.raises(ScrapeError) as exc_info:
        await scraper.scrape_product("https://www.walmart.com/ip/example/5257371669")

    message = str(exc_info.value)
    assert "Walmart 要求人工验证" in message
    assert "未抓取到商品数据" in message
    assert "模型尚未调用" in message
    page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocked_browser_falls_back_to_public_product_html(monkeypatch):
    page = BlockedPage()
    scraper = ProductDetailScraper(FakeBrowser(page))
    monkeypatch.setattr(scraper, "_wait_for_captcha", AsyncMock(return_value=False))
    monkeypatch.setattr(
        scraper,
        "_fetch_public_html",
        AsyncMock(return_value="<html><head></head><body>product</body></html>"),
        raising=False,
    )
    monkeypatch.setattr(scraper, "_expand_collapsible_sections", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(side_effect=["Real Walmart product", "$19.99"]),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=["image.jpg"]))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_review_count",
        AsyncMock(return_value=("4.4", "100")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_attributes", AsyncMock(return_value={}))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    result = await scraper.scrape_product(
        "https://www.walmart.com/ip/example/5257371669"
    )

    assert result.title == "Real Walmart product"
    assert result.price == "$19.99"
    page.set_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocked_headless_browser_restarts_visible_then_continues(monkeypatch):
    first = BlockedPage()
    second = BlockedPage()
    browser = RecoveringBrowser([first, second])
    scraper = ProductDetailScraper(browser)
    monkeypatch.setattr(
        scraper, "_wait_for_captcha", AsyncMock(side_effect=[False, True])
    )
    monkeypatch.setattr(scraper, "_fetch_public_html", AsyncMock(return_value=None))
    monkeypatch.setattr(scraper, "_expand_collapsible_sections", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(side_effect=["Verified product", "$19.99"]),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_review_count",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_attributes", AsyncMock(return_value={}))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    result = await scraper.scrape_product(
        "https://www.walmart.com/ip/example/5257371669"
    )

    assert result.title == "Verified product"
    assert browser.restart_visible_calls == 1
    assert browser.new_page_calls == 2


@pytest.mark.asyncio
async def test_navigation_timeout_on_verification_page_restarts_visible_browser(
    monkeypatch,
):
    first = BlockedPage()
    first.goto.side_effect = PlaywrightTimeoutError("Timeout 30000ms exceeded")
    first.evaluate.return_value = "Robot or human?"
    second = BlockedPage()
    browser = RecoveringBrowser([first, second])
    verification_status = AsyncMock()
    scraper = ProductDetailScraper(browser, verification_status=verification_status)
    monkeypatch.setattr(scraper, "_wait_for_captcha", AsyncMock(return_value=True))
    monkeypatch.setattr(scraper, "_expand_collapsible_sections", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(side_effect=["Recovered product", "$19.99"]),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_review_count",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_attributes", AsyncMock(return_value={}))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    result = await scraper.scrape_product(
        "https://www.walmart.com/ip/example/5257371669"
    )

    assert result.title == "Recovered product"
    assert browser.restart_visible_calls == 1
    verification_status.assert_any_await(True)


@pytest.mark.asyncio
async def test_normal_navigation_timeout_has_stable_error_without_verification(
    monkeypatch,
):
    page = BlockedPage()
    page.url = "https://www.walmart.com/ip/example/5257371669"
    page.title = AsyncMock(return_value="Walmart product")
    page.goto.side_effect = PlaywrightTimeoutError("Timeout 30000ms exceeded")
    page.evaluate.return_value = "Product page still loading"
    browser = FakeBrowser(page)
    verification_status = AsyncMock()
    scraper = ProductDetailScraper(browser, verification_status=verification_status)

    with pytest.raises(WalmartNavigationTimeoutError) as exc_info:
        await scraper.scrape_product(
            "https://www.walmart.com/ip/example/5257371669"
        )

    assert exc_info.value.code == "WALMART_NAVIGATION_TIMEOUT"
    verification_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_network_navigation_failure_has_stable_error_without_verification():
    page = BlockedPage()
    page.url = "https://www.walmart.com/ip/example/5257371669"
    page.title = AsyncMock(return_value="Walmart product")
    page.goto.side_effect = PlaywrightError("net::ERR_PROXY_CONNECTION_FAILED")
    page.evaluate.return_value = "Product page unavailable"
    scraper = ProductDetailScraper(FakeBrowser(page))

    with pytest.raises(WalmartNetworkError) as exc_info:
        await scraper.scrape_product(
            "https://www.walmart.com/ip/example/5257371669"
        )

    assert exc_info.value.code == "WALMART_NETWORK_FAILED"


@pytest.mark.asyncio
async def test_verification_status_is_set_then_cleared_after_success(monkeypatch):
    first = BlockedPage()
    second = BlockedPage()
    browser = RecoveringBrowser([first, second])
    status = AsyncMock()
    scraper = ProductDetailScraper(browser, verification_status=status)
    monkeypatch.setattr(
        scraper, "_wait_for_captcha", AsyncMock(side_effect=[False, True])
    )
    monkeypatch.setattr(scraper, "_fetch_public_html", AsyncMock(return_value=None))
    monkeypatch.setattr(scraper, "_expand_collapsible_sections", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(side_effect=["Verified product", "$19.99"]),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_review_count",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    await scraper.scrape_product("https://www.walmart.com/ip/example/5257371669")

    assert status.await_args_list[0].args == (True,)
    assert status.await_args_list[1].args == (False,)


@pytest.mark.asyncio
async def test_visible_verification_timeout_has_stable_error(monkeypatch):
    first = BlockedPage()
    second = BlockedPage()
    browser = RecoveringBrowser([first, second])
    scraper = ProductDetailScraper(browser)
    monkeypatch.setattr(
        scraper, "_wait_for_captcha", AsyncMock(side_effect=[False, False])
    )
    monkeypatch.setattr(scraper, "_fetch_public_html", AsyncMock(return_value=None))

    with pytest.raises(Exception) as exc_info:
        await scraper.scrape_product(
            "https://www.walmart.com/ip/example/5257371669"
        )

    assert getattr(exc_info.value, "code", None) == "WALMART_CAPTCHA_TIMEOUT"
    assert "模型尚未调用" in str(exc_info.value)
    assert browser.restart_visible_calls == 1


@pytest.mark.asyncio
async def test_page_cleanup_does_not_override_original_scrape_failure():
    page = BlockedPage()
    page.goto.side_effect = RuntimeError("original scrape failure")
    page.close.side_effect = RuntimeError("browser already closed")
    scraper = ProductDetailScraper(FakeBrowser(page))

    with pytest.raises(ScrapeError, match="original scrape failure"):
        await scraper.scrape_product("https://www.walmart.com/ip/example/5257371669")

    page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_closed_restarts_browser_once_then_returns_product(monkeypatch):
    first = BlockedPage()
    first.goto.side_effect = TargetClosedError("Target page, context or browser has been closed")
    second = BlockedPage()
    browser = RecoveringBrowser([first, second])
    scraper = ProductDetailScraper(browser)
    monkeypatch.setattr(scraper, "_wait_for_captcha", AsyncMock(return_value=True))
    monkeypatch.setattr(scraper, "_expand_collapsible_sections", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(side_effect=["Recovered product", "$19.99"]),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_review_count",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_attributes", AsyncMock(return_value={}))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    result = await scraper.scrape_product("https://www.walmart.com/ip/example/5257371669")

    assert result.title == "Recovered product"
    assert browser.new_page_calls == 2
    assert browser.restart_calls == 1


@pytest.mark.asyncio
async def test_target_closed_during_field_extraction_restarts_browser(monkeypatch):
    first = BlockedPage()
    second = BlockedPage()
    browser = RecoveringBrowser([first, second])
    scraper = ProductDetailScraper(browser)
    monkeypatch.setattr(scraper, "_wait_for_captcha", AsyncMock(return_value=True))
    monkeypatch.setattr(scraper, "_expand_collapsible_sections", AsyncMock())
    monkeypatch.setattr(
        scraper,
        "_extract_text",
        AsyncMock(
            side_effect=[
                TargetClosedError("Target page, context or browser has been closed"),
                "Recovered product",
                "$19.99",
            ]
        ),
    )
    monkeypatch.setattr(scraper, "_extract_images", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        scraper,
        "_extract_rating_and_review_count",
        AsyncMock(return_value=("4.5", "10")),
    )
    monkeypatch.setattr(scraper, "_extract_bullet_points", AsyncMock(return_value=[]))
    monkeypatch.setattr(scraper, "_extract_attributes", AsyncMock(return_value={}))
    monkeypatch.setattr(scraper, "_extract_reviews", AsyncMock(return_value=[]))

    result = await scraper.scrape_product(
        "https://www.walmart.com/ip/example/5257371669"
    )

    assert result.title == "Recovered product"
    assert browser.restart_calls == 1


@pytest.mark.asyncio
async def test_optional_field_extractors_propagate_target_closed():
    page = BlockedPage()
    error = TargetClosedError("Target page, context or browser has been closed")
    page.evaluate.side_effect = error
    scraper = ProductDetailScraper(FakeBrowser(page))

    extractors = [
        scraper._extract_images(page),
        scraper._expand_collapsible_sections(page),
        scraper._extract_text(page, "h1"),
        scraper._extract_rating_and_review_count(page),
        scraper._extract_bullet_points(page),
        scraper._extract_attributes(page),
    ]
    for extraction in extractors:
        with pytest.raises(TargetClosedError):
            await extraction


@pytest.mark.asyncio
async def test_review_extractor_propagates_target_closed():
    page = BlockedPage()
    page.goto.side_effect = TargetClosedError(
        "Target page, context or browser has been closed"
    )
    scraper = ProductDetailScraper(FakeBrowser(page))

    with pytest.raises(TargetClosedError):
        await scraper._extract_reviews(
            page, "https://www.walmart.com/ip/example/5257371669"
        )


@pytest.mark.asyncio
async def test_target_closed_twice_stops_after_one_restart():
    first = BlockedPage()
    second = BlockedPage()
    error = TargetClosedError("Target page, context or browser has been closed")
    first.goto.side_effect = error
    second.goto.side_effect = error
    browser = RecoveringBrowser([first, second])
    scraper = ProductDetailScraper(browser)

    with pytest.raises(BrowserTargetClosedError) as exc_info:
        await scraper.scrape_product("https://www.walmart.com/ip/example/5257371669")

    assert exc_info.value.code == "BROWSER_TARGET_CLOSED"
    assert browser.new_page_calls == 2
    assert browser.restart_calls == 1


@pytest.mark.asyncio
async def test_target_closed_during_restart_has_stable_browser_error():
    page = BlockedPage()
    page.goto.side_effect = TargetClosedError(
        "Target page, context or browser has been closed"
    )
    browser = RecoveringBrowser([page])
    browser.restart = AsyncMock(
        side_effect=TargetClosedError(
            "Target page, context or browser has been closed"
        )
    )
    scraper = ProductDetailScraper(browser)

    with pytest.raises(BrowserTargetClosedError) as exc_info:
        await scraper.scrape_product(
            "https://www.walmart.com/ip/example/5257371669"
        )

    assert exc_info.value.code == "BROWSER_TARGET_CLOSED"
    browser.restart.assert_awaited_once()
