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


def test_extract_emits_layout_metadata_for_texts_and_assets() -> None:
    section_node = {
        "id": "cards",
        "name": "Cards",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "itemSpacing": 24,
        "paddingTop": 32,
        "paddingRight": 40,
        "paddingBottom": 32,
        "paddingLeft": 40,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 960, "height": 640},
        "children": [
            {
                "id": "cards-title",
                "name": "Cards Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Responsive cards",
                "textAutoResize": "HEIGHT",
                "layoutSizingHorizontal": "FILL",
                "constraints": {"horizontal": "STRETCH", "vertical": "TOP"},
                "style": {"fontFamily": "Inter", "fontSize": 32},
                "absoluteBoundingBox": {"x": 40, "y": 32, "width": 420, "height": 48},
            },
            {
                "id": "cards-image",
                "name": "cards-image",
                "type": "RECTANGLE",
                "visible": True,
                "layoutSizingHorizontal": "FILL",
                "layoutSizingVertical": "FIXED",
                "constraints": {"horizontal": "STRETCH", "vertical": "TOP"},
                "fills": [{"type": "IMAGE", "visible": True, "imageRef": "cards-image-ref"}],
                "absoluteBoundingBox": {"x": 40, "y": 120, "width": 880, "height": 320},
            },
        ],
    }
    section = SectionCandidate(
        id="cards",
        name="Cards",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 960.0, "height": 640.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={"cards-image-ref": "https://example.com/card.png"})

    assert result.texts["cards-title"]["layout"]["text_auto_resize"] == "HEIGHT"
    assert result.texts["cards-title"]["layout"]["layout_sizing_horizontal"] == "FILL"
    assert result.texts["cards-title"]["layout"]["constraints"]["horizontal"] == "STRETCH"
    assert result.texts["cards-title"]["layout"]["inferred_strategy"] == "text"
    assert result.assets[0]["layout"]["layout_sizing_horizontal"] == "FILL"
    assert result.assets[0]["layout"]["layout_sizing_vertical"] == "FIXED"
    assert result.assets[0]["layout"]["constraints"]["horizontal"] == "STRETCH"
    assert result.assets[0]["layout"]["inferred_strategy"] == "leaf"


def test_extract_captures_textless_section_root_with_masks_as_composite_asset() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1240, "height": 587},
        "children": [
            {
                "id": "hero-bg",
                "name": "hero-bg",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "SOLID", "visible": True, "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1240, "height": 587},
            },
            {
                "id": "hero-photo",
                "name": "hero-photo",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "IMAGE", "visible": True, "imageRef": "hero-ref"}],
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1240, "height": 587},
            },
            {
                "id": "hero-mask",
                "name": "hero-mask",
                "type": "VECTOR",
                "visible": True,
                "isMask": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1240, "height": 587},
            },
        ],
    }
    section = SectionCandidate(
        id="hero",
        name="Hero",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1240.0, "height": 587.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["hero"]
    assert result.assets[0]["renderMode"] == "composite"


def test_extract_collapses_complex_vector_only_groups_into_composite_assets() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "hero-decor",
                "name": "Hero Decor",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 80, "width": 320, "height": 180},
                "children": [
                    {
                        "id": f"vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 120 + (index * 12), "y": 80, "width": 24, "height": 24},
                    }
                    for index in range(6)
                ],
            },
            {
                "id": "hero-title",
                "name": "Hero Title",
                "type": "TEXT",
                "visible": True,
                "characters": "Hello",
                "style": {"fontFamily": "Inter", "fontSize": 32},
                "absoluteBoundingBox": {"x": 560, "y": 120, "width": 200, "height": 48},
            },
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

    assert [asset["nodeId"] for asset in result.assets] == ["hero-decor"]
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["format"] == "svg"
    assert result.assets[0]["isVector"] is True


