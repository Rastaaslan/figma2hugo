"""Transforme les donnees brutes Figma en arbre de document plus simple a traiter."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from figma2hugo.pipeline.geometry import (
    snap_declared_board_width,
    snap_section_horizontal_box,
)
from figma2hugo.pipeline.models import (
    CoordinateSpace,
    GeometryBox,
    GeometrySource,
    IntermediatePipelineDocument,
    IssueSeverity,
    NodeKind,
    NormalizedNode,
    PipelineIssue,
    RawNode,
)
from figma2hugo.pipeline.naming import name_key as _name_key

SECTION_TYPES = {"FRAME", "GROUP", "SECTION", "COMPONENT", "INSTANCE"}
TEXT_TYPES = {"TEXT"}
ASSET_TYPES = {"RECTANGLE", "ELLIPSE", "VECTOR", "LINE", "STAR", "POLYGON", "BOOLEAN_OPERATION"}
WRAPPER_KEEP_TOKENS = ("hero", "header", "footer", "nav", "menu")
SECTION_NAME_PREFIXES = ("section-", "region-")
WRAPPER_PROMOTION_TOLERANCE_PX = 2.0


def normalize_document(root_payload: dict[str, Any]) -> IntermediatePipelineDocument:
    raw_root = RawNode.from_mapping(root_payload)
    diagnostics: list[PipelineIssue] = []
    page_origin = _node_bounds(raw_root, diagnostics=diagnostics)
    snapped_width = snap_declared_board_width(int(round(page_origin.width)))
    page_bounds = GeometryBox(
        x=0.0,
        y=0.0,
        width=float(snapped_width or page_origin.width),
        height=page_origin.height,
    )
    page_node = _normalize_node(
        raw_root,
        page_origin=page_origin,
        parent_absolute=page_origin,
        kind=NodeKind.PAGE,
        diagnostics=diagnostics,
        page_width=int(round(page_bounds.width)),
    )
    page_node = NormalizedNode(
        id=page_node.id,
        name=page_node.name,
        type=page_node.type,
        kind=NodeKind.PAGE,
        coordinate_space=CoordinateSpace.PAGE,
        geometry_source=page_node.geometry_source,
        absolute_bounds=page_node.absolute_bounds,
        page_bounds=page_bounds,
        parent_bounds=page_bounds,
        render_bounds=page_node.render_bounds,
        children=page_node.children,
        payload=page_node.payload,
    )
    sections = _section_candidates(page_node)
    if not sections:
        sections = (page_node,)
        diagnostics.append(
            PipelineIssue(
                code="no-section-candidates",
                severity=IssueSeverity.WARNING,
                message="No top-level section candidate found; page root is used as a section.",
                node_id=page_node.id,
            )
        )
    return IntermediatePipelineDocument(
        page=page_node,
        sections=sections,
        diagnostics=tuple(diagnostics),
    )


def _section_candidates(page_node: NormalizedNode) -> tuple[NormalizedNode, ...]:
    sections: list[NormalizedNode] = []
    page_width = int(round(page_node.page_bounds.width))
    for child in page_node.children:
        if child.kind not in {NodeKind.SECTION, NodeKind.CONTAINER}:
            continue
        promoted = _promoted_section_children(child)
        if promoted:
            sections.extend(
                _snap_section_candidate(section, page_width=page_width) for section in promoted
            )
            continue
        sections.append(_snap_section_candidate(child, page_width=page_width))
    return tuple(sections)


def _snap_section_candidate(section: NormalizedNode, *, page_width: int) -> NormalizedNode:
    left, width = snap_section_horizontal_box(
        left=section.page_bounds.x,
        width=section.page_bounds.width,
        page_width=page_width,
    )
    if left == section.page_bounds.x and width == section.page_bounds.width:
        return section
    return replace(
        section, page_bounds=section.page_bounds.with_horizontal_box(x=left, width=width)
    )


def _promoted_section_children(node: NormalizedNode) -> tuple[NormalizedNode, ...]:
    if not _is_promotable_wrapper(node):
        return ()
    candidates_by_id = {
        descendant.id: descendant
        for descendant in (
            _leaf_renderable_section(candidate) for candidate in _descendant_sections(node)
        )
        if descendant is not None
    }
    candidates = tuple(candidates_by_id.values())
    if len(candidates) != 1:
        return ()
    candidate = candidates[0]
    if not _bounds_contain(node.page_bounds, candidate.page_bounds):
        return ()
    if _has_renderable_content_outside_candidate(node, candidate):
        return ()
    return candidates


def _has_renderable_content_outside_candidate(
    node: NormalizedNode,
    candidate: NormalizedNode,
) -> bool:
    candidate_ids = {descendant.id for descendant in candidate.walk()}

    def inspect(current: NormalizedNode) -> bool:
        if current.id in candidate_ids:
            return False
        if current is not node and (
            _has_visual_style(current) or _has_direct_renderable_content(current)
        ):
            return True
        return any(inspect(child) for child in current.children)

    return inspect(node)


def _leaf_renderable_section(node: NormalizedNode) -> NormalizedNode | None:
    if node.kind is not NodeKind.SECTION or not _has_renderable_content(node):
        return None
    child_sections = tuple(
        candidate
        for child in _descendant_sections(node)
        if (candidate := _leaf_renderable_section(child)) is not None
    )
    if (
        len(child_sections) == 1
        and not _has_visual_style(node)
        and not _has_direct_renderable_content(node)
    ):
        return child_sections[0]
    if not child_sections:
        return node
    return None


def _is_promotable_wrapper(node: NormalizedNode) -> bool:
    name = node.name.strip().lower()
    if not _is_semantic_section_name(name):
        return False
    if any(token in name for token in WRAPPER_KEEP_TOKENS):
        return False
    if _has_visual_style(node) or _has_direct_renderable_content(node):
        return False
    return True


def _descendant_sections(node: NormalizedNode) -> tuple[NormalizedNode, ...]:
    sections: list[NormalizedNode] = []
    for child in node.children:
        if child.kind is NodeKind.SECTION:
            sections.append(child)
        sections.extend(_descendant_sections(child))
    return tuple(sections)


def _bounds_contain(parent: GeometryBox, child: GeometryBox) -> bool:
    tolerance = WRAPPER_PROMOTION_TOLERANCE_PX
    return (
        child.x >= parent.x - tolerance
        and child.y >= parent.y - tolerance
        and child.right <= parent.right + tolerance
        and child.bottom <= parent.bottom + tolerance
    )


def _has_renderable_content(node: NormalizedNode) -> bool:
    return (
        _has_visual_style(node)
        or _has_direct_renderable_content(node)
        or any(_has_renderable_content(child) for child in node.children)
    )


def _has_direct_renderable_content(node: NormalizedNode) -> bool:
    if (
        node.kind is NodeKind.TEXT
        and str(
            node.payload.get("characters")
            or node.payload.get("value")
            or node.payload.get("rawValue")
            or ""
        ).strip()
    ):
        return True
    if node.kind is NodeKind.ASSET and (
        node.payload.get("pipelineImageUrl")
        or node.payload.get("imageUrl")
        or node.payload.get("imageURL")
        or node.payload.get("image_url")
    ):
        return True
    return False


def _has_visual_style(node: NormalizedNode) -> bool:
    fills = node.payload.get("fills")
    if not isinstance(fills, list):
        return False
    for fill in fills:
        if isinstance(fill, dict) and fill.get("visible") is not False:
            if str(fill.get("type", "")).upper() in {"SOLID", "GRADIENT_LINEAR", "IMAGE"}:
                return True
    return False


def _normalize_node(
    raw_node: RawNode,
    *,
    page_origin: GeometryBox,
    parent_absolute: GeometryBox,
    kind: NodeKind | None = None,
    diagnostics: list[PipelineIssue],
    page_width: int,
) -> NormalizedNode:
    absolute_bounds = _node_bounds(raw_node, diagnostics=diagnostics)
    node_kind = kind or _infer_kind(raw_node)
    page_bounds = absolute_bounds.relative_to(page_origin)
    if node_kind in {NodeKind.SECTION, NodeKind.PAGE}:
        left, width = snap_section_horizontal_box(
            left=page_bounds.x,
            width=page_bounds.width,
            page_width=page_width,
        )
        page_bounds = page_bounds.with_horizontal_box(x=left, width=width)
    parent_bounds = absolute_bounds.relative_to(parent_absolute)
    children = tuple(
        _normalize_node(
            child,
            page_origin=page_origin,
            parent_absolute=absolute_bounds,
            diagnostics=diagnostics,
            page_width=page_width,
        )
        for child in raw_node.children
        if child.visible or _is_metadata_url_node(child)
    )
    return NormalizedNode(
        id=raw_node.id,
        name=raw_node.name,
        type=raw_node.type,
        kind=node_kind,
        coordinate_space=CoordinateSpace.PAGE,
        geometry_source=_geometry_source(raw_node),
        absolute_bounds=absolute_bounds,
        page_bounds=page_bounds,
        parent_bounds=parent_bounds,
        render_bounds=raw_node.render_bounds.relative_to(page_origin)
        if raw_node.render_bounds is not None
        else None,
        children=children,
        payload=_safe_payload(raw_node.payload),
    )


def _node_bounds(raw_node: RawNode, *, diagnostics: list[PipelineIssue]) -> GeometryBox:
    if raw_node.absolute_bounds is not None:
        return raw_node.absolute_bounds
    if raw_node.render_bounds is not None:
        diagnostics.append(
            PipelineIssue(
                code="bounds-from-render-bounds",
                severity=IssueSeverity.WARNING,
                message="Node has no absoluteBoundingBox; absoluteRenderBounds was used.",
                node_id=raw_node.id,
            )
        )
        return raw_node.render_bounds
    diagnostics.append(
        PipelineIssue(
            code="missing-bounds",
            severity=IssueSeverity.ERROR,
            message="Node has no usable geometry bounds.",
            node_id=raw_node.id,
        )
    )
    return GeometryBox(x=0.0, y=0.0, width=0.0, height=0.0)


def _geometry_source(raw_node: RawNode) -> GeometrySource:
    if raw_node.absolute_bounds is not None:
        return GeometrySource.BOUNDING_BOX
    if raw_node.render_bounds is not None:
        return GeometrySource.RENDER_BOUNDS
    return GeometrySource.MISSING


def _infer_kind(raw_node: RawNode) -> NodeKind:
    node_type = raw_node.type.strip().upper()
    node_name = raw_node.name.strip().lower()
    if node_type in TEXT_TYPES:
        return NodeKind.TEXT
    if node_type in ASSET_TYPES:
        return NodeKind.ASSET
    if node_type in SECTION_TYPES and (
        _is_semantic_section_name(node_name)
        or node_name in {"header", "footer"}
        or node_name.startswith("footer-")
    ):
        return NodeKind.SECTION
    if node_type in SECTION_TYPES:
        return NodeKind.CONTAINER
    return NodeKind.UNKNOWN


def _is_metadata_url_node(raw_node: RawNode) -> bool:
    if raw_node.type.strip().upper() not in TEXT_TYPES:
        return False
    name = _name_key(raw_node.name)
    value = str(
        raw_node.payload.get("characters")
        or raw_node.payload.get("value")
        or raw_node.payload.get("rawValue")
        or ""
    ).strip()
    return bool(
        name.startswith(("href-", "url-", "link-url-"))
        and value.lower().startswith(("http://", "https://", "/"))
    )


def _is_semantic_section_name(node_name: str) -> bool:
    return node_name.startswith(SECTION_NAME_PREFIXES)


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("children", None)
    return cleaned
