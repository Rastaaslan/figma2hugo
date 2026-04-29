from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from lxml import etree
except ImportError:  # pragma: no cover - environment dependent
    from xml.etree import ElementTree as etree

from figma2hugo.asset_downloader import AssetDownloader
from figma2hugo.content_extractor import ContentExtractor
from figma2hugo.figma_reader.mcp_client import FigmaMcpClient, FigmaMcpError
from figma2hugo.figma_reader.rest_client import FigmaRestClient, FigmaRestError
from figma2hugo.figma_reader.storage import ExtractionStore
from figma2hugo.figma_reader.url_tools import ParsedFigmaUrl, parse_figma_url
from figma2hugo.layout_analyzer import LayoutAnalyzer
from figma2hugo.model import IntermediateDocument

SECTION_LIKE_TYPES = {"FRAME", "SECTION", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET"}
NON_CONTENT_ASSET_FUNCTIONS = {"background", "decorative", "foreground", "icon", "mask"}
GENERIC_CONTAINER_NAME_TOKENS = {
    "auto",
    "bloc",
    "block",
    "container",
    "content",
    "div",
    "frame",
    "group",
    "groupe",
    "inner",
    "layout",
    "node",
    "outer",
    "wrapper",
}
SEMANTIC_CONTAINER_ROLES = {
    "carousel",
    "carousel-nav",
    "carousel-slide",
    "carousel-stage",
    "carousel-thumb",
    "link-card",
    "link-grid",
    "accordion",
    "accordion-item",
    "accordion-panel",
    "accordion-trigger",
    "button",
    "card",
    "field",
    "footer",
    "form",
    "header",
    "nav",
    "section",
}


class FigmaExtractionService:
    def __init__(
        self,
        *,
        rest_client: FigmaRestClient | None = None,
        mcp_client: FigmaMcpClient | None = None,
        layout_analyzer: LayoutAnalyzer | None = None,
        content_extractor: ContentExtractor | None = None,
        asset_downloader: AssetDownloader | None = None,
    ) -> None:
        self.rest_client = rest_client or FigmaRestClient.from_env()
        self.mcp_client = mcp_client or FigmaMcpClient()
        self.layout_analyzer = layout_analyzer or LayoutAnalyzer()
        self.content_extractor = content_extractor or ContentExtractor()
        self.asset_downloader = asset_downloader or AssetDownloader(self.rest_client)

    def inspect(self, figma_url: str, out_dir: str | Path) -> dict[str, Any]:
        model = self.extract(figma_url, out_dir)
        summary = {
            "page": model["page"],
            "sectionCount": len(model.get("sections", [])),
            "textCount": len(model.get("texts", {})),
            "assetCount": len(model.get("assets", [])),
            "warnings": model.get("warnings", []),
        }
        store = ExtractionStore(Path(out_dir))
        store.write_json("inspect.json", summary)
        return summary

    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
        *,
        asset_mode: str = "mixed",
    ) -> dict[str, Any]:
        store = ExtractionStore(Path(out_dir))

        parsed_url = parse_figma_url(figma_url)
        warnings: list[str] = []
        raw_payload = self._collect_raw_payload(parsed_url, store, warnings)
        root_node = self._select_root_node(raw_payload, parsed_url)
        self._validate_root_structure(root_node)
        sections = self.layout_analyzer.identify_sections(root_node)
        extracted = self.content_extractor.extract(
            sections,
            image_fill_urls=raw_payload.get("image_fill_urls", {}),
            token_payload=raw_payload.get("variables", {}),
        )

        assets = self.asset_downloader.materialize_assets(
            parsed_url.file_key,
            extracted.assets,
            store.dirs.assets_dir,
            asset_mode=asset_mode,
        )
        warnings.extend(raw_payload.get("warnings", []))
        warnings.extend(extracted.warnings)

        page_model = {
            "page": {
                "id": parsed_url.node_id or root_node.get("id"),
                "name": root_node.get("name") or parsed_url.page_hint or "Page",
                "width": (root_node.get("absoluteBoundingBox") or {}).get("width", 0),
                "height": (root_node.get("absoluteBoundingBox") or {}).get("height", 0),
                "layout": self._layout_metadata(root_node, fallback_strategy="absolute"),
                "meta": {
                    "figmaUrl": figma_url,
                    "fileKey": parsed_url.file_key,
                    "nodeId": parsed_url.node_id,
                    "pageHint": parsed_url.page_hint,
                    "sourceModes": raw_payload.get("source_modes", []),
                },
            },
            "sections": [
                {
                    **section.to_dict(),
                    "children": self._build_section_children(
                        section.node,
                        text_ids={
                            text_id
                            for text_id, text in extracted.texts.items()
                            if text.get("sectionId") == section.id
                        },
                        asset_ids={
                            asset.get("nodeId")
                            for asset in assets
                            if asset.get("sectionId") == section.id and asset.get("nodeId")
                        },
                        extra_nodes=section.extra_nodes,
                    ),
                    "texts": [
                        text_id
                        for text_id, text in extracted.texts.items()
                        if text.get("sectionId") == section.id
                    ],
                    "assets": [
                        asset.get("nodeId")
                        for asset in assets
                        if asset.get("sectionId") == section.id and asset.get("function") not in NON_CONTENT_ASSET_FUNCTIONS
                    ],
                    "decorative_assets": [
                        asset.get("nodeId")
                        for asset in assets
                        if asset.get("sectionId") == section.id and asset.get("function") in NON_CONTENT_ASSET_FUNCTIONS
                    ],
                    "layout": self._layout_metadata(section.node, fallback_strategy="absolute"),
                    "metadata": {
                        "sourceNodeType": section.node.get("type"),
                        "clipsContent": bool(section.node.get("clipsContent", False)),
                        "rawChildIds": [
                            child.get("id")
                            for child in section.node.get("children", [])
                            if child.get("visible", True)
                        ]
                        + [
                            child.get("id")
                            for child in section.extra_nodes
                            if child.get("visible", True)
                        ],
                    },
                }
                for section in sections
            ],
            "texts": extracted.texts,
            "assets": assets,
            "tokens": extracted.tokens,
            "warnings": self._dedupe_warnings(warnings),
        }

        validated_model = IntermediateDocument.model_validate(page_model)
        serialized = validated_model.model_dump(by_alias=True, mode="json")
        store.write_json("page.json", serialized)
        return serialized

    def _collect_raw_payload(
        self,
        parsed_url: ParsedFigmaUrl,
        store: ExtractionStore,
        warnings: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"warnings": [], "source_modes": []}
        root_node_id = parsed_url.node_id
        if self.rest_client.available:
            try:
                rest_tree = (
                    self.rest_client.get_file_nodes(parsed_url.file_key, [root_node_id])
                    if root_node_id
                    else self.rest_client.get_file(parsed_url.file_key)
                )
                store.write_json("raw/rest-tree.json", rest_tree)
                payload["rest_tree"] = rest_tree
                payload["source_modes"].append("rest")

                image_fills = self.rest_client.get_image_fills(parsed_url.file_key)
                store.write_json("raw/image-fills.json", image_fills)
                payload["image_fill_urls"] = image_fills

                variables = self.rest_client.get_local_variables(parsed_url.file_key)
                store.write_json("raw/variables-rest.json", variables)
                payload["variables"] = variables

                if root_node_id:
                    screenshot_urls = self.rest_client.get_render_urls(
                        parsed_url.file_key,
                        [root_node_id],
                        image_format="png",
                        scale=2,
                    )
                    store.write_json("raw/render-urls.json", screenshot_urls)
                    screenshot_url = screenshot_urls.get(root_node_id)
                    if screenshot_url:
                        reference_bytes = self._download_bytes(screenshot_url)
                        store.write_bytes("reference/figma-reference.png", reference_bytes)
                        payload["reference_image"] = "reference/figma-reference.png"
            except FigmaRestError as exc:
                warnings.append(str(exc))

        if self.mcp_client.available:
            try:
                metadata = self.mcp_client.get_metadata(parsed_url.figma_url)
                store.write_json("raw/mcp-metadata.json", metadata)
                payload["mcp_metadata"] = metadata
                payload["source_modes"].append("mcp")

                variables = self.mcp_client.get_variable_defs(parsed_url.figma_url)
                store.write_json("raw/mcp-variables.json", variables)
                payload["variables"] = variables or payload.get("variables", {})

                screenshot = self.mcp_client.get_screenshot(parsed_url.figma_url)
                store.write_json("raw/mcp-screenshot.json", screenshot)

                if os.getenv("FIGMA2HUGO_INCLUDE_DESIGN_CONTEXT", "1") == "1":
                    design_context = self.mcp_client.get_design_context(parsed_url.figma_url)
                    store.write_json("raw/mcp-design-context.json", design_context)
                    payload["design_context"] = design_context
            except (FigmaMcpError, RuntimeError, ValueError) as exc:
                warnings.append(f"MCP extraction skipped: {exc}")

        if "rest_tree" not in payload and "mcp_metadata" in payload:
            payload["rest_tree"] = self._metadata_xml_to_tree(payload["mcp_metadata"])
            payload["source_modes"].append("metadata-xml")

        if "rest_tree" not in payload:
            raise RuntimeError(
                "Unable to extract Figma data. Configure FIGMA_ACCESS_TOKEN or a FIGMA_MCP_* bridge."
            )

        return payload

    def _select_root_node(self, raw_payload: dict[str, Any], parsed_url: ParsedFigmaUrl) -> dict[str, Any]:
        rest_tree = raw_payload["rest_tree"]
        if "nodes" in rest_tree:
            if parsed_url.node_id and parsed_url.node_id in rest_tree["nodes"]:
                return rest_tree["nodes"][parsed_url.node_id]["document"]
            first_node = next(iter(rest_tree["nodes"].values()))
            return first_node["document"]
        return rest_tree.get("document", rest_tree)

    def _metadata_xml_to_tree(self, metadata_payload: dict[str, Any]) -> dict[str, Any]:
        contents = metadata_payload.get("content", [])
        xml_chunks = [item.get("text", "") for item in contents if item.get("type") == "text"]
        xml_text = "\n".join(chunk for chunk in xml_chunks if chunk.strip())
        if not xml_text:
            return {
                "document": {
                    "id": "metadata-root",
                    "name": "Page",
                    "type": "FRAME",
                    "visible": True,
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 0, "height": 0},
                    "children": [],
                }
            }

        root = etree.fromstring(xml_text.encode("utf-8"))
        document = self._xml_node_to_tree(root)
        return {"document": document}

    def _validate_root_structure(self, root_node: dict[str, Any]) -> None:
        visible_children = [
            child
            for child in root_node.get("children", [])
            if isinstance(child, dict) and child.get("visible", True)
        ]
        if len(visible_children) < 250:
            return

        container_children = [child for child in visible_children if child.get("type") in SECTION_LIKE_TYPES]
        if container_children:
            return

        text_children = [child for child in visible_children if child.get("type") == "TEXT"]
        if text_children:
            return

        raise RuntimeError(
            "Selected Figma node is too flat for structured extraction: "
            f"{len(visible_children)} visible children are placed at the same level with no grouping frames or sections. "
            "Please restructure the file so the page is grouped into frames/sections instead of keeping everything at one level."
        )

    def _xml_node_to_tree(self, element: Any) -> dict[str, Any]:
        width = float(element.attrib.get("width", 0))
        height = float(element.attrib.get("height", 0))
        x = float(element.attrib.get("x", 0))
        y = float(element.attrib.get("y", 0))
        return {
            "id": element.attrib.get("id", element.tag),
            "name": element.attrib.get("name", element.tag),
            "type": element.attrib.get("type", element.tag.upper()),
            "visible": element.attrib.get("visible", "true") != "false",
            "absoluteBoundingBox": {"x": x, "y": y, "width": width, "height": height},
            "children": [self._xml_node_to_tree(child) for child in element],
        }

    def _download_bytes(self, url: str) -> bytes:
        import httpx

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
        response.raise_for_status()
        return response.content

    def _dedupe_warnings(self, warnings: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for warning in warnings:
            normalized = warning.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def _build_section_children(
        self,
        root_node: dict[str, Any],
        *,
        text_ids: set[str],
        asset_ids: set[str],
        extra_nodes: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        ordered: list[Any] = []
        section_bounds = root_node.get("absoluteBoundingBox") or root_node.get("absoluteRenderBounds") or {}

        root_node_id = root_node.get("id")
        if root_node_id in asset_ids:
            ordered.append(root_node_id)

        for child in root_node.get("children", []):
            ordered.extend(
                self._collect_child_descriptors(
                    child,
                    text_ids=text_ids,
                    asset_ids=asset_ids,
                    container_parent_bounds=section_bounds,
                    leaf_parent_bounds=None,
                    container_space="section",
                )
            )
        for child in sorted(extra_nodes or [], key=self._node_sort_key):
            ordered.extend(
                self._collect_child_descriptors(
                    child,
                    text_ids=text_ids,
                    asset_ids=asset_ids,
                    container_parent_bounds=section_bounds,
                    leaf_parent_bounds=None,
                    container_space="section",
                )
            )
        return ordered

    def _collect_child_descriptors(
        self,
        node: dict[str, Any],
        *,
        text_ids: set[str],
        asset_ids: set[str],
        container_parent_bounds: dict[str, Any] | None = None,
        leaf_parent_bounds: dict[str, Any] | None = None,
        container_space: str = "section",
    ) -> list[Any]:
        if not isinstance(node, dict) or not node.get("visible", True):
            return []

        node_id = node.get("id")
        node_type = str(node.get("type") or "").upper()
        if node_type == "TEXT" and node_id in text_ids:
            if leaf_parent_bounds:
                return [self._contextual_text_descriptor(node, parent_bounds=leaf_parent_bounds)]
            return [node_id]
        if node_id in asset_ids:
            if leaf_parent_bounds:
                return [self._contextual_asset_descriptor(node, parent_bounds=leaf_parent_bounds)]
            return [node_id]

        children: list[Any] = []
        node_bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        for child in node.get("children", []):
            children.extend(
                self._collect_child_descriptors(
                    child,
                    text_ids=text_ids,
                    asset_ids=asset_ids,
                    container_parent_bounds=container_parent_bounds,
                    leaf_parent_bounds=leaf_parent_bounds,
                    container_space=container_space,
                )
            )
        if not children:
            return []
        if not self._should_preserve_container(node, children):
            return children
        localized_children: list[Any] = []
        for child in node.get("children", []):
            localized_children.extend(
                self._collect_child_descriptors(
                    child,
                    text_ids=text_ids,
                    asset_ids=asset_ids,
                    container_parent_bounds=node_bounds,
                    leaf_parent_bounds=node_bounds,
                    container_space="parent",
                )
            )
        return [
            self._container_descriptor(
                node,
                localized_children,
                parent_bounds=container_parent_bounds,
                coordinate_space=container_space,
            )
        ]

    def _should_preserve_container(self, node: dict[str, Any], children: list[Any]) -> bool:
        node_type = str(node.get("type") or "").upper()
        if node_type not in SECTION_LIKE_TYPES:
            return False

        role = self._infer_container_role(node.get("name"), fallback="")
        if role in SEMANTIC_CONTAINER_ROLES:
            return True

        if len(children) < 2:
            return False

        return self._has_meaningful_container_name(node.get("name"))

    def _container_descriptor(
        self,
        node: dict[str, Any],
        children: list[Any],
        *,
        parent_bounds: dict[str, Any] | None = None,
        coordinate_space: str = "section",
    ) -> dict[str, Any]:
        role = self._infer_container_role(node.get("name"), fallback="container")
        bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        if parent_bounds:
            bounds = self._relative_bounds(bounds, parent_bounds)
        return {
            "id": node.get("id"),
            "name": node.get("name") or node.get("id") or "container",
            "kind": "container",
            "role": role,
            "bounds": bounds,
            "layout": self._layout_metadata(node, fallback_strategy=self._container_layout_fallback(role)),
            "coordinate_space": coordinate_space,
            "children_coordinate_space": "parent",
            "children": children,
        }

    def _contextual_text_descriptor(
        self,
        node: dict[str, Any],
        *,
        parent_bounds: dict[str, Any],
    ) -> dict[str, Any]:
        bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        render_bounds = node.get("absoluteRenderBounds") or node.get("absoluteBoundingBox") or {}
        return {
            "id": node.get("id"),
            "kind": "text",
            "text": node.get("id"),
            "bounds": self._relative_bounds(bounds, parent_bounds),
            "render_bounds": self._relative_bounds(render_bounds, parent_bounds),
            "layout": self._layout_metadata(node, fallback_strategy="text"),
            "coordinate_space": "parent",
        }

    def _contextual_asset_descriptor(
        self,
        node: dict[str, Any],
        *,
        parent_bounds: dict[str, Any],
    ) -> dict[str, Any]:
        bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        return {
            "id": node.get("id"),
            "kind": "asset",
            "asset": node.get("id"),
            "bounds": self._relative_bounds(bounds, parent_bounds),
            "layout": self._layout_metadata(node, fallback_strategy="leaf"),
            "coordinate_space": "parent",
        }

    def _relative_bounds(
        self,
        bounds: dict[str, Any],
        parent_bounds: dict[str, Any],
    ) -> dict[str, float]:
        return {
            "x": float(bounds.get("x", 0.0) or 0.0) - float(parent_bounds.get("x", 0.0) or 0.0),
            "y": float(bounds.get("y", 0.0) or 0.0) - float(parent_bounds.get("y", 0.0) or 0.0),
            "width": float(bounds.get("width", 0.0) or 0.0),
            "height": float(bounds.get("height", 0.0) or 0.0),
        }

    def _infer_container_role(self, name: Any, *, fallback: str = "container") -> str:
        normalized_name = self._normalize_layer_name(name)
        if self._name_matches(normalized_name, prefixes=("href-card", "link-card"), tokens=()):
            return "link-card"
        if self._name_matches(normalized_name, prefixes=("href-grid", "link-grid"), tokens=()):
            return "link-grid"
        if self._name_matches(normalized_name, prefixes=("accordion-item",), tokens=()):
            return "accordion-item"
        if self._name_matches(normalized_name, prefixes=("accordion-trigger",), tokens=()):
            return "accordion-trigger"
        if self._name_matches(normalized_name, prefixes=("accordion-panel",), tokens=()):
            return "accordion-panel"
        if self._name_matches(normalized_name, prefixes=("accordion",), tokens=()):
            return "accordion"
        if self._name_matches(normalized_name, prefixes=("carousel-stage", "carousel-main"), tokens=()):
            return "carousel-stage"
        if self._name_matches(normalized_name, prefixes=("carousel-thumbs", "carousel-nav", "carousel-track"), tokens=()):
            return "carousel-nav"
        if self._name_matches(normalized_name, prefixes=("carousel-slide",), tokens=()):
            return "carousel-slide"
        if self._name_matches(normalized_name, prefixes=("carousel-thumb",), tokens=()):
            return "carousel-thumb"
        if self._name_matches(normalized_name, prefixes=("carousel",), tokens=()):
            return "carousel"
        if self._name_matches(normalized_name, prefixes=("formulaire", "form"), tokens=()):
            return "form"
        if self._name_matches(normalized_name, prefixes=("button", "btn"), tokens=()):
            return "button"
        if self._name_matches(normalized_name, prefixes=("input", "champ", "zone", "field"), tokens=()):
            return "field"
        if self._name_matches(normalized_name, prefixes=("card-v", "card-h", "card", "article"), tokens=()):
            return "card"
        if self._name_matches(normalized_name, prefixes=("nav",), tokens=()):
            return "nav"
        if self._name_matches(normalized_name, prefixes=("footer",), tokens=()):
            return "footer"
        if self._name_matches(normalized_name, prefixes=("header",), tokens=()):
            return "header"
        if self._name_matches(normalized_name, prefixes=("hero", "section"), tokens=()):
            return "section"
        return str(fallback or "container").strip().lower() or "container"

    def _has_meaningful_container_name(self, name: Any) -> bool:
        tokens = [token for token in self._normalize_layer_name(name).split("-") if token]
        if not tokens:
            return False
        meaningful_tokens = [
            token
            for token in tokens
            if not token.isdigit() and token not in GENERIC_CONTAINER_NAME_TOKENS
        ]
        return bool(meaningful_tokens)

    def _normalize_layer_name(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        normalized = "".join(character if character.isalnum() else "-" for character in text)
        while "--" in normalized:
            normalized = normalized.replace("--", "-")
        return normalized.strip("-")

    def _name_matches(
        self,
        normalized_name: str,
        *,
        prefixes: tuple[str, ...],
        tokens: tuple[str, ...],
    ) -> bool:
        if not normalized_name:
            return False
        if any(normalized_name == prefix or normalized_name.startswith(f"{prefix}-") for prefix in prefixes):
            return True
        if not tokens:
            return False
        node_tokens = {token for token in normalized_name.split("-") if token}
        return any(token in node_tokens for token in tokens)

    def _node_sort_key(self, node: dict[str, Any]) -> tuple[float, float]:
        box = node.get("absoluteRenderBounds") or node.get("absoluteBoundingBox") or {}
        return (
            float(box.get("y", 0.0) or 0.0),
            float(box.get("x", 0.0) or 0.0),
        )

    def _layout_metadata(
        self,
        node: dict[str, Any],
        *,
        fallback_strategy: str,
    ) -> dict[str, Any]:
        strategy = self._infer_layout_strategy(node, fallback_strategy=fallback_strategy)
        metadata = {
            "layout_mode": self._string_or_none(node.get("layoutMode")),
            "layout_wrap": self._string_or_none(node.get("layoutWrap")),
            "layout_positioning": self._string_or_none(node.get("layoutPositioning")),
            "layout_sizing_horizontal": self._string_or_none(node.get("layoutSizingHorizontal")),
            "layout_sizing_vertical": self._string_or_none(node.get("layoutSizingVertical")),
            "primary_axis_sizing_mode": self._string_or_none(node.get("primaryAxisSizingMode")),
            "counter_axis_sizing_mode": self._string_or_none(node.get("counterAxisSizingMode")),
            "primary_axis_align_items": self._string_or_none(node.get("primaryAxisAlignItems")),
            "counter_axis_align_items": self._string_or_none(node.get("counterAxisAlignItems")),
            "counter_axis_align_content": self._string_or_none(node.get("counterAxisAlignContent")),
            "item_spacing": self._number_or_none(node.get("itemSpacing")),
            "counter_axis_spacing": self._number_or_none(node.get("counterAxisSpacing")),
            "padding_top": self._number_or_none(node.get("paddingTop")),
            "padding_right": self._number_or_none(node.get("paddingRight")),
            "padding_bottom": self._number_or_none(node.get("paddingBottom")),
            "padding_left": self._number_or_none(node.get("paddingLeft")),
            "min_width": self._number_or_none(node.get("minWidth")),
            "max_width": self._number_or_none(node.get("maxWidth")),
            "min_height": self._number_or_none(node.get("minHeight")),
            "max_height": self._number_or_none(node.get("maxHeight")),
            "text_auto_resize": self._string_or_none(node.get("textAutoResize")),
            "clips_content": self._bool_or_none(node, "clipsContent"),
            "constraints": self._constraints_payload(node),
            "inferred_strategy": strategy,
            "inferred_flow": strategy == "flow",
        }
        return {
            key: value
            for key, value in metadata.items()
            if value not in (None, "")
            and not (key == "constraints" and not value)
        }

    def _infer_layout_strategy(self, node: dict[str, Any], *, fallback_strategy: str) -> str:
        layout_mode = self._string_or_none(node.get("layoutMode"))
        layout_wrap = self._string_or_none(node.get("layoutWrap"))
        if layout_mode in {"HORIZONTAL", "VERTICAL"}:
            return "flow"
        if layout_wrap and layout_wrap != "NO_WRAP":
            return "flow"
        if str(node.get("type") or "").upper() == "TEXT":
            return "text"
        if node.get("children"):
            return "absolute"
        return fallback_strategy

    def _container_layout_fallback(self, role: str) -> str:
        if role in {"accordion", "accordion-item", "accordion-panel", "accordion-trigger", "link-grid", "card", "link-card"}:
            return "absolute"
        if role in {"carousel", "carousel-stage", "carousel-nav", "carousel-slide", "carousel-thumb"}:
            return "absolute"
        return "absolute"

    def _constraints_payload(self, node: dict[str, Any]) -> dict[str, Any]:
        constraints = node.get("constraints")
        if isinstance(constraints, dict):
            return {
                key: value
                for key, value in constraints.items()
                if value not in (None, "")
            }
        return {}

    def _string_or_none(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _number_or_none(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _bool_or_none(self, node: dict[str, Any], key: str) -> bool | None:
        if key not in node:
            return None
        return bool(node.get(key))