def test_extract_collapses_textless_vector_only_section_roots_into_composite_assets() -> None:
    section_node = {
        "id": "decor",
        "name": "Decor",
        "type": "GROUP",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 640, "height": 220},
        "children": [
            {
                "id": f"decor-vector-{index}",
                "name": f"Decor Vector {index}",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": index * 32, "y": 0, "width": 28, "height": 28},
            }
            for index in range(7)
        ],
    }
    section = SectionCandidate(
        id="decor",
        name="Decor",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 640.0, "height": 220.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["decor"]
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["format"] == "svg"
    assert result.assets[0]["isVector"] is True


def test_extract_preserves_editable_svg_subtrees_inside_masked_section_roots() -> None:
    section_node = {
        "id": "showcase",
        "name": "visual-showcase",
        "type": "GROUP",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1600, "height": 900},
        "children": [
            {
                "id": "primary-graphic-cluster",
                "name": "primary-graphic-cluster",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1200, "height": 720},
                "children": [
                    {
                        "id": f"main-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 20 + (index * 24), "y": 40, "width": 60, "height": 60},
                    }
                    for index in range(8)
                ],
            },
            {
                "id": "hero-image",
                "name": "Hero",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 940, "y": 80, "width": 520, "height": 540},
                "children": [
                    {
                        "id": "hero-mask",
                        "name": "hero-mask",
                        "type": "VECTOR",
                        "visible": True,
                        "isMask": True,
                        "absoluteBoundingBox": {"x": 940, "y": 80, "width": 520, "height": 540},
                    },
                    {
                        "id": "hero-photo",
                        "name": "hero-photo",
                        "type": "RECTANGLE",
                        "visible": True,
                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "hero-ref"}],
                        "absoluteBoundingBox": {"x": 940, "y": 80, "width": 520, "height": 540},
                    },
                ],
            },
            {
                "id": "overlay-cluster",
                "name": "overlay-cluster",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 1080, "y": 0, "width": 360, "height": 260},
                "children": [
                    {
                        "id": f"overlay-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {
                            "x": 1100 + (index * 16),
                            "y": 20 + (index * 6),
                            "width": 40,
                            "height": 40,
                        },
                    }
                    for index in range(6)
                ],
            },
        ],
    }
    section = SectionCandidate(
        id="showcase",
        name="visual-showcase",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1600.0, "height": 900.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == [
        "primary-graphic-cluster",
        "hero-image",
        "overlay-cluster",
    ]
    assert result.assets[0]["format"] == "svg"
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["isVector"] is True
    assert result.assets[0]["function"] == "content"
    assert result.assets[1]["format"] == "png"
    assert result.assets[1]["renderMode"] == "composite"
    assert result.assets[2]["format"] == "svg"
    assert result.assets[2]["renderMode"] == "composite"
    assert result.assets[2]["isVector"] is True
    assert result.assets[2]["function"] == "content"


def test_extract_collapses_imported_image_wrapper_groups_into_composite_assets() -> None:
    section_node = {
        "id": "gallery",
        "name": "Gallery",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "imported-photo",
                "name": "ImportedPhoto.tif",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 80, "width": 220, "height": 200},
                "children": [
                    {
                        "id": "layer-0",
                        "name": "Layer 0",
                        "type": "RECTANGLE",
                        "visible": True,
                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "imported-ref"}],
                        "absoluteBoundingBox": {"x": 120, "y": 80, "width": 220, "height": 200},
                    }
                ],
            }
        ],
    }
    section = SectionCandidate(
        id="gallery",
        name="Gallery",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["imported-photo"]
    assert result.assets[0]["renderMode"] == "composite"


def test_extract_promotes_solid_fill_rectangles_to_shape_assets() -> None:
    section_node = {
        "id": "cta",
        "name": "CTA",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 960, "height": 320},
        "children": [
            {
                "id": "button-bg",
                "name": "Rectangle 2",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "SOLID", "visible": True, "color": {"r": 0.15, "g": 0.64, "b": 0.75, "a": 1}}],
                "absoluteBoundingBox": {"x": 120, "y": 220, "width": 180, "height": 45},
            }
        ],
    }
    section = SectionCandidate(
        id="cta",
        name="CTA",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 960.0, "height": 320.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["button-bg"]
    assert result.assets[0]["format"] == "shape"
    assert result.assets[0]["renderMode"] == "shape"
    assert result.assets[0]["style"]["background"] == "rgb(38 163 191)"


def test_extract_preserves_text_render_bounds_when_available() -> None:
    section_node = {
        "id": "breaker",
        "name": "breaker",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 100, "y": 200, "width": 960, "height": 480},
        "children": [
            {
                "id": "copy",
                "name": "Copy",
                "type": "TEXT",
                "visible": True,
                "characters": "Paragraph copy",
                "absoluteBoundingBox": {"x": 120, "y": 240, "width": 300, "height": 160},
                "absoluteRenderBounds": {"x": 123, "y": 244, "width": 294, "height": 96},
                "style": {"fontFamily": "Roboto", "fontSize": 16, "lineHeightPx": 30},
            }
        ],
    }
    section = SectionCandidate(
        id="breaker",
        name="breaker",
        role="section",
        node=section_node,
        bounds={"x": 100.0, "y": 200.0, "width": 960.0, "height": 480.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    text = result.texts["copy"]
    assert text["bounds"] == {"x": 20.0, "y": 40.0, "width": 300.0, "height": 160.0}
    assert text["renderBounds"] == {"x": 23.0, "y": 44.0, "width": 294.0, "height": 96.0}


def test_extract_treats_composite_mask_groups_as_renderable_content() -> None:
    section_node = {
        "id": "showcase",
        "name": "Showcase",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
        "children": [
            {
                "id": "masked-product",
                "name": "Mask Group",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 720, "y": 240, "width": 640, "height": 520},
                "children": [
                    {
                        "id": "mask-shape",
                        "name": "Mask",
                        "type": "ELLIPSE",
                        "visible": True,
                        "isMask": True,
                        "absoluteBoundingBox": {"x": 760, "y": 240, "width": 560, "height": 520},
                    },
                    {
                        "id": "product-image",
                        "name": "Product",
                        "type": "RECTANGLE",
                        "visible": True,
                        "fills": [{"type": "IMAGE", "visible": True, "imageRef": "product-ref"}],
                        "absoluteBoundingBox": {"x": 720, "y": 240, "width": 640, "height": 520},
                    },
                ],
            }
        ],
    }
    section = SectionCandidate(
        id="showcase",
        name="Showcase",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 900.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == ["masked-product"]
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["function"] == "content"


def test_extract_classifies_decor_prefix_layers_as_decorative() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "decor-page-accent",
                "name": "decor-page-accent",
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

    assert [asset["nodeId"] for asset in result.assets] == ["decor-page-accent"]
    assert result.assets[0]["function"] == "decorative"


def test_extract_classifies_foreground_prefix_layers() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "fg-page-accent",
                "name": "fg-page-accent",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1200, "height": 700},
            },
            {
                "id": "foreground-page-accent",
                "name": "foreground-page-accent",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 24, "y": 24, "width": 1180, "height": 680},
            },
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

    assert [asset["nodeId"] for asset in result.assets] == ["fg-page-accent", "foreground-page-accent"]
    assert all(asset["function"] == "foreground" for asset in result.assets)


