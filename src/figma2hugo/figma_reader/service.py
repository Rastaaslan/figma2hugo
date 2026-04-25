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
                    "children": self._ordered_child_ids(
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
                    ),
                    "texts": [
                        text_id
                        for text_id, text in extracted.texts.items()
                        if text.get("sectionId") == section.id
                    ],
                    "assets": [
                        asset.get("nodeId")
                        for asset in assets
                        if asset.get("sectionId") == section.id and asset.get("function") != "decorative"
                    ],
                    "decorative_assets": [
                        asset.get("nodeId")
                        for asset in assets
                        if asset.get("sectionId") == section.id and asset.get("function") == "decorative"
                    ],
                    "metadata": {
                        "rawChildIds": [
                            child.get("id")
                            for child in section.node.get("children", [])
                            if child.get("visible", True)
                        ]
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

    def _ordered_child_ids(
        self,
        root_node: dict[str, Any],
        *,
        text_ids: set[str],
        asset_ids: set[str],
    ) -> list[str]:
        ordered: list[str] = []

        def visit(node: dict[str, Any]) -> None:
            if not node.get("visible", True):
                return
            node_id = node.get("id")
            if node.get("type") == "TEXT" and node_id in text_ids:
                ordered.append(node_id)
            elif node_id in asset_ids:
                ordered.append(node_id)
            for child in node.get("children", []):
                visit(child)

        for child in root_node.get("children", []):
            visit(child)
        return ordered
