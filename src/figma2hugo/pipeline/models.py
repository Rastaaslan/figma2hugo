"""Modeles types qui decrivent les noeuds Figma normalises et les plans de rendu."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CoordinateSpace(StrEnum):
    ABSOLUTE = "absolute"
    PAGE = "page"
    PARENT = "parent"


class GeometrySource(StrEnum):
    BOUNDING_BOX = "absoluteBoundingBox"
    RENDER_BOUNDS = "absoluteRenderBounds"
    COMPUTED = "computed"
    MISSING = "missing"


class NodeKind(StrEnum):
    PAGE = "page"
    SECTION = "section"
    CONTAINER = "container"
    TEXT = "text"
    ASSET = "asset"
    UNKNOWN = "unknown"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class GeometryBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def relative_to(self, origin: GeometryBox) -> GeometryBox:
        return GeometryBox(
            x=self.x - origin.x,
            y=self.y - origin.y,
            width=self.width,
            height=self.height,
        )

    def with_horizontal_box(self, *, x: float, width: float) -> GeometryBox:
        return GeometryBox(x=x, y=self.y, width=width, height=self.height)

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_mapping(cls, value: Any) -> GeometryBox | None:
        if not isinstance(value, dict):
            return None
        try:
            width = float(value.get("width", 0) or 0)
            height = float(value.get("height", 0) or 0)
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        try:
            x = float(value.get("x", 0) or 0)
            y = float(value.get("y", 0) or 0)
        except (TypeError, ValueError):
            x = 0.0
            y = 0.0
        return cls(x=x, y=y, width=width, height=height)


@dataclass(frozen=True, slots=True)
class PipelineIssue:
    code: str
    severity: IssueSeverity
    message: str
    node_id: str = ""
    related_node_id: str = ""
    width: int | None = None
    metrics: dict[str, float | int | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.node_id:
            payload["nodeId"] = self.node_id
        if self.related_node_id:
            payload["relatedNodeId"] = self.related_node_id
        if self.width is not None:
            payload["width"] = self.width
        if self.metrics:
            payload["metrics"] = dict(self.metrics)
        return payload


@dataclass(frozen=True, slots=True)
class RawNode:
    id: str
    name: str
    type: str
    visible: bool
    absolute_bounds: GeometryBox | None
    render_bounds: GeometryBox | None
    children: tuple[RawNode, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> RawNode:
        children = tuple(
            cls.from_mapping(child)
            for child in value.get("children", [])
            if isinstance(child, dict)
        )
        return cls(
            id=str(value.get("id") or value.get("nodeId") or value.get("node_id") or ""),
            name=str(value.get("name") or ""),
            type=str(value.get("type") or ""),
            visible=value.get("visible") is not False,
            absolute_bounds=GeometryBox.from_mapping(value.get("absoluteBoundingBox")),
            render_bounds=GeometryBox.from_mapping(value.get("absoluteRenderBounds")),
            children=children,
            payload=dict(value),
        )


@dataclass(frozen=True, slots=True)
class NormalizedNode:
    id: str
    name: str
    type: str
    kind: NodeKind
    coordinate_space: CoordinateSpace
    geometry_source: GeometrySource
    absolute_bounds: GeometryBox
    page_bounds: GeometryBox
    parent_bounds: GeometryBox
    render_bounds: GeometryBox | None = None
    children: tuple[NormalizedNode, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    def walk(self) -> tuple[NormalizedNode, ...]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.walk())
        return tuple(nodes)


@dataclass(frozen=True, slots=True)
class IntermediatePipelineDocument:
    page: NormalizedNode
    sections: tuple[NormalizedNode, ...]
    diagnostics: tuple[PipelineIssue, ...] = ()

    @property
    def width(self) -> int:
        return int(round(self.page.page_bounds.width))

    @property
    def slug(self) -> str:
        return self.page.name.strip().lower().replace(" ", "-")


@dataclass(frozen=True, slots=True)
class RenderTextRun:
    text: str
    style: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RenderNodePlan:
    node_id: str
    name: str
    kind: NodeKind
    bounds: GeometryBox
    layer: str
    text: str = ""
    asset_url: str = ""
    style: dict[str, str] = field(default_factory=dict)
    component: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    text_runs: tuple[RenderTextRun, ...] = ()
    children: tuple[RenderNodePlan, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderSectionPlan:
    section_id: str
    name: str
    bounds: GeometryBox
    layout_mode: str
    style: dict[str, str] = field(default_factory=dict)
    nodes: tuple[RenderNodePlan, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderPlan:
    page_id: str
    page_name: str
    width: int
    height: int
    sections: tuple[RenderSectionPlan, ...]
    diagnostics: tuple[PipelineIssue, ...] = ()
