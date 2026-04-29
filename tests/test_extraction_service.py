from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.content_extractor.extractor import ExtractionResult
from figma2hugo.figma_reader.service import FigmaExtractionService
from figma2hugo.layout_analyzer.analyzer import SectionCandidate


def test_extraction_service_rejects_flat_roots_without_grouping_frames() -> None:
    root_node = {
        "id": "0:1",
        "name": "Page 1",
        "type": "CANVAS",
        "visible": True,
        "children": [
            {
                "id": f"vector-{index}",
                "name": f"Vector {index}",
                "type": "VECTOR",
                "visible": True,
            }
            for index in range(300)
        ],
    }

    service = FigmaExtractionService()

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_root_structure(root_node)

    message = str(exc_info.value)
    assert "too flat for structured extraction" in message
    assert "grouping frames or sections" in message


def test_extraction_service_routes_named_layer_functions_into_decorative_assets() -> None:
    root_node = {
        "id": "1:1",
        "name": "Landing Page",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
        "children": [
            {
                "id": "hero-title",
                "name": "Hero Title",
                "type": "TEXT",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 96, "width": 420, "height": 64},
            },
            {
                "id": "page-bg-panel",
                "name": "page-bg-panel",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 320},
            },
            {
                "id": "hero-photo",
                "name": "hero-photo",
                "type": "RECTANGLE",
                "visible": True,
                "absoluteBoundingBox": {"x": 720, "y": 132, "width": 460, "height": 320},
            },
            {
                "id": "brand-icon-mark",
                "name": "brand-icon-mark",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 196, "width": 48, "height": 48},
            },
            {
                "id": "page-fg-overlay",
                "name": "page-fg-overlay",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 660, "y": 100, "width": 560, "height": 400},
            },
            {
                "id": "page-overlay-pattern",
                "name": "page-overlay-pattern",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 80, "y": 80, "width": 220, "height": 220},
            },
        ],
    }
    section = SectionCandidate(
        id="1:1",
        name="Landing Page",
        role="hero",
        node=root_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 900.0},
    )

    class StubLayoutAnalyzer:
        def identify_sections(self, root: dict[str, Any]) -> list[SectionCandidate]:
            assert root["id"] == "1:1"
            return [section]

    class StubContentExtractor:
        def extract(
            self,
            sections: list[SectionCandidate],
            *,
            image_fill_urls: dict[str, str] | None = None,
            token_payload: dict[str, Any] | None = None,
        ) -> ExtractionResult:
            assert [candidate.id for candidate in sections] == ["1:1"]
            return ExtractionResult(
                texts={
                    "hero-title": {
                        "id": "hero-title",
                        "name": "Hero Title",
                        "value": "Build faster",
                        "rawValue": "Build faster",
                        "sectionId": "1:1",
                        "bounds": {"x": 120, "y": 96, "width": 420, "height": 64},
                        "styleRuns": [{"start": 0, "end": 5, "style": {"fontFamily": "Inter"}}],
                        "tag": "h1",
                        "style": {"fontFamily": "Inter", "fontSize": 64},
                    }
                },
                assets=[
                    {
                        "nodeId": "page-bg-panel",
                        "sectionId": "1:1",
                        "name": "page-bg-panel",
                        "format": "svg",
                        "localPath": "images/page-bg-panel.svg",
                        "function": "background",
                        "bounds": {"x": 0, "y": 0, "width": 1440, "height": 320},
                        "isVector": True,
                        "imageRef": None,
                    },
                    {
                        "nodeId": "hero-photo",
                        "sectionId": "1:1",
                        "name": "hero-photo",
                        "format": "png",
                        "localPath": "images/hero-photo.png",
                        "function": "content",
                        "bounds": {"x": 720, "y": 132, "width": 460, "height": 320},
                        "isVector": False,
                        "imageRef": None,
                    },
                    {
                        "nodeId": "brand-icon-mark",
                        "sectionId": "1:1",
                        "name": "brand-icon-mark",
                        "format": "svg",
                        "localPath": "images/brand-icon-mark.svg",
                        "function": "icon",
                        "bounds": {"x": 120, "y": 196, "width": 48, "height": 48},
                        "isVector": True,
                        "imageRef": None,
                    },
                    {
                        "nodeId": "page-fg-overlay",
                        "sectionId": "1:1",
                        "name": "page-fg-overlay",
                        "format": "svg",
                        "localPath": "images/page-fg-overlay.svg",
                        "function": "foreground",
                        "bounds": {"x": 660, "y": 100, "width": 560, "height": 400},
                        "isVector": True,
                        "imageRef": None,
                    },
                    {
                        "nodeId": "page-overlay-pattern",
                        "sectionId": "1:1",
                        "name": "page-overlay-pattern",
                        "format": "svg",
                        "localPath": "images/page-overlay-pattern.svg",
                        "function": "decorative",
                        "bounds": {"x": 80, "y": 80, "width": 220, "height": 220},
                        "isVector": True,
                        "imageRef": None,
                    },
                ],
                tokens={},
                warnings=[],
            )

    class StubAssetDownloader:
        def materialize_assets(
            self,
            file_key: str,
            assets: list[dict[str, Any]],
            assets_dir: Path,
            *,
            asset_mode: str = "mixed",
        ) -> list[dict[str, Any]]:
            assert file_key == "FILE"
            assert assets_dir.name == "assets"
            assert asset_mode == "mixed"
            return assets

    class StubExtractionService(FigmaExtractionService):
        def _collect_raw_payload(self, parsed_url: Any, store: Any, warnings: list[str]) -> dict[str, Any]:
            return {
                "rest_tree": {"document": root_node},
                "image_fill_urls": {},
                "variables": {},
                "warnings": [],
                "source_modes": ["stub"],
            }

    service = StubExtractionService(
        rest_client=object(),
        mcp_client=object(),
        layout_analyzer=StubLayoutAnalyzer(),
        content_extractor=StubContentExtractor(),
        asset_downloader=StubAssetDownloader(),
    )

    output_dir = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "test-extraction-service-buckets"
    shutil.rmtree(output_dir, ignore_errors=True)

    model = service.extract("https://www.figma.com/design/FILE/Landing-Page?node-id=1-1", output_dir)
    section_payload = model["sections"][0]

    assert section_payload["children"] == [
        "hero-title",
        "page-bg-panel",
        "hero-photo",
        "brand-icon-mark",
        "page-fg-overlay",
        "page-overlay-pattern",
    ]
    assert section_payload["texts"] == ["hero-title"]
    assert section_payload["assets"] == ["hero-photo"]
    assert section_payload["decorative_assets"] == [
        "page-bg-panel",
        "brand-icon-mark",
        "page-fg-overlay",
        "page-overlay-pattern",
    ]


