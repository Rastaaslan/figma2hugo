from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, AnyHttpUrl, ConfigDict, Field, model_validator

from figma2hugo.model.base import FigmaBaseModel
from figma2hugo.model.enums import AssetRole, SectionRole
from figma2hugo.model.geometry import Bounds


class LayoutMetadata(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    layout_mode: str | None = None
    layout_wrap: str | None = None
    layout_positioning: str | None = None
    layout_sizing_horizontal: str | None = None
    layout_sizing_vertical: str | None = None
    primary_axis_sizing_mode: str | None = None
    counter_axis_sizing_mode: str | None = None
    primary_axis_align_items: str | None = None
    counter_axis_align_items: str | None = None
    counter_axis_align_content: str | None = None
    item_spacing: float | None = None
    counter_axis_spacing: float | None = None
    padding_top: float | None = None
    padding_right: float | None = None
    padding_bottom: float | None = None
    padding_left: float | None = None
    min_width: float | None = None
    max_width: float | None = None
    min_height: float | None = None
    max_height: float | None = None
    text_auto_resize: str | None = None
    clips_content: bool | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    inferred_strategy: str | None = None
    inferred_flow: bool | None = None


class PageNode(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    layout: LayoutMetadata | None = None
    meta: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("meta", "sourceMeta", "source_meta"),
        serialization_alias="meta",
    )


class TextStyleRun(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    style: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_offsets(self) -> "TextStyleRun":
        if self.end <= self.start:
            raise ValueError("Text style run end must be greater than start.")
        return self


class TextNode(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    name: str | None = None
    value: str = Field(min_length=1)
    raw_value: str | None = None
    section_id: str | None = None
    bounds: Bounds | None = None
    style_runs: list[TextStyleRun] = Field(default_factory=list)
    tag: str | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    layout: LayoutMetadata | None = None

    @model_validator(mode="after")
    def default_raw_value(self) -> "TextNode":
        if self.raw_value is None:
            self.raw_value = self.value
        return self


class AssetRef(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    node_id: str = Field(min_length=1)
    name: str | None = None
    section_id: str | None = None
    source_url: AnyHttpUrl | None = None
    format: str | None = None
    local_path: str | None = None
    function: AssetRole = Field(
        default=AssetRole.CONTENT,
        validation_alias=AliasChoices("function", "role"),
        serialization_alias="function",
    )
    bounds: Bounds | None = None
    is_vector: bool = False
    image_ref: str | None = None
    layout: LayoutMetadata | None = None


class TokenBag(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    colors: dict[str, Any] = Field(default_factory=dict)
    spacing: dict[str, Any] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    shadows: dict[str, Any] = Field(default_factory=dict)
    radii: dict[str, Any] = Field(default_factory=dict)


class SectionNode(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: SectionRole = SectionRole.SECTION
    bounds: Bounds
    children: list[Any] = Field(default_factory=list)
    texts: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    layout: LayoutMetadata | None = None
    decorative_assets: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("decorative_assets", "decorativeAssets"),
        serialization_alias="decorative_assets",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntermediateDocument(FigmaBaseModel):
    model_config = ConfigDict(extra="allow")

    page: PageNode
    sections: list[SectionNode] = Field(default_factory=list)
    texts: dict[str, TextNode] = Field(default_factory=dict)
    assets: list[AssetRef] = Field(default_factory=list)
    tokens: TokenBag = Field(default_factory=TokenBag)
    warnings: list[str] = Field(default_factory=list)
