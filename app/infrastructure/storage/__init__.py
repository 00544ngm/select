from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.domain.dto import HypothesisResultDTO, JudgmentResultDTO, ProductDTO


def _result_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{timestamp}_{uuid4().hex[:8]}"


class FileStorage:
    """Simple file-based storage abstraction."""

    def __init__(self, base_dir: str = "output/bundling") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def save_json(self, data: dict, filename: str) -> Path:
        path = self._base / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_json(self, filename: str) -> dict:
        path = self._base / filename
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))


class BundleResultStore:
    """Store for A+B bundling results."""

    def __init__(self, base_dir: str = "output/bundling") -> None:
        self._storage = FileStorage(base_dir)

    def save_hypothesis(self, result: HypothesisResultDTO, suffix: str = "") -> Path:
        timestamp = _result_id()
        data = {
            "model_version": result.model_version,
            "product": {
                "url": result.product.url,
                "title": result.product.title,
                "price": result.product.price,
                "rating": result.product.rating,
                "review_count": result.product.review_count,
            },
            "product_analysis": result.product_analysis,
            "product_profile": result.product_profile,
            "evidence_table": result.evidence_table,
            "strategic_judgment": result.strategic_judgment,
            "directions": [asdict(d) for d in result.directions],
            "result_status": result.result_status,
            "result_message": result.result_message,
            "raw_direction_count": result.raw_direction_count,
            "qualified_direction_count": result.qualified_direction_count,
            "hold_direction_count": result.hold_direction_count,
            "rejected_direction_count": result.rejected_direction_count,
            "rejection_summary": result.rejection_summary,
            "audit_performed": result.audit_performed,
            "audit_reason": result.audit_reason,
            "initial_raw_direction_count": result.initial_raw_direction_count,
            "audit_raw_direction_count": result.audit_raw_direction_count,
            "audit_outcome": result.audit_outcome,
            "provider": result.provider,
            "provider_model": result.provider_model,
            "keyword_pack": result.keyword_pack,
            "generated_at": timestamp,
        }
        return self._storage.save_json(data, f"hypothesis_{timestamp}{suffix}.json")

    def save_judgment(self, result: JudgmentResultDTO,
                      product_a: ProductDTO | None = None,
                      products_b: list[ProductDTO] | None = None,
                      suffix: str = "") -> Path:
        timestamp = _result_id()
        data: dict = {
            "alignment_review": result.alignment_review,
            "motivation_review": result.motivation_review,
            "price_calculation": result.price_calculation,
            "veto_check": result.veto_check,
            "c_score": result.c_score,
            "b_score": result.b_score,
            "final_grade": result.final_grade,
            "delivery_package": result.delivery_package,
            "priority_score": result.priority_score,
            "generated_at": timestamp,
        }
        if product_a:
            data["product_a"] = {"url": product_a.url, "title": product_a.title}
        if products_b:
            data["products_b"] = [{"url": p.url, "title": p.title} for p in products_b]
        return self._storage.save_json(data, f"judgment_{timestamp}{suffix}.json")


__all__ = [
    "BundleResultStore",
    "FileStorage",
]
