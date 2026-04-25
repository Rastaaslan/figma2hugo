from __future__ import annotations

from pydantic import Field

from figma2hugo.model.base import FigmaBaseModel


class Bounds(FigmaBaseModel):
    x: float = 0
    y: float = 0
    width: float = Field(ge=0)
    height: float = Field(ge=0)
