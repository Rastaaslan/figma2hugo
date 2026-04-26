from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SECTION_LIKE_TYPES = {"FRAME", "SECTION", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET"}


@dataclass(slots=True)
class SectionCandidate:
    id: str
    name: str
    role: str
    node: dict[str, Any]
    bounds: dict[str, float]
    extra_nodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "bounds": self.bounds,
        }


class LayoutAnalyzer:
    def identify_sections(self, root_node: dict[str, Any]) -> list[SectionCandidate]:
        analysis_root = self._unwrap_single_section_wrapper(root_node)
        visible_children = [
            child
            for child in analysis_root.get("children", [])
            if child.get("visible", True) and child.get("type") in SECTION_LIKE_TYPES
        ]

        if self._is_container(analysis_root) and visible_children:
            candidates = [child for child in visible_children if self._looks_like_section(child, analysis_root)]
        else:
            candidates = []

        if not candidates:
            candidates = [analysis_root]

        result: list[SectionCandidate] = []
        ordered_candidates = sorted(candidates, key=self._sort_key)
        for index, node in enumerate(ordered_candidates):
            section_id = node.get("id", f"section-{index + 1}")
            result.append(
                SectionCandidate(
                    id=section_id,
                    name=node.get("name") or f"Section {index + 1}",
                    role=self._guess_role(node, index, len(ordered_candidates)),
                    node=node,
                    bounds=self._bounds(node),
                )
            )
        self._attach_orphan_nodes(analysis_root, result)
        if analysis_root is not root_node:
            self._attach_orphan_nodes(root_node, result, ignored_ids={analysis_root.get("id")})
        return result

    def _unwrap_single_section_wrapper(self, root_node: dict[str, Any]) -> dict[str, Any]:
        if root_node.get("type") not in {"DOCUMENT", "CANVAS", "PAGE"}:
            return root_node
        visible_children = [
            child
            for child in root_node.get("children", [])
            if child.get("visible", True) and child.get("type") in SECTION_LIKE_TYPES
        ]
        if len(visible_children) != 1:
            return root_node
        wrapper = visible_children[0]
        wrapper_children = [
            child
            for child in wrapper.get("children", [])
            if child.get("visible", True) and child.get("type") in SECTION_LIKE_TYPES
        ]
        section_like_children = [child for child in wrapper_children if self._looks_like_section(child, wrapper)]
        if len(section_like_children) >= 2:
            return wrapper
        return root_node

    def _is_container(self, node: dict[str, Any]) -> bool:
        return node.get("type") in {"DOCUMENT", "CANVAS", "PAGE", "FRAME", "SECTION"}

    def _looks_like_section(self, node: dict[str, Any], parent: dict[str, Any]) -> bool:
        bounds = self._bounds(node)
        parent_bounds = self._bounds(parent)
        area = bounds["width"] * bounds["height"]
        parent_area = max(parent_bounds["width"] * parent_bounds["height"], 1)
        if area / parent_area >= 0.03:
            return True
        name = (node.get("name") or "").lower()
        if any(token in name for token in ("hero", "header", "footer", "section", "feature", "contact", "nav", "menu")):
            return True
        return self._subtree_contains_visible_text(node)

    def _guess_role(self, node: dict[str, Any], index: int, total: int) -> str:
        name = (node.get("name") or "").lower()
        if "footer" in name:
            return "footer"
        if "nav" in name or "menu" in name:
            return "nav"
        if "form" in name or "contact" in name or "newsletter" in name:
            return "section"
        if index == 0 and any(token in name for token in ("header", "hero", "masthead")):
            return "header"
        if index == total - 1 and any(token in name for token in ("footer", "contact")):
            return "footer"
        return "section"

    def _bounds(self, node: dict[str, Any]) -> dict[str, float]:
        absolute_box = node.get("absoluteBoundingBox") or {}
        render_box = node.get("absoluteRenderBounds") or {}
        if self._box_has_area(render_box) and not self._box_has_area(absolute_box):
            box = render_box
        else:
            box = absolute_box or render_box
        return {
            "x": float(box.get("x", 0.0)),
            "y": float(box.get("y", 0.0)),
            "width": float(box.get("width", 0.0)),
            "height": float(box.get("height", 0.0)),
        }

    def _sort_key(self, node: dict[str, Any]) -> tuple[float, float]:
        bounds = self._bounds(node)
        return (bounds["y"], bounds["x"])

    def _attach_orphan_nodes(
        self,
        root_node: dict[str, Any],
        sections: list[SectionCandidate],
        *,
        ignored_ids: set[str] | None = None,
    ) -> None:
        if not sections or root_node.get("id") in {section.id for section in sections}:
            return
        ignored_ids = ignored_ids or set()
        section_ids = {section.id for section in sections}
        for child in root_node.get("children", []):
            if not child.get("visible", True):
                continue
            child_id = child.get("id")
            if child_id in section_ids or child_id in ignored_ids:
                continue
            target = self._nearest_section(child, sections)
            if target is not None:
                target.extra_nodes.append(child)

    def _nearest_section(
        self,
        node: dict[str, Any],
        sections: list[SectionCandidate],
    ) -> SectionCandidate | None:
        node_bounds = self._bounds(node)
        if node_bounds["width"] <= 0 and node_bounds["height"] <= 0:
            return sections[0] if sections else None

        def score(section: SectionCandidate) -> tuple[float, float]:
            overlap = self._vertical_overlap(node_bounds, section.bounds)
            distance = abs(self._center_y(node_bounds) - self._center_y(section.bounds))
            return (-overlap, distance)

        return min(sections, key=score, default=None)

    def _vertical_overlap(self, first: dict[str, float], second: dict[str, float]) -> float:
        first_top = first["y"]
        first_bottom = first["y"] + first["height"]
        second_top = second["y"]
        second_bottom = second["y"] + second["height"]
        return max(0.0, min(first_bottom, second_bottom) - max(first_top, second_top))

    def _center_y(self, bounds: dict[str, float]) -> float:
        return bounds["y"] + (bounds["height"] / 2.0)

    def _subtree_contains_visible_text(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        if node.get("type") == "TEXT":
            return True
        return any(self._subtree_contains_visible_text(child) for child in node.get("children", []))

    def _box_has_area(self, box: dict[str, Any]) -> bool:
        try:
            width = float(box.get("width", 0.0) or 0.0)
            height = float(box.get("height", 0.0) or 0.0)
        except (AttributeError, TypeError, ValueError):
            return False
        return width > 0 and height > 0
