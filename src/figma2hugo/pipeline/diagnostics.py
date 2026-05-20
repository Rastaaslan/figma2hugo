"""Diagnostics reutilisables pour signaler les soucis de layout, structure et rendu."""

from __future__ import annotations

from itertools import combinations

from figma2hugo.pipeline.components import FORM_CONTROL_COMPONENTS
from figma2hugo.pipeline.geometry import walk_render_nodes
from figma2hugo.pipeline.models import (
    GeometryBox,
    IssueSeverity,
    NodeKind,
    PipelineIssue,
    RenderNodePlan,
    RenderPlan,
    RenderSectionPlan,
)
from figma2hugo.pipeline.naming import name_key as _name_key

BOARD_TOLERANCE_PX = 2.0
MIN_FOOTER_HEIGHT_PX = 44.0
OVERLAP_RATIO_THRESHOLD = 0.15
SECTION_OVERLAP_TOLERANCE_PX = 8.0
TEXT_AVERAGE_CHAR_WIDTH_RATIO = 0.48
STRUCTURAL_COMPONENTS = {
    "link-grid",
    "link-row",
    "accordion",
    "carousel",
    "carousel-stage",
    "carousel-nav",
}
NON_RENDERED_CHILD_COMPONENTS = FORM_CONTROL_COMPONENTS
MINOR_VERTICAL_GAP_RATIO = 1.5


def analyze_render_plan(plan: RenderPlan) -> tuple[PipelineIssue, ...]:
    issues: list[PipelineIssue] = []
    issues.extend(_section_bounds_issues(plan))
    issues.extend(_vertical_gap_issues(plan))
    issues.extend(_section_overlap_issues(plan))
    for section in plan.sections:
        issues.extend(_section_content_issues(plan, section))
    return tuple(issues)


def _section_bounds_issues(plan: RenderPlan) -> list[PipelineIssue]:
    issues: list[PipelineIssue] = []
    horizontal_tolerance = _section_horizontal_tolerance(plan)
    for section in plan.sections:
        bounds = section.bounds
        if bounds.x < -horizontal_tolerance:
            issues.append(
                PipelineIssue(
                    code="section-outside-page-left",
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Section starts before the page board: x={bounds.x:g}, boardLeft=0px."
                    ),
                    node_id=section.section_id,
                    width=plan.width,
                    metrics={"x": bounds.x, "boardLeft": 0},
                )
            )
        if bounds.right > plan.width + horizontal_tolerance:
            issues.append(
                PipelineIssue(
                    code="section-outside-page-right",
                    severity=IssueSeverity.ERROR,
                    message=(
                        "Section extends beyond the page board: "
                        f"right={bounds.right:g}, boardRight={plan.width}px."
                    ),
                    node_id=section.section_id,
                    width=plan.width,
                    metrics={"right": bounds.right, "boardRight": plan.width},
                )
            )
        if bounds.y < -BOARD_TOLERANCE_PX:
            issues.append(
                PipelineIssue(
                    code="section-before-page-top",
                    severity=IssueSeverity.WARNING,
                    message=f"Section starts before the page top: y={bounds.y:g}.",
                    node_id=section.section_id,
                    width=plan.width,
                    metrics={"y": bounds.y, "pageTop": 0},
                )
            )
        if bounds.bottom > plan.height + BOARD_TOLERANCE_PX:
            issues.append(
                PipelineIssue(
                    code="section-after-page-bottom",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "Section extends below the declared page height: "
                        f"bottom={bounds.bottom:g}, pageBottom={plan.height}px."
                    ),
                    node_id=section.section_id,
                    width=plan.width,
                    metrics={"bottom": bounds.bottom, "pageBottom": plan.height},
                )
            )
    return issues


