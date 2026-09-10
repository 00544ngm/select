"""Amazon product page scraper using Playwright + CDP."""
from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import BrowserTargetClosedError, ScrapeError
from app.core.logger import logger
from app.domain.dto import ProductDTO
from app.domain.interfaces import BrowserManager, ProductScraper
from app.infrastructure.image_utils import normalize_image_urls


class AmazonProductDetailScraper(ProductScraper):
    """Scrapes Amazon product detail pages using Playwright + CDP."""

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._browser = browser_manager

    async def scrape_product(self, url: str) -> ProductDTO:
        """Scrape a product, restarting the browser once on target closure."""
        for attempt in range(2):
            try:
                return await self._scrape_product_once(url)
            except Exception as error:
                if not _is_browser_target_closed(error):
                    raise
                if attempt == 1:
                    raise BrowserTargetClosedError() from error
                logger.warning("Browser target closed during Amazon scrape; restarting once")
                restart = getattr(self._browser, "restart", None)
                if restart is None:
                    raise BrowserTargetClosedError() from error
                try:
                    await restart()
                except Exception as restart_error:
                    if _is_browser_target_closed(restart_error):
                        raise BrowserTargetClosedError() from restart_error
                    raise
        raise AssertionError("unreachable")

    async def _scrape_product_once(self, url: str) -> ProductDTO:
        page = await self._browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=settings.timeout_ms)
            await page.wait_for_timeout(3000)

            dto = ProductDTO(url=url)
            dto.title = await self._extract_text(page, "#productTitle")
            dto.images = await self._extract_images(page)
            dto.price = await self._extract_price(page)
            dto.rating, dto.review_count = await self._extract_rating_and_reviews(page)
            dto.bullet_points = await self._extract_bullet_points(page)
            dto.description = await self._extract_text(page, "#productDescription")
            dto.review_snippets = await self._extract_reviews(page, url)
            return dto
        except Exception as e:
            raise ScrapeError(f"Failed to scrape Amazon product: {e}") from e
        finally:
            await self._safe_close_page(page)

    @staticmethod
    async def _safe_close_page(page) -> None:
        try:
            await page.close()
        except Exception as error:
            logger.warning("Amazon page cleanup failed: {}", type(error).__name__)

    async def _extract_images(self, page) -> list[str]:
        try:
            values = await page.evaluate("""(() => {
                const values = [];
                const add = (value) => { if (typeof value === 'string') values.push(value); };
                document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]').forEach((el) => add(el.content));
                document.querySelectorAll('#landingImage, #imgTagWrapperId img, img').forEach((el) => add(el.currentSrc || el.src || el.dataset.src));
                document.querySelectorAll('script[type="application/ld+json"]').forEach((el) => {
                    try {
                        const data = JSON.parse(el.textContent || '{}');
                        const collect = (value) => {
                            if (Array.isArray(value)) value.forEach(collect);
                            else if (typeof value === 'string') add(value);
                            else if (value && typeof value === 'object' && value.image) collect(value.image);
                        };
                        collect(data.image);
                    } catch (_) { /* ignore malformed JSON-LD */ }
                });
                return values;
            })()""")
            return normalize_image_urls(values or [], getattr(page, "url", ""))
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return []

    async def _extract_text(self, page, selector: str) -> str:
        try:
            return await page.evaluate(f"""(() => {{
                const el = document.querySelector('{selector}');
                return el ? el.textContent.trim() : "";
            }})()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return ""

    async def _extract_price(self, page) -> str:
        try:
            return await page.evaluate("""(() => {
                // Prefer the visible price (sale/current), fallback to list price
                const selectors = [
                    '#corePrice_desktop .a-price .a-offscreen',
                    '.reinventPricePriceToPayMargin .a-offscreen',
                    '.a-price.aok-align-center.reinventPricePr .a-offscreen',
                    '#priceblock_ourprice',
                    '#priceblock_dealprice',
                    '.a-price .a-offscreen',
                    '.a-price-whole',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.textContent.trim();
                        if (text && !text.startsWith('$0')) return text;
                    }
                }
                return '';
            })()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return ""

    async def _extract_rating_and_reviews(self, page) -> tuple[str, str]:
        try:
            return await page.evaluate("""(() => {
                const ratingEl = document.querySelector('.a-icon-alt');
                const rating = ratingEl ? (ratingEl.textContent.trim().match(/([\\d.]+)\\s*out/)?.[1] || '') : '';
                const countEl = document.querySelector('#acrCustomerReviewText');
                const count = countEl ? countEl.textContent.trim().replace(/[^0-9]/g, '') : '';
                return [rating, count];
            })()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return ("", "")

    async def _extract_bullet_points(self, page) -> list[str]:
        try:
            return await page.evaluate("""(() => {
                const items = document.querySelectorAll('#feature-bullets ul li');
                return Array.from(items).map(li => {
                    const span = li.querySelector('span');
                    return span ? span.textContent.trim() : '';
                }).filter(Boolean);
            })()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return []

    @staticmethod
    def _get_asin(url: str) -> str | None:
        """Extract Amazon ASIN from URL (10-character alphanumeric)."""
        import re
        m = re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', url)
        return m.group(1) if m else None

    async def _extract_reviews(self, page, product_url: str) -> list[str]:
        """Extract review content from Amazon product page."""
        asin = self._get_asin(product_url)
        if not asin:
            logger.warning("Could not extract ASIN from URL: {}", product_url)
            return []

        # Try the dedicated reviews page first (requires login)
        reviews_url = f"https://www.amazon.com/product-reviews/{asin}"
        try:
            resp = await page.goto(reviews_url, wait_until="domcontentloaded",
                                   timeout=settings.timeout_ms)
            if resp and resp.status != 200:
                logger.warning("Reviews page returned status {}", resp.status)
            else:
                await page.wait_for_timeout(3000)

                # If redirected to sign-in, we're not logged in — fall back to product page
                if "signin" in page.url.lower():
                    logger.info("Amazon reviews page requires login, falling back to product page")
                else:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
                    snippets = await page.evaluate(
                        """(() => {
                        const seen = new Set();
                        document.querySelectorAll('.review-text-content span, [data-hook="review-body"] span').forEach(el => {
                            const t = (el.textContent || '').trim().slice(0, 2000);
                            if (t.length > 20) seen.add(t);
                        });
                        return [...seen].slice(0, 15);
                    })()"""
                    )
                    if snippets:
                        return snippets
        except Exception as error:
            if _is_browser_target_closed(error):
                raise

        # Fallback: extract reviews from the product page itself
        try:
            await page.goto(product_url, wait_until="domcontentloaded",
                            timeout=settings.timeout_ms)
            await page.wait_for_timeout(3000)
            # Scroll to the review section
            await page.evaluate("window.scrollTo(0, 3000)")
            await page.wait_for_timeout(3000)
            await page.evaluate(
                "document.getElementById('customer-reviews_feature_div')?.scrollIntoView({behavior: 'instant'})"
            )
            await page.wait_for_timeout(3000)

            # Try individual review texts
            snippets = await page.evaluate(
                """(() => {
                const seen = new Set();
                document.querySelectorAll('.review-text-content span, [data-hook="review-body"]').forEach(el => {
                    const t = (el.textContent || '').trim().slice(0, 2000);
                    if (t.length > 20) seen.add(t);
                });
                return [...seen].slice(0, 15);
            })()"""
            )
            if snippets:
                return snippets

            # Fallback: extract the AI-generated "Customers say" summary
            summary = await page.evaluate(
                """(() => {
                const el = document.querySelector('[data-hook="cr-insights-widget"]');
                if (el) return el.innerText.slice(0, 2000);
                // Fallback: look for text near "Customers say"
                const text = document.body.innerText || '';
                const idx = text.indexOf('Customers say');
                if (idx >= 0) return text.slice(idx, idx + 1500);
                return '';
            })()"""
            )
            if summary:
                return [summary]

        except Exception as e:
            if _is_browser_target_closed(e):
                raise
            logger.warning("Failed to extract Amazon reviews from product page: {}", e)

        return []


def _is_browser_target_closed(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        name = type(current).__name__.lower()
        message = str(current).lower()
        if (
            "targetclosed" in name
            or "target page, context or browser has been closed" in message
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


__all__ = ["AmazonProductDetailScraper"]
