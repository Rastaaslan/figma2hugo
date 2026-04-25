from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.content_extractor import ContentExtractor
from figma2hugo.layout_analyzer.analyzer import SectionCandidate


def test_extract_captures_masked_groups_as_composite_assets() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "hero-image",
                "name": "hero-image",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": 700, "y": 80, "width": 500, "height": 400},
                "children": [
                    {
                        "id": "mask-shape",
                        "name": "mask-shape",
                        "type": "VECTOR",
                        "visible": True,
                        "isMask": True,
                        "absoluteBoundingBox": {"x": 700, "y": 80, "width": 500, "height": 400},
                    },
                    {
                        "id": "hero-photo",
                        "name": "hero-photo",
                        "type": "VECTOR",
                        "visible": True,
                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "hero-ref"}],
                        "absoluteBoundingBox": {"x": 700, "y": 80, "width": 500, "height": 400},
                    },
                ],
            }
        ],
    }
    section = SectionCandidate(
        id="hero",
        name="Hero",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["hero-image"]
    assert result.assets[0]["format"] == "png"
    assert result.assets[0]["renderMode"] == "composite"


def test_extract_detects_image_refs_from_fill_override_table() -> None:
    section_node = {
        "id": "contact",
        "name": "Contact",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "masked-photo-shape",
                "name": "profile-photo-shape",
                "type": "VECTOR",
                "visible": True,
                "fillOverrideTable": {
                    "1": {
                        "fills": [
                            {"type": "IMAGE", "visible": True, "imageRef": "portrait-ref"},
                        ]
                    }
                },
                "absoluteBoundingBox": {"x": 100, "y": 120, "width": 320, "height": 440},
            }
        ],
    }
    section = SectionCandidate(
        id="contact",
        name="Contact",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["masked-photo-shape"]
    assert result.assets[0]["imageRef"] == "portrait-ref"
    assert result.assets[0]["isVector"] is False


def test_extract_classifies_foreground_assets_explicitly() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "hero-foreground",
                "name": "foreground-overlay",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1200, "height": 700},
            }
        ],
    }
    section = SectionCandidate(
        id="hero",
        name="Hero",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["hero-foreground"]
    assert result.assets[0]["function"] == "foreground"


def test_extract_uses_structural_background_heuristics_for_large_non_vector_assets() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "ambient-panel",
                "name": "ambient-panel",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "IMAGE", "visible": True, "imageRef": "ambient-ref"}],
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 420},
            }
        ],
    }
    section = SectionCandidate(
        id="hero",
        name="Hero",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.assets[0]["function"] == "background"


def test_extract_uses_structural_icon_heuristics_for_small_vector_assets() -> None:
    section_node = {
        "id": "features",
        "name": "Features",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "brand-mark",
                "name": "brand-mark",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 64, "y": 64, "width": 48, "height": 48},
            }
        ],
    }
    section = SectionCandidate(
        id="features",
        name="Features",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.assets[0]["function"] == "icon"


def test_extract_does_not_treat_debug_names_as_backgrounds() -> None:
    section_node = {
        "id": "tools",
        "name": "Tools",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "debug-panel",
                "name": "debug-panel",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 120, "width": 320, "height": 180},
            }
        ],
    }
    section = SectionCandidate(
        id="tools",
        name="Tools",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.assets[0]["function"] != "background"


def test_extract_warns_on_unsupported_visible_leaf_types() -> None:
    section_node = {
        "id": "misc",
        "name": "Misc",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "shape-with-text",
                "name": "shape-with-text",
                "type": "SHAPE_WITH_TEXT",
                "visible": True,
                "absoluteBoundingBox": {"x": 40, "y": 40, "width": 120, "height": 60},
            }
        ],
    }
    section = SectionCandidate(
        id="misc",
        name="Misc",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert any("SHAPE_WITH_TEXT" in warning for warning in result.warnings)
