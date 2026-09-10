from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.core.config import settings
from app.core.exceptions import (
    BrowserTargetClosedError,
    ScrapeError,
    WalmartCaptchaRequiredError,
    WalmartCaptchaTimeoutError,
    WalmartNavigationTimeoutError,
    WalmartNetworkError,
)
from app.core.logger import logger
from app.domain.dto import ProductDTO
from app.domain.interfaces import BrowserManager, ProductScraper
from app.infrastructure.image_utils import normalize_image_urls


class ProductDetailScraper(ProductScraper):
    """Scrapes Walmart product detail pages using Playwright + CDP."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        verification_status: Callable[[bool], Awaitable[None]] | None = None,
    ) -> None:
        self._browser = browser_manager
        self._verification_status = verification_status

    async def _fetch_public_html(self, url: str) -> str | None:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
        }
        try:
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=30,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Public Walmart HTML fallback failed: {}", type(error).__name__)
            return None
        html = response.text
        if "Robot or human?" in html or "__NEXT_DATA__" not in html:
            return None
        return html

    async def _wait_for_captcha(self, page, timeout: int = 9) -> bool:
        """Check if page is blocked by CAPTCHA/robot verification and wait passively.

        Returns True if resolved, False if timed out. Does not refresh or navigate.
        """
        import time

        current_url = page.url
        title = await page.title()
        if "/blocked" not in current_url and "robot" not in title.lower():
            return True

        logger.warning("CAPTCHA/robot verification detected. Waiting for manual verification...")
        start = time.monotonic()

        while time.monotonic() - start < timeout:
            await page.wait_for_timeout(3000)
            current_url = page.url
            title = await page.title()
            if "/blocked" not in current_url and "robot" not in title.lower():
                logger.info("CAPTCHA verification passed. Continuing...")
                return True

        logger.error("CAPTCHA verification timed out after {}s", timeout)
        return False

    async def _is_walmart_verification_page(self, page) -> bool:
        """Inspect bounded page signals without logging or retaining page content."""
        try:
            current_url = str(getattr(page, "url", ""))
            title = str(await page.title())
            body = await page.evaluate(
                "() => (document.body?.innerText || '').slice(0, 4000)"
            )
        except Exception:  # noqa: BLE001 - page may be closed while reading bounded signals
            return False

        body_text = body if isinstance(body, str) else ""
        signals = f"{current_url} {title} {body_text}".lower()
        return any(
            marker in signals
            for marker in (
                "/blocked",
                "robot or human",
                "captcha",
                "verify you are human",
                "security challenge",
            )
        )

    async def scrape_product(self, url: str) -> ProductDTO:
        """Scrape a product with one browser and one CAPTCHA recovery."""
        target_closed_attempts = 0
        visible_verification_started = False
        while True:
            try:
                timeout = (
                    settings.captcha_wait_timeout_seconds
                    if visible_verification_started
                    else 9
                )
                product = await self._scrape_product_once(
                    url,
                    captcha_timeout=timeout,
                )
                if visible_verification_started and self._verification_status:
                    await self._verification_status(False)
                return product
            except WalmartCaptchaRequiredError as error:
                if visible_verification_started:
                    raise WalmartCaptchaTimeoutError() from error
                restart_visible = getattr(self._browser, "restart_visible", None)
                if restart_visible is None:
                    raise WalmartCaptchaTimeoutError() from error
                logger.warning(
                    "Walmart verification required; opening an interactive browser"
                )
                if self._verification_status:
                    await self._verification_status(True)
                await restart_visible()
                visible_verification_started = True
            except Exception as error:
                if not _is_browser_target_closed(error):
                    raise
                if target_closed_attempts >= 1:
                    raise BrowserTargetClosedError() from error
                target_closed_attempts += 1
                logger.warning("Browser target closed during product scrape; restarting once")
                restart = getattr(self._browser, "restart", None)
                if restart is None:
                    raise BrowserTargetClosedError() from error
                try:
                    await restart()
                except Exception as restart_error:
                    if _is_browser_target_closed(restart_error):
                        raise BrowserTargetClosedError() from restart_error
                    raise

    async def _scrape_product_once(
        self, url: str, *, captcha_timeout: int = 9
    ) -> ProductDTO:
        page = await self._browser.new_page()
        try:
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=settings.timeout_ms,
                )
            except PlaywrightTimeoutError as error:
                if _is_browser_target_closed(error):
                    raise
                if await self._is_walmart_verification_page(page):
                    raise WalmartCaptchaRequiredError(
                        "Walmart verification required"
                    ) from error
                raise WalmartNavigationTimeoutError() from error
            except PlaywrightError as error:
                if _is_browser_target_closed(error):
                    raise
                if await self._is_walmart_verification_page(page):
                    raise WalmartCaptchaRequiredError(
                        "Walmart verification required"
                    ) from error
                if _is_network_navigation_error(error):
                    raise WalmartNetworkError() from error
                raise WalmartNavigationTimeoutError() from error
            if not await self._wait_for_captcha(page, timeout=captcha_timeout):
                html = await self._fetch_public_html(url)
                if not html:
                    raise WalmartCaptchaRequiredError(
                        "Walmart 要求人工验证，本次未抓取到商品数据，模型尚未调用"
                    )
                html = html.replace(
                    "<head>",
                    f'<head><base href="{url}">',
                    1,
                )
                await page.set_content(
                    html,
                    wait_until="domcontentloaded",
                    timeout=settings.timeout_ms,
                )
            else:
                await page.wait_for_timeout(3000)
            await self._expand_collapsible_sections(page)

            dto = ProductDTO(url=url)
            dto.title = await self._extract_text(page, "h1")
            dto.images = await self._extract_images(page)
            dto.price = await self._extract_text(page, "[itemprop=price], .price-characteristic")
            dto.rating, dto.review_count = await self._extract_rating_and_review_count(page)
            dto.bullet_points = await self._extract_bullet_points(page)
            dto.attributes = await self._extract_attributes(page)
            dto.review_snippets = await self._extract_reviews(page, url)
            return dto
        except (
            WalmartCaptchaRequiredError,
            WalmartNavigationTimeoutError,
            WalmartNetworkError,
        ):
            raise
        except Exception as e:
            raise ScrapeError(f"Failed to scrape product: {e}") from e
        finally:
            await self._safe_close_page(page)

    @staticmethod
    async def _safe_close_page(page) -> None:
        try:
            await page.close()
        except Exception as error:
            logger.warning("Page cleanup failed: {}", type(error).__name__)
    async def _extract_images(self, page) -> list[str]:
        try:
            values = await page.evaluate("""(() => {
                const values = [];
                const add = (value) => { if (typeof value === 'string') values.push(value); };
                document.querySelectorAll('meta[property="og:image"], meta[name="twitter:image"]').forEach((el) => add(el.content));
                document.querySelectorAll('img').forEach((el) => add(el.currentSrc || el.src || el.dataset.src));
                document.querySelectorAll('script[type="application/ld+json"]').forEach((el) => {
                    try {
                        const data = JSON.parse(el.textContent || '{}');
                        const collect = (value) => {
                            if (Array.isArray(value)) value.forEach(collect);
                            else if (typeof value === 'string') add(value);
                            else if (value && typeof value === 'object') {
                                if (value.image) collect(value.image);
                                if (value.url && /image/i.test(value['@type'] || '')) add(value.url);
                            }
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

    async def _expand_collapsible_sections(self, page) -> None:
        """Click all collapsible accordion buttons (e.g. Product Details) to expand content."""
        try:
            await page.evaluate("""(() => {
                const buttons = document.querySelectorAll(
                    '.expand-collapse-section .expand-collapse-header button[aria-expanded="false"]'
                );
                buttons.forEach(b => b.click());
            })()""")
            await page.wait_for_timeout(500)
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            pass

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

    async def _extract_rating_and_review_count(self, page) -> tuple[str, str]:
        try:
            return await page.evaluate("""(() => {
                const el = document.querySelector('[aria-label*="rating"]');
                if (!el) return ["", ""];
                const label = el.getAttribute('aria-label') || '';
                // e.g. "4.4 out of 5 stars rating, 13407 ratings"
                const ratingMatch = label.match(/([\\d.]+)\\s*out\\s*of/);
                const countMatch = label.match(/([\\d,.Kk]+)\\s*ratings?/);
                const rating = ratingMatch ? ratingMatch[1] : '';
                const count = countMatch ? countMatch[1] : '';
                return [rating, count];
            })()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return ("", "")

    async def _extract_bullet_points(self, page) -> list[str]:
        try:
            return await page.evaluate("""(() => {
                const els = document.querySelectorAll('.expand-collapse-content ul.mv0.pl4 li');
                return Array.from(els).map(el => el.textContent.trim()).filter(Boolean);
            })()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return []

    async def _extract_attributes(self, page) -> dict[str, str]:
        try:
            return await page.evaluate("""(() => {
                const result = {};
                const rows = document.querySelectorAll('.expand-collapse-content ul.mv0.pl4 li');
                rows.forEach(li => {
                    const text = li.textContent.trim();
                    if (text.includes(':')) {
                        const sep = text.indexOf(':');
                        const key = text.substring(0, sep).trim();
                        const val = text.substring(sep + 1).trim();
                        if (key && val) result[key] = val;
                    }
                });
                return result;
            })()""")
        except Exception as error:
            if _is_browser_target_closed(error):
                raise
            return {}

    @staticmethod
    def _get_product_id(url: str) -> str | None:
        """Extract Walmart product ID from URL path."""
        import re
        m = re.search(r'/(\d{5,})(?:\?|#|$)', url)
        return m.group(1) if m else None

    async def _extract_reviews(self, page, product_url: str) -> list[str]:
        """Navigate to the Walmart reviews page and extract review snippets across pages."""
        product_id = self._get_product_id(product_url)
        if not product_id:
            logger.warning("Could not extract product ID from URL: {}", product_url)
            return []

        base_url = f"https://www.walmart.com/reviews/product/{product_id}"
        all_reviews: list[str] = []
        seen: set[str] = set()
        max_pages = 10
        for page_num in range(1, max_pages + 1):
            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
            try:
                resp = await page.goto(url, wait_until="domcontentloaded",
                                       timeout=settings.timeout_ms)
                if resp and resp.status != 200:
                    logger.warning("Reviews page {} returned status {}", page_num, resp.status)
                    break
                if not await self._wait_for_captcha(page):
                    logger.warning("Blocked by CAPTCHA while fetching reviews page {}", page_num)
                    break
                await page.wait_for_timeout(2000)

                # Extract review texts on this page
                snippets = await page.evaluate("""(() => {
                    const results = [];
                    const candidates = document.querySelectorAll('.tl-m.db-m, [class*="review-body"]');
                    candidates.forEach(el => {
                        const text = (el.textContent || '').trim().slice(0, 2000);
                        if (text.length > 20) results.push(text);
                    });
                    return results;
                })()""")

                new_count = 0
                for s in snippets:
                    if s not in seen:
                        seen.add(s)
                        all_reviews.append(s)
                        new_count += 1

                logger.debug("Page {}: got {} reviews ({} new)", page_num, len(snippets), new_count)

                # Stop if this page had no new content (end of pagination)
                if new_count == 0 and page_num > 1:
                    break

                # Stop if we have enough reviews
                if len(all_reviews) >= 30:
                    break

                # Small delay between pages
                await page.wait_for_timeout(1000)

            except Exception as e:
                if _is_browser_target_closed(e):
                    raise
                logger.warning("Failed on reviews page {}: {}", page_num, e)
                break

        return all_reviews[:30]


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


def _is_network_navigation_error(error: BaseException) -> bool:
    """Match transport failures without treating verification pages as network errors.

    Verification markers are checked before this helper is called.
    """
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "err_proxy_connection_failed",
            "err_connection_reset",
            "err_connection_closed",
            "err_name_not_resolved",
            "err_internet_disconnected",
            "err_timed_out",
        )
    )


__all__ = ["ProductDetailScraper"]
