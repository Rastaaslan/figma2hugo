"""Ajustements de layout propres aux accordions interactifs dans le navigateur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, NamedTuple

from figma2hugo.pipeline.geometry import GEOMETRY_EPSILON
from figma2hugo.pipeline.geometry import (
    shift_node_tree as _shift_node_tree,
)
from figma2hugo.pipeline.geometry import (
    union_node_bounds as _union_bounds,
)
from figma2hugo.pipeline.models import (
    GeometryBox,
    IssueSeverity,
    PipelineIssue,
    RenderNodePlan,
    RenderPlan,
    RenderSectionPlan,
)
from figma2hugo.pipeline.naming import name_key as _name_key

ACCORDION_RESERVED_SPACE_MIN_PX = 24.0
ACCORDION_RESERVED_SPACE_RATIO = 0.25
ACCORDION_ITEM_GAP_MAX_PX = 24.0
ACCORDION_OPEN_ITEM_OVERLAP_TOLERANCE_PX = 1.0


class AccordionAdjustment(NamedTuple):
    node: RenderNodePlan
    issues: tuple[PipelineIssue, ...]


AdjustChild = Callable[[RenderPlan, RenderSectionPlan, RenderNodePlan], Any]
ExpandNode = Callable[
    [RenderPlan, RenderNodePlan, tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]],
    Any,
]


def adjust_accordion_item_node(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
    *,
    adjust_child: AdjustChild,
    expand_node: ExpandNode,
) -> AccordionAdjustment:
    children: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for child in node.children:
        adjusted = adjust_child(plan, section, child)
        children.append(adjusted.node)
        issues.extend(adjusted.issues)

    trigger_index = next(
        (index for index, child in enumerate(children) if child.component == "accordion-trigger"),
        None,
    )
    panel_index = next(
        (index for index, child in enumerate(children) if child.component == "accordion-panel"),
        None,
    )
    if trigger_index is None or panel_index is None:
        if tuple(children) == node.children:
            return AccordionAdjustment(node=node, issues=tuple(issues))
        expanded = expand_node(plan, node, tuple(children), tuple(issues))
        return AccordionAdjustment(node=expanded.node, issues=expanded.issues)

    trigger = children[trigger_index]
    panel = children[panel_index]
    trigger_bottom = _node_visual_bottom(trigger, default=trigger.bounds.bottom)
    panel_top = _node_visual_top(panel, default=panel.bounds.y)
    overlap = trigger_bottom - panel_top
    if overlap <= GEOMETRY_EPSILON:
        if tuple(children) == node.children:
            return AccordionAdjustment(node=node, issues=tuple(issues))
        expanded = expand_node(plan, node, tuple(children), tuple(issues))
        return AccordionAdjustment(node=expanded.node, issues=expanded.issues)

    next_panel = _shift_node_tree(panel, dx=0, dy=overlap)
    children[panel_index] = next_panel
    bottom = _nodes_bottom(tuple(children), default=node.bounds.bottom)
    next_node = replace(
        node,
        bounds=GeometryBox(
            x=node.bounds.x,
            y=node.bounds.y,
            width=node.bounds.width,
            height=max(node.bounds.height, bottom - node.bounds.y),
        ),
        children=tuple(children),
    )
    return AccordionAdjustment(
        node=next_node,
        issues=(
            *issues,
            PipelineIssue(
                code="accordion-panel-shifted-for-trigger-space",
                severity=IssueSeverity.INFO,
                message="Accordion panel was shifted below its trigger to avoid overlap.",
                node_id=panel.node_id,
                related_node_id=trigger.node_id,
                width=plan.width,
                metrics={
                    "beforeY": round(panel.bounds.y, 3),
                    "afterY": round(next_panel.bounds.y, 3),
                    "shiftY": round(overlap, 3),
                },
            ),
        ),
    )


def adjust_accordion_node(
    plan: RenderPlan,
    section: RenderSectionPlan,
    node: RenderNodePlan,
    *,
    adjust_child: AdjustChild,
    expand_node: ExpandNode,
) -> AccordionAdjustment:
    adjusted_children: list[RenderNodePlan] = []
    issues: list[PipelineIssue] = []
    for child in node.children:
        adjusted = adjust_child(plan, section, child)
        adjusted_children.append(adjusted.node)
        issues.extend(adjusted.issues)

    children = tuple(adjusted_children)
    children, initial_state_issues = _normalize_single_accordion_open_state(
        node,
        children,
        width=plan.width,
    )
    issues.extend(initial_state_issues)
    item_indexes = [
        index for index, child in enumerate(children) if child.component == "accordion-item"
    ]
    if len(item_indexes) < 2:
        if children == node.children:
            return AccordionAdjustment(node=node, issues=tuple(issues))
        expanded = expand_node(plan, node, children, tuple(issues))
        return AccordionAdjustment(node=expanded.node, issues=expanded.issues)

    item_infos: list[tuple[int, RenderNodePlan, GeometryBox, bool]] = []
    for index in item_indexes:
        item = children[index]
        trigger = _first_direct_child_component(item, "accordion-trigger")
        if trigger is None:
            return AccordionAdjustment(
                node=replace(node, children=children),
                issues=tuple(issues),
            )
        panel = _first_direct_child_component(item, "accordion-panel")
        is_open = bool(item.attributes.get("open"))
        included = (trigger, panel) if is_open and panel is not None else (trigger,)
        effective_bounds = _union_bounds(included)
        if effective_bounds is None:
            return AccordionAdjustment(
                node=replace(node, children=children),
                issues=tuple(issues),
            )
        item_infos.append((index, item, effective_bounds, is_open))

    sorted_infos = sorted(item_infos, key=lambda info: (info[2].y, info[2].x))
    current_top = sorted_infos[0][2].y
    compacted_by_index: dict[int, RenderNodePlan] = {}
    moved = False
    max_shift_y = 0.0
    reserved_space_total = 0.0
    max_reserved_space = 0.0
    previous_original_gap = 0.0
    previous_original_bottom = sorted_infos[0][2].bottom
    for order, (index, item, effective_bounds, is_open) in enumerate(sorted_infos):
        if order:
            original_gap = max(0.0, effective_bounds.y - previous_original_bottom)
            max_expected_gap = ACCORDION_ITEM_GAP_MAX_PX
            if previous_original_gap > GEOMETRY_EPSILON and original_gap > max(
                ACCORDION_RESERVED_SPACE_MIN_PX, previous_original_gap * 2.5
            ):
                next_gap = previous_original_gap
            else:
                next_gap = min(original_gap or previous_original_gap, max_expected_gap)
                if original_gap and original_gap <= max_expected_gap:
                    previous_original_gap = original_gap
            current_top += next_gap
        dy = current_top - effective_bounds.y
        compact_height = effective_bounds.height
        if not is_open:
            reserved_space = max(0.0, item.bounds.height - compact_height)
            if reserved_space > max(
                ACCORDION_RESERVED_SPACE_MIN_PX,
                item.bounds.height * ACCORDION_RESERVED_SPACE_RATIO,
            ):
                reserved_space_total += reserved_space
                max_reserved_space = max(max_reserved_space, reserved_space)
        shifted_item = _shift_node_tree(item, dx=0, dy=dy) if abs(dy) > GEOMETRY_EPSILON else item
        compacted = replace(
            shifted_item,
            bounds=GeometryBox(
                x=item.bounds.x,
                y=current_top,
                width=item.bounds.width,
                height=compact_height,
            ),
        )
        if (
            abs(dy) > GEOMETRY_EPSILON
            or abs(compacted.bounds.height - item.bounds.height) > GEOMETRY_EPSILON
        ):
            moved = True
            max_shift_y = max(max_shift_y, abs(dy))
        compacted_by_index[index] = compacted
        current_top += compact_height
        previous_original_bottom = effective_bounds.bottom

    if not moved:
        return AccordionAdjustment(node=replace(node, children=children), issues=tuple(issues))

    next_children = tuple(
        compacted_by_index.get(index, child) for index, child in enumerate(children)
    )
    next_bounds = _union_bounds(next_children) or node.bounds
    adjusted_node = replace(node, bounds=next_bounds, children=next_children)
    if reserved_space_total > 0:
        issues.append(
            PipelineIssue(
                code="accordion-closed-panel-space",
                severity=IssueSeverity.INFO,
                message="Closed accordion items were compacted to avoid reserving panel space.",
                node_id=node.node_id,
                width=plan.width,
                metrics={
                    "beforeHeight": round(node.bounds.height, 3),
                    "afterHeight": round(adjusted_node.bounds.height, 3),
                    "reservedSpace": round(reserved_space_total, 3),
                    "maxReservedSpace": round(max_reserved_space, 3),
                    "itemCount": len(item_infos),
                },
            )
        )
    elif max_shift_y > ACCORDION_OPEN_ITEM_OVERLAP_TOLERANCE_PX:
        issues.append(
            PipelineIssue(
                code="accordion-open-items-stacked",
                severity=IssueSeverity.INFO,
                message="Open accordion items were stacked to avoid overlapping panels.",
                node_id=node.node_id,
                width=plan.width,
                metrics={
                    "beforeHeight": round(node.bounds.height, 3),
                    "afterHeight": round(adjusted_node.bounds.height, 3),
                    "maxShiftY": round(max_shift_y, 3),
                    "itemCount": len(item_infos),
                },
            )
        )
    return AccordionAdjustment(node=adjusted_node, issues=tuple(issues))


def _normalize_single_accordion_open_state(
    node: RenderNodePlan,
    children: tuple[RenderNodePlan, ...],
    *,
    width: int,
) -> tuple[tuple[RenderNodePlan, ...], tuple[PipelineIssue, ...]]:
    if _accordion_allows_multiple_open_items(node):
        return children, ()
    opened_indexes = [
        index
        for index, child in enumerate(children)
        if child.component == "accordion-item" and child.attributes.get("open")
    ]
    if len(opened_indexes) <= 1:
        return children, ()
    keep_index = min(opened_indexes, key=lambda index: (children[index].bounds.y, index))
    adjusted = list(children)
    closed_count = 0
    for index in opened_indexes:
        if index == keep_index:
            continue
        attributes = dict(adjusted[index].attributes)
        attributes.pop("open", None)
        adjusted[index] = replace(adjusted[index], attributes=attributes)
        closed_count += 1
    return (
        tuple(adjusted),
        (
            PipelineIssue(
                code="accordion-single-open-state-normalized",
                severity=IssueSeverity.INFO,
                message="Single accordion initial state keeps only the first open item.",
                node_id=node.node_id,
                width=width,
                metrics={"closedItems": closed_count},
            ),
        ),
    )


def _accordion_allows_multiple_open_items(node: RenderNodePlan) -> bool:
    tokens = set(_name_key(node.name).split("-"))
    return "multi" in tokens


def _first_direct_child_component(
    node: RenderNodePlan,
    component: str,
) -> RenderNodePlan | None:
    for child in node.children:
        if child.component == component:
            return child
    return None


def _nodes_bottom(nodes: tuple[RenderNodePlan, ...], *, default: float) -> float:
    bottom = default
    for node in nodes:
        bottom = max(bottom, _node_visual_bottom(node, default=default))
    return bottom


def _node_visual_bottom(node: RenderNodePlan, *, default: float) -> float:
    if node.component == "accordion-item" and not node.attributes.get("open"):
        trigger = _first_direct_child_component(node, "accordion-trigger")
        return trigger.bounds.bottom if trigger is not None else node.bounds.bottom
    bottom = max(default, node.bounds.bottom)
    for child in node.children:
        bottom = max(bottom, _node_visual_bottom(child, default=default))
    return bottom


def _node_visual_top(node: RenderNodePlan, *, default: float) -> float:
    top = min(default, node.bounds.y)
    for child in node.children:
        top = min(top, _node_visual_top(child, default=default))
    return top
