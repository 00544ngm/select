from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.domain.dto import ProductDTO
from app.domain.interfaces import BrowserManager
from app.domain.product_url import detect_product_platform, extract_product_id
from app.domain.product_validation import validate_product
from app.infrastructure.amazon.scraper import AmazonProductDetailScraper
from app.infrastructure.walmart.scraper import ProductDetailScraper


class ProductService:
    """Aggregates product data from supported e-commerce platforms."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        verification_status: Callable[[bool], Awaitable[None]] | None = None,
    ) -> None:
        self._browser = browser_manager
        self._verification_status = verification_status

    async def get_product(self, url: str) -> ProductDTO:
        """Fetch product details from a supported product URL."""
        scraper = self._create_scraper(url)
        product = await scraper.scrape_product(url)
        product = validate_product(product)
        product.product_id = extract_product_id(product.url)
        return product

    def _create_scraper(self, url: str):
        platform = detect_product_platform(url)
        if platform == "walmart":
            if self._verification_status is None:
                return ProductDetailScraper(self._browser)
            return ProductDetailScraper(
                self._browser,
                verification_status=self._verification_status,
            )
        if platform == "amazon":
            return AmazonProductDetailScraper(self._browser)
        raise AssertionError(f"Unhandled product platform: {platform}")


__all__ = ["ProductService"]
