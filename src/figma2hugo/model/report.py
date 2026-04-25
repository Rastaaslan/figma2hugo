from __future__ import annotations

from pydantic import Field

from figma2hugo.model.base import FigmaBaseModel


class GenerationReport(FigmaBaseModel):
    build_ok: bool = False
    visual_score: float | None = Field(default=None, ge=0, le=1)
    missing_assets: list[str] = Field(default_factory=list)
    missing_texts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
