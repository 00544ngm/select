from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.dependencies import get_browser
from backend.security.auth import get_current_user
from app.infrastructure.walmart.search import search_walmart_page

# Server (web) mode: product search is part of task authoring and requires a
# valid login. Desktop mode: get_current_user returns None, unchanged.
router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(get_current_user)],
)


class SearchRequest(BaseModel):
    keyword: str


class SearchResult(BaseModel):
    title: str
    url: str
    price: str
    rating: str
    review_count: str
    image: str


class SearchResponse(BaseModel):
    results: list[SearchResult]


@router.post("", response_model=SearchResponse)
async def search_products(
    request: SearchRequest,
    browser: Any = Depends(get_browser),
) -> SearchResponse:
    keyword = request.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail={"code": "INVALID_KEYWORD", "message": "Keyword is required"})

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )
    page = await context.new_page()

    try:
        results = await search_walmart_page(page, keyword)
        return SearchResponse(results=results)
    except HTTPException:
        raise
    except RuntimeError as error:
        if "bot detection" in str(error).lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "WALMART_SEARCH_REQUIRES_BROWSER",
                    "message": "Walmart 要求人工验证，请在浏览器中打开搜索并复制商品链接。",
                },
            ) from error
        raise HTTPException(
            status_code=502,
            detail={"code": "SEARCH_FAILED", "message": str(error)},
        ) from error
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "SEARCH_FAILED", "message": str(e)},
        ) from e
    finally:
        await page.close()
        await context.close()
