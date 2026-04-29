from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.model import (
    AssetRef,
    Bounds,
    GenerationReport,
    IntermediateDocument,
    LayoutMetadata,
    PageNode,
    SectionNode,
    TextNode,
    TextStyleRun,
)


def test_intermediate_document_serializes_with_aliases() -> None:
    document = IntermediateDocument(
        page=PageNode(
            id="3:964",
            name="Landing Page",
            width=1920,
            height=7422,
            layout=LayoutMetadata(layout_mode="VERTICAL", item_spacing=48, inferred_strategy="flow"),
            meta={"figmaUrl": "https://www.figma.com/design/FILE/Page?node-id=3-964"},
        ),
        sections=[
            SectionNode(
                id="section-hero",
                name="Hero",
                bounds=Bounds(x=0, y=0, width=1920, height=900),
                layout=LayoutMetadata(layout_mode="VERTICAL", inferred_strategy="flow"),
                texts=["text-1"],
                assets=["asset-1"],
            )
        ],
        texts={
            "text-1": TextNode(
                id="text-1",
                value="Hello world",
                section_id="section-hero",
                style_runs=[TextStyleRun(start=0, end=5, style={"fontFamily": "Inter", "fontSize": 16})],
                layout=LayoutMetadata(text_auto_resize="HEIGHT", inferred_strategy="text"),
            )
        },
        assets=[
            AssetRef(
                node_id="asset-1",
                source_url="https://example.com/hero.svg",
                format="svg",
                local_path="images/hero.svg",
                layout=LayoutMetadata(layout_sizing_horizontal="FILL", inferred_strategy="leaf"),
            )
        ],
        warnings=["placeholder"],
    )

    payload = document.model_dump(by_alias=True, mode="json")

    assert payload["page"]["meta"]["figmaUrl"].endswith("3-964")
    assert payload["page"]["layout"]["layoutMode"] == "VERTICAL"
    assert payload["page"]["layout"]["itemSpacing"] == 48.0
    assert payload["assets"][0]["nodeId"] == "asset-1"
    assert payload["assets"][0]["layout"]["layoutSizingHorizontal"] == "FILL"
    assert payload["texts"]["text-1"]["styleRuns"][0]["style"]["fontFamily"] == "Inter"
    assert payload["texts"]["text-1"]["layout"]["textAutoResize"] == "HEIGHT"


def test_text_style_run_rejects_invalid_offsets() -> None:
    with pytest.raises(ValidationError, match="greater than start"):
        TextStyleRun(start=4, end=4)


def test_generation_report_accepts_camel_case_payload() -> None:
    report = GenerationReport.model_validate(
        {
            "buildOk": True,
            "visualScore": 0.91,
            "missingAssets": [],
            "missingTexts": [],
            "warnings": ["none"],
        }
    )

    assert report.build_ok is True
    assert report.visual_score == 0.91


def test_intermediate_document_accepts_service_payload_shape() -> None:
    payload = {
            "page": {
                "id": "3:964",
                "name": "Landing Page",
                "width": 1920,
                "height": 7422,
                "layout": {"layoutMode": "VERTICAL", "itemSpacing": 32, "inferredStrategy": "flow"},
                "meta": {
                    "figmaUrl": "https://www.figma.com/design/FILE/Page?node-id=3-964",
                    "fileKey": "FILE",
                },
            },
        "sections": [
            {
                "id": "section-1",
                "name": "Hero",
                "role": "header",
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 900},
                "children": ["text-1"],
                "texts": ["text-1"],
                "assets": ["asset-1"],
                "layout": {"layoutMode": "VERTICAL", "inferredStrategy": "flow"},
                "decorative_assets": [],
            }
        ],
        "texts": {
            "text-1": {
                "id": "text-1",
                "name": "Headline",
                "value": "Hello world",
                "rawValue": "Hello world",
                "sectionId": "section-1",
                "bounds": {"x": 0, "y": 0, "width": 320, "height": 48},
                "styleRuns": [{"start": 0, "end": 5, "style": {"fontFamily": "Inter"}}],
                "tag": "h1",
                "style": {"fontFamily": "Inter", "fontSize": 48},
                "layout": {"textAutoResize": "HEIGHT", "inferredStrategy": "text"},
            }
        },
        "assets": [
            {
                "nodeId": "asset-1",
                "sectionId": "section-1",
                "name": "Hero Illustration",
                "format": "svg",
                "sourceUrl": "https://example.com/hero.svg",
                "localPath": "images/hero.svg",
                "function": "content",
                "bounds": {"x": 0, "y": 0, "width": 640, "height": 480},
                "isVector": True,
                "imageRef": None,
                "layout": {"layoutSizingHorizontal": "FILL", "inferredStrategy": "leaf"},
            }
        ],
        "tokens": {
            "colors": {"brand-primary": "#000000"},
            "spacing": {},
            "typography": {},
            "shadows": {},
            "radii": {},
        },
        "warnings": [],
    }

    document = IntermediateDocument.model_validate(payload)

    assert document.page.meta["fileKey"] == "FILE"
    assert document.page.layout.layout_mode == "VERTICAL"
    assert document.sections[0].decorative_assets == []
    assert document.sections[0].layout.inferred_strategy == "flow"
    assert document.texts["text-1"].layout.text_auto_resize == "HEIGHT"
    assert document.assets[0].function.value == "content"
    assert document.assets[0].layout.layout_sizing_horizontal == "FILL"


