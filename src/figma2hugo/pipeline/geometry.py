"""Primitives de geometrie pour deplacer, mesurer et parcourir les noeuds de rendu."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from figma2hugo.pipeline.models import GeometryBox, RenderNodePlan

CANONICAL_BOARD_WIDTHS = (1920, 834, 402)
BOARD_WIDTH_SNAP_TOLERANCE_PX = 8.0
SECTION_EDGE_SNAP_TOLERANCE_PX = 6.0
GEOMETRY_EPSILON = 0.01


def snap_declared_board_width(width: int) -> int:
    if width <= 0:
        return width
    for board_width in CANONICAL_BOARD_WIDTHS:
        if abs(width - board_width) <= BOARD_WIDTH_SNAP_TOLERANCE_PX:
            return board_width
    return width


def snap_page_horizontal_extent(
    *,
    raw_width: int,
    origin_x: float,
    max_right: float,
    extent_width: float,
) -> tuple[float, float]:
    if raw_width <= 0:
        return origin_x, extent_width
    tolerance = SECTION_EDGE_SNAP_TOLERANCE_PX
    if abs(origin_x) <= tolerance and (
        abs(max_right - raw_width) <= tolerance or abs(extent_width - raw_width) <= tolerance
    ):
        return 0.0, float(raw_width)
    center = (origin_x + max_right) / 2
    page_center = raw_width / 2
    if (
        extent_width > raw_width
        and origin_x < 0
        and max_right > raw_width
        and abs(center - page_center) <= tolerance
    ):
        return 0.0, float(raw_width)
    return origin_x, extent_width


def snap_section_horizontal_box(
    *,
    left: float,
    width: float,
    page_width: int,
) -> tuple[float, float]:
    if page_width <= 0 or width <= 0:
        return left, width
    tolerance = SECTION_EDGE_SNAP_TOLERANCE_PX
    right = left + width
    if abs(left) <= tolerance and (
        abs(right - page_width) <= tolerance or abs(width - page_width) <= tolerance
    ):
        return 0.0, float(page_width)
    center = left + (width / 2)
    page_center = page_width / 2
    if (
        width > page_width
        and left < 0
        and right > page_width
        and abs(center - page_center) <= tolerance
    ):
        return 0.0, float(page_width)
    if abs(left) <= 0.01:
        return 0.0, width
    return left, width


def shifted_bounds(bounds: GeometryBox, *, dx: float, dy: float) -> GeometryBox:
    return GeometryBox(
        x=bounds.x + dx,
        y=bounds.y + dy,
        width=bounds.width,
        height=bounds.height,
    )


def shift_node_tree(node: RenderNodePlan, *, dx: float, dy: float) -> RenderNodePlan:
    return replace(
        node,
        bounds=shifted_bounds(node.bounds, dx=dx, dy=dy),
        children=tuple(shift_node_tree(child, dx=dx, dy=dy) for child in node.children),
    )


def walk_render_nodes(
    nodes: tuple[RenderNodePlan, ...],
    *,
    children: Callable[[RenderNodePlan], tuple[RenderNodePlan, ...]] | None = None,
) -> tuple[RenderNodePlan, ...]:
    flattened: list[RenderNodePlan] = []
    child_nodes = children or (lambda node: node.children)
    for node in nodes:
        flattened.append(node)
        flattened.extend(walk_render_nodes(child_nodes(node), children=children))
    return tuple(flattened)


def vertical_overlap(a: GeometryBox, b: GeometryBox) -> float:
    return max(0.0, min(a.bottom, b.bottom) - max(a.y, b.y))


def union_node_bounds(nodes: Iterable[RenderNodePlan | None]) -> GeometryBox | None:
    present_nodes = tuple(node for node in nodes if node is not None)
    if not present_nodes:
        return None
    return union_geometry_bounds(node.bounds for node in present_nodes)


def union_geometry_bounds(bounds: Iterable[GeometryBox | None]) -> GeometryBox | None:
    present_bounds = tuple(box for box in bounds if box is not None)
    if not present_bounds:
        return None
    left = min(box.x for box in present_bounds)
    top = min(box.y for box in present_bounds)
    right = max(box.right for box in present_bounds)
    bottom = max(box.bottom for box in present_bounds)
    return GeometryBox(x=left, y=top, width=right - left, height=bottom - top)