def test_extract_classifies_background_prefix_layers() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "bg-page-panel",
                "name": "bg-page-panel",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 120, "width": 320, "height": 180},
            },
            {
                "id": "background-page-panel",
                "name": "background-page-panel",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 160, "y": 160, "width": 280, "height": 140},
            },
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

    assert [asset["nodeId"] for asset in result.assets] == ["bg-page-panel", "background-page-panel"]
    assert all(asset["function"] == "background" for asset in result.assets)


def test_extract_classifies_icon_prefix_layers() -> None:
    section_node = {
        "id": "features",
        "name": "Features",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "icon-badge-mark",
                "name": "icon-badge-mark",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 120, "width": 180, "height": 180},
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

    assert [asset["nodeId"] for asset in result.assets] == ["icon-badge-mark"]
    assert result.assets[0]["function"] == "icon"


def test_extract_keeps_foreground_named_editable_groups_as_svg_assets() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "fg-page-cluster",
                "name": "fg-page-cluster",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 880, "y": 40, "width": 420, "height": 360},
                "children": [
                    {
                        "id": f"foreground-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {
                            "x": 900 + (index * 24),
                            "y": 70 + (index * 8),
                            "width": 56,
                            "height": 56,
                        },
                    }
                    for index in range(8)
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

    assert [asset["nodeId"] for asset in result.assets] == ["fg-page-cluster"]
    assert result.assets[0]["function"] == "foreground"
    assert result.assets[0]["format"] == "svg"
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["isVector"] is True


