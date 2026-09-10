from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ReviewEvidenceOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    review_index: StrictInt
    is_relevant: bool = False
    translation_zh: str = ""
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""
    strength: str = ""


class ComplementEvidenceOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reviews: list[ReviewEvidenceOutput] = Field(default_factory=list)


__all__ = ["ComplementEvidenceOutput", "ReviewEvidenceOutput"]
