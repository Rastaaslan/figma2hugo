from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SECTION_LIKE_TYPES = {"FRAME", "SECTION", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET"}
SECTION_NAME_HINTS = ("hero", "header", "footer", "section", "feature", "contact", "nav", "menu")


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
        wrapper_chain_ids = self._wrapper_chain_ids(root_node, analysis_root)
        visible_children = [
            child
            for child in analysis_root.get("children", [])
            if child.get("visible", True) and child.get("type") in SECTION_LIKE_TYPES
        ]

        if self._is_container(analysis_root) and visible_children:
            candidates = [child for child in visible_children if self._looks_like_section(child, analysis_root)]
        else:
            candidates = []

        # Imported SVGs and other vectorized exports often expose a frame that
        # contains only graphic groups. Splitting those groups into standalone
        # sections destroys the original stacking order, so we preserve the root
        # as a single visual section when no visible text exists anywhere.
        if (
            candidates
            and not self._subtree_contains_visible_text(analysis_root)
            and not any(self._has_section_name_hint(candidate) for candidate in candidates)
        ):
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
        # When we promote an inner frame/group as the effective page root, the
        # outer wrapper often contains editor notes, exports, or other siblings
        # that are not part of the page itself. Re-attaching those "orphans"
        # from the outer root pollutes the rendered page with huge stray texts
        # and graphics, so we keep orphan attachment scoped to the promoted
        # analysis root only.
        return result

    def _unwrap_single_section_wrapper(self, root_node: dict[str, Any]) -> dict[str, Any]:
        current = root_node
        visited: set[str] = set()

        while current.get("type") in {"DOCUMENT", "CANVAS", "PAGE", "FRAME", "SECTION", "GROUP"}:
            current_id = str(current.get("id") or "")
            if current_id:
                if current_id in visited:
                    break
                visited.add(current_id)

            visible_children = self._visible_section_children(current)
            if len(visible_children) != 1:
                promoted_child = self._pick_dominant_page_root_child(current, visible_children)
                if promoted_child is not None:
                    current = promoted_child
                    continue
                return current

            wrapper = visible_children[0]
            wrapper_children = self._visible_section_children(wrapper)
            section_like_children = [child for child in wrapper_children if self._looks_like_section(child, wrapper)]
            if len(section_like_children) >= 2:
                return wrapper

            if not self._is_trivial_single_child_wrapper(current, wrapper):
                return current

            current = wrapper

        return current

    def _pick_dominant_page_root_child(
        self,
        parent: dict[str, Any],
        visible_children: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        parent_bounds = self._bounds(parent)
        parent_area = max(parent_bounds["width"] * parent_bounds["height"], 1.0)
        eligible: list[tuple[int, float, dict[str, Any]]] = []
        substantial_children = 0

        for child in visible_children:
            child_bounds = self._bounds(child)
            child_area = child_bounds["width"] * child_bounds["height"]
            child_area_ratio = child_area / parent_area
            if child_area_ratio >= 0.12:
                substantial_children += 1
            if child_area_ratio < 0.2:
                continue

            child_visible_children = self._visible_section_children(child)
            section_like_children = [item for item in child_visible_children if self._looks_like_section(item, child)]
            if len(section_like_children) < 2:
                continue

            normalized_name = (child.get("name") or "").strip().lower()
            name_priority = 1 if normalized_name in {"page", "root", "canvas"} else 0
            eligible.append((name_priority, child_area, child))

        if not eligible:
            return None

        eligible.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_priority, best_area, best_child = eligible[0]
        if best_priority > 0:
            return best_child
        if substantial_children > 1:
            return None
        best_area_ratio = best_area / parent_area
        if best_area_ratio < 0.55:
            return None
        if len(eligible) == 1:
            return best_child

        _, second_area, _ = eligible[1]
        if second_area <= 0:
            return best_child
        if best_area / second_area >= 2.0:
            return best_child
        return None

    def _wrapper_chain_ids(self, root_node: dict[str, Any], analysis_root: dict[str, Any]) -> set[str]:
        if root_node is analysis_root:
            return set()

        current = root_node
        target_id = analysis_root.get("id")
        wrapper_ids: set[str] = set()

        while current is not analysis_root and current.get("id") != target_id:
            visible_children = self._visible_section_children(current)
            if len(visible_children) != 1:
                break
            child = visible_children[0]
            child_id = child.get("id")
            if child_id == target_id:
                break
            if child_id:
                wrapper_ids.add(child_id)
            current = child

        return wrapper_ids

    def _visible_section_children(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            child
            for child in node.get("children", [])
            if child.get("visible", True) and child.get("type") in SECTION_LIKE_TYPES
        ]

    def _is_trivial_single_child_wrapper(self, node: dict[str, Any], child: dict[str, Any]) -> bool:
        node_bounds = self._bounds(node)
        child_bounds = self._bounds(child)
        node_area = max(node_bounds["width"] * node_bounds["height"], 1.0)
        child_area = child_bounds["width"] * child_bounds["height"]
        return (child_area / node_area) >= 0.6

    def _is_container(self, node: dict[str, Any]) -> bool:
        return node.get("type") in {"DOCUMENT", "CANVAS", "PAGE", "FRAME", "SECTION", "GROUP"}

    def _looks_like_section(self, node: dict[str, Any], parent: dict[str, Any]) -> bool:
        bounds = self._bounds(node)
        parent_bounds = self._bounds(parent)
        area = bounds["width"] * bounds["height"]
        parent_area = max(parent_bounds["width"] * parent_bounds["height"], 1)
        if area / parent_area >= 0.03:
            return True
        name = (node.get("name") or "").lower()
        if any(token in name for token in SECTION_NAME_HINTS):
            return True
        return self._subtree_contains_visible_text(node)

    def _has_section_name_hint(self, node: dict[str, Any]) -> bool:
        name = (node.get("name") or "").lower()
        return any(token in name for token in SECTION_NAME_HINTS)

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
