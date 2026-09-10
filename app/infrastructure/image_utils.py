from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urljoin, urlparse


def normalize_image_urls(values: Iterable[object], base_url: str = "") -> list[str]:
    """Return unique, browser-loadable HTTP(S) image URLs in source order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = urljoin(base_url, value.strip())
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
        if len(result) >= 8:
            break
    return result


__all__ = ["normalize_image_urls"]
