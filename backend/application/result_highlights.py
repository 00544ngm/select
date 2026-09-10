from __future__ import annotations

from typing import Any


def _primary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("structured_directions") or payload.get("product_title"):
        return payload
    models = payload.get("models")
    if isinstance(models, dict):
        if isinstance(models.get("gpt"), dict):
            return models["gpt"]
        first_model = next((item for item in models.values() if isinstance(item, dict)), None)
        if first_model is not None:
            return first_model
    return payload


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def extract_result_highlights(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    source = _primary_payload(payload)
    images = source.get("product_images")
    product_image = (
        images[0]
        if isinstance(images, list) and images and isinstance(images[0], str)
        else None
    )

    raw_directions = source.get("structured_directions")
    directions = [
        item for item in raw_directions or [] if isinstance(item, dict)
    ]
    scored = [
        item for item in directions
        if item.get("rejected") is not True
        and _direction_score(item) is not None
    ]
    top = max(
        scored,
        key=lambda item: _direction_score(item) or 0,
    ) if scored else {}
    keywords = top.get("keywords")

    return {
        "provider": source.get("provider") or None,
        "provider_model": source.get("provider_model") or None,
        "product_title": source.get("product_title") or None,
        "product_title_zh": source.get("product_title_zh") or None,
        "product_id": source.get("product_id") or None,
        "product_image": product_image,
        "top_direction_name": top.get("name") or None,
        "top_direction_keywords": (
            dict(keywords) if isinstance(keywords, dict) else {}
        ),
        "top_direction_score": _direction_score(top),
        "top_direction_type": top.get("type") or None,
    }


def _direction_score(item: dict[str, Any]) -> float | None:
    final_score = _number(item.get("final_score"))
    if final_score is not None and final_score > 0:
        return final_score
    return _number(item.get("score"))


__all__ = ["extract_result_highlights"]
