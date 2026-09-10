from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JudgmentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alignment_review: list[dict[str, Any]] = Field(default_factory=list)
    motivation_review: dict[str, Any] = Field(default_factory=dict)
    price_calculation: dict[str, Any] = Field(default_factory=dict)
    veto_check: dict[str, Any] = Field(default_factory=dict)
    c_score: dict[str, Any] = Field(default_factory=dict)
    b_score: dict[str, Any] = Field(default_factory=dict)
    final_grade: str = ""
    delivery_package: dict[str, Any] = Field(default_factory=dict)
    priority_score: float = Field(default=0.0)
    product_title_zh: str = ""
    user_rationality: dict[str, Any] = Field(default_factory=dict)

    @field_validator("priority_score", mode="before")
    @classmethod
    def clamp_priority(cls, v: Any) -> float:
        if v is None:
            return 0.0
        try:
            return max(0.0, min(100.0, float(v)))
        except (ValueError, TypeError):
            return 0.0

    @field_validator("final_grade", mode="before")
    @classmethod
    def normalize_grade(cls, v: Any) -> str:
        if not v:
            return ""
        s = str(v).strip().upper()
        return s[0] if s and s[0] in ("S", "A", "B", "C") else ""


__all__ = ["JudgmentOutput"]