def test_extraction_service_emits_layout_metadata_for_page_sections_and_containers() -> None:
    root_node = {
        "id": "1:10",
        "name": "Responsive Page",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "itemSpacing": 48,
        "paddingTop": 64,
        "paddingBottom": 64,
        "paddingLeft": 80,
        "paddingRight": 80,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
        "children": [
            {
                "id": "link-grid-projects",
                "name": "link-grid-projects",
                "type": "FRAME",
                "visible": True,
                "layoutMode": "HORIZONTAL",
                "layoutWrap": "WRAP",
                "itemSpacing": 24,
                "paddingTop": 16,
                "paddingBottom": 16,
                "paddingLeft": 16,
                "paddingRight": 16,
                "absoluteBoundingBox": {"x": 80, "y": 160, "width": 1280, "height": 520},
                "children": [
                    {
                        "id": "project-title",
                        "name": "Project Title",
                        "type": "TEXT",
                        "visible": True,
                        "characters": "A great project",
                        "layoutSizingHorizontal": "FILL",
                        "textAutoResize": "HEIGHT",
                        "constraints": {"horizontal": "STRETCH", "vertical": "TOP"},
                        "style": {"fontFamily": "Inter", "fontSize": 24},
                        "absoluteBoundingBox": {"x": 96, "y": 176, "width": 420, "height": 40},
                    },
                    {
                        "id": "project-image",
                        "name": "project-image",
                        "type": "RECTANGLE",
                        "visible": True,
                        "layoutSizingHorizontal": "FILL",
                        "layoutSizingVertical": "FIXED",
                        "constraints": {"horizontal": "STRETCH", "vertical": "TOP"},
                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "project-image-ref"}],
                        "absoluteBoundingBox": {"x": 96, "y": 248, "width": 640, "height": 360},
                    },
                ],
            }
        ],
    }
    section = SectionCandidate(
        id="1:10",
        name="Responsive Page",
        role="section",
        node=root_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 900.0},
    )

    class StubLayoutAnalyzer:
        def identify_sections(self, root: dict[str, Any]) -> list[SectionCandidate]:
            assert root["id"] == "1:10"
            return [section]

    class StubExtractionService(FigmaExtractionService):
        def _collect_raw_payload(self, parsed_url: Any, store: Any, warnings: list[str]) -> dict[str, Any]:
            return {
                "rest_tree": {"document": root_node},
                "image_fill_urls": {"project-image-ref": "https://example.com/project.png"},
                "variables": {},
                "warnings": [],
                "source_modes": ["stub"],
            }

    class StubAssetDownloader:
        def materialize_assets(
            self,
            file_key: str,
            assets: list[dict[str, Any]],
            assets_dir: Path,
            *,
            asset_mode: str = "mixed",
        ) -> list[dict[str, Any]]:
            assert file_key == "FILE"
            assert assets_dir.name == "assets"
            assert asset_mode == "mixed"
            return assets

    output_dir = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "test-extraction-service-layout"
    shutil.rmtree(output_dir, ignore_errors=True)

    service = StubExtractionService(layout_analyzer=StubLayoutAnalyzer(), asset_downloader=StubAssetDownloader())
    model = service.extract("https://www.figma.com/design/FILE/Responsive-Page?node-id=1-10", output_dir)

    assert model["page"]["layout"]["layoutMode"] == "VERTICAL"
    assert model["page"]["layout"]["itemSpacing"] == 48.0
    assert model["page"]["layout"]["inferredStrategy"] == "flow"

    section_payload = model["sections"][0]
    assert section_payload["layout"]["layoutMode"] == "VERTICAL"
    assert section_payload["layout"]["paddingLeft"] == 80.0
    assert section_payload["layout"]["inferredStrategy"] == "flow"

    container_payload = section_payload["children"][0]
    assert container_payload["layout"]["layout_mode"] == "HORIZONTAL"
    assert container_payload["layout"]["layout_wrap"] == "WRAP"
    assert container_payload["layout"]["item_spacing"] == 24.0
    assert container_payload["layout"]["inferred_strategy"] == "flow"

    text_payload = model["texts"]["project-title"]
    assert text_payload["layout"]["layoutSizingHorizontal"] == "FILL"
    assert text_payload["layout"]["textAutoResize"] == "HEIGHT"
    assert text_payload["layout"]["inferredStrategy"] == "text"

    asset_payload = model["assets"][0]
    assert asset_payload["layout"]["layoutSizingVertical"] == "FIXED"
    assert asset_payload["layout"]["constraints"]["horizontal"] == "STRETCH"
    assert asset_payload["layout"]["inferredStrategy"] == "leaf"