def test_intermediate_document_accepts_nested_children_payloads() -> None:
    payload = {
        "page": {
            "id": "3:964",
            "name": "Landing Page",
            "width": 1920,
            "height": 7422,
            "meta": {},
        },
        "sections": [
            {
                "id": "section-1",
                "name": "Contact",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 900},
                "children": [
                    {
                        "id": "formulaire-contact",
                        "name": "formulaire-contact",
                        "kind": "container",
                        "role": "form",
                        "bounds": {"x": 320, "y": 420, "width": 520, "height": 240},
                        "coordinate_space": "section",
                        "children_coordinate_space": "section",
                        "children": [
                            {
                                "id": "button-envoyer",
                                "name": "button-envoyer",
                                "kind": "container",
                                "role": "button",
                                "bounds": {"x": 560, "y": 580, "width": 180, "height": 52},
                                "coordinate_space": "section",
                                "children_coordinate_space": "section",
                                "children": ["submit-label"],
                            }
                        ],
                    }
                ],
                "texts": ["submit-label"],
                "assets": [],
                "decorative_assets": [],
            }
        ],
        "texts": {
            "submit-label": {
                "id": "submit-label",
                "name": "Submit Label",
                "value": "Envoyer",
                "rawValue": "Envoyer",
                "sectionId": "section-1",
                "bounds": {"x": 600, "y": 596, "width": 100, "height": 20},
                "styleRuns": [],
                "tag": "p",
                "style": {"fontFamily": "Inter", "fontSize": 16},
            }
        },
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    document = IntermediateDocument.model_validate(payload)
    nested_form = document.sections[0].children[0]
    nested_button = nested_form["children"][0]

    assert nested_form["role"] == "form"
    assert nested_button["role"] == "button"
    assert nested_button["children"] == ["submit-label"]


def test_intermediate_document_accepts_fractional_page_dimensions() -> None:
    document = IntermediateDocument.model_validate(
        {
            "page": {
                "id": "3:964",
                "name": "Landing Page",
                "width": 1920.0,
                "height": 7422.64013671875,
                "meta": {},
            },
            "sections": [],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }
    )

    assert document.page.width == 1920.0
    assert document.page.height == 7422.64013671875


def test_intermediate_document_accepts_foreground_assets() -> None:
    document = IntermediateDocument.model_validate(
        {
            "page": {
                "id": "3:964",
                "name": "Landing Page",
                "width": 1920.0,
                "height": 7422.64013671875,
                "meta": {},
            },
            "sections": [],
            "texts": {},
            "assets": [
                {
                    "nodeId": "page-fg-overlay",
                    "name": "Page FG Overlay",
                    "function": "foreground",
                    "format": "svg",
                    "localPath": "images/page-fg-overlay.svg",
                }
            ],
            "tokens": {},
            "warnings": [],
        }
    )

    assert document.assets[0].function.value == "foreground"
