from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.dependencies import get_browser
from backend.main import create_app
from backend.security.auth import get_current_user


class FakePage:
    def __init__(
        self,
        results: list[dict[str, str]] | None = None,
        *,
        title: str = "Walmart Search",
        goto_error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.page_title = title
        self.goto_error = goto_error
        self.goto_url: str | None = None
        self.closed = False

    async def goto(self, url: str, **_kwargs: Any) -> None:
        self.goto_url = url
        if self.goto_error:
            raise self.goto_error

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None

    async def title(self) -> str:
        return self.page_title

    async def evaluate(self, _script: str) -> list[dict[str, str]]:
        return self.results

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.context = FakeContext(page)
        self.new_context_called = False

    async def new_context(self, **_kwargs: Any) -> FakeContext:
        self.new_context_called = True
        return self.context


async def post_search(browser: FakeBrowser, keyword: str):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_browser] = lambda: browser
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/search", json={"keyword": keyword})


@pytest.mark.asyncio
async def test_rejects_blank_keyword_before_opening_context() -> None:
    browser = FakeBrowser(FakePage())

    response = await post_search(browser, "   ")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_KEYWORD"
    assert browser.new_context_called is False


@pytest.mark.asyncio
async def test_maps_search_results_without_rewriting_fields() -> None:
    product = {
        "title": "Non Slip Mat",
        "url": "https://www.walmart.com/ip/123",
        "price": "$9.99",
        "rating": "4.5",
        "review_count": "20",
        "image": "https://i5.walmartimages.com/example.jpg",
    }
    page = FakePage([product])
    browser = FakeBrowser(page)

    response = await post_search(browser, "non slip mat")

    assert response.status_code == 200
    assert response.json() == {"results": [product]}
    assert page.goto_url == "https://www.walmart.com/search?q=non+slip+mat"
    assert page.closed is True
    assert browser.context.closed is True


@pytest.mark.asyncio
async def test_returns_normal_empty_search_results() -> None:
    page = FakePage([])
    browser = FakeBrowser(page)

    response = await post_search(browser, "no matching candidate")

    assert response.status_code == 200
    assert response.json() == {"results": []}
    assert page.closed is True
    assert browser.context.closed is True


@pytest.mark.asyncio
async def test_returns_structured_failure_and_closes_resources() -> None:
    page = FakePage(goto_error=RuntimeError("network down"))
    browser = FakeBrowser(page)

    response = await post_search(browser, "non slip mat")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "SEARCH_FAILED",
        "message": "network down",
    }
    assert page.closed is True
    assert browser.context.closed is True


@pytest.mark.asyncio
async def test_reports_bot_detection_as_structured_failure() -> None:
    page = FakePage(title="Robot or human?")
    browser = FakeBrowser(page)

    response = await post_search(browser, "non slip mat")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "WALMART_SEARCH_REQUIRES_BROWSER",
        "message": "Walmart 要求人工验证，请在浏览器中打开搜索并复制商品链接。",
    }
    assert page.closed is True
    assert browser.context.closed is True