def test_extraction_service_preserves_named_nested_groups_for_forms_and_buttons() -> None:
    root_node = {
        "id": "1:2",
        "name": "Contact Section",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
        "children": [
            {
                "id": "contact-title",
                "name": "Contact Title",
                "type": "TEXT",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 120, "width": 320, "height": 60},
            },
            {
                "id": "formulaire-contact",
                "name": "formulaire-contact",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 400, "y": 500, "width": 420, "height": 240},
                "children": [
                    {
                        "id": "input-email",
                        "name": "input-email",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 420, "y": 540, "width": 320, "height": 40},
                        "children": [
                            {
                                "id": "contact-email-label",
                                "name": "Contact Email Label",
                                "type": "TEXT",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 438, "y": 550, "width": 180, "height": 18},
                            }
                        ],
                    },
                    {
                        "id": "button-envoyer",
                        "name": "button-envoyer",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 620, "y": 680, "width": 180, "height": 52},
                        "children": [
                            {
                                "id": "contact-submit-bg",
                                "name": "contact-submit-bg",
                                "type": "RECTANGLE",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 620, "y": 680, "width": 180, "height": 52},
                            },
                            {
                                "id": "contact-submit-label",
                                "name": "Contact Submit Label",
                                "type": "TEXT",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 660, "y": 696, "width": 100, "height": 20},
                            },
                        ],
                    },
                ],
            },
        ],
    }
    section = SectionCandidate(
        id="1:2",
        name="Contact Section",
        role="section",
        node=root_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 900.0},
    )

    class StubLayoutAnalyzer:
        def identify_sections(self, root: dict[str, Any]) -> list[SectionCandidate]:
            assert root["id"] == "1:2"
            return [section]

    class StubContentExtractor:
        def extract(
            self,
            sections: list[SectionCandidate],
            *,
            image_fill_urls: dict[str, str] | None = None,
            token_payload: dict[str, Any] | None = None,
        ) -> ExtractionResult:
            assert [candidate.id for candidate in sections] == ["1:2"]
            return ExtractionResult(
                texts={
                    "contact-title": {
                        "id": "contact-title",
                        "name": "Contact Title",
                        "value": "Contact us",
                        "rawValue": "Contact us",
                        "sectionId": "1:2",
                        "bounds": {"x": 120, "y": 120, "width": 320, "height": 60},
                        "styleRuns": [],
                        "tag": "h2",
                        "style": {"fontFamily": "Inter", "fontSize": 48},
                    },
                    "contact-email-label": {
                        "id": "contact-email-label",
                        "name": "Contact Email Label",
                        "value": "Votre email",
                        "rawValue": "Votre email",
                        "sectionId": "1:2",
                        "bounds": {"x": 438, "y": 550, "width": 180, "height": 18},
                        "styleRuns": [],
                        "tag": "p",
                        "style": {"fontFamily": "Inter", "fontSize": 16},
                    },
                    "contact-submit-label": {
                        "id": "contact-submit-label",
                        "name": "Contact Submit Label",
                        "value": "Envoyer",
                        "rawValue": "Envoyer",
                        "sectionId": "1:2",
                        "bounds": {"x": 660, "y": 696, "width": 100, "height": 20},
                        "styleRuns": [],
                        "tag": "p",
                        "style": {"fontFamily": "Inter", "fontSize": 16},
                    },
                },
                assets=[
                    {
                        "nodeId": "contact-submit-bg",
                        "sectionId": "1:2",
                        "name": "contact-submit-bg",
                        "format": "svg",
                        "localPath": "images/contact-submit-bg.svg",
                        "function": "content",
                        "bounds": {"x": 620, "y": 680, "width": 180, "height": 52},
                        "isVector": True,
                        "imageRef": None,
                    }
                ],
                tokens={},
                warnings=[],
            )

    class StubAssetDownloader:
        def materialize_assets(
            self,
            file_key: str,
            assets: list[dict[str, Any]],
            assets_dir: Path,
            *,
            asset_mode: str = "mixed",
        ) -> list[dict[str, Any]]:
            assert file_key == "FILE"
            assert assets_dir.name == "assets"
            assert asset_mode == "mixed"
            return assets

    class StubExtractionService(FigmaExtractionService):
        def _collect_raw_payload(self, parsed_url: Any, store: Any, warnings: list[str]) -> dict[str, Any]:
            return {
                "rest_tree": {"document": root_node},
                "image_fill_urls": {},
                "variables": {},
                "warnings": [],
                "source_modes": ["stub"],
            }

    service = StubExtractionService(
        rest_client=object(),
        mcp_client=object(),
        layout_analyzer=StubLayoutAnalyzer(),
        content_extractor=StubContentExtractor(),
        asset_downloader=StubAssetDownloader(),
    )

    output_dir = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "test-extraction-service-nesting"
    shutil.rmtree(output_dir, ignore_errors=True)

    model = service.extract("https://www.figma.com/design/FILE/Contact?node-id=1-2", output_dir)
    section_payload = model["sections"][0]

    assert section_payload["children"] == [
        "contact-title",
            {
                "id": "formulaire-contact",
                "name": "formulaire-contact",
                "kind": "container",
                "role": "form",
                "bounds": {"x": 400, "y": 500, "width": 420, "height": 240},
                "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                "coordinate_space": "section",
                "children_coordinate_space": "parent",
                "children": [
                    {
                        "id": "input-email",
                        "name": "input-email",
                        "kind": "container",
                        "role": "field",
                        "bounds": {"x": 20, "y": 40, "width": 320, "height": 40},
                        "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                        "coordinate_space": "parent",
                        "children_coordinate_space": "parent",
                        "children": [
                            {
                                "id": "contact-email-label",
                                "kind": "text",
                                "text": "contact-email-label",
                                "bounds": {"x": 18, "y": 10, "width": 180, "height": 18},
                                "render_bounds": {"x": 18, "y": 10, "width": 180, "height": 18},
                                "layout": {"inferred_strategy": "text", "inferred_flow": False},
                                "coordinate_space": "parent",
                            }
                        ],
                    },
                {
                    "id": "button-envoyer",
                        "name": "button-envoyer",
                        "kind": "container",
                        "role": "button",
                        "bounds": {"x": 220, "y": 180, "width": 180, "height": 52},
                        "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                        "coordinate_space": "parent",
                        "children_coordinate_space": "parent",
                        "children": [
                            {
                                "id": "contact-submit-bg",
                                "kind": "asset",
                                "asset": "contact-submit-bg",
                                "bounds": {"x": 0, "y": 0, "width": 180, "height": 52},
                                "layout": {"inferred_strategy": "leaf", "inferred_flow": False},
                                "coordinate_space": "parent",
                            },
                            {
                                "id": "contact-submit-label",
                                "kind": "text",
                                "text": "contact-submit-label",
                                "bounds": {"x": 40, "y": 16, "width": 100, "height": 20},
                                "render_bounds": {"x": 40, "y": 16, "width": 100, "height": 20},
                                "layout": {"inferred_strategy": "text", "inferred_flow": False},
                                "coordinate_space": "parent",
                            },
                        ],
                    },
            ],
        },
    ]
    assert section_payload["texts"] == [
        "contact-title",
        "contact-email-label",
        "contact-submit-label",
    ]
    assert section_payload["assets"] == ["contact-submit-bg"]
    assert section_payload["decorative_assets"] == []


