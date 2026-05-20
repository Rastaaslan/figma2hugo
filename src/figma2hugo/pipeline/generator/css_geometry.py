"""Petits helpers de geometrie CSS utilises par les templates Hugo generes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from figma2hugo.pipeline.geometry import (
    snap_declared_board_width,
    snap_page_horizontal_extent,
    snap_section_horizontal_box,
)


@dataclass(frozen=True)
class PageGeometry:
    width: int
    height: int
    origin_x: float
    origin_y: float


@dataclass(frozen=True)
class SectionGeometry:
    left: float
    top: float
    width: int
    height: int


def compute_page_geometry(
    page: dict[str, Any],
    sections: list[dict[str, Any]],
    *,
    prefer_declared_width: bool = False,
) -> PageGeometry:
    raw_width = snap_declared_board_width(int(float(page.get("width", 0) or 0)))
    raw_height = int(float(page.get("height", 0) or 0))
    if not sections:
        return PageGeometry(raw_width or 1440, raw_height, 0.0, 0.0)

    section_bounds = [section.get("bounds", {}) or {} for section in sections]
    lefts = [float(bounds.get("x", 0) or 0) for bounds in section_bounds]
    tops = [float(bounds.get("y", 0) or 0) for bounds in section_bounds]
    rights = [
        float(bounds.get("x", 0) or 0) + float(bounds.get("width", 0) or 0)
        for bounds in section_bounds
    ]
    bottoms = [
        float(bounds.get("y", 0) or 0) + float(bounds.get("height", 0) or 0)
        for bounds in section_bounds
    ]

    origin_x = min(lefts)
    origin_y = min(tops)
    max_right = max(rights)
    extent_width = max(0.0, max_right - origin_x)
    origin_x, extent_width = snap_page_horizontal_extent(
        raw_width=raw_width,
        origin_x=origin_x,
        max_right=max_right,
        extent_width=extent_width,
    )
    extent_height = max(0.0, max(bottoms) - origin_y)
    page_width = (
        raw_width
        if prefer_declared_width and raw_width > 0
        else max(raw_width or 0, int(round(extent_width)) or 0) or 1440
    )
    page_height = max(raw_height or 0, int(round(extent_height)) or 0)
    return PageGeometry(page_width, page_height, origin_x, origin_y)


def compute_section_geometry(
    section: dict[str, Any],
    *,
    page_width: int,
    page_origin_x: float,
    page_origin_y: float,
) -> SectionGeometry:
    bounds = section.get("bounds", {}) or {}
    left = float(bounds.get("x", 0) or 0) - page_origin_x
    top = float(bounds.get("y", 0) or 0) - page_origin_y
    left, width_value = snap_section_horizontal_box(
        left=left,
        width=float(bounds.get("width", 0) or 0),
        page_width=page_width,
    )
    return SectionGeometry(
        left=left,
        top=top,
        width=int(round(width_value)),
        height=int(float(bounds.get("height", 0) or 0)),
    )
