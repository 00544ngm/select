"""Deterministic gates for link-driven product pairing candidates.

The model may suggest candidate names, but edible goods must never reach the
pairing scorer.  This module deliberately has no network or database
dependencies so the same classification is used for live and historical
results.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

FoodFilterStatus = Literal["food", "allowed", "needs_verification"]


@dataclass(frozen=True)
class ProductPairingClassification:
    """Stable result of the product-type gate."""

    status: FoodFilterStatus
    reason: str
    matched_terms: tuple[str, ...] = ()


# Keep patterns specific enough that appliance names such as ``pepper
# grinder`` are not classified as edible products.  Terms are returned in the
# same order in which they are declared, making output and tests deterministic.
_FOOD_TERMS: tuple[tuple[str, str], ...] = (
    ("black peppercorns", "black peppercorns"),
    ("peppercorns", "peppercorns"),
    ("peppercorn", "peppercorn"),
    ("coarse sea salt", "coarse sea salt"),
    ("sea salt", "sea salt"),
    ("himalayan salt", "himalayan salt"),
    ("salt crystals", "salt crystals"),
    ("cumin seeds", "cumin seeds"),
    ("coriander seeds", "coriander seeds"),
    ("seasoning", "seasoning"),
    ("spice", "spice"),
    ("beverage", "beverage"),
    ("drink", "drink"),
    ("snack", "snack"),
    ("ingredient", "ingredient"),
    ("edible", "edible"),
    ("supplement", "supplement"),
    ("vitamin", "vitamin"),
    ("coffee beans", "coffee beans"),
    ("tea leaves", "tea leaves"),
    ("food", "food"),
)

_NON_FOOD_CONTEXTS: tuple[str, ...] = (
    "food processor",
    "food storage",
    "food safe",
    "food-safe",
    "spice rack",
    "spice storage",
    "spice jar",
    "spice container",
    "spice organizer",
    "spice grinder",
    "spice funnel",
    "pepper grinder",
    "pepper mill",
    "replacement blade",
)

_ALLOWED_TERMS: tuple[tuple[str, str], ...] = (
    ("ink cartridge", "ink cartridge"),
    ("cartridge", "cartridge"),
    ("filter", "filter"),
    ("battery", "battery"),
    ("batteries", "batteries"),
    ("blade", "blade"),
    ("cleaning brush", "cleaning brush"),
    ("brush", "brush"),
    ("replacement part", "replacement part"),
    ("grinder", "grinder"),
    ("mill", "mill"),
    ("lens", "lens"),
    ("camera bag", "camera bag"),
    ("cable", "cable"),
    ("usb", "usb"),
    ("scissors", "scissors"),
    ("rack", "rack"),
    ("container", "container"),
    ("case", "case"),
    ("cover", "cover"),
    ("stand", "stand"),
    ("holder", "holder"),
    ("adapter", "adapter"),
    ("charger", "charger"),
    ("tripod", "tripod"),
    ("funnel", "funnel"),
    ("processor", "processor"),
    ("storage", "storage"),
)

_AMBIGUOUS_TERMS: tuple[tuple[str, str], ...] = (
    ("refill", "refill"),
    ("natural", "natural"),
    ("organic", "organic"),
    ("powder", "powder"),
    ("extract", "extract"),
    ("consumable", "consumable"),
)


def classify_candidate(
    title: str,
    *,
    keywords: Iterable[str] | Mapping[str, str] | None = None,
    product_type: str = "",
    description: str = "",
) -> ProductPairingClassification:
    """Classify a candidate as edible, allowed, or requiring verification.

    ``title`` is the primary signal.  Optional keywords, product type, and
    description are included because scraped listings often put the decisive
    product classification outside the title.  Food terms take precedence;
    otherwise known non-food parts/maintenance items are allowed.  Ambiguous
    refill-like language is intentionally held for verification.
    """

    text = _combined_text(title, keywords, product_type, description)
    non_food_context = _find_phrase_matches(text, _NON_FOOD_CONTEXTS)
    food_matches = _find_matches(text, _FOOD_TERMS)
    if non_food_context:
        food_matches = tuple(
            match for match in food_matches if match not in {"food", "spice"}
        )
    if food_matches:
        return ProductPairingClassification(
            status="food",
            reason="edible product term detected: " + ", ".join(food_matches),
            matched_terms=food_matches,
        )

    allowed_matches = _find_matches(text, _ALLOWED_TERMS)
    if allowed_matches:
        return ProductPairingClassification(
            status="allowed",
            reason="non-food accessory or consumable detected: "
            + ", ".join(allowed_matches),
            matched_terms=allowed_matches,
        )

    ambiguous_matches = _find_matches(text, _AMBIGUOUS_TERMS)
    if ambiguous_matches or not text:
        reason = (
            "ambiguous product type; verify that the candidate is non-food"
            if ambiguous_matches
            else "product type is missing; verify before recommending"
        )
        return ProductPairingClassification(
            status="needs_verification",
            reason=reason,
            matched_terms=ambiguous_matches,
        )

    return ProductPairingClassification(
        status="needs_verification",
        reason="no deterministic food or non-food product type signal",
    )


def _combined_text(
    title: str,
    keywords: Iterable[str] | Mapping[str, str] | None,
    product_type: str,
    description: str,
) -> str:
    parts = [title, product_type, description]
    if isinstance(keywords, Mapping):
        parts.extend(keywords.keys())
        parts.extend(keywords.values())
    elif keywords:
        parts.extend(str(item) for item in keywords)
    normalized = " ".join(str(part or "") for part in parts)
    normalized = normalized.casefold()
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


def _find_matches(
    text: str, patterns: tuple[tuple[str, str], ...]
) -> tuple[str, ...]:
    matches: list[str] = []
    for raw_pattern, label in patterns:
        pattern = re.sub(r"[^\w]+", " ", raw_pattern.casefold()).strip()
        if re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", text):
            matches.append(label)
    return tuple(matches)


def _find_phrase_matches(text: str, phrases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        phrase
        for phrase in phrases
        if re.search(
            rf"(?<!\w){re.escape(re.sub(r'[^\w]+', ' ', phrase.casefold()).strip())}(?!\w)",
            text,
        )
    )


__all__ = [
    "FoodFilterStatus",
    "ProductPairingClassification",
    "classify_candidate",
]