def test_extraction_service_preserves_named_nested_groups_for_accordions() -> None:
    root_node = {
        "id": "1:3",
        "name": "FAQ Section",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 1200},
        "children": [
            {
                "id": "accordion-faq",
                "name": "accordion-single-faq",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 320, "y": 220, "width": 720, "height": 420},
                "children": [
                    {
                        "id": "accordion-item-1",
                        "name": "accordion-item-1-open",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 320, "y": 220, "width": 720, "height": 180},
                        "children": [
                            {
                                "id": "accordion-trigger-1",
                                "name": "accordion-trigger-1",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 320, "y": 220, "width": 720, "height": 60},
                                "children": [
                                    {
                                        "id": "question-1",
                                        "name": "Question 1",
                                        "type": "TEXT",
                                        "visible": True,
                                        "absoluteBoundingBox": {"x": 350, "y": 238, "width": 420, "height": 24},
                                    }
                                ],
                            },
                            {
                                "id": "accordion-panel-1",
                                "name": "accordion-panel-1",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 320, "y": 300, "width": 720, "height": 100},
                                "children": [
                                    {
                                        "id": "answer-1",
                                        "name": "Answer 1",
                                        "type": "TEXT",
                                        "visible": True,
                                        "absoluteBoundingBox": {"x": 350, "y": 318, "width": 500, "height": 52},
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    section = SectionCandidate(
        id="1:3",
        name="FAQ Section",
        role="section",
        node=root_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 1200.0},
    )

    class StubLayoutAnalyzer:
        def identify_sections(self, root: dict[str, Any]) -> list[SectionCandidate]:
            assert root["id"] == "1:3"
            return [section]

    class StubContentExtractor:
        def extract(
            self,
            sections: list[SectionCandidate],
            *,
            image_fill_urls: dict[str, str] | None = None,
            token_payload: dict[str, Any] | None = None,
        ) -> ExtractionResult:
            assert [candidate.id for candidate in sections] == ["1:3"]
            return ExtractionResult(
                texts={
                    "question-1": {
                        "id": "question-1",
                        "name": "Question 1",
                        "value": "Quels services proposez-vous ?",
                        "rawValue": "Quels services proposez-vous ?",
                        "sectionId": "1:3",
                        "bounds": {"x": 350, "y": 238, "width": 420, "height": 24},
                        "styleRuns": [],
                        "tag": "p",
                        "style": {"fontFamily": "Inter", "fontSize": 20},
                    },
                    "answer-1": {
                        "id": "answer-1",
                        "name": "Answer 1",
                        "value": "Nous accompagnons le produit et l'embarque.",
                        "rawValue": "Nous accompagnons le produit et l'embarque.",
                        "sectionId": "1:3",
                        "bounds": {"x": 350, "y": 318, "width": 500, "height": 52},
                        "styleRuns": [],
                        "tag": "p",
                        "style": {"fontFamily": "Inter", "fontSize": 18},
                    },
                },
                assets=[],
                tokens={},
                warnings=[],
            )

    class StubExtractionService(FigmaExtractionService):
        def _collect_raw_payload(self, parsed_url: Any, store: Any, warnings: list[str]) -> dict[str, Any]:
            return {
                "rest_tree": {"document": root_node},
                "image_fill_urls": {},
                "variables": {},
                "warnings": [],
                "source_modes": ["stub"],
            }

    class StubAssetDownloader:
        def materialize_assets(
            self,
            file_key: str,
            assets: list[dict[str, Any]],
            assets_dir: Path,
            *,
            asset_mode: str = "mixed",
        ) -> list[dict[str, Any]]:
            assert file_key == "FILE"
            assert assets_dir.name == "assets"
            assert asset_mode == "mixed"
            return assets

    service = StubExtractionService(
        rest_client=object(),
        mcp_client=object(),
        layout_analyzer=StubLayoutAnalyzer(),
        content_extractor=StubContentExtractor(),
        asset_downloader=StubAssetDownloader(),
    )

    output_dir = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "test-extraction-service-accordion"
    shutil.rmtree(output_dir, ignore_errors=True)

    model = service.extract("https://www.figma.com/design/FILE/FAQ?node-id=1-3", output_dir)
    section_payload = model["sections"][0]

    assert section_payload["children"] == [
            {
                "id": "accordion-faq",
                "name": "accordion-single-faq",
                "kind": "container",
                "role": "accordion",
                "bounds": {"x": 320, "y": 220, "width": 720, "height": 420},
                "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                "coordinate_space": "section",
                "children_coordinate_space": "parent",
                "children": [
                    {
                        "id": "accordion-item-1",
                        "name": "accordion-item-1-open",
                        "kind": "container",
                        "role": "accordion-item",
                        "bounds": {"x": 0, "y": 0, "width": 720, "height": 180},
                        "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                        "coordinate_space": "parent",
                        "children_coordinate_space": "parent",
                        "children": [
                            {
                                "id": "accordion-trigger-1",
                                "name": "accordion-trigger-1",
                                "kind": "container",
                                "role": "accordion-trigger",
                                "bounds": {"x": 0, "y": 0, "width": 720, "height": 60},
                                "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                                "coordinate_space": "parent",
                                "children_coordinate_space": "parent",
                                "children": [
                                    {
                                        "id": "question-1",
                                        "kind": "text",
                                        "text": "question-1",
                                        "bounds": {"x": 30, "y": 18, "width": 420, "height": 24},
                                        "render_bounds": {"x": 30, "y": 18, "width": 420, "height": 24},
                                        "layout": {"inferred_strategy": "text", "inferred_flow": False},
                                        "coordinate_space": "parent",
                                    }
                                ],
                            },
                        {
                            "id": "accordion-panel-1",
                                "name": "accordion-panel-1",
                                "kind": "container",
                                "role": "accordion-panel",
                                "bounds": {"x": 0, "y": 80, "width": 720, "height": 100},
                                "layout": {"inferred_strategy": "absolute", "inferred_flow": False},
                                "coordinate_space": "parent",
                                "children_coordinate_space": "parent",
                                "children": [
                                    {
                                        "id": "answer-1",
                                        "kind": "text",
                                        "text": "answer-1",
                                        "bounds": {"x": 30, "y": 18, "width": 500, "height": 52},
                                        "render_bounds": {"x": 30, "y": 18, "width": 500, "height": 52},
                                        "layout": {"inferred_strategy": "text", "inferred_flow": False},
                                        "coordinate_space": "parent",
                                    }
                                ],
                            },
                    ],
                }
            ],
        }
    ]
    assert section_payload["texts"] == ["question-1", "answer-1"]
    assert section_payload["assets"] == []
    assert section_payload["decorative_assets"] == []


def test_extraction_service_preserves_image_only_named_carousel_groups() -> None:
    root_node = {
        "id": "1:4",
        "name": "Carousel Section",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
        "children": [
            {
                "id": "carousel-gallery",
                "name": "carousel-gallery",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 420},
                "children": [
                    {
                        "id": "carousel-stage-gallery",
                        "name": "carousel-stage-gallery",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                        "children": [
                            {
                                "id": "carousel-slide-1-active",
                                "name": "carousel-slide-1-active",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                                "children": [
                                    {
                                        "id": "slide-image-1",
                                        "name": "image-slide-1",
                                        "type": "RECTANGLE",
                                        "visible": True,
                                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "slide-1-ref"}],
                                        "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                                    }
                                ],
                            },
                            {
                                "id": "carousel-slide-2",
                                "name": "carousel-slide-2",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                                "children": [
                                    {
                                        "id": "slide-image-2",
                                        "name": "image-slide-2",
                                        "type": "RECTANGLE",
                                        "visible": True,
                                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "slide-2-ref"}],
                                        "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                                    }
                                ],
                            },
                            {
                                "id": "carousel-slide-3",
                                "name": "carousel-slide-3",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                                "children": [
                                    {
                                        "id": "slide-image-3",
                                        "name": "image-slide-3",
                                        "type": "RECTANGLE",
                                        "visible": True,
                                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "slide-3-ref"}],
                                        "absoluteBoundingBox": {"x": 240, "y": 120, "width": 720, "height": 300},
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "id": "carousel-thumbs-gallery",
                        "name": "carousel-thumbs-gallery",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 240, "y": 450, "width": 720, "height": 90},
                        "children": [
                            {
                                "id": "carousel-thumb-1",
                                "name": "carousel-thumb-1",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 240, "y": 450, "width": 160, "height": 90},
                                "children": [
                                    {
                                        "id": "thumb-image-1",
                                        "name": "image-thumb-1",
                                        "type": "RECTANGLE",
                                        "visible": True,
                                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "thumb-1-ref"}],
                                        "absoluteBoundingBox": {"x": 240, "y": 450, "width": 160, "height": 90},
                                    }
                                ],
                            },
                            {
                                "id": "carousel-thumb-2",
                                "name": "carousel-thumb-2",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 420, "y": 450, "width": 160, "height": 90},
                                "children": [
                                    {
                                        "id": "thumb-image-2",
                                        "name": "image-thumb-2",
                                        "type": "RECTANGLE",
                                        "visible": True,
                                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "thumb-2-ref"}],
                                        "absoluteBoundingBox": {"x": 420, "y": 450, "width": 160, "height": 90},
                                    }
                                ],
                            },
                            {
                                "id": "carousel-thumb-3",
                                "name": "carousel-thumb-3",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": 600, "y": 450, "width": 160, "height": 90},
                                "children": [
                                    {
                                        "id": "thumb-image-3",
                                        "name": "image-thumb-3",
                                        "type": "RECTANGLE",
                                        "visible": True,
                                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "thumb-3-ref"}],
                                        "absoluteBoundingBox": {"x": 600, "y": 450, "width": 160, "height": 90},
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }
    section = SectionCandidate(
        id="1:4",
        name="Carousel Section",
        role="section",
        node=root_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 900.0},
    )

    class StubLayoutAnalyzer:
        def identify_sections(self, root: dict[str, Any]) -> list[SectionCandidate]:
            assert root["id"] == "1:4"
            return [section]

    class StubExtractionService(FigmaExtractionService):
        def _collect_raw_payload(self, parsed_url: Any, store: Any, warnings: list[str]) -> dict[str, Any]:
            return {
                "rest_tree": {"document": root_node},
                "image_fill_urls": {
                    "slide-1-ref": "https://example.test/slide-1.png",
                    "slide-2-ref": "https://example.test/slide-2.png",
                    "slide-3-ref": "https://example.test/slide-3.png",
                    "thumb-1-ref": "https://example.test/thumb-1.png",
                    "thumb-2-ref": "https://example.test/thumb-2.png",
                    "thumb-3-ref": "https://example.test/thumb-3.png",
                },
                "variables": {},
                "warnings": [],
                "source_modes": ["stub"],
            }

    class StubAssetDownloader:
        def materialize_assets(
            self,
            file_key: str,
            assets: list[dict[str, Any]],
            assets_dir: Path,
            *,
            asset_mode: str = "mixed",
        ) -> list[dict[str, Any]]:
            assert file_key == "FILE"
            assert assets_dir.name == "assets"
            assert asset_mode == "mixed"
            return assets

    service = StubExtractionService(
        rest_client=object(),
        mcp_client=object(),
        layout_analyzer=StubLayoutAnalyzer(),
        asset_downloader=StubAssetDownloader(),
    )

    output_dir = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "test-extraction-service-carousel"
    shutil.rmtree(output_dir, ignore_errors=True)

    model = service.extract("https://www.figma.com/design/FILE/Carousel?node-id=1-4", output_dir)
    section_payload = model["sections"][0]

    assert section_payload["children"][0]["id"] == "carousel-gallery"
    assert section_payload["children"][0]["role"] == "carousel"
    assert section_payload["children"][0]["children"][0]["role"] == "carousel-stage"
    assert section_payload["children"][0]["children"][1]["role"] == "carousel-nav"
    assert section_payload["children"][0]["children"][0]["children"][0]["role"] == "carousel-slide"
    assert section_payload["children"][0]["children"][1]["children"][0]["role"] == "carousel-thumb"
    assert model["assets"][0]["nodeId"] == "slide-image-1"
    assert all(asset["nodeId"] not in {"1:4", "carousel-gallery"} for asset in model["assets"])