def _vertical_gap_issues(plan: RenderPlan) -> list[PipelineIssue]:
    issues: list[PipelineIssue] = []
    sections = sorted(plan.sections, key=lambda section: (section.bounds.y, section.bounds.x))
    for previous, current in zip(sections, sections[1:], strict=False):
        gap = current.bounds.y - previous.bounds.bottom
        threshold = _section_gap_threshold(plan)
        if gap > threshold:
            gap_ratio = gap / threshold if threshold else 0.0
            issues.append(
                PipelineIssue(
                    code="large-vertical-gap",
                    severity=IssueSeverity.INFO,
                    message=(
                        "Large vertical gap between consecutive sections: "
                        f"{gap:g}px after {previous.section_id}; threshold={threshold:g}px."
                    ),
                    node_id=current.section_id,
                    related_node_id=previous.section_id,
                    width=plan.width,
                    metrics={
                        "gap": gap,
                        "threshold": threshold,
                        "gapRatio": round(gap_ratio, 3),
                        "gapOverThreshold": round(gap - threshold, 3),
                        "gapKind": (
                            "near-threshold"
                            if gap_ratio <= MINOR_VERTICAL_GAP_RATIO
                            else "large-empty-space"
                        ),
                        "previousBottom": previous.bounds.bottom,
                        "nextTop": current.bounds.y,
                        "previousSectionName": previous.name,
                        "nextSectionName": current.name,
                        "previousSectionRole": _section_role(previous),
                        "nextSectionRole": _section_role(current),
                    },
                )
            )
    return issues


def _section_overlap_issues(plan: RenderPlan) -> list[PipelineIssue]:
    issues: list[PipelineIssue] = []
    sections = sorted(plan.sections, key=lambda section: (section.bounds.y, section.bounds.x))
    for previous, current in zip(sections, sections[1:], strict=False):
        overlap = previous.bounds.bottom - current.bounds.y
        if overlap > SECTION_OVERLAP_TOLERANCE_PX:
            issues.append(
                PipelineIssue(
                    code="section-overlap",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "Consecutive sections overlap vertically: "
                        f"{overlap:g}px between {previous.section_id} and {current.section_id}."
                    ),
                    node_id=current.section_id,
                    related_node_id=previous.section_id,
                    width=plan.width,
                    metrics={
                        "overlap": overlap,
                        "previousBottom": previous.bounds.bottom,
                        "nextTop": current.bounds.y,
                    },
                )
            )
    return issues


def _section_content_issues(plan: RenderPlan, section: RenderSectionPlan) -> list[PipelineIssue]:
    issues: list[PipelineIssue] = []
    visible_nodes = [node for node in _walk_nodes(section.nodes) if _is_directly_visible_node(node)]
    for node in visible_nodes:
        if _is_edge_decorative_asset(node, section.bounds) or _is_intentional_band_bleed(
            node,
            section,
        ):
            continue
        horizontal_tolerance = _node_horizontal_tolerance(plan)
        if node.bounds.x < section.bounds.x - horizontal_tolerance or node.bounds.right > (
            section.bounds.right + horizontal_tolerance
        ):
            issues.append(
                PipelineIssue(
                    code="node-out-of-section-horizontal",
                    severity=IssueSeverity.WARNING,
                    message="Visible node exceeds its section horizontal bounds.",
                    node_id=node.node_id,
                    width=plan.width,
                )
            )
        vertical_tolerance = _node_vertical_tolerance(plan)
        if node.bounds.bottom > section.bounds.bottom + vertical_tolerance:
            overflow = node.bounds.bottom - section.bounds.bottom
            issues.append(
                PipelineIssue(
                    code="section-content-clipped",
                    severity=IssueSeverity.ERROR
                    if _is_sensitive_section(section)
                    else IssueSeverity.WARNING,
                    message=(
                        "Visible node extends below its section; this can cut forms/footer "
                        "when rendered without runtime repair."
                    ),
                    node_id=node.node_id,
                    related_node_id=section.section_id,
                    width=plan.width,
                    metrics={
                        "overflow": overflow,
                        "contentBottom": node.bounds.bottom,
                        "sectionBottom": section.bounds.bottom,
                    },
                )
            )
    issues.extend(_overlap_issues(plan, section.nodes))
    if _is_footer(section) and section.bounds.height < MIN_FOOTER_HEIGHT_PX:
        issues.append(
            PipelineIssue(
                code="tiny-footer",
                severity=IssueSeverity.ERROR,
                message=f"Footer height is below {MIN_FOOTER_HEIGHT_PX:g}px.",
                node_id=section.section_id,
                width=plan.width,
                metrics={"height": section.bounds.height, "minimum": MIN_FOOTER_HEIGHT_PX},
            )
        )
    return issues


