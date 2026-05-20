"""Ajustements web generiques appliques apres le plan de rendu Figma-first."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import NamedTuple

from figma2hugo.pipeline.components import FORM_CONTROL_COMPONENTS
from figma2hugo.pipeline.geometry import GEOMETRY_EPSILON
from figma2hugo.pipeline.geometry import (
    shift_node_tree as _shift_node_tree,
)
from figma2hugo.pipeline.geometry import (
    shifted_bounds as _shift_bounds,
)
from figma2hugo.pipeline.geometry import (
    walk_render_nodes as _walk_nodes,
)
from figma2hugo.pipeline.models import (
    GeometryBox,
    IssueSeverity,
    NodeKind,
    PipelineIssue,
    RenderNodePlan,
    RenderPlan,
    RenderSectionPlan,
)
from figma2hugo.pipeline.naming import (
    name_key as _name_key,
)
from figma2hugo.pipeline.semantic_accordion import (
    adjust_accordion_item_node as _adjust_accordion_item_node,
)
from figma2hugo.pipeline.semantic_accordion import (
    adjust_accordion_node as _adjust_accordion_node,
)
from figma2hugo.pipeline.semantic_limits import (
    ACCORDION_SECTION_PADDING_PX,
    BAND_SECTION_PADDING_MAX_PX,
    BAND_SECTION_PADDING_MIN_PX,
    BAND_SECTION_PADDING_RATIO,
    BAND_VISUAL_EDGE_TOLERANCE_RATIO,
    BAND_VISUAL_MAX_EDGE_TOLERANCE_PX,
    BAND_VISUAL_MIN_EDGE_TOLERANCE_PX,
    BAND_VISUAL_MIN_WIDTH_RATIO,
    DECORATIVE_SECTION_OVERFLOW_TOLERANCE_PX,
    FLOW_SIBLING_HORIZONTAL_OVERLAP_RATIO,
    FLOW_SIBLING_OVERLAP_TOLERANCE_PX,
    FOOTER_BG_VERTICAL_PADDING_PX,
    FOOTER_LEGAL_TEXT_MARKERS,
    FOOTER_READABILITY_MAX_PAGE_WIDTH,
    FOOTER_SECTION_MIN_HEIGHT_PX,
    FOOTER_TEXT_HORIZONTAL_PADDING_PX,
    FOOTER_TEXT_MIN_FONT_SIZE_PX,
    FOOTER_TEXT_MIN_HEIGHT_PX,
    FOOTER_TEXT_MIN_LINE_HEIGHT_PX,
    FOOTER_TEXT_TOP_PADDING_PX,
    FORM_SCALE_MAX_PAGE_WIDTH,
    FORM_SECTION_PADDING_PX,
    HEADING_EXPLICIT_LINE_PRESERVE_MIN_PAGE_WIDTH,
    HEADING_EXPLICIT_LINE_PRESERVE_TOLERANCE_PX,
    SECTION_COMPACTION_MIN_EMPTY_PX,
    TEXT_AVERAGE_CHAR_WIDTH_RATIO,
    TEXT_INTRINSIC_TOLERANCE_PX,
    TEXT_SIBLING_HORIZONTAL_OVERLAP_RATIO,
    TEXT_SIBLING_OVERLAP_TOLERANCE_PX,
    TEXT_STACK_EXCLUDED_COMPONENTS,
)


class AdjustmentResult(NamedTuple):
    plan: RenderPlan
    issues: tuple[PipelineIssue, ...]


class _SectionAdjustment(NamedTuple):
    section: RenderSectionPlan
    issues: tuple[PipelineIssue, ...]


class _NodeAdjustment(NamedTuple):
    node: RenderNodePlan
    issues: tuple[PipelineIssue, ...]


_NodesAndIssues = tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]
_SectionNodePhase = Callable[
    [tuple[RenderNodePlan, ...]],
    _NodesAndIssues,
]


def apply_semantic_adjustments(plan: RenderPlan) -> AdjustmentResult:
    """Apply deterministic product-readability adjustments to semantic nodes."""
    # Les sections sont traitees de haut en bas. Si une section gagne ou perd
    # de la hauteur apres un ajustement web generique, les sections suivantes
    # bougent du meme delta pour garder une page continue.
    sections: list[RenderSectionPlan] = []
    issues: list[PipelineIssue] = []
    cumulative_shift_y = 0.0
    for section in plan.sections:
        working_section = (
            _shift_section(section, dy=cumulative_shift_y) if cumulative_shift_y else section
        )
        if cumulative_shift_y:
            issues.append(
                PipelineIssue(
                    code="section-shifted-for-semantic-content",
                    severity=IssueSeverity.INFO,
                    message="Section was shifted after semantic geometry adjustments above it.",
                    node_id=section.section_id,
                    width=plan.width,
                    metrics={
                        "beforeY": round(section.bounds.y, 3),
                        "afterY": round(working_section.bounds.y, 3),
                        "shiftY": round(cumulative_shift_y, 3),
                    },
                )
            )
        adjusted = _adjust_section(plan, working_section)
        sections.append(adjusted.section)
        issues.extend(adjusted.issues)
        delta_height = adjusted.section.bounds.height - working_section.bounds.height
        if abs(delta_height) > GEOMETRY_EPSILON:
            cumulative_shift_y += delta_height

    page_bottom = max((section.bounds.bottom for section in sections), default=float(plan.height))
    has_section_compaction = _has_issue(issues, "section-compacted-for-semantic-content")
    height = (
        max(1, int(round(page_bottom)))
        if has_section_compaction and page_bottom < plan.height
        else max(plan.height, int(round(page_bottom)))
    )
    if issues and height > plan.height:
        issues.append(
            PipelineIssue(
                code="page-height-expanded-for-semantic-content",
                severity=IssueSeverity.INFO,
                message="Page height was expanded to contain semantic readability adjustments.",
                width=plan.width,
                metrics={"beforeHeight": plan.height, "afterHeight": height},
            )
        )
    elif has_section_compaction and height < plan.height:
        issues.append(
            PipelineIssue(
                code="page-height-compacted-for-semantic-content",
                severity=IssueSeverity.INFO,
                message="Page height was compacted after semantic section compaction.",
                width=plan.width,
                metrics={"beforeHeight": plan.height, "afterHeight": height},
            )
        )

    return AdjustmentResult(
        plan=replace(plan, height=height, sections=tuple(sections)),
        issues=tuple(issues),
    )


def _adjust_section(plan: RenderPlan, section: RenderSectionPlan) -> _SectionAdjustment:
    nodes: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    # Les phases de section passent avant les phases de noeud quand la decision
    # depend du bandeau complet, par exemple la lisibilite du texte dans un CTA.
    source_nodes = _run_section_node_phases(
        section.nodes,
        issues,
        (lambda current: _normalize_band_text_readability(plan, section, current),),
    )
    for node in source_nodes:
        adjusted = _adjust_node(plan, section, node)
        nodes.append(adjusted.node)
        issues.extend(adjusted.issues)

    nodes = list(
        _run_section_node_phases(
            tuple(nodes),
            issues,
            (
                # Ce sont des garde-fous navigateur generiques, pas des corrections par page.
                lambda current: _adjust_footer_legal_text(plan, section, current),
                lambda current: _contain_narrow_decorative_overflow(plan, section, current),
            ),
        )
    )
    nodes = list(
        _run_section_node_phases(
            tuple(nodes),
            issues,
            (lambda current: _contain_full_band_background_overflow(plan, section, current),),
        )
    )
    content_bottom = _section_visible_content_bottom(
        tuple(nodes),
        default=section.bounds.y,
        section_bounds=section.bounds,
    )
    should_expand_for_content = content_bottom > section.bounds.bottom + GEOMETRY_EPSILON
    next_bounds = section.bounds
    expansion_padding = _section_expansion_padding(section, tuple(nodes))
    expansion_bottom = content_bottom
    if should_expand_for_content and (expansion_bottom + expansion_padding > section.bounds.bottom):
        after_height = expansion_bottom + expansion_padding - section.bounds.y
        if _is_footer_section(section):
            after_height = max(after_height, FOOTER_SECTION_MIN_HEIGHT_PX)
        next_bounds = GeometryBox(
            x=section.bounds.x,
            y=section.bounds.y,
            width=section.bounds.width,
            height=after_height,
        )
        if not _is_compact_full_bleed_visual_section(section, tuple(nodes)):
            nodes_tuple, anchored_issues = _shift_bottom_anchored_section_nodes(
                original_nodes=section.nodes,
                adjusted_nodes=tuple(nodes),
                original_bounds=section.bounds,
                next_bounds=next_bounds,
                width=plan.width,
            )
            nodes = list(nodes_tuple)
            issues.extend(anchored_issues)
        nodes = list(
            _stretch_section_backgrounds(
                tuple(nodes),
                original_bounds=section.bounds,
                next_bounds=next_bounds,
            )
        )
        issues.append(
            PipelineIssue(
                code="section-expanded-for-semantic-content",
                severity=IssueSeverity.INFO,
                message="Section height was expanded to contain semantic readability adjustments.",
                node_id=section.section_id,
                width=plan.width,
                metrics={
                    "beforeHeight": section.bounds.height,
                    "afterHeight": after_height,
                    "contentBottom": expansion_bottom,
                },
            )
        )
    elif _should_compact_section_for_semantic_content(section, tuple(nodes), content_bottom):
        after_height = (
            content_bottom + _section_compaction_padding(section, tuple(nodes)) - section.bounds.y
        )
        next_bounds = GeometryBox(
            x=section.bounds.x,
            y=section.bounds.y,
            width=section.bounds.width,
            height=max(1.0, after_height),
        )
        nodes = list(
            _resize_section_backgrounds(
                tuple(nodes),
                original_bounds=section.bounds,
                next_bounds=next_bounds,
            )
        )
        issues.append(
            PipelineIssue(
                code="section-compacted-for-semantic-content",
                severity=IssueSeverity.INFO,
                message="Section height was compacted around visible semantic content.",
                node_id=section.section_id,
                width=plan.width,
                metrics={
                    "beforeHeight": section.bounds.height,
                    "afterHeight": next_bounds.height,
                    "contentBottom": content_bottom,
                },
            )
        )

    nodes = list(_apply_sibling_stack_order(tuple(nodes)))

    return _SectionAdjustment(
        section=replace(section, bounds=next_bounds, nodes=tuple(nodes)),
        issues=tuple(issues),
    )


def _run_section_node_phases(
    nodes: tuple[RenderNodePlan, ...],
    issues: list[PipelineIssue],
    phases: tuple[_SectionNodePhase, ...],
) -> tuple[RenderNodePlan, ...]:
    current = nodes
    for phase in phases:
        current, phase_issues = phase(current)
        issues.extend(phase_issues)
    return current


def _adjust_node(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
) -> _NodeAdjustment:
    if node.component == "form":
        return _adjust_form_node(plan, section, node)
    if node.component in FORM_CONTROL_COMPONENTS:
        return _NodeAdjustment(
            node=_normalize_native_form_control_tree(node, width=plan.width),
            issues=(),
        )
    if node.component == "accordion":
        accordion_adjusted = _adjust_accordion_node(
            plan,
            section,
            node,
            adjust_child=_adjust_node,
            expand_node=_expand_node_for_adjusted_children,
        )
        return _NodeAdjustment(node=accordion_adjusted.node, issues=accordion_adjusted.issues)
    if node.component == "accordion-item":
        accordion_item_adjusted = _adjust_accordion_item_node(
            plan,
            section,
            node,
            adjust_child=_adjust_node,
            expand_node=_expand_node_for_adjusted_children,
        )
        return _NodeAdjustment(
            node=accordion_item_adjusted.node, issues=accordion_item_adjusted.issues
        )
    if node.kind is NodeKind.TEXT:
        return _adjust_text_node(plan, section, node)

    children: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for child in node.children:
        adjusted = _adjust_node(plan, section, child)
        children.append(adjusted.node)
        issues.extend(adjusted.issues)
    if _is_accordion_container_node(node):
        children_tuple, flow_issues = _stack_accordion_like_children(
            tuple(children),
            width=plan.width,
            parent_id=node.node_id,
        )
        children = list(children_tuple)
        issues.extend(flow_issues)
    if tuple(children) == node.children:
        return _compact_structure_wrapper_node(plan, node, node.children, tuple(issues))
    compacted = _compact_structure_wrapper_node(plan, node, tuple(children), tuple(issues))
    if compacted.node.bounds != node.bounds:
        return compacted
    return _expand_node_for_adjusted_children(plan, node, tuple(children), tuple(issues))


def _adjust_text_node(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
) -> _NodeAdjustment:
    style, preserves_explicit_lines = _preserve_explicit_heading_lines(
        node,
        width=plan.width,
        section=section,
    )
    working_node = replace(node, style=style) if preserves_explicit_lines else node
    issues: list[PipelineIssue] = []
    if preserves_explicit_lines:
        issues.append(
            PipelineIssue(
                code="heading-explicit-lines-preserved",
                severity=IssueSeverity.INFO,
                message=(
                    "Explicit multiline heading breaks were preserved when the authored "
                    "lines fit the Figma text box."
                ),
                node_id=node.node_id,
                width=plan.width,
                metrics={
                    "explicitLines": _explicit_line_count(node.text),
                    "estimatedMaxLineWidth": round(
                        _estimated_heading_explicit_line_width(node),
                        3,
                    ),
                    "boundsWidth": round(node.bounds.width, 3),
                },
            )
        )
    return _NodeAdjustment(node=working_node, issues=tuple(issues))


def _is_accordion_container_node(node: RenderNodePlan) -> bool:
    if node.component == "accordion":
        return True
    tokens = set(_name_key(node.name).split("-"))
    return "accordion" in tokens


def _stack_accordion_like_children(
    children: tuple[RenderNodePlan, ...],
    *,
    width: int,
    parent_id: str,
) -> _NodesAndIssues:
    item_indexes = [
        index
        for index, child in enumerate(children)
        if child.component == "accordion-item" or "accordion-item" in _name_key(child.name)
    ]
    if len(item_indexes) < 2:
        return children, ()

    sorted_indexes = sorted(item_indexes, key=lambda index: (children[index].bounds.y, index))
    replacements: dict[int, RenderNodePlan] = {}
    issues: list[PipelineIssue] = []
    current_bottom: float | None = None
    max_shift = 0.0
    for index in sorted_indexes:
        child = replacements.get(index, children[index])
        if current_bottom is not None and child.bounds.y < current_bottom - GEOMETRY_EPSILON:
            shift_y = current_bottom - child.bounds.y
            child = _shift_node_tree(child, dx=0, dy=shift_y)
            replacements[index] = child
            max_shift = max(max_shift, shift_y)
        current_bottom = _node_visual_bottom(child, default=child.bounds.bottom)

    if not replacements:
        return children, ()
    issues.append(
        PipelineIssue(
            code="accordion-open-items-stacked",
            severity=IssueSeverity.INFO,
            message="Accordion items were stacked to avoid overlapping panels.",
            related_node_id=parent_id,
            width=width,
            metrics={"maxShiftY": round(max_shift, 3), "itemCount": len(item_indexes)},
        )
    )
    return tuple(replacements.get(index, child) for index, child in enumerate(children)), tuple(
        issues
    )


def _preserve_explicit_heading_lines(
    node: RenderNodePlan,
    *,
    width: int,
    section: RenderSectionPlan,
) -> tuple[dict[str, str], bool]:
    name = _name_key(node.name)
    if (
        width < HEADING_EXPLICIT_LINE_PRESERVE_MIN_PAGE_WIDTH
        or _is_band_like_section(section)
        or not _is_heading_text_node(node)
        or _explicit_line_count(node.text) <= 1
        or not _text_aligns_center(node)
        or str(node.style.get("white-space") or "").lower() == "pre"
        or {"band", "banner", "bandeau"} & set(name.split("-"))
    ):
        return node.style, False
    estimated_width = _estimated_heading_explicit_line_width(node)
    if estimated_width > node.bounds.width + HEADING_EXPLICIT_LINE_PRESERVE_TOLERANCE_PX:
        return node.style, False
    return {**node.style, "white-space": "pre"}, True


def _estimated_heading_explicit_line_width(node: RenderNodePlan) -> float:
    font_size = _style_px(node, "font-size")
    if font_size is None or font_size <= 0:
        line_box = _text_line_box(node)
        font_size = line_box / 1.2 if line_box > 0 else 0.0
    if font_size <= 0:
        return node.bounds.width
    average_char_width = max(1.0, font_size * TEXT_AVERAGE_CHAR_WIDTH_RATIO)
    return max(
        (len(line.strip()) * average_char_width for line in str(node.text).splitlines()),
        default=0.0,
    )


def _adjust_form_node(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
) -> _NodeAdjustment:
    return _normalize_unscaled_form_node(plan, section, node)


def _normalize_unscaled_form_node(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
) -> _NodeAdjustment:
    return _normalize_native_form_controls(
        _adjust_node_children(plan, section, node),
        width=plan.width,
    )


def _normalize_native_form_controls(
    adjustment: _NodeAdjustment,
    *,
    width: int,
) -> _NodeAdjustment:
    return _NodeAdjustment(
        node=_normalize_native_form_control_tree(adjustment.node, width=width),
        issues=adjustment.issues,
    )


def _normalize_native_form_control_tree(node: RenderNodePlan, *, width: int) -> RenderNodePlan:
    children = tuple(
        _normalize_native_form_control_tree(child, width=width) for child in node.children
    )
    next_node = replace(node, children=children) if children != node.children else node
    if next_node.component in FORM_CONTROL_COMPONENTS:
        next_node = _with_fixed_native_control_height(next_node)
    if next_node.component != "textarea":
        return next_node
    return replace(next_node, style=_textarea_native_style(next_node))


def _with_fixed_native_control_height(node: RenderNodePlan) -> RenderNodePlan:
    if node.bounds.height <= 0:
        return node
    height = f"{node.bounds.height:g}px"
    style = {**node.style, "height": height}
    if node.component in {"field", "select"}:
        style["line-height"] = height
    if style == node.style:
        return node
    return replace(node, style=style)


def _textarea_native_style(node: RenderNodePlan) -> dict[str, str]:
    style = dict(node.style)
    font_size = _style_value_px(style, "font-size")
    line_height = _style_value_px(style, "line-height")
    if (
        font_size is not None
        and font_size > 0
        and (line_height is None or line_height + GEOMETRY_EPSILON < font_size)
    ):
        style["line-height"] = f"{font_size:g}px"
        line_height = font_size
    style["display"] = "block"
    if _style_value_px(style, "padding-top") is None:
        centered = style.get("justify-content") == "center"
        if (
            centered
            and line_height is not None
            and line_height > 0
            and node.bounds.height > line_height
        ):
            style["padding-top"] = f"{((node.bounds.height - line_height) / 2):g}px"
    return style


def _adjust_footer_legal_text(
    plan: RenderPlan,
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    if not _is_footer_section(section):
        return nodes, ()
    nodes, child_issues = _adjust_nested_footer_legal_text(plan, nodes)

    footer_text_index = next(
        (index for index, node in enumerate(nodes) if _is_footer_legal_text(node)),
        None,
    )
    if footer_text_index is None:
        return nodes, child_issues

    footer_text = nodes[footer_text_index]
    font_size = _style_px(footer_text, "font-size") or 0.0
    line_height = _style_px(footer_text, "line-height") or 0.0
    use_readability_bounds = plan.width <= FOOTER_READABILITY_MAX_PAGE_WIDTH
    horizontal_padding = FOOTER_TEXT_HORIZONTAL_PADDING_PX if use_readability_bounds else 0.0
    target_left = max(0.0, section.bounds.x)
    target_right = min(float(plan.width), section.bounds.right)
    if target_right <= target_left + GEOMETRY_EPSILON:
        target_left = max(0.0, min(float(plan.width), section.bounds.x))
        target_right = float(plan.width)
    available_width = max(1.0, target_right - target_left - horizontal_padding * 2)
    needs_horizontal_containment = (
        footer_text.bounds.x < target_left - GEOMETRY_EPSILON
        or footer_text.bounds.right > target_right + GEOMETRY_EPSILON
    )
    needs_readability_adjustment = use_readability_bounds and (
        font_size < FOOTER_TEXT_MIN_FONT_SIZE_PX
        or line_height < FOOTER_TEXT_MIN_LINE_HEIGHT_PX
        or footer_text.bounds.width < available_width - GEOMETRY_EPSILON
        or footer_text.bounds.height < FOOTER_TEXT_MIN_HEIGHT_PX
        or section.bounds.height < FOOTER_SECTION_MIN_HEIGHT_PX
    )
    needs_alignment_adjustment = (
        footer_text.style.get("display") != "flex"
        or footer_text.style.get("align-items") != "center"
        or footer_text.style.get("justify-content") != "center"
    )
    if (
        not needs_readability_adjustment
        and not needs_horizontal_containment
        and not needs_alignment_adjustment
    ):
        return nodes, child_issues

    next_style = {
        **footer_text.style,
        "align-items": "center",
        "display": "flex",
        "font-size": (
            f"{max(font_size, FOOTER_TEXT_MIN_FONT_SIZE_PX):g}px"
            if use_readability_bounds
            else footer_text.style.get("font-size", f"{font_size:g}px" if font_size else "inherit")
        ),
        "justify-content": "center",
        "line-height": (
            f"{max(line_height, FOOTER_TEXT_MIN_LINE_HEIGHT_PX):g}px"
            if use_readability_bounds
            else footer_text.style.get(
                "line-height", f"{line_height:g}px" if line_height else "normal"
            )
        ),
        "text-align": "center",
    }
    next_bounds = footer_text.bounds
    preceding_bottom = section.bounds.y
    if needs_readability_adjustment:
        preceding_bottom = _nodes_bottom(
            tuple(node for node in nodes if not _is_footer_strip_node(node)),
            default=section.bounds.y,
        )
        next_y = max(
            section.bounds.y + FOOTER_TEXT_TOP_PADDING_PX,
            preceding_bottom + FOOTER_TEXT_TOP_PADDING_PX,
        )
        min_height = (
            max(
                FOOTER_TEXT_MIN_HEIGHT_PX,
                FOOTER_SECTION_MIN_HEIGHT_PX - FOOTER_BG_VERTICAL_PADDING_PX * 2,
            )
            if section.bounds.height < FOOTER_SECTION_MIN_HEIGHT_PX
            else FOOTER_TEXT_MIN_HEIGHT_PX
        )
        next_bounds = GeometryBox(
            x=target_left + horizontal_padding,
            y=next_y,
            width=available_width,
            height=max(footer_text.bounds.height, min_height),
        )
    elif needs_horizontal_containment:
        next_bounds = GeometryBox(
            x=target_left + horizontal_padding,
            y=footer_text.bounds.y,
            width=available_width,
            height=footer_text.bounds.height,
        )
    next_footer_text = replace(
        footer_text,
        bounds=next_bounds,
        style=next_style,
    )

    adjusted_nodes = list(nodes)
    adjusted_nodes[footer_text_index] = next_footer_text
    bg_index = next(
        (index for index, node in enumerate(nodes) if _is_footer_background(node)), None
    )
    if bg_index is not None and needs_readability_adjustment:
        bg = adjusted_nodes[bg_index]
        bg_y = max(preceding_bottom, next_footer_text.bounds.y - FOOTER_BG_VERTICAL_PADDING_PX)
        adjusted_nodes[bg_index] = replace(
            bg,
            bounds=GeometryBox(
                x=section.bounds.x,
                y=bg_y,
                width=section.bounds.width,
                height=next_footer_text.bounds.bottom + FOOTER_BG_VERTICAL_PADDING_PX - bg_y,
            ),
        )

    issues: tuple[PipelineIssue, ...] = child_issues
    if needs_readability_adjustment:
        issues = (
            *issues,
            PipelineIssue(
                code="footer-text-expanded-for-readability",
                severity=IssueSeverity.INFO,
                message="Footer legal text was expanded for readability.",
                node_id=footer_text.node_id,
                width=plan.width,
                metrics={
                    "beforeFontSize": round(font_size, 3),
                    "afterFontSize": max(font_size, FOOTER_TEXT_MIN_FONT_SIZE_PX),
                    "beforeHeight": round(footer_text.bounds.height, 3),
                    "afterHeight": round(next_footer_text.bounds.height, 3),
                },
            ),
        )
    return tuple(adjusted_nodes), issues


def _adjust_nested_footer_legal_text(
    plan: RenderPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    adjusted_nodes: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    changed = False
    for node in nodes:
        if node.children:
            next_children, child_issues = _adjust_nested_footer_legal_text(
                plan,
                node.children,
            )
            issues.extend(child_issues)
            if _is_footer_node(node):
                next_children, footer_issues = _adjust_footer_legal_text_in_bounds(
                    plan,
                    node.bounds,
                    next_children,
                )
                issues.extend(footer_issues)
            if next_children != node.children:
                node = replace(node, children=next_children)
                changed = True
        adjusted_nodes.append(node)
    return (tuple(adjusted_nodes) if changed else nodes), tuple(issues)


def _adjust_footer_legal_text_in_bounds(
    plan: RenderPlan,
    section_bounds: GeometryBox,
    nodes: tuple[RenderNodePlan, ...],
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    section = RenderSectionPlan(
        section_id="nested-footer",
        name="footer",
        bounds=section_bounds,
        layout_mode="absolute",
        nodes=nodes,
    )
    return _adjust_footer_legal_text(plan, section, nodes)


def _is_footer_section(section: RenderSectionPlan) -> bool:
    return section.name.strip().lower().startswith("footer")


def _is_footer_node(node: RenderNodePlan) -> bool:
    return node.name.strip().lower().startswith("footer")


def _is_footer_legal_text(node: RenderNodePlan) -> bool:
    return _looks_like_footer_legal_text(node.text)


def _contains_footer_legal_text(node: RenderNodePlan) -> bool:
    return _is_footer_legal_text(node) or any(
        _contains_footer_legal_text(child) for child in node.children
    )


def _looks_like_footer_legal_text(text: str) -> bool:
    normalized = _repair_mojibake(text).lower()
    return any(marker in normalized for marker in FOOTER_LEGAL_TEXT_MARKERS)


def _repair_mojibake(text: str) -> str:
    repaired = text
    for _ in range(2):
        try:
            next_repaired = repaired.encode("latin1").decode("utf-8")
        except UnicodeError:
            try:
                next_repaired = repaired.encode("cp1252").decode("utf-8")
            except UnicodeError:
                break
        if next_repaired == repaired:
            break
        repaired = next_repaired
    return repaired


def _is_footer_background(node: RenderNodePlan) -> bool:
    return node.name.lower() == "bg-footer"


def _is_footer_strip_node(node: RenderNodePlan) -> bool:
    return _is_footer_background(node) or _is_footer_legal_text(node)


def _section_expansion_padding(
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> float:
    if _is_footer_section(section):
        return 0.0
    if _is_band_like_section(section):
        return _band_section_expansion_padding(section)
    if _is_compact_full_bleed_visual_section(section, nodes):
        return 0.0
    return FORM_SECTION_PADDING_PX


def _band_section_expansion_padding(section: RenderSectionPlan) -> float:
    return min(
        BAND_SECTION_PADDING_MAX_PX,
        max(BAND_SECTION_PADDING_MIN_PX, section.bounds.height * BAND_SECTION_PADDING_RATIO),
    )


def _should_compact_section_for_semantic_content(
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
    content_bottom: float,
) -> bool:
    if _is_footer_section(section) or _is_band_like_section(section):
        return False
    if not any(node.component == "accordion" for node in _walk_nodes(nodes)):
        return False
    empty_space = section.bounds.bottom - content_bottom
    threshold = max(SECTION_COMPACTION_MIN_EMPTY_PX, section.bounds.height * 0.12)
    return empty_space > threshold


def _section_compaction_padding(
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> float:
    if any(node.component == "accordion" for node in _walk_nodes(nodes)):
        return ACCORDION_SECTION_PADDING_PX
    return _section_expansion_padding(section, nodes)


def _is_band_like_section(section: RenderSectionPlan) -> bool:
    key = _name_key(section.name)
    tokens = set(key.split("-"))
    return bool(tokens & {"band", "banner", "bandeau"})


def _normalize_band_text_readability(
    plan: RenderPlan,
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    if not _is_band_like_section(section):
        return nodes, ()
    adjusted: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for node in nodes:
        next_node, node_issues = _normalize_band_text_readability_node(plan, node)
        adjusted.append(next_node)
        issues.extend(node_issues)
    return tuple(adjusted), tuple(issues)


def _normalize_band_text_readability_node(
    plan: RenderPlan,
    node: RenderNodePlan,
) -> tuple[RenderNodePlan, tuple[PipelineIssue, ...]]:
    children: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for child in node.children:
        next_child, child_issues = _normalize_band_text_readability_node(plan, child)
        children.append(next_child)
        issues.extend(child_issues)

    if node.kind is not NodeKind.TEXT:
        if tuple(children) == node.children:
            return node, tuple(issues)
        return replace(node, children=tuple(children)), tuple(issues)

    if _is_heading_text_node(node):
        style, changed = _preserve_explicit_band_heading_lines(node, width=plan.width)
        style, centered = _with_vertical_centered_text_box(node, style)
        next_node = replace(node, style=style, children=tuple(children))
        if changed:
            issues.append(
                PipelineIssue(
                    code="band-heading-explicit-lines-preserved",
                    severity=IssueSeverity.INFO,
                    message=(
                        "Explicit multiline band heading breaks were preserved to avoid "
                        "browser-added wrapping differences."
                    ),
                    node_id=node.node_id,
                    width=plan.width,
                    metrics={
                        "explicitLines": _explicit_line_count(node.text),
                    },
                )
            )
        if centered:
            issues.append(
                PipelineIssue(
                    code="band-text-vertical-centering-preserved",
                    severity=IssueSeverity.INFO,
                    message="Centered band text was rendered as a vertical text box to preserve its authored placement.",
                    node_id=node.node_id,
                    width=plan.width,
                )
            )
        if not changed and not centered and tuple(children) == node.children:
            return node, tuple(issues)
        return next_node, tuple(issues)

    style, text_runs, changed = node.style, node.text_runs, False
    style, centered = _with_vertical_centered_text_box(node, style)
    next_node = replace(node, style=style, text_runs=text_runs, children=tuple(children))
    if changed:
        issues.append(
            PipelineIssue(
                code="band-text-line-height-normalized",
                severity=IssueSeverity.INFO,
                message="Band text line-height was raised to the minimum readable web value.",
                node_id=node.node_id,
                width=plan.width,
                metrics={
                    "fontSize": round(_style_value_px(node.style, "font-size") or 0.0, 3),
                    "beforeLineHeight": round(
                        _style_value_px(node.style, "line-height") or 0.0,
                        3,
                    ),
                    "afterLineHeight": round(
                        _style_value_px(style, "line-height") or 0.0,
                        3,
                    ),
                },
            )
        )
    if centered:
        issues.append(
            PipelineIssue(
                code="band-text-vertical-centering-preserved",
                severity=IssueSeverity.INFO,
                message="Centered band text was rendered as a vertical text box to preserve its authored placement.",
                node_id=node.node_id,
                width=plan.width,
            )
        )
    return next_node, tuple(issues)


def _preserve_explicit_band_heading_lines(
    node: RenderNodePlan,
    *,
    width: int,
) -> tuple[dict[str, str], bool]:
    if (
        _explicit_line_count(node.text) <= 1
        or not _text_aligns_center(node)
        or str(node.style.get("white-space") or "").lower() == "pre"
    ):
        return node.style, False
    estimated_width = _estimated_heading_explicit_line_width(node)
    if estimated_width > node.bounds.width + HEADING_EXPLICIT_LINE_PRESERVE_TOLERANCE_PX:
        return node.style, False
    return {**node.style, "white-space": "pre"}, True


def _with_vertical_centered_text_box(
    node: RenderNodePlan,
    style: dict[str, str],
) -> tuple[dict[str, str], bool]:
    if not _text_aligns_center(node):
        return style, False
    if (
        str(style.get("justify-content") or "").lower() == "center"
        and str(style.get("display") or "").lower() == "flex"
    ):
        return style, False
    line_box = _text_line_box(replace(node, style=style))
    if line_box <= 0:
        return style, False
    visual_height = line_box * _explicit_line_count(node.text)
    if visual_height >= node.bounds.height - TEXT_INTRINSIC_TOLERANCE_PX:
        return style, False
    return (
        {
            **style,
            "display": "flex",
            "flex-direction": "column",
            "justify-content": "center",
        },
        True,
    )


def _text_aligns_center(node: RenderNodePlan) -> bool:
    return str(node.style.get("text-align") or "").lower() == "center"


def _contain_narrow_decorative_overflow(
    plan: RenderPlan,
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    if plan.width > FORM_SCALE_MAX_PAGE_WIDTH and not _is_footer_section(section):
        return nodes, ()

    adjusted: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for node in nodes:
        next_node, node_issues = _contain_decorative_node_tree(
            node,
            section_bounds=section.bounds,
            width=plan.width,
        )
        adjusted.append(next_node)
        issues.extend(node_issues)
    return tuple(adjusted), tuple(issues)


def _contain_full_band_background_overflow(
    plan: RenderPlan,
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    section_bounds = _background_containment_bounds(section, nodes)
    adjusted: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for node in nodes:
        next_node, node_issues = _contain_full_band_background_node_tree(
            node,
            section_bounds=section_bounds,
            width=plan.width,
            force=False,
            preserve_bleed=_is_band_like_section(section) or _is_hero_section(section),
        )
        adjusted.append(next_node)
        issues.extend(node_issues)
    return tuple(adjusted), tuple(issues)


def _background_containment_bounds(
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> GeometryBox:
    if not _is_footer_section(section):
        return section.bounds
    bottom = max(section.bounds.bottom, _nodes_bottom(nodes, default=section.bounds.bottom))
    return GeometryBox(
        x=section.bounds.x,
        y=section.bounds.y,
        width=section.bounds.width,
        height=bottom - section.bounds.y,
    )


def _contain_full_band_background_node_tree(
    node: RenderNodePlan,
    *,
    section_bounds: GeometryBox,
    width: int,
    force: bool,
    preserve_bleed: bool,
) -> tuple[RenderNodePlan, tuple[PipelineIssue, ...]]:
    is_section_spanning_background = _is_section_spanning_background_node(node, section_bounds)
    preserve_self = preserve_bleed and _should_preserve_background_bleed(node, section_bounds)
    contain_self = (
        (is_section_spanning_background or (force and node.layer == "background"))
        and not preserve_self
        and _overflows_bounds(
            node.bounds,
            section_bounds,
            DECORATIVE_SECTION_OVERFLOW_TOLERANCE_PX,
        )
    )
    next_bounds = _intersect_bounds(node.bounds, section_bounds) if contain_self else node.bounds
    issues: list[PipelineIssue] = []
    if contain_self and next_bounds is not None:
        issues.append(
            PipelineIssue(
                code="background-overflow-contained",
                severity=IssueSeverity.INFO,
                message="Section-spanning background bounds were contained within the section.",
                node_id=node.node_id,
                width=width,
                metrics={
                    "beforeX": round(node.bounds.x, 3),
                    "beforeY": round(node.bounds.y, 3),
                    "beforeWidth": round(node.bounds.width, 3),
                    "beforeHeight": round(node.bounds.height, 3),
                    "afterX": round(next_bounds.x, 3),
                    "afterY": round(next_bounds.y, 3),
                    "afterWidth": round(next_bounds.width, 3),
                    "afterHeight": round(next_bounds.height, 3),
                },
            )
        )
    else:
        next_bounds = node.bounds

    children: list[RenderNodePlan] = []
    for child in node.children:
        next_child, child_issues = _contain_full_band_background_node_tree(
            child,
            section_bounds=section_bounds,
            width=width,
            force=force or (is_section_spanning_background and not preserve_self),
            preserve_bleed=preserve_bleed,
        )
        children.append(next_child)
        issues.extend(child_issues)

    if next_bounds != node.bounds or tuple(children) != node.children:
        return replace(node, bounds=next_bounds, children=tuple(children)), tuple(issues)
    return node, tuple(issues)


def _is_hero_section(section: RenderSectionPlan) -> bool:
    key = _name_key(section.name)
    return "hero" in set(key.split("-"))


def _should_preserve_background_bleed(
    node: RenderNodePlan,
    section_bounds: GeometryBox,
) -> bool:
    if node.layer != "background":
        return False
    name = _name_key(node.name)
    if not ({"bandeau", "band", "banner", "hero"} & set(name.split("-"))):
        return False
    if section_bounds.width <= 0 or section_bounds.height <= 0:
        return False
    max_horizontal_bleed = max(48.0, section_bounds.width * 0.14)
    max_vertical_bleed = max(12.0, section_bounds.height * 0.08)
    return (
        section_bounds.x - node.bounds.x <= max_horizontal_bleed
        and node.bounds.right - section_bounds.right <= max_horizontal_bleed
        and section_bounds.y - node.bounds.y <= max_vertical_bleed
        and node.bounds.bottom - section_bounds.bottom <= max_vertical_bleed
    )


def _is_section_spanning_background_node(
    node: RenderNodePlan,
    section_bounds: GeometryBox,
) -> bool:
    if node.layer != "background":
        return False
    if node.bounds.width < section_bounds.width * BAND_VISUAL_MIN_WIDTH_RATIO:
        return False
    tolerance = _band_visual_edge_tolerance(section_bounds)
    return (
        node.bounds.x <= section_bounds.x + tolerance
        and node.bounds.right >= section_bounds.right - tolerance
    )


def _band_visual_edge_tolerance(section_bounds: GeometryBox) -> float:
    return min(
        BAND_VISUAL_MAX_EDGE_TOLERANCE_PX,
        max(
            BAND_VISUAL_MIN_EDGE_TOLERANCE_PX,
            section_bounds.width * BAND_VISUAL_EDGE_TOLERANCE_RATIO,
        ),
    )


def _is_heading_text_node(node: RenderNodePlan) -> bool:
    if node.kind is not NodeKind.TEXT or not node.text.strip():
        return False
    name = node.name.strip().lower()
    return (
        name.startswith(("titre-", "title-", "heading-"))
        or "-h1-" in name
        or "-h2-" in name
        or "-h3-" in name
        or "-h4-" in name
        or name.startswith(("h1-", "h2-", "h3-", "h4-"))
    )


def _contain_decorative_node_tree(
    node: RenderNodePlan,
    *,
    section_bounds: GeometryBox,
    width: int,
) -> tuple[RenderNodePlan, tuple[PipelineIssue, ...]]:
    next_children: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    changed = False
    for child in node.children:
        next_child, child_issues = _contain_decorative_node_tree(
            child,
            section_bounds=section_bounds,
            width=width,
        )
        next_children.append(next_child)
        issues.extend(child_issues)
        changed = changed or next_child is not child

    next_node = replace(node, children=tuple(next_children)) if changed else node
    if not _should_contain_decorative_node(next_node, section_bounds):
        return next_node, tuple(issues)

    contained_bounds = _intersect_bounds(next_node.bounds, section_bounds)
    if contained_bounds is None:
        contained_bounds = GeometryBox(
            x=max(section_bounds.x, min(next_node.bounds.x, section_bounds.right)),
            y=max(section_bounds.y, min(next_node.bounds.y, section_bounds.bottom)),
            width=1.0,
            height=1.0,
        )
    contained = replace(next_node, bounds=contained_bounds)
    issues.append(
        PipelineIssue(
            code="decorative-overflow-contained",
            severity=IssueSeverity.INFO,
            message="Decorative node bounds were contained within the section on a narrow viewport.",
            node_id=node.node_id,
            width=width,
            metrics={
                "beforeX": round(next_node.bounds.x, 3),
                "beforeY": round(next_node.bounds.y, 3),
                "beforeWidth": round(next_node.bounds.width, 3),
                "beforeHeight": round(next_node.bounds.height, 3),
                "afterX": round(contained.bounds.x, 3),
                "afterY": round(contained.bounds.y, 3),
                "afterWidth": round(contained.bounds.width, 3),
                "afterHeight": round(contained.bounds.height, 3),
            },
        )
    )
    return contained, tuple(issues)


def _should_contain_decorative_node(node: RenderNodePlan, section_bounds: GeometryBox) -> bool:
    if node.layer != "decorative":
        return False
    if _is_top_only_decorative_overflow(node.bounds, section_bounds):
        return False
    return _overflows_bounds(
        node.bounds,
        section_bounds,
        DECORATIVE_SECTION_OVERFLOW_TOLERANCE_PX,
    )


def _is_top_only_decorative_overflow(bounds: GeometryBox, section_bounds: GeometryBox) -> bool:
    tolerance = DECORATIVE_SECTION_OVERFLOW_TOLERANCE_PX
    overflows_top = bounds.y < section_bounds.y - tolerance
    overflows_left = bounds.x < section_bounds.x - tolerance
    overflows_right = bounds.right > section_bounds.right + tolerance
    overflows_bottom = bounds.bottom > section_bounds.bottom + tolerance
    if not overflows_top or overflows_left or overflows_right or overflows_bottom:
        return False
    horizontal_overlap = min(bounds.right, section_bounds.right) - max(bounds.x, section_bounds.x)
    min_overlap = max(1.0, min(bounds.width, section_bounds.width) * 0.05)
    return horizontal_overlap >= min_overlap


def _intersect_bounds(a: GeometryBox, b: GeometryBox) -> GeometryBox | None:
    x = max(a.x, b.x)
    y = max(a.y, b.y)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    if right <= x or bottom <= y:
        return None
    return GeometryBox(x=x, y=y, width=right - x, height=bottom - y)


def _overflows_bounds(bounds: GeometryBox, container: GeometryBox, tolerance: float) -> bool:
    return (
        bounds.x < container.x - tolerance
        or bounds.y < container.y - tolerance
        or bounds.right > container.right + tolerance
        or bounds.bottom > container.bottom + tolerance
    )


def _adjust_node_children(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
) -> _NodeAdjustment:
    children: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for child in node.children:
        adjusted = _adjust_node(plan, section, child)
        children.append(adjusted.node)
        issues.extend(adjusted.issues)
    children_tuple, overlap_issues = _push_overlapping_text_siblings(
        tuple(children),
        width=plan.width,
        parent_id=node.node_id,
        original_children=node.children,
    )
    children = list(children_tuple)
    issues.extend(overlap_issues)
    children_tuple, flow_issues = _push_overlapping_flow_siblings(
        tuple(children),
        width=plan.width,
        parent_id=node.node_id,
        original_children=node.children,
    )
    children = list(children_tuple)
    issues.extend(flow_issues)
    if tuple(children) == node.children:
        return _compact_structure_wrapper_node(plan, node, node.children, tuple(issues))
    compacted = _compact_structure_wrapper_node(plan, node, tuple(children), tuple(issues))
    if compacted.node.bounds != node.bounds:
        return compacted
    return _expand_node_for_adjusted_children(plan, node, tuple(children), tuple(issues))


def _compact_structure_wrapper_node(
    plan: RenderPlan,
    node: RenderNodePlan,
    children: tuple[RenderNodePlan, ...],
    issues: tuple[PipelineIssue, ...],
) -> _NodeAdjustment:
    _ = plan
    return _NodeAdjustment(node=replace(node, children=children), issues=issues)


def _expand_node_for_adjusted_children(
    plan: RenderPlan,
    node: RenderNodePlan,
    children: tuple[RenderNodePlan, ...],
    issues: tuple[PipelineIssue, ...],
) -> _NodeAdjustment:
    content_bottom = _nodes_bottom(children, default=float("-inf"))
    bottom = max(node.bounds.bottom, content_bottom)
    if not issues or bottom <= node.bounds.bottom:
        return _NodeAdjustment(
            node=replace(node, children=children),
            issues=issues,
        )

    next_bounds = GeometryBox(
        x=node.bounds.x,
        y=node.bounds.y,
        width=node.bounds.width,
        height=bottom - node.bounds.y,
    )
    return _NodeAdjustment(
        node=replace(node, bounds=next_bounds, children=children),
        issues=(
            *issues,
            PipelineIssue(
                code="container-expanded-for-semantic-content",
                severity=IssueSeverity.INFO,
                message="Container height was expanded to contain semantic readability adjustments.",
                node_id=node.node_id,
                width=plan.width,
                metrics={
                    "beforeHeight": round(node.bounds.height, 3),
                    "afterHeight": round(next_bounds.height, 3),
                    "contentBottom": round(bottom, 3),
                },
            ),
        ),
    )


def _stretch_section_backgrounds(
    nodes: tuple[RenderNodePlan, ...],
    *,
    original_bounds: GeometryBox,
    next_bounds: GeometryBox,
) -> tuple[RenderNodePlan, ...]:
    stretched: list[RenderNodePlan] = []
    for node in nodes:
        if not _is_section_background_node(node, original_bounds):
            stretched.append(node)
            continue
        next_height = max(1.0, next_bounds.bottom - node.bounds.y)
        if abs(next_height - node.bounds.height) <= GEOMETRY_EPSILON:
            stretched.append(node)
            continue
        stretched.append(
            replace(
                node,
                bounds=GeometryBox(
                    x=node.bounds.x,
                    y=node.bounds.y,
                    width=node.bounds.width,
                    height=next_height,
                ),
            )
        )
    return tuple(stretched)


def _resize_section_backgrounds(
    nodes: tuple[RenderNodePlan, ...],
    *,
    original_bounds: GeometryBox,
    next_bounds: GeometryBox,
) -> tuple[RenderNodePlan, ...]:
    resized: list[RenderNodePlan] = []
    for node in nodes:
        if not _is_section_background_node(node, original_bounds):
            resized.append(node)
            continue
        next_height = max(1.0, next_bounds.bottom - node.bounds.y)
        if abs(next_height - node.bounds.height) <= GEOMETRY_EPSILON:
            resized.append(node)
            continue
        resized.append(
            replace(
                node,
                bounds=GeometryBox(
                    x=node.bounds.x,
                    y=node.bounds.y,
                    width=node.bounds.width,
                    height=next_height,
                ),
            )
        )
    return tuple(resized)


def _is_section_background_node(node: RenderNodePlan, section_bounds: GeometryBox) -> bool:
    if node.layer != "background":
        return False
    horizontal_padding = max(4.0, section_bounds.width * 0.08)
    covers_most_width = node.bounds.width >= section_bounds.width * 0.66
    reaches_left = node.bounds.x <= section_bounds.x + horizontal_padding
    reaches_right = node.bounds.right >= section_bounds.right - horizontal_padding
    return covers_most_width and reaches_left and reaches_right


def _shift_bottom_anchored_section_nodes(
    *,
    original_nodes: tuple[RenderNodePlan, ...],
    adjusted_nodes: tuple[RenderNodePlan, ...],
    original_bounds: GeometryBox,
    next_bounds: GeometryBox,
    width: int,
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    delta_y = next_bounds.bottom - original_bounds.bottom
    if delta_y <= GEOMETRY_EPSILON:
        return adjusted_nodes, ()

    original_by_id = {node.node_id: node for node in original_nodes}
    shifted: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for node in adjusted_nodes:
        original = original_by_id.get(node.node_id)
        if original is None or not _is_bottom_anchored_section_node(original, original_bounds):
            shifted.append(node)
            continue
        if (
            abs(node.bounds.height - original.bounds.height) > GEOMETRY_EPSILON
            or abs(node.bounds.y - original.bounds.y) > GEOMETRY_EPSILON
        ):
            shifted.append(node)
            continue
        next_node = _shift_node_tree(node, dx=0, dy=delta_y)
        shifted.append(next_node)
        issues.append(
            PipelineIssue(
                code="section-bottom-anchored-content-shifted",
                severity=IssueSeverity.INFO,
                message="Bottom-anchored section content was shifted after semantic expansion.",
                node_id=node.node_id,
                width=width,
                metrics={
                    "beforeY": round(node.bounds.y, 3),
                    "afterY": round(next_node.bounds.y, 3),
                    "shiftY": round(delta_y, 3),
                },
            )
        )
    return tuple(shifted), tuple(issues)


def _is_bottom_anchored_section_node(node: RenderNodePlan, section_bounds: GeometryBox) -> bool:
    if node.bounds.bottom > section_bounds.bottom + GEOMETRY_EPSILON:
        return False
    if node.bounds.bottom < section_bounds.bottom - FORM_SECTION_PADDING_PX:
        return False
    if (
        node.layer in {"background", "decorative"}
        and node.bounds.y <= section_bounds.y + FORM_SECTION_PADDING_PX
        and node.bounds.height >= section_bounds.height * 0.65
    ):
        return False
    return node.layer in {"background", "content"}


def _is_compact_full_bleed_visual_section(
    section: RenderSectionPlan,
    nodes: tuple[RenderNodePlan, ...],
) -> bool:
    if _is_footer_section(section):
        return False
    if section.bounds.height > max(420.0, section.bounds.width * 0.28):
        return False
    return any(_is_full_bleed_visual_node(node, section.bounds) for node in nodes)


def _is_full_bleed_visual_node(node: RenderNodePlan, section_bounds: GeometryBox) -> bool:
    if node.layer not in {"asset", "background", "decorative"}:
        return False
    if node.layer == "asset" and node.children:
        return False
    if node.bounds.width < section_bounds.width * 0.82:
        return False
    if node.bounds.height < section_bounds.height * 0.55:
        return False
    horizontal_tolerance = max(8.0, section_bounds.width * 0.08)
    return (
        node.bounds.x <= section_bounds.x + horizontal_tolerance
        and node.bounds.right >= section_bounds.right - horizontal_tolerance
    )


def _apply_sibling_stack_order(nodes: tuple[RenderNodePlan, ...]) -> tuple[RenderNodePlan, ...]:
    if not nodes:
        return nodes
    sibling_count = len(nodes)
    stacked: list[RenderNodePlan] = []
    for index, node in enumerate(nodes):
        children = _apply_sibling_stack_order(node.children)
        z_index = _sibling_stack_z_index(node, sibling_count=sibling_count, index=index)
        style = node.style
        if style.get("z-index") != z_index:
            style = {**style, "z-index": z_index}
        if children != node.children or style != node.style:
            stacked.append(replace(node, style=style, children=children))
        else:
            stacked.append(node)
    return tuple(stacked)


def _sibling_stack_z_index(
    node: RenderNodePlan,
    *,
    sibling_count: int,
    index: int,
) -> str:
    layer_rank = _sibling_layer_rank(node)
    if layer_rank == 0:
        return "0"
    source_rank = max(1, sibling_count - index)
    return str(layer_rank * (sibling_count + 1) + source_rank)


def _sibling_layer_rank(node: RenderNodePlan) -> int:
    if node.layer == "background":
        return 0
    if node.layer == "decorative" and _contains_background_layer(node):
        return 0
    if node.layer == "decorative":
        return 1
    if node.layer == "asset":
        return 2
    if node.layer == "content":
        return 3
    if node.layer == "foreground":
        return 4
    return 2


def _contains_background_layer(node: RenderNodePlan) -> bool:
    return any(
        child.layer == "background" or _contains_background_layer(child) for child in node.children
    )


def _shift_section(section: RenderSectionPlan, *, dy: float) -> RenderSectionPlan:
    return replace(
        section,
        bounds=_shift_bounds(section.bounds, dx=0, dy=dy),
        nodes=tuple(_shift_node_tree(node, dx=0, dy=dy) for node in section.nodes),
    )


def _push_overlapping_text_siblings(
    children: tuple[RenderNodePlan, ...],
    *,
    width: int,
    parent_id: str,
    original_children: tuple[RenderNodePlan, ...] | None = None,
) -> _NodesAndIssues:
    return _push_overlapping_siblings(
        children,
        width=width,
        parent_id=parent_id,
        original_children=original_children,
        shiftable=_text_stack_shiftable,
        participant=_text_stack_participant,
        min_horizontal_overlap=TEXT_SIBLING_HORIZONTAL_OVERLAP_RATIO,
        overlap_tolerance=TEXT_SIBLING_OVERLAP_TOLERANCE_PX,
        issue_code="text-sibling-shifted-for-intrinsic-height",
        issue_message="Text sibling was shifted to avoid overlap after intrinsic text sizing.",
    )


def _push_overlapping_flow_siblings(
    children: tuple[RenderNodePlan, ...],
    *,
    width: int,
    parent_id: str,
    original_children: tuple[RenderNodePlan, ...] | None = None,
) -> _NodesAndIssues:
    return _push_overlapping_siblings(
        children,
        width=width,
        parent_id=parent_id,
        original_children=original_children,
        shiftable=_flow_stack_shiftable,
        participant=_flow_stack_participant,
        min_horizontal_overlap=FLOW_SIBLING_HORIZONTAL_OVERLAP_RATIO,
        overlap_tolerance=FLOW_SIBLING_OVERLAP_TOLERANCE_PX,
        issue_code="flow-sibling-shifted-for-overlap",
        issue_message="Flow content was shifted to avoid overlapping preceding visual content.",
    )


def _push_overlapping_siblings(
    children: tuple[RenderNodePlan, ...],
    *,
    width: int,
    parent_id: str,
    original_children: tuple[RenderNodePlan, ...] | None,
    shiftable: Callable[[RenderNodePlan], bool],
    participant: Callable[[RenderNodePlan], bool],
    min_horizontal_overlap: float,
    overlap_tolerance: float,
    issue_code: str,
    issue_message: str,
) -> _NodesAndIssues:
    if len(children) < 2:
        return children, ()
    indexed = sorted(enumerate(children), key=lambda item: (item[1].bounds.y, item[1].bounds.x))
    original_by_id = _nodes_by_id(original_children or ())
    replacements: dict[int, RenderNodePlan] = {}
    issues: list[PipelineIssue] = []
    column_bottoms: list[tuple[GeometryBox, float, RenderNodePlan | None]] = []
    for index, child in indexed:
        current = replacements.get(index, child)
        current_original = original_by_id.get(current.node_id)
        shift_y = 0.0
        preserved_gap = 0.0
        if shiftable(current):
            for previous_bounds, previous_bottom, previous_original in column_bottoms:
                if (
                    _horizontal_overlap_ratio(previous_bounds, current.bounds)
                    < min_horizontal_overlap
                ):
                    continue
                overlap = previous_bottom - current.bounds.y
                if overlap > overlap_tolerance:
                    gap = _preserved_original_vertical_gap(
                        previous_original,
                        current_original,
                        min_horizontal_overlap=min_horizontal_overlap,
                    )
                    target_shift_y = overlap + gap
                    if target_shift_y > shift_y:
                        shift_y = target_shift_y
                        preserved_gap = gap
        if shift_y:
            current = _shift_node_tree(current, dx=0, dy=shift_y)
            replacements[index] = current
            issues.append(
                PipelineIssue(
                    code=issue_code,
                    severity=IssueSeverity.INFO,
                    message=issue_message,
                    node_id=current.node_id,
                    related_node_id=parent_id,
                    width=width,
                    metrics={
                        "shiftY": round(shift_y, 3),
                        "preservedGap": round(preserved_gap, 3),
                    },
                )
            )
        if participant(current):
            column_bottoms.append(
                (
                    current.bounds,
                    _node_visual_bottom(current, default=current.bounds.bottom),
                    current_original,
                )
            )
    if not replacements:
        return children, ()
    return tuple(replacements.get(index, child) for index, child in enumerate(children)), tuple(
        issues
    )


def _nodes_by_id(nodes: tuple[RenderNodePlan, ...]) -> dict[str, RenderNodePlan]:
    return {node.node_id: node for node in nodes}


def _preserved_original_vertical_gap(
    previous: RenderNodePlan | None,
    current: RenderNodePlan | None,
    *,
    min_horizontal_overlap: float,
) -> float:
    if previous is None or current is None:
        return 0.0
    if _horizontal_overlap_ratio(previous.bounds, current.bounds) < min_horizontal_overlap:
        return 0.0
    gap = current.bounds.y - previous.bounds.bottom
    return gap if gap > GEOMETRY_EPSILON else 0.0


def _flow_stack_participant(node: RenderNodePlan) -> bool:
    return _text_stack_participant(node) or _flow_visual_anchor(node)


def _flow_stack_shiftable(node: RenderNodePlan) -> bool:
    if node.layer in {"background", "decorative"}:
        return False
    if node.component in TEXT_STACK_EXCLUDED_COMPONENTS:
        return False
    name = _name_key(node.name)
    return bool(
        node.kind in {NodeKind.CONTAINER, NodeKind.SECTION}
        and ("card" in name or name.startswith(("bloc-", "block-", "item-")))
        and _has_visible_text_descendant(node)
    )


def _flow_visual_anchor(node: RenderNodePlan) -> bool:
    if node.layer != "asset" or not node.asset_url:
        return False
    name = _name_key(node.name)
    if name.startswith(("decor-", "decoration-")) or "decor" in name:
        return False
    return True


def _text_stack_participant(node: RenderNodePlan) -> bool:
    if node.layer in {"background", "decorative"}:
        return False
    if node.component in TEXT_STACK_EXCLUDED_COMPONENTS:
        return False
    return node.component == "submit" or _text_like(node) or _has_visible_text_descendant(node)


def _text_stack_shiftable(node: RenderNodePlan) -> bool:
    if node.layer in {"background", "decorative"}:
        return False
    if node.component in TEXT_STACK_EXCLUDED_COMPONENTS:
        return False
    if node.kind is NodeKind.ASSET and not node.text.strip() and not node.children:
        return False
    return bool(
        node.text.strip() or node.asset_url or node.component or node.children or node.style
    )


def _has_visible_text_descendant(node: RenderNodePlan) -> bool:
    for child in _semantic_children(node):
        if _text_like(child) or _has_visible_text_descendant(child):
            return True
    return False


def _semantic_children(node: RenderNodePlan) -> tuple[RenderNodePlan, ...]:
    if node.component == "accordion-item" and not node.attributes.get("open"):
        trigger = _first_direct_child_component(node, "accordion-trigger")
        return (trigger,) if trigger is not None else ()
    return node.children


def _text_line_box(node: RenderNodePlan) -> float:
    line_height = _style_px(node, "line-height")
    font_size = _style_px(node, "font-size")
    return line_height or (font_size * 1.2 if font_size else 0)


def _explicit_line_count(text: str) -> int:
    return max(1, len(str(text).splitlines()) or 1)


def _text_like(node: RenderNodePlan) -> bool:
    return node.kind is NodeKind.TEXT and bool(node.text.strip())


def _horizontal_overlap_ratio(a: GeometryBox, b: GeometryBox) -> float:
    overlap = min(a.right, b.right) - max(a.x, b.x)
    if overlap <= 0:
        return 0.0
    return overlap / max(1.0, min(a.width, b.width))


def _first_direct_child_component(
    node: RenderNodePlan,
    component: str,
) -> RenderNodePlan | None:
    for child in node.children:
        if child.component == component:
            return child
    return None


def _has_issue(issues: tuple[PipelineIssue, ...] | list[PipelineIssue], code: str) -> bool:
    return any(issue.code == code for issue in issues)


def _style_value_px(style: dict[str, str], name: str) -> float | None:
    value = style.get(name, "")
    if not value.endswith("px"):
        return None
    try:
        return float(value[:-2])
    except ValueError:
        return None


def _style_px(node: RenderNodePlan, name: str) -> float | None:
    return _style_value_px(node.style, name)


def _nodes_bottom(nodes: tuple[RenderNodePlan, ...], *, default: float) -> float:
    bottom = default
    for node in nodes:
        bottom = max(bottom, _node_visual_bottom(node, default=default))
    return bottom


def _section_visible_content_bottom(
    nodes: tuple[RenderNodePlan, ...],
    *,
    default: float,
    section_bounds: GeometryBox,
) -> float:
    bottom = default
    for node in nodes:
        bottom = max(
            bottom,
            _node_section_content_bottom(
                node,
                default=default,
                section_bounds=section_bounds,
            ),
        )
    return bottom


def _node_section_content_bottom(
    node: RenderNodePlan,
    *,
    default: float,
    section_bounds: GeometryBox,
) -> float:
    if node.component == "accordion-item" and not node.attributes.get("open"):
        trigger = _first_direct_child_component(node, "accordion-trigger")
        return trigger.bounds.bottom if trigger is not None else default
    bottom = (
        _node_visual_bottom(node, default=default)
        if _is_section_extent_content(node, section_bounds=section_bounds)
        else default
    )
    for child in node.children:
        bottom = max(
            bottom,
            _node_section_content_bottom(
                child,
                default=default,
                section_bounds=section_bounds,
            ),
        )
    return bottom


def _is_section_extent_content(
    node: RenderNodePlan,
    *,
    section_bounds: GeometryBox,
) -> bool:
    if node.layer in {"background", "decorative"}:
        return False
    if node.kind is NodeKind.SECTION:
        return False
    if node.layer == "asset" and _is_edge_decorative_asset(node, section_bounds):
        return False
    return bool(
        node.text.strip() or node.asset_url or node.component or (node.style and not node.children)
    )


def _is_edge_decorative_asset(node: RenderNodePlan, section_bounds: GeometryBox) -> bool:
    if not node.asset_url:
        return False
    key = _name_key(node.name)
    if key.startswith(("decor-", "decoration-")) or "decor" in key:
        return True
    directional_tokens = {"gauche", "droite", "left", "right", "haut", "bas", "top", "bottom"}
    tokens = set(key.split("-"))
    if {"image", "img"} & tokens and directional_tokens & tokens:
        return True
    overflows_vertical_edge = (
        node.bounds.y < section_bounds.y - GEOMETRY_EPSILON
        or node.bounds.bottom > section_bounds.bottom + GEOMETRY_EPSILON
    )
    if not overflows_vertical_edge:
        return False
    near_horizontal_edge = node.bounds.x <= section_bounds.x + max(
        12.0, section_bounds.width * 0.08
    ) or node.bounds.right >= section_bounds.right - max(12.0, section_bounds.width * 0.08)
    if not near_horizontal_edge:
        return False
    width_ratio = node.bounds.width / max(1.0, section_bounds.width)
    height_ratio = node.bounds.height / max(1.0, section_bounds.height)
    return width_ratio <= 0.25 or height_ratio <= 0.45


def _node_visual_bottom(node: RenderNodePlan, *, default: float) -> float:
    if node.component == "accordion-item" and not node.attributes.get("open"):
        trigger = _first_direct_child_component(node, "accordion-trigger")
        return trigger.bounds.bottom if trigger is not None else node.bounds.bottom
    bottom = max(default, node.bounds.bottom)
    for child in node.children:
        bottom = max(bottom, _node_visual_bottom(child, default=default))
    return bottom
