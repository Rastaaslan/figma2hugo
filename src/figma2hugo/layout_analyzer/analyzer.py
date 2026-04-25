from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SECTION_LIKE_TYPES = {"FRAME", "SECTION", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET"}


@dataclass(slots=True)
class SectionCandidate:
    id: str
    name: str
    role: str
    node: dict[str, Any]
    bounds: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "bounds": self.bounds,
        }


class LayoutAnalyzer:
    def identify_sections(self, root_node: dict[str, Any]) -> list[SectionCandidate]:
        visible_children = [
            child
            for child in root_node.get("children", [])
            if child.get("visible", True) and child.get("type") in SECTION_LIKE_TYPES
        ]

        if self._is_container(root_node) and visible_children:
            candidates = [child for child in visible_children if self._looks_like_section(child, root_node)]
        else:
            candidates = []

        if not candidates:
            candidates = [root_node]

        result: list[SectionCandidate] = []
        for index, node in enumerate(candidates):
            section_id = node.get("id", f"section-{index + 1}")
            result.append(
                SectionCandidate(
                    id=section_id,
                    name=node.get("name") or f"Section {index + 1}",
                    role=self._guess_role(node, index, len(candidates)),
                    node=node,
                    bounds=self._bounds(node),
                )
            )
        return result

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
        return any(token in name for token in ("hero", "header", "footer", "section", "feature", "contact"))

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
        box = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        return {
            "x": float(box.get("x", 0.0)),
            "y": float(box.get("y", 0.0)),
            "width": float(box.get("width", 0.0)),
            "height": float(box.get("height", 0.0)),
        }