def _overlap_issues(plan: RenderPlan, nodes: tuple[RenderNodePlan, ...]) -> list[PipelineIssue]:
    issues: list[PipelineIssue] = []
    candidates = [
        node
        for node in nodes
        if node.kind in {NodeKind.TEXT, NodeKind.CONTAINER}
        and _is_directly_visible_node(node)
        and node.bounds.width > 0
        and node.bounds.height > 0
    ]
    for first, second in combinations(candidates, 2):
        first_bounds = _collision_bounds(first)
        second_bounds = _collision_bounds(second)
        overlap = _overlap_area(first_bounds, second_bounds)
        smallest_area = min(first_bounds.area, second_bounds.area)
        ratio = overlap / smallest_area if smallest_area else 0.0
        if ratio > OVERLAP_RATIO_THRESHOLD:
            issues.append(
                PipelineIssue(
                    code="content-overlap",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "Visible content nodes overlap: "
                        f"{first.node_id} / {second.node_id}, area={overlap:g}px2."
                    ),
                    node_id=second.node_id,
                    related_node_id=first.node_id,
                    width=plan.width,
                    metrics={
                        "overlapArea": overlap,
                        "overlapRatio": ratio,
                        "threshold": OVERLAP_RATIO_THRESHOLD,
                    },
                )
            )
    for node in nodes:
        issues.extend(_overlap_issues(plan, _diagnostic_children(node)))
    return issues


def _walk_nodes(nodes: tuple[RenderNodePlan, ...]) -> list[RenderNodePlan]:
    return list(walk_render_nodes(nodes, children=_diagnostic_children))


def _diagnostic_children(node: RenderNodePlan) -> tuple[RenderNodePlan, ...]:
    if node.component in NON_RENDERED_CHILD_COMPONENTS:
        return ()
    if node.component == "accordion-item" and not node.attributes.get("open"):
        return tuple(child for child in node.children if child.component != "accordion-panel")
    if node.component == "carousel-stage":
        return _diagnostic_carousel_stage_children(node)
    return node.children


def _diagnostic_carousel_stage_children(node: RenderNodePlan) -> tuple[RenderNodePlan, ...]:
    slides = [child for child in node.children if child.component == "carousel-slide"]
    if not slides:
        return node.children
    default_slide = next(
        (slide for slide in slides if slide.attributes.get("default") == "true"),
        slides[0],
    )
    return tuple(
        child
        for child in node.children
        if child.component != "carousel-slide" or child is default_slide
    )


def _is_directly_visible_node(node: RenderNodePlan) -> bool:
    if node.layer in {"background", "decorative"}:
        return False
    if node.component in STRUCTURAL_COMPONENTS:
        return False
    return bool(
        node.text.strip() or node.asset_url or node.component or _has_painted_style(node.style)
    )


def _has_painted_style(style: dict[str, str]) -> bool:
    return any(
        key
        for key in style
        if key
        not in {
            "z-index",
        }
    )


