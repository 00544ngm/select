from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BrowserManager(ABC):
    """Abstract interface for browser lifecycle management."""

    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    async def new_page(self):
        ...

    async def restart_visible(self) -> None:
        """Restart in an interactive window when human verification is required."""
        raise NotImplementedError


class LLMClient(ABC):
    """Abstract interface for LLM (GPT) interactions."""

    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        """Send a chat completion request and return text response."""
        ...

    @abstractmethod
    async def chat_structured(
        self, messages: list[dict], output_schema: dict, **kwargs: Any
    ) -> dict:
        """Send a chat request and return structured JSON response."""
        ...


class ProductScraper(ABC):
    """Abstract interface for platform-specific product scrapers."""

    @abstractmethod
    async def scrape_product(self, url: str) -> Any:
        """Scrape a product page and return a ProductDTO."""
        ...


__all__ = [
    "BrowserManager",
    "LLMClient",
    "ProductScraper",
]