def test_extract_keeps_background_named_editable_groups_as_svg_assets() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "bg-page-cluster",
                "name": "bg-page-cluster",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 40, "y": 48, "width": 540, "height": 360},
                "children": [
                    {
                        "id": f"background-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {
                            "x": 60 + (index * 28),
                            "y": 72 + (index * 10),
                            "width": 72,
                            "height": 72,
                        },
                    }
                    for index in range(8)
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

    assert [asset["nodeId"] for asset in result.assets] == ["bg-page-cluster"]
    assert result.assets[0]["function"] == "background"
    assert result.assets[0]["format"] == "svg"
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["isVector"] is True


def test_extract_keeps_large_graphic_clusters_as_editable_svg_assets() -> None:
    section_node = {
        "id": "hero",
        "name": "Hero",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "graphic-cluster-left",
                "name": "graphic-cluster-left",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 80, "width": 320, "height": 220},
                "children": [
                    {
                        "id": f"shape-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 120 + (index * 12), "y": 80, "width": 40, "height": 40},
                    }
                    for index in range(14)
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

    assert [asset["nodeId"] for asset in result.assets] == ["graphic-cluster-left"]
    assert result.assets[0]["format"] == "svg"
    assert result.assets[0]["renderMode"] == "composite"
    assert result.assets[0]["isVector"] is True
    assert result.assets[0]["function"] == "content"


def test_extract_keeps_small_graphic_cluster_groups_as_editable_svg_assets() -> None:
    section_node = {
        "id": "breaker",
        "name": "Breaker",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "accent-cluster-alpha",
                "name": "Accent Cluster Alpha",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 420, "width": 260, "height": 300},
                "children": [
                    {
                        "id": f"accent-alpha-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {
                            "x": 12 + (index * 16),
                            "y": 452 + (index * 12),
                            "width": 64,
                            "height": 64,
                        },
                    }
                    for index in range(6)
                ],
            },
            {
                "id": "accent-cluster-beta",
                "name": "Accent Cluster Beta",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 1120, "y": 40, "width": 280, "height": 340},
                "children": [
                    {
                        "id": f"accent-beta-vector-{index}",
                        "name": f"Vector {index}",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {
                            "x": 1140 + (index * 18),
                            "y": 72 + (index * 10),
                            "width": 72,
                            "height": 72,
                        },
                    }
                    for index in range(6)
                ],
            },
        ],
    }
    section = SectionCandidate(
        id="breaker",
        name="Breaker",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert [asset["nodeId"] for asset in result.assets] == [
        "accent-cluster-alpha",
        "accent-cluster-beta",
    ]
    assert all(asset["function"] == "content" for asset in result.assets)
    assert all(asset["format"] == "svg" for asset in result.assets)
    assert all(asset["renderMode"] == "composite" for asset in result.assets)
    assert all(asset["isVector"] is True for asset in result.assets)


def test_extract_keeps_unnamed_large_image_panels_as_content() -> None:
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

    assert result.assets[0]["function"] == "content"


def test_extract_does_not_promote_partial_width_image_panels_to_backgrounds() -> None:
    section_node = {
        "id": "cta-corner",
        "name": "cta-corner",
        "type": "GROUP",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1039, "height": 520},
        "children": [
            {
                "id": "cta-photo",
                "name": "Rectangle 6",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [
                    {"type": "SOLID", "visible": True, "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
                    {"type": "IMAGE", "visible": True, "imageRef": "cta-photo-ref"},
                ],
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 450, "height": 500},
            }
        ],
    }
    section = SectionCandidate(
        id="cta-corner",
        name="cta-corner",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1039.0, "height": 520.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.assets[0]["function"] == "content"


def test_extract_keeps_unnamed_small_vector_assets_as_content() -> None:
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

    assert result.assets[0]["function"] == "content"


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


def test_extract_uses_paragraph_tag_for_multiline_copy_blocks_even_with_large_font() -> None:
    section_node = {
        "id": "content",
        "name": "Content",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "copy-block",
                "name": "Body Text",
                "type": "TEXT",
                "visible": True,
                "characters": (
                    "Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n"
                    "Aenean commodo ligula eget dolor. Aenean massa.\n"
                    "Cum sociis natoque penatibus et magnis dis parturient montes."
                ),
                "style": {"fontFamily": "Inter", "fontSize": 30, "lineHeightPx": 38},
                "absoluteBoundingBox": {"x": 80, "y": 120, "width": 620, "height": 180},
            }
        ],
    }
    section = SectionCandidate(
        id="content",
        name="Content",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.texts["copy-block"]["tag"] == "p"


def test_extract_detects_multiline_bullet_lists_as_unordered_lists() -> None:
    section_node = {
        "id": "services",
        "name": "Services",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "services-list",
                "name": "Services List",
                "type": "TEXT",
                "visible": True,
                "characters": "• Audit UX detaille\n• Prototype rapide",
                "style": {"fontFamily": "Inter", "fontSize": 20, "fontWeight": 400},
                "absoluteBoundingBox": {"x": 120, "y": 140, "width": 420, "height": 120},
            }
        ],
    }
    section = SectionCandidate(
        id="services",
        name="Services",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.texts["services-list"]["tag"] == "ul"
    assert result.texts["services-list"]["role"] == "list"
    assert result.texts["services-list"]["value"] == "• Audit UX detaille\n• Prototype rapide"


def test_extract_keeps_bullet_lines_as_distinct_texts() -> None:
    section_node = {
        "id": "roadmap",
        "name": "Roadmap",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "bullet-1",
                "name": "Bullet 1",
                "type": "TEXT",
                "visible": True,
                "characters": "- premiere etape tres importante",
                "style": {"fontFamily": "Inter", "fontSize": 18, "fontWeight": 400},
                "absoluteBoundingBox": {"x": 120, "y": 160, "width": 420, "height": 28},
            },
            {
                "id": "bullet-2",
                "name": "Bullet 2",
                "type": "TEXT",
                "visible": True,
                "characters": "- seconde etape tout aussi utile",
                "style": {"fontFamily": "Inter", "fontSize": 18, "fontWeight": 400},
                "absoluteBoundingBox": {"x": 120, "y": 204, "width": 420, "height": 28},
            },
        ],
    }
    section = SectionCandidate(
        id="roadmap",
        name="Roadmap",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert set(result.texts) == {"bullet-1", "bullet-2"}
    assert result.texts["bullet-1"]["value"] == "- premiere etape tres importante"
    assert result.texts["bullet-2"]["value"] == "- seconde etape tout aussi utile"


def test_extract_retags_split_sentence_lines_as_paragraph_clusters() -> None:
    section_node = {
        "id": "content",
        "name": "Content",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "copy-line-1",
                "name": "Lorem ipsum dolor sit amet, consectetur",
                "type": "TEXT",
                "visible": True,
                "characters": "Lorem ipsum dolor sit amet, consectetur ",
                "style": {"fontFamily": "Inter", "fontSize": 36, "fontWeight": 400, "lineHeightPx": 43.56},
                "absoluteBoundingBox": {"x": 80, "y": 120, "width": 680, "height": 44},
            },
            {
                "id": "copy-line-2",
                "name": "adipiscing elit. Vestibulum quis consequat",
                "type": "TEXT",
                "visible": True,
                "characters": "adipiscing elit. Vestibulum quis consequat ",
                "style": {"fontFamily": "Inter", "fontSize": 36, "fontWeight": 400, "lineHeightPx": 43.56},
                "absoluteBoundingBox": {"x": 80, "y": 164, "width": 704, "height": 44},
            },
            {
                "id": "copy-line-3",
                "name": "lacus, sed tristique augue. Donec efficitur,",
                "type": "TEXT",
                "visible": True,
                "characters": "lacus, sed tristique augue. Donec efficitur, ",
                "style": {"fontFamily": "Inter", "fontSize": 36, "fontWeight": 400, "lineHeightPx": 43.56},
                "absoluteBoundingBox": {"x": 80, "y": 208, "width": 700, "height": 44},
            },
        ],
    }
    section = SectionCandidate(
        id="content",
        name="Content",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert list(result.texts) == ["copy-line-1"]
    assert result.texts["copy-line-1"]["tag"] == "p"
    assert result.texts["copy-line-1"]["role"] == "body"
    assert result.texts["copy-line-1"]["value"] == (
        "Lorem ipsum dolor sit amet, consectetur\n"
        "adipiscing elit. Vestibulum quis consequat\n"
        "lacus, sed tristique augue. Donec efficitur,"
    )
    assert result.texts["copy-line-1"]["bounds"] == {"x": 80.0, "y": 120.0, "width": 704.0, "height": 132.0}


def test_extract_does_not_retag_single_sentence_headings_as_paragraphs() -> None:
    section_node = {
        "id": "content",
        "name": "Content",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "subtitle",
                "name": "Un bureau d'etude au coeur de la vallee de l'arve.",
                "type": "TEXT",
                "visible": True,
                "characters": "Un bureau d'etude au coeur de la vallee de l'arve. ",
                "style": {"fontFamily": "Roboto", "fontSize": 40, "fontWeight": 400, "lineHeightPx": 46.875},
                "absoluteBoundingBox": {"x": 120, "y": 140, "width": 850, "height": 47},
            }
        ],
    }
    section = SectionCandidate(
        id="content",
        name="Content",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.texts["subtitle"]["tag"] == "h2"


def test_extract_respects_explicit_heading_levels_from_naming() -> None:
    section_node = {
        "id": "content",
        "name": "Content",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "service-title",
                "name": "titre-h4-service-cloud",
                "type": "TEXT",
                "visible": True,
                "characters": "Architecture cloud",
                "style": {"fontFamily": "Inter", "fontSize": 22, "fontWeight": 700, "lineHeightPx": 28},
                "absoluteBoundingBox": {"x": 120, "y": 140, "width": 420, "height": 32},
            },
            {
                "id": "faq-title",
                "name": "titre-h5-faq-rgpd",
                "type": "TEXT",
                "visible": True,
                "characters": "Protection des donnees",
                "style": {"fontFamily": "Inter", "fontSize": 18, "fontWeight": 700, "lineHeightPx": 24},
                "absoluteBoundingBox": {"x": 120, "y": 196, "width": 360, "height": 28},
            },
        ],
    }
    section = SectionCandidate(
        id="content",
        name="Content",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert result.texts["service-title"]["tag"] == "h4"
    assert result.texts["service-title"]["role"] == "heading"
    assert result.texts["faq-title"]["tag"] == "h5"
    assert result.texts["faq-title"]["role"] == "heading"


def test_extract_retags_interleaved_paragraph_columns_independently() -> None:
    shared_style = {"fontFamily": "Inter", "fontSize": 36, "fontWeight": 400, "lineHeightPx": 43.56}
    section_node = {
        "id": "content",
        "name": "Content",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "children": [
            {
                "id": "left-1",
                "name": "Lorem ipsum dolor sit amet, consectetur",
                "type": "TEXT",
                "visible": True,
                "characters": "Lorem ipsum dolor sit amet, consectetur ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 120, "y": 100, "width": 680, "height": 44},
            },
            {
                "id": "right-1",
                "name": "Lorem ipsum dolor sit amet, consectetur",
                "type": "TEXT",
                "visible": True,
                "characters": "Lorem ipsum dolor sit amet, consectetur ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 980, "y": 104, "width": 680, "height": 44},
            },
            {
                "id": "left-2",
                "name": "adipiscing elit. Vestibulum quis consequat",
                "type": "TEXT",
                "visible": True,
                "characters": "adipiscing elit. Vestibulum quis consequat ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 120, "y": 144, "width": 704, "height": 44},
            },
            {
                "id": "right-2",
                "name": "adipiscing elit. Vestibulum quis consequat",
                "type": "TEXT",
                "visible": True,
                "characters": "adipiscing elit. Vestibulum quis consequat ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 980, "y": 148, "width": 704, "height": 44},
            },
            {
                "id": "left-3",
                "name": "lacus, sed tristique augue. Donec efficitur,",
                "type": "TEXT",
                "visible": True,
                "characters": "lacus, sed tristique augue. Donec efficitur, ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 120, "y": 188, "width": 700, "height": 44},
            },
            {
                "id": "right-3",
                "name": "lacus, sed tristique augue. Donec efficitur,",
                "type": "TEXT",
                "visible": True,
                "characters": "lacus, sed tristique augue. Donec efficitur, ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 980, "y": 192, "width": 700, "height": 44},
            },
        ],
    }
    section = SectionCandidate(
        id="content",
        name="Content",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1920.0, "height": 1080.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert set(result.texts) == {"left-1", "right-1"}
    assert result.texts["left-1"]["tag"] == "p"
    assert result.texts["right-1"]["tag"] == "p"
    assert result.texts["left-1"]["value"] == (
        "Lorem ipsum dolor sit amet, consectetur\n"
        "adipiscing elit. Vestibulum quis consequat\n"
        "lacus, sed tristique augue. Donec efficitur,"
    )
    assert result.texts["right-1"]["value"] == (
        "Lorem ipsum dolor sit amet, consectetur\n"
        "adipiscing elit. Vestibulum quis consequat\n"
        "lacus, sed tristique augue. Donec efficitur,"
    )


def test_extract_merges_multiline_paragraph_blocks_with_continuation_lines() -> None:
    shared_style = {"fontFamily": "Inter", "fontSize": 36, "fontWeight": 400, "lineHeightPx": 43.56}
    section_node = {
        "id": "content",
        "name": "Content",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 1080},
        "children": [
            {
                "id": "copy-1",
                "name": "Lorem ipsum dolor sit amet, consectetur",
                "type": "TEXT",
                "visible": True,
                "characters": (
                    "Lorem ipsum dolor sit amet, consectetur\n"
                    "adipiscing elit. Vestibulum quis consequat\n"
                    "lacus, sed tristique augue. Donec efficitur,"
                ),
                "style": shared_style,
                "absoluteBoundingBox": {"x": 80, "y": 120, "width": 715, "height": 132},
            },
            {
                "id": "copy-2",
                "name": "sapien vitae cursus dictum, arcu velit feugiat",
                "type": "TEXT",
                "visible": True,
                "characters": "sapien vitae cursus dictum, arcu velit feugiat ",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 80, "y": 252, "width": 758, "height": 44},
            },
            {
                "id": "copy-3",
                "name": "risus, a mollis ipsum sem at libero. Donec",
                "type": "TEXT",
                "visible": True,
                "characters": (
                    "risus, a mollis ipsum sem at libero. Donec\n"
                    "diam nibh, hendrerit sit amet est eu, iaculis"
                ),
                "style": shared_style,
                "absoluteBoundingBox": {"x": 80, "y": 296, "width": 728, "height": 88},
            },
        ],
    }
    section = SectionCandidate(
        id="content",
        name="Content",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 1080.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert list(result.texts) == ["copy-1"]
    assert result.texts["copy-1"]["tag"] == "p"
    assert result.texts["copy-1"]["value"] == (
        "Lorem ipsum dolor sit amet, consectetur\n"
        "adipiscing elit. Vestibulum quis consequat\n"
        "lacus, sed tristique augue. Donec efficitur,\n"
        "sapien vitae cursus dictum, arcu velit feugiat\n"
        "risus, a mollis ipsum sem at libero. Donec\n"
        "diam nibh, hendrerit sit amet est eu, iaculis"
    )
    assert result.texts["copy-1"]["bounds"] == {"x": 80.0, "y": 120.0, "width": 758.0, "height": 264.0}


def test_extract_does_not_merge_href_utility_text_into_card_copy() -> None:
    shared_style = {"fontFamily": "Inter", "fontSize": 38, "fontWeight": 700, "lineHeightPx": 74}
    section_node = {
        "id": "cards",
        "name": "Cards",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "children": [
            {
                "id": "copy-1",
                "name": "texte-projet-1",
                "type": "TEXT",
                "visible": True,
                "characters": "voila ma premiere carte cliquable",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 120, "y": 120, "width": 700, "height": 74},
            },
            {
                "id": "href-1",
                "name": "href-projet-1",
                "type": "TEXT",
                "visible": True,
                "characters": "https://example.com/galerie/bleu",
                "style": shared_style,
                "absoluteBoundingBox": {"x": 120, "y": 194, "width": 700, "height": 74},
            },
        ],
    }
    section = SectionCandidate(
        id="cards",
        name="Cards",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1920.0, "height": 1080.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    assert set(result.texts) == {"copy-1", "href-1"}
    assert result.texts["copy-1"]["value"] == "voila ma premiere carte cliquable"
    assert result.texts["href-1"]["value"] == "https://example.com/galerie/bleu"


def test_extract_pads_truncated_style_override_arrays_for_trailing_default_text() -> None:
    characters = (
        "btw: we’re hirin’\n"
        "and you just look like you’d fit in\n\n"
        "Lorem ipsum dolor sit amet."
    )
    section_node = {
        "id": "footer",
        "name": "Footer",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "job-copy",
                "name": "Job Copy",
                "type": "TEXT",
                "visible": True,
                "characters": characters,
                "characterStyleOverrides": [3] * 18,
                "styleOverrideTable": {
                    "3": {"fontFamily": "Roboto Slab", "fontSize": 25, "fontWeight": 700}
                },
                "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "fontWeight": 300},
                "absoluteBoundingBox": {"x": 64, "y": 64, "width": 480, "height": 240},
            }
        ],
    }
    section = SectionCandidate(
        id="footer",
        name="Footer",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    runs = result.texts["job-copy"]["styleRuns"]
    assert len(runs) == 2
    assert runs[0]["start"] == 0
    assert runs[0]["end"] == 18
    assert runs[1]["start"] == 18
    assert runs[1]["end"] == len(characters)
    assert runs[1]["style"] == {}


def test_extract_normalizes_segment_line_height_overrides() -> None:
    section_node = {
        "id": "breaker",
        "name": "Breaker",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 720},
        "children": [
            {
                "id": "breaker-copy",
                "name": "Breaker Copy",
                "type": "TEXT",
                "visible": True,
                "characters": "First paragraph.\n\nSecond paragraph.\r",
                "characterStyleOverrides": [4] * 18 + [3] * 18,
                "styleOverrideTable": {
                    "4": {
                        "fontFamily": "Roboto",
                        "fontStyle": "Light",
                        "fontWeight": 300,
                        "lineHeightPx": 18.75,
                        "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
                    },
                    "3": {
                        "fontFamily": "Roboto",
                        "fontStyle": "Medium",
                        "fontWeight": 500,
                        "lineHeightPx": 18.75,
                        "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}],
                    },
                },
                "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "lineHeightPx": 30},
                "absoluteBoundingBox": {"x": 64, "y": 64, "width": 394, "height": 278},
                "absoluteRenderBounds": {"x": 68, "y": 68, "width": 388, "height": 164},
            }
        ],
    }
    section = SectionCandidate(
        id="breaker",
        name="Breaker",
        role="section",
        node=section_node,
        bounds={"x": 0.0, "y": 0.0, "width": 1440.0, "height": 720.0},
    )

    result = ContentExtractor().extract([section], image_fill_urls={})

    runs = result.texts["breaker-copy"]["styleRuns"]
    assert runs[0]["style"]["lineHeight"] == 18.75
    assert runs[1]["style"]["lineHeight"] == 18.75
    assert runs[0]["style"]["fontFamily"] == "Roboto"
    assert runs[1]["style"]["fontWeight"] == 500