def _is_edge_decorative_asset(node: RenderNodePlan, section_bounds: GeometryBox) -> bool:
    if node.layer != "asset" or not node.asset_url:
        return False
    key = _name_key(node.name)
    if key.startswith(("decor-", "decoration-")) or "decor" in key:
        return True
    directional_tokens = {"gauche", "droite", "left", "right", "haut", "bas", "top", "bottom"}
    tokens = set(key.split("-"))
    if {"image", "img"} & tokens and directional_tokens & tokens:
        return True
    overflows_vertical_edge = (
        node.bounds.y < section_bounds.y - BOARD_TOLERANCE_PX
        or node.bounds.bottom > section_bounds.bottom + BOARD_TOLERANCE_PX
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


def _is_intentional_band_bleed(node: RenderNodePlan, section: RenderSectionPlan) -> bool:
    section_tokens = set(_name_key(section.name).split("-"))
    if not (section_tokens & {"band", "banner", "bandeau"}):
        return False
    if node.kind not in {NodeKind.SECTION, NodeKind.CONTAINER} and node.layer != "asset":
        return False
    if node.text.strip() or node.component:
        return False
    horizontal_bleed = max(
        section.bounds.x - node.bounds.x,
        node.bounds.right - section.bounds.right,
        0.0,
    )
    return horizontal_bleed <= max(48.0, section.bounds.width * 0.14)


def _overlap_area(first: GeometryBox, second: GeometryBox) -> float:
    left = max(first.x, second.x)
    right = min(first.right, second.right)
    top = max(first.y, second.y)
    bottom = min(first.bottom, second.bottom)
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _collision_bounds(node: RenderNodePlan) -> GeometryBox:
    if node.kind is not NodeKind.TEXT or not node.text.strip():
        return node.bounds
    text_height = _estimated_text_height(node)
    text_width = _estimated_text_width(node)
    x = node.bounds.x
    if node.style.get("text-align") == "center":
        x += max(0.0, (node.bounds.width - text_width) / 2.0)
    elif node.style.get("text-align") == "right":
        x += max(0.0, node.bounds.width - text_width)
    return GeometryBox(
        x=x,
        y=node.bounds.y,
        width=text_width,
        height=min(node.bounds.height, text_height),
    )


def _estimated_text_height(node: RenderNodePlan) -> float:
    line_height = _style_px(node, "line-height") or ((_style_px(node, "font-size") or 16.0) * 1.2)
    line_count = _estimated_text_line_count(node, line_box=line_height)
    return line_height * line_count


def _estimated_text_width(node: RenderNodePlan) -> float:
    font_size = _style_px(node, "font-size") or 16.0
    average_char_width = max(1.0, font_size * TEXT_AVERAGE_CHAR_WIDTH_RATIO)
    max_width = 0.0
    for raw_line in str(node.text).splitlines() or [str(node.text)]:
        max_width = max(max_width, len(raw_line) * average_char_width)
    return min(node.bounds.width, max(1.0, max_width))


def _estimated_text_line_count(node: RenderNodePlan, *, line_box: float) -> int:
    explicit_lines = max(1, len(node.text.splitlines()) or 1)
    font_size = _style_px(node, "font-size") or (line_box / 1.2 if line_box else 0.0)
    if font_size <= 0 or node.bounds.width <= 0:
        return explicit_lines
    average_char_width = max(1.0, font_size * TEXT_AVERAGE_CHAR_WIDTH_RATIO)
    max_chars_per_line = max(1, int(node.bounds.width / average_char_width))
    wrapped_lines = 0
    for raw_line in str(node.text).splitlines() or [str(node.text)]:
        words = raw_line.split()
        if not words:
            wrapped_lines += 1
            continue
        line_length = 0
        for word in words:
            word_length = len(word)
            next_length = word_length if line_length == 0 else line_length + 1 + word_length
            if next_length > max_chars_per_line and line_length > 0:
                wrapped_lines += 1
                line_length = word_length
            else:
                line_length = next_length
        wrapped_lines += 1
    return max(explicit_lines, wrapped_lines)


def _style_px(node: RenderNodePlan, name: str) -> float | None:
    value = node.style.get(name, "")
    if not value.endswith("px"):
        return None
    try:
        return float(value[:-2])
    except ValueError:
        return None


def _node_horizontal_tolerance(plan: RenderPlan) -> float:
    return max(BOARD_TOLERANCE_PX, min(12.0, plan.width * 0.015))


def _node_vertical_tolerance(plan: RenderPlan) -> float:
    return max(BOARD_TOLERANCE_PX, min(12.0, plan.width * 0.015))


def _section_horizontal_tolerance(plan: RenderPlan) -> float:
    return max(BOARD_TOLERANCE_PX, min(12.0, plan.width * 0.015))


def _is_footer(section: RenderSectionPlan) -> bool:
    name = section.name.lower()
    return name == "footer" or name.startswith("footer-") or "footer" in name


def _is_sensitive_section(section: RenderSectionPlan) -> bool:
    name = section.name.lower()
    return _is_footer(section) or "formulaire" in name or _section_contains_form_controls(section)


def _section_role(section: RenderSectionPlan) -> str:
    name = section.name.lower()
    if "hero" in name:
        return "hero"
    if _is_footer(section):
        return "footer"
    if "formulaire" in name or _section_contains_form_controls(section):
        return "form"
    if name.startswith("bandeau") or "bandeau" in name:
        return "band"
    if "faq" in name or "accordion" in name:
        return "faq"
    return "content"


def _section_contains_form_controls(section: RenderSectionPlan) -> bool:
    return any(
        node.component in NON_RENDERED_CHILD_COMPONENTS or node.component == "form"
        for node in _walk_nodes(section.nodes)
    )


def _section_gap_threshold(plan: RenderPlan) -> float:
    return max(96.0, min(220.0, plan.width * 0.1))
