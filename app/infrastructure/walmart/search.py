from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

EXTRACT_JS = """
() => {
    const items = [];
    const seen = new Set();
    const addCard = (card) => {
        const link = card.querySelector('a[href*="/ip/"], a[href*="/product/"]');
        if (!link) return;
        const href = link.getAttribute('href') || '';
        const url = href.startsWith('http') ? href : 'https://www.walmart.com' + href;
        if (seen.has(url)) return;
        const title = (link.getAttribute('title') || link.textContent || '').trim();
        if (!title) return;
        seen.add(url);
        const price = card.querySelector('[data-testid="price"], [itemprop="price"]');
        const image = card.querySelector('img');
        items.push({title, url, price: price ? (price.textContent || '').trim() : '', rating: '', review_count: '', image: image ? (image.getAttribute('src') || image.getAttribute('data-src') || '') : ''});
    };
    document.querySelectorAll('[data-testid="item-stack"] > div, [data-automation-id="product-grid"] > div, [data-testid="list-view"] > div').forEach(addCard);
    if (items.length === 0) document.querySelectorAll('a[href*="/ip/"]').forEach((link) => addCard(link.parentElement || link));
    return items.slice(0, 20);
}
"""


async def search_walmart_page(page: Any, keyword: str) -> list[dict[str, str]]:
    query = quote_plus(keyword.strip())
    await page.goto(
        f"https://www.walmart.com/search?q={query}",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    await page.wait_for_timeout(3000)
    if "robot" in (await page.title()).lower():
        raise RuntimeError("Walmart blocked the request (bot detection)")
    return list(await page.evaluate(EXTRACT_JS) or [])[:20]


__all__ = ["EXTRACT_JS", "search_walmart_page"]
