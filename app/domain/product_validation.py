from __future__ import annotations

from app.core.exceptions import ScrapeIncompleteError
from app.domain.dto import ProductDTO


def validate_product(product: ProductDTO) -> ProductDTO:
    """Require the minimum product fields needed for trustworthy analysis."""
    missing_fields = [
        field_name
        for field_name in ("title", "price")
        if not str(getattr(product, field_name, "")).strip()
    ]
    if missing_fields:
        raise ScrapeIncompleteError(
            "Incomplete product data; missing required fields: "
            + ", ".join(missing_fields)
        )
    return product


__all__ = ["validate_product"]
