from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.dto import ProductDTO


@dataclass(frozen=True)
class ProductFact:
    fact_id: str
    field: str
    text: str


def build_product_facts(product: ProductDTO) -> tuple[ProductFact, ...]:
    """Build stable, addressable facts from data actually collected by the server."""
    facts: list[ProductFact] = []

    def add(fact_id: str, field: str, value: object) -> None:
        text = str(value).strip() if value is not None else ""
        if text:
            facts.append(ProductFact(fact_id=fact_id, field=field, text=text))

    add("url", "URL", product.url)
    add("title", "Title", product.title)
    add("price", "Price", product.price)
    add("rating", "Rating", product.rating)
    add("review_count", "Review count", product.review_count)
    for index, text in enumerate(product.bullet_points):
        add(f"bullet:{index}", "Bullet point", text)
    add("description", "Description", product.description)
    for key, value in product.attributes.items():
        add(f"attribute:{key}", f"Attribute {key}", value)
    for index, text in enumerate(product.review_snippets):
        add(f"review:{index}", "Review", text)
    for index, pair in enumerate(product.qa_pairs):
        add(f"qa:{index}", "Q&A", _structured_text(pair))
    for index, item in enumerate(product.fbt_items):
        add(f"fbt:{index}", "Frequently bought together", _structured_text(item))
    return tuple(facts)


def validate_fact_ids(
    fact_ids: Iterable[str], facts: Sequence[ProductFact]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separate references that point to server facts from unknown references."""
    known = {fact.fact_id for fact in facts}
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw_id in fact_ids:
        fact_id = str(raw_id).strip()
        if not fact_id or fact_id in seen:
            continue
        seen.add(fact_id)
        (valid if fact_id in known else invalid).append(fact_id)
    return tuple(valid), tuple(invalid)


def render_product_facts(facts: Sequence[ProductFact]) -> str:
    return "\n".join(
        f"[{fact.fact_id}] {fact.field}: {fact.text}" for fact in facts
    )


def _structured_text(value: object) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


__all__ = [
    "ProductFact",
    "build_product_facts",
    "render_product_facts",
    "validate_fact_ids",
]
