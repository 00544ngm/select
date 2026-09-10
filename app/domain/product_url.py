from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.exceptions import UnsupportedPlatformError


PLATFORM_HOSTS: dict[str, frozenset[str]] = {
    "walmart": frozenset({"walmart.com", "www.walmart.com"}),
    "amazon": frozenset(
        {"amazon.com", "www.amazon.com", "amzn.to", "www.amzn.to"}
    ),
}


def detect_product_platform(url: str) -> str:
    """Return the supported platform for a normalized HTTP(S) product URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsupportedPlatformError(
            f"Unsupported platform URL: {url[:60]}. "
            "Supported: walmart.com, amazon.com"
        )

    hostname = parsed.hostname.lower().rstrip(".")
    for platform, hosts in PLATFORM_HOSTS.items():
        if hostname in hosts:
            return platform

    raise UnsupportedPlatformError(
        f"Unsupported platform URL: {url[:60]}. "
        "Supported: walmart.com, amazon.com"
    )


def extract_product_id(url: str) -> str | None:
    """Extract a platform-native product identifier without guessing."""
    try:
        platform = detect_product_platform(url)
    except UnsupportedPlatformError:
        return None

    path = urlparse(url.strip()).path.rstrip("/")
    if platform == "walmart":
        match = re.search(r"/ip/(?:[^/]+/)?(\d+)$", path)
        return match.group(1) if match else None

    match = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})$", path)
    return match.group(1).upper() if match else None


__all__ = ["PLATFORM_HOSTS", "detect_product_platform", "extract_product_id"]
