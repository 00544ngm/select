from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.infrastructure.amazon.scraper import AmazonProductDetailScraper
from app.infrastructure.walmart.scraper import ProductDetailScraper


class FakePage:
    def __init__(self, images: list[str]):
        self.images = images

    async def evaluate(self, _script: str):
        return self.images


@pytest.mark.asyncio
async def test_walmart_extracts_unique_product_images():
    page = FakePage(
        [
            "https://cdn.example/a.jpg",
            "",
            "data:image/png;base64,x",
            "https://cdn.example/a.jpg",
            "https://cdn.example/b.jpg",
        ]
    )

    assert await ProductDetailScraper(AsyncMock())._extract_images(page) == [
        "https://cdn.example/a.jpg",
        "https://cdn.example/b.jpg",
    ]


@pytest.mark.asyncio
async def test_amazon_extracts_unique_product_images():
    page = FakePage(
        [
            "https://images.example/one.jpg",
            "https://images.example/two.jpg",
            "https://images.example/one.jpg",
        ]
    )

    assert await AmazonProductDetailScraper(AsyncMock())._extract_images(page) == [
        "https://images.example/one.jpg",
        "https://images.example/two.jpg",
    ]
