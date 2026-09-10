"""Tests for ProductService URL routing and scraper selection."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppError
from app.domain.dto import ProductDTO
from app.domain.interfaces import BrowserManager
from app.services.product_service import ProductService


@pytest.fixture
def browser():
    bm = AsyncMock(spec=BrowserManager)
    bm.new_page = AsyncMock()
    return bm


@pytest.fixture
def service(browser):
    return ProductService(browser)


@pytest.mark.asyncio
class TestURLRouting:
    """ProductService should route URLs to the correct scraper."""

    async def test_walmart_url(self, service, monkeypatch):
        called = []

        class FakeWalmart:
            def __init__(self, bm):
                self._browser = bm

            async def scrape_product(self, url):
                called.append(url)
                return ProductDTO(url=url, title="Walmart Product", price="$19.99")

        monkeypatch.setattr(
            "app.services.product_service.ProductDetailScraper", FakeWalmart
        )

        result = await service.get_product("https://www.walmart.com/ip/some-product")
        assert result.title == "Walmart Product"
        assert called == ["https://www.walmart.com/ip/some-product"]

    async def test_amazon_url(self, service, monkeypatch):
        called = []

        class FakeAmazon:
            def __init__(self, bm):
                self._browser = bm

            async def scrape_product(self, url):
                called.append(url)
                return ProductDTO(url=url, title="Amazon Product", price="$19.99")

        monkeypatch.setattr(
            "app.services.product_service.AmazonProductDetailScraper", FakeAmazon
        )

        result = await service.get_product("https://www.amazon.com/dp/B0FBWG9ZPT")
        assert result.title == "Amazon Product"
        assert called == ["https://www.amazon.com/dp/B0FBWG9ZPT"]

    async def test_amazon_short_url(self, service, monkeypatch):
        called = []

        class FakeAmazon:
            def __init__(self, bm):
                self._browser = bm

            async def scrape_product(self, url):
                called.append(url)
                return ProductDTO(url=url, title="Amazon Product", price="$19.99")

        monkeypatch.setattr(
            "app.services.product_service.AmazonProductDetailScraper", FakeAmazon
        )

        result = await service.get_product("https://amzn.to/3test")
        assert result.title == "Amazon Product"

    async def test_unsupported_platform(self, service):
        with pytest.raises(AppError, match="Unsupported platform"):
            await service.get_product("https://target.com/product")

    async def test_unsupported_platform_empty_domain(self, service):
        with pytest.raises(AppError, match="Unsupported platform"):
            await service.get_product("https://example.com/item")

    @pytest.mark.parametrize(
        "url",
        [
            "https://notwalmart.com/ip/12345",
            "https://walmart.com.evil.example/ip/12345",
            "https://amazon.com.evil.example/dp/B0FBWG9ZPT",
            "javascript:https://www.walmart.com/ip/12345",
        ],
    )
    async def test_rejects_lookalike_or_unsafe_urls(self, service, monkeypatch, url):
        class UnexpectedScraper:
            def __init__(self, browser):
                self._browser = browser

            async def scrape_product(self, product_url):
                return ProductDTO(url=product_url, title="Should not be scraped")

        monkeypatch.setattr(
            "app.services.product_service.ProductDetailScraper", UnexpectedScraper
        )
        monkeypatch.setattr(
            "app.services.product_service.AmazonProductDetailScraper", UnexpectedScraper
        )

        with pytest.raises(AppError, match="Unsupported platform"):
            await service.get_product(url)

    @pytest.mark.parametrize(
        ("title", "price", "missing_field"),
        [
            ("", "$19.99", "title"),
            ("Product", "", "price"),
        ],
    )
    async def test_rejects_incomplete_scrape_results(
        self, service, monkeypatch, title, price, missing_field
    ):
        class IncompleteScraper:
            def __init__(self, browser):
                self._browser = browser

            async def scrape_product(self, url):
                return ProductDTO(url=url, title=title, price=price)

        monkeypatch.setattr(
            "app.services.product_service.ProductDetailScraper", IncompleteScraper
        )

        with pytest.raises(AppError, match=missing_field):
            await service.get_product("https://www.walmart.com/ip/example/12345")
