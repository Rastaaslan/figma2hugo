from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from figma2hugo.generators import HugoGenerator, StaticGenerator
from figma2hugo.generators._shared import CanonicalModelBuilder
from figma2hugo.generators.css import CssGenerator

try:
    from figma2hugo.model.enums import AssetRole, SectionRole
    from figma2hugo.model.geometry import Bounds
    from figma2hugo.model.intermediate import (
        AssetRef,
        IntermediateDocument,
        PageNode,
        SectionNode,
        TextNode,
        TokenBag,
    )
    MODEL_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local environment
    AssetRole = SectionRole = Bounds = AssetRef = IntermediateDocument = PageNode = SectionNode = TextNode = TokenBag = None
    MODEL_IMPORT_ERROR = exc

HUGO_BIN = shutil.which("hugo")


SAMPLE_MODEL = {
    "page": {
        "id": "3:964",
        "name": "Landing Page",
        "width": 1440,
        "height": 2200,
        "meta": {"source": "figma"},
    },
    "sections": [
        {
            "id": "hero",
            "name": "Hero",
            "role": "hero",
            "bounds": {"x": 0, "y": 0, "width": 1440, "height": 720},
            "children": [
                {
                    "id": "hero-stack",
                    "role": "group",
                    "children": [
                        {
                            "id": "hero-title",
                            "kind": "text",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Build faster\nwith Hugo",
                        },
                        {
                            "id": "hero-copy",
                            "kind": "text",
                            "name": "Hero Copy",
                            "role": "body",
                            "value": "Stable HTML, CSS and JSON output.",
                        },
                        {
                            "id": "hero-image",
                            "kind": "asset",
                            "name": "Hero Illustration",
                            "format": "png",
                            "purpose": "content",
                            "local_path": "images/hero.png",
                            "bounds": {"x": 880, "y": 160, "width": 420, "height": 300},
                        },
                    ],
                }
            ],
            "texts": [
                {
                    "id": "hero-eyebrow",
                    "name": "Hero Eyebrow",
                    "role": "eyebrow",
                    "value": "Maintainable export",
                }
            ],
            "decorative_assets": [
                {
                    "id": "hero-glow",
                    "name": "Hero Glow",
                    "format": "svg",
                    "purpose": "decorative",
                    "local_path": "images/glow.svg",
                }
            ],
        },
        {
            "id": "footer",
            "name": "Footer",
            "role": "footer",
            "bounds": {"x": 0, "y": 1800, "width": 1440, "height": 200},
            "texts": [
                {
                    "id": "footer-copy",
                    "name": "Footer Copy",
                    "role": "body",
                    "value": "All rights reserved.",
                }
            ],
        },
    ],
    "tokens": {
        "colors": {
            "brand": {"value": "#1434cb"},
            "surface": {"value": "#f6f3ee"},
        },
        "spacing": {
            "section": {"value": "96px"},
        },
        "typography": {
            "display": {
                "fontFamily": "Georgia",
                "fontSize": "56px",
                "fontWeight": 700,
                "lineHeight": "1.1",
            }
        },
    },
    "warnings": ["Complex masks rendered as plain assets."],
}


def build_hugo_site(model: dict[str, object], site_dir: Path) -> Path:
    HugoGenerator().generate(model, site_dir)
    public_dir = site_dir / "public"
    subprocess.run(
        [HUGO_BIN, "--source", str(site_dir), "--destination", str(public_dir), "--quiet"],
        check=True,
        capture_output=True,
        text=True,
    )
    return public_dir


class CssGeneratorTests(unittest.TestCase):
    def test_css_generator_emits_root_tokens_and_sections(self) -> None:
        canonical = CanonicalModelBuilder(mode="static").build(SAMPLE_MODEL)
        css = CssGenerator().generate(canonical)

        self.assertIn("--color-brand: #1434cb;", css)
        self.assertIn("--space-section: 96px;", css)
        self.assertIn("/* Section: Hero */", css)
        self.assertIn(".section-hero", css)

    def test_css_generator_emits_absolute_layout_rules(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 720},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Hello",
                            "bounds": {"x": 120, "y": 90, "width": 420, "height": 88},
                            "style": {"fontFamily": "Inter", "fontSize": 64, "fontWeight": 700},
                        }
                    ],
                    "assets": [
                        {
                            "id": "hero-image",
                            "name": "Hero Image",
                            "nodeId": "hero-image",
                            "format": "png",
                            "local_path": "images/hero.png",
                            "bounds": {"x": 760, "y": 110, "width": 320, "height": 240},
                        }
                    ],
                    "decorative_assets": [],
                    "children": ["hero-title", "hero-image"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-hero-title {", css)
        self.assertIn("left: 120.00px;", css)
        self.assertIn("top: 90.00px;", css)
        self.assertIn("position: absolute;", css)

    def test_css_generator_positions_sections_from_global_canvas_bounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1000, "height": 0},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 100, "y": 200, "width": 600, "height": 300},
                    "children": [
                        {
                            "kind": "text",
                            "id": "hero-title",
                            "text": {
                                "id": "hero-title",
                                "name": "Hero Title",
                                "role": "heading",
                                "value": "Hello",
                                "bounds": {"x": 40, "y": 20, "width": 200, "height": 40},
                            },
                        }
                    ],
                },
                {
                    "id": "cta",
                    "name": "CTA",
                    "role": "section",
                    "bounds": {"x": 250, "y": 650, "width": 400, "height": 180},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "cta-image",
                            "asset": {
                                "id": "cta-image",
                                "name": "CTA Image",
                                "nodeId": "cta-image",
                                "purpose": "content",
                                "local_path": "images/cta.png",
                                "bounds": {"x": 0, "y": 0, "width": 120, "height": 120},
                            },
                        }
                    ],
                },
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".page {", css)
        self.assertIn("min-height: 630px;", css)
        self.assertIn(".section-hero {", css)
        self.assertIn("left: 0.00px;", css)
        self.assertIn("top: 0.00px;", css)
        self.assertIn("width: 600px;", css)
        self.assertIn(".section-cta {", css)
        self.assertIn("left: 150.00px;", css)
        self.assertIn("top: 450.00px;", css)
        self.assertIn("width: 400px;", css)
        self.assertIn(".section-cta .page-section__inner {", css)

    def test_builder_sorts_sections_by_vertical_position(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 1200},
            "sections": [
                {
                    "id": "footer",
                    "name": "Footer",
                    "role": "footer",
                    "bounds": {"x": 0, "y": 800, "width": 1440, "height": 200},
                },
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 600},
                },
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)

        self.assertEqual(["hero", "footer"], [section["id"] for section in canonical["sections"]])

    def test_css_generator_keeps_single_line_labels_on_one_line(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 400},
            "sections": [
                {
                    "id": "labels",
                    "name": "Labels",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 400},
                    "texts": [
                        {
                            "id": "ideas-label",
                            "name": "Ideas Label",
                            "role": "label",
                            "value": "Ideas",
                            "bounds": {"x": 120, "y": 80, "width": 224, "height": 24},
                            "style": {"fontFamily": "Inter", "fontSize": 48, "lineHeight": 24},
                        }
                    ],
                    "children": ["ideas-label"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-ideas-label {", css)
        self.assertIn("white-space: nowrap;", css)

    def test_css_generator_expands_centered_single_line_label_to_its_box_height(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 240},
            "sections": [
                {
                    "id": "actions",
                    "name": "Actions",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 240},
                    "texts": [
                        {
                            "id": "primary-label",
                            "name": "Primary Label",
                            "role": "label",
                            "value": "Learn More",
                            "bounds": {"x": 971, "y": 819, "width": 166, "height": 65},
                            "renderBounds": {"x": 974.35, "y": 836.99, "width": 146.6, "height": 28.45},
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 38,
                                "lineHeight": 24,
                                "textAlignVertical": "CENTER",
                            },
                        }
                    ],
                    "children": ["primary-label"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-primary-label {", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn("line-height: 65.00px;", css)
        self.assertNotIn("line-height: 24px;", css)

    def test_css_generator_expands_centered_single_line_heading_line_height_to_its_box_height(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 400},
            "sections": [
                {
                    "id": "features",
                    "name": "Features",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 400},
                    "texts": [
                        {
                            "id": "feature-title",
                            "name": "Feature Title",
                            "role": "heading",
                            "value": "Feature Lab",
                            "bounds": {"x": 401, "y": 782.83, "width": 142, "height": 66},
                            "renderBounds": {"x": 404.56, "y": 801.47, "width": 136.31, "height": 28.86},
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 39,
                                "lineHeight": 24,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "CENTER",
                            },
                        }
                    ],
                    "children": ["feature-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-feature-title {", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn("line-height: 66.00px;", css)
        self.assertNotIn("line-height: 24.0px;", css)

    def test_css_generator_expands_centered_single_line_display_text_to_its_box_height(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 400},
            "sections": [
                {
                    "id": "team",
                    "name": "Team",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 400},
                    "texts": [
                        {
                            "id": "display-name",
                            "name": "Display Name",
                            "role": "hero-title",
                            "value": "Jordan Rivers",
                            "bounds": {"x": 257, "y": 1054, "width": 742, "height": 117},
                            "renderBounds": {"x": 265.54, "y": 1075.25, "width": 729.13, "height": 73.99},
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 97,
                                "lineHeight": 60,
                                "textAlignVertical": "CENTER",
                            },
                        }
                    ],
                    "children": ["display-name"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-display-name {", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn("line-height: 117.00px;", css)
        self.assertNotIn("line-height: 60.0px;", css)

    def test_css_generator_respects_hard_line_breaks_without_extra_wrapping(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 500},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 500},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Plan,\nship\niterate.",
                            "bounds": {"x": 120, "y": 90, "width": 648, "height": 312},
                            "style": {"fontFamily": "Inter", "fontSize": 80, "lineHeight": 104, "fontWeight": 700},
                        }
                    ],
                    "children": ["hero-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-hero-title {", css)
        self.assertIn("white-space: normal;", css)
        self.assertIn(".content-text span {\n  white-space: inherit;", css)

    def test_css_generator_uses_render_height_for_text_with_spacer_breaks(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 500},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 500},
                    "texts": [
                        {
                            "id": "breaker-copy",
                            "name": "Breaker Copy",
                            "role": "body",
                            "value": "Long paragraph content that should not spill into the CTA area.\n\nSecond paragraph.",
                            "bounds": {"x": 800, "y": 120, "width": 360, "height": 240},
                            "renderBounds": {"x": 804, "y": 124, "width": 352, "height": 152},
                            "style": {"fontFamily": "Roboto", "fontSize": 16, "lineHeight": 30},
                        }
                    ],
                    "children": ["breaker-copy"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-breaker-copy {", css)
        self.assertIn("height: 152.00px;", css)
        self.assertIn("overflow: hidden;", css)
        self.assertNotIn("min-height: 240.00px;", css)

    def test_css_generator_keeps_bounds_height_for_compact_multiline_titles(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 400},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 400},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "title here\nthis is a subheadline",
                            "bounds": {"x": 820, "y": 60, "width": 420, "height": 69},
                            "renderBounds": {"x": 1087, "y": 66, "width": 152, "height": 49.2},
                            "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "lineHeight": 21.1},
                        }
                    ],
                    "children": ["hero-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-hero-title {", css)
        self.assertIn("height: 69.00px;", css)
        self.assertNotIn("height: 49.20px;", css)

    def test_css_generator_falls_back_to_bounds_when_render_bounds_are_larger(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 500},
            "sections": [
                {
                    "id": "cards",
                    "name": "Cards",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 500},
                    "texts": [
                        {
                            "id": "card-copy",
                            "name": "Card Copy",
                            "role": "body",
                            "value": "Copy that visually renders a little taller than its box.",
                            "bounds": {"x": 80, "y": 180, "width": 320, "height": 149},
                            "renderBounds": {"x": 84, "y": 184, "width": 312, "height": 164},
                            "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "lineHeight": 30},
                        }
                    ],
                    "children": ["card-copy"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-card-copy {", css)
        self.assertIn("height: 149.00px;", css)
        self.assertIn("overflow: hidden;", css)

    def test_css_generator_uses_render_bounds_height_for_nowrap_labels(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 240},
            "sections": [
                {
                    "id": "nav",
                    "name": "Nav",
                    "role": "nav",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 120},
                    "texts": [
                        {
                            "id": "nav-link",
                            "name": "Nav Link",
                            "role": "body",
                            "value": "product tour",
                            "bounds": {"x": 860, "y": 24, "width": 120, "height": 21},
                            "renderBounds": {"x": 862, "y": 29, "width": 112, "height": 12.5},
                            "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "lineHeight": 21.1},
                        }
                    ],
                    "children": ["nav-link"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-nav-link {", css)
        self.assertIn("white-space: nowrap;", css)
        self.assertIn("height: 21.00px;", css)
        self.assertIn("overflow: hidden;", css)

    def test_css_generator_preserves_significant_spaces_for_nowrap_nav_text(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 240},
            "sections": [
                {
                    "id": "nav",
                    "name": "Nav",
                    "role": "nav",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 120},
                    "texts": [
                        {
                            "id": "nav-links",
                            "name": "Nav Links",
                            "role": "body",
                            "value": "home     company     product tour     pricing     contact",
                            "bounds": {"x": 666, "y": 0, "width": 574, "height": 21},
                            "style": {
                                "fontFamily": "Roboto Slab",
                                "fontSize": 16,
                                "lineHeight": 21.1,
                                "textAlignHorizontal": "JUSTIFIED",
                            },
                        }
                    ],
                    "children": ["nav-links"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-nav-links {", css)
        self.assertIn("white-space: pre;", css)
        self.assertIn("text-align: left;", css)
        self.assertNotIn("text-align: justify;", css)

    def test_css_generator_keeps_bounds_height_for_spacer_break_text_with_compact_segment_line_heights(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 500},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 500},
                    "texts": [
                        {
                            "id": "breaker-copy",
                            "name": "Breaker Copy",
                            "role": "body",
                            "value": "First paragraph.\n\nSecond paragraph.\r",
                            "bounds": {"x": 848, "y": 147, "width": 394, "height": 278},
                            "renderBounds": {"x": 853, "y": 150, "width": 388, "height": 164.16},
                            "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "lineHeight": 30},
                            "styleRuns": [
                                {
                                    "start": 0,
                                    "end": 18,
                                    "style": {
                                        "fontFamily": "Roboto",
                                        "fontWeight": 300,
                                        "lineHeight": 18.75,
                                    },
                                },
                                {
                                    "start": 18,
                                    "end": 36,
                                    "style": {
                                        "fontFamily": "Roboto",
                                        "fontWeight": 500,
                                        "lineHeight": 18.75,
                                    },
                                },
                            ],
                        }
                    ],
                    "children": ["breaker-copy"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".text-breaker-copy {", css)
        self.assertIn("height: 278.00px;", css)
        self.assertNotIn("height: 164.16px;", css)
        self.assertIn("line-height: 18.75px;", css)

    def test_css_generator_keeps_group_section_overflow_visible_for_large_decorative_bleeds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 1000, "width": 1440, "height": 465},
                    "metadata": {"sourceNodeType": "GROUP", "clipsContent": False},
                    "decorative_assets": [
                        {
                            "id": "blob",
                            "name": "Blob",
                            "nodeId": "blob",
                            "purpose": "decorative",
                            "local_path": "images/blob.svg",
                            "bounds": {"x": 1157, "y": 1086, "width": 566.83, "height": 655.64},
                            "width": 566,
                            "height": 655,
                        }
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".section-breaker .page-section__inner {", css)
        self.assertNotIn("overflow: hidden;", css)

    def test_css_generator_clips_unclipped_sections_with_large_content_overflow(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    "metadata": {"sourceNodeType": "GROUP", "clipsContent": False},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "hero-product",
                            "asset": {
                                "id": "hero-product",
                                "name": "Hero Product",
                                "nodeId": "hero-product",
                                "purpose": "content",
                                "local_path": "images/hero-product.png",
                                "bounds": {"x": 108, "y": 356, "width": 1224, "height": 688},
                                "width": 1224,
                                "height": 688,
                            },
                        }
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".section-hero .page-section__inner {", css)
        self.assertIn("overflow: hidden;", css)

    def test_css_generator_places_group_section_decorative_bleeds_below_backgrounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 1000, "width": 1440, "height": 465},
                    "metadata": {"sourceNodeType": "GROUP", "clipsContent": False},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "breaker-bg",
                            "asset": {
                                "id": "breaker-bg",
                                "name": "Breaker BG",
                                "nodeId": "breaker-bg",
                                "purpose": "background",
                                "format": "shape",
                                "renderMode": "shape",
                                "bounds": {"x": 0, "y": 1000, "width": 1440, "height": 465},
                                "style": {"background": "rgb(38 164 191)"},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "blob",
                            "asset": {
                                "id": "blob",
                                "name": "Blob",
                                "nodeId": "blob",
                                "purpose": "decorative",
                                "local_path": "images/blob.svg",
                                "bounds": {"x": 1157, "y": 1086, "width": 566.83, "height": 655.64},
                                "width": 566,
                                "height": 655,
                            },
                        }
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        background_match = re.search(r"\.asset-breaker-bg\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        blob_match = re.search(r"\.asset-blob\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(background_match)
        self.assertIsNotNone(blob_match)
        self.assertLess(int(blob_match.group(1)), int(background_match.group(1)))

    def test_css_generator_keeps_late_group_section_bleeds_below_backgrounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 1000, "width": 1440, "height": 465},
                    "metadata": {"sourceNodeType": "GROUP", "clipsContent": False},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "breaker-bg",
                            "asset": {
                                "id": "breaker-bg",
                                "name": "Breaker BG",
                                "nodeId": "breaker-bg",
                                "purpose": "background",
                                "format": "shape",
                                "renderMode": "shape",
                                "bounds": {"x": 0, "y": 1000, "width": 1440, "height": 465},
                                "style": {"background": "rgb(38 164 191)"},
                            },
                        },
                        {
                            "kind": "text",
                            "id": "copy-1",
                            "text": {
                                "id": "copy-1",
                                "name": "Copy 1",
                                "role": "body",
                                "value": "one",
                                "bounds": {"x": 100, "y": 1100, "width": 100, "height": 20},
                            },
                        },
                        {
                            "kind": "text",
                            "id": "copy-2",
                            "text": {
                                "id": "copy-2",
                                "name": "Copy 2",
                                "role": "body",
                                "value": "two",
                                "bounds": {"x": 100, "y": 1130, "width": 100, "height": 20},
                            },
                        },
                        {
                            "kind": "text",
                            "id": "copy-3",
                            "text": {
                                "id": "copy-3",
                                "name": "Copy 3",
                                "role": "body",
                                "value": "three",
                                "bounds": {"x": 100, "y": 1160, "width": 100, "height": 20},
                            },
                        },
                        {
                            "kind": "text",
                            "id": "copy-4",
                            "text": {
                                "id": "copy-4",
                                "name": "Copy 4",
                                "role": "body",
                                "value": "four",
                                "bounds": {"x": 100, "y": 1190, "width": 100, "height": 20},
                            },
                        },
                        {
                            "kind": "text",
                            "id": "copy-5",
                            "text": {
                                "id": "copy-5",
                                "name": "Copy 5",
                                "role": "body",
                                "value": "five",
                                "bounds": {"x": 100, "y": 1220, "width": 100, "height": 20},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "blob",
                            "asset": {
                                "id": "blob",
                                "name": "Blob",
                                "nodeId": "blob",
                                "purpose": "decorative",
                                "local_path": "images/blob.svg",
                                "bounds": {"x": 1157, "y": 1086, "width": 566.83, "height": 655.64},
                                "width": 566,
                                "height": 655,
                            },
                        },
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        background_match = re.search(r"\.asset-breaker-bg\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        blob_match = re.search(r"\.asset-blob\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(background_match)
        self.assertIsNotNone(blob_match)
        self.assertLess(int(blob_match.group(1)), int(background_match.group(1)))

    def test_css_generator_places_foreground_above_content_assets(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    "assets": [
                        {
                            "id": "hero-image",
                            "name": "Hero Image",
                            "nodeId": "hero-image",
                            "format": "png",
                            "purpose": "content",
                            "local_path": "images/hero.png",
                            "bounds": {"x": 700, "y": 120, "width": 420, "height": 300},
                        },
                        {
                            "id": "hero-foreground",
                            "name": "Hero Foreground",
                            "nodeId": "hero-foreground",
                            "format": "svg",
                            "purpose": "foreground",
                            "local_path": "images/hero-foreground.svg",
                            "bounds": {"x": 640, "y": 80, "width": 520, "height": 380},
                        },
                    ],
                    "children": ["hero-image", "hero-foreground"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        self.assertIn(".asset-hero-image {", css)
        self.assertIn(".asset-hero-foreground {", css)
        image_match = re.search(r"\.asset-hero-image\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        foreground_match = re.search(r"\.asset-hero-foreground\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(image_match)
        self.assertIsNotNone(foreground_match)
        self.assertGreater(int(foreground_match.group(1)), int(image_match.group(1)))

    def test_css_generator_promotes_overlapping_decorative_assets_after_content(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "showcase",
                    "name": "Showcase",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    "assets": [],
                    "children": [
                        {
                            "kind": "asset",
                            "id": "content-photo",
                            "asset": {
                                "id": "content-photo",
                                "name": "Content Photo",
                                "nodeId": "content-photo",
                                "format": "png",
                                "purpose": "content",
                                "local_path": "images/content-photo.png",
                                "bounds": {"x": 520, "y": 140, "width": 360, "height": 260},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "overlay-shards",
                            "asset": {
                                "id": "overlay-shards",
                                "name": "Overlay Shards",
                                "nodeId": "overlay-shards",
                                "format": "svg",
                                "purpose": "decorative",
                                "local_path": "images/overlay-shards.svg",
                                "bounds": {"x": 500, "y": 120, "width": 420, "height": 300},
                            },
                        },
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        photo_match = re.search(r"\.asset-content-photo\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        overlay_match = re.search(r"\.asset-overlay-shards\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(photo_match)
        self.assertIsNotNone(overlay_match)
        self.assertGreater(int(overlay_match.group(1)), int(photo_match.group(1)))

    def test_css_generator_keeps_large_decorative_backgrounds_below_content(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "feature-photo",
                            "asset": {
                                "id": "feature-photo",
                                "name": "Feature Photo",
                                "format": "png",
                                "purpose": "content",
                                "local_path": "images/feature-photo.png",
                                "bounds": {"x": 180, "y": 120, "width": 500, "height": 360},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "ambient-blob",
                            "asset": {
                                "id": "ambient-blob",
                                "name": "Ambient Blob",
                                "format": "svg",
                                "purpose": "decorative",
                                "local_path": "images/ambient-blob.svg",
                                "bounds": {"x": 430, "y": 90, "width": 566, "height": 655},
                            },
                        },
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        photo_match = re.search(r"\.asset-feature-photo\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        decorative_match = re.search(r"\.asset-ambient-blob\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(photo_match)
        self.assertIsNotNone(decorative_match)
        self.assertLess(int(decorative_match.group(1)), int(photo_match.group(1)))

    def test_css_generator_demotes_decorative_shadow_shapes_behind_backgrounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 600},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 600},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "section-shadow",
                            "asset": {
                                "id": "section-shadow",
                                "name": "shadow",
                                "format": "shape",
                                "renderMode": "shape",
                                "purpose": "decorative",
                                "bounds": {"x": 100, "y": 260, "width": 1240, "height": 200},
                                "style": {
                                    "background": "rgb(196 196 196)",
                                    "boxShadow": "0 4px 20px 0 rgb(0 0 0 / 0.25)",
                                },
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "section-bg",
                            "asset": {
                                "id": "section-bg",
                                "name": "bg",
                                "format": "shape",
                                "renderMode": "shape",
                                "purpose": "background",
                                "bounds": {"x": 0, "y": 0, "width": 1440, "height": 465},
                                "style": {"background": "rgb(38 164 191)"},
                            },
                        },
                    ],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        css = CssGenerator().generate(canonical)

        shadow_match = re.search(r"\.asset-shadow\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        bg_match = re.search(r"\.asset-bg\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(shadow_match)
        self.assertIsNotNone(bg_match)
        self.assertLess(int(shadow_match.group(1)), int(bg_match.group(1)))

    def test_builder_disambiguates_duplicate_text_and_asset_names_globally(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 1400},
            "sections": [
                {
                    "id": "cards",
                    "name": "Cards",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 600},
                    "texts": [
                        {
                            "id": "card-title-1",
                            "name": "Card Title",
                            "role": "heading",
                            "value": "title here",
                            "bounds": {"x": 0, "y": 0, "width": 200, "height": 40},
                        },
                        {
                            "id": "card-title-2",
                            "name": "Card Title",
                            "role": "heading",
                            "value": "title here",
                            "bounds": {"x": 300, "y": 0, "width": 200, "height": 40},
                        },
                    ],
                    "assets": [
                        {
                            "id": "card-image-1",
                            "name": "Card Image",
                            "format": "png",
                            "local_path": "images/card-image-1.png",
                            "bounds": {"x": 0, "y": 80, "width": 240, "height": 180},
                        },
                        {
                            "id": "card-image-2",
                            "name": "Card Image",
                            "format": "png",
                            "local_path": "images/card-image-2.png",
                            "bounds": {"x": 300, "y": 80, "width": 240, "height": 180},
                        },
                    ],
                    "children": ["card-title-1", "card-title-2", "card-image-1", "card-image-2"],
                },
                {
                    "id": "cta",
                    "name": "CTA",
                    "role": "section",
                    "bounds": {"x": 0, "y": 700, "width": 1440, "height": 400},
                    "texts": [
                        {
                            "id": "card-title-3",
                            "name": "Card Title",
                            "role": "heading",
                            "value": "title here",
                            "bounds": {"x": 100, "y": 20, "width": 200, "height": 40},
                        }
                    ],
                    "assets": [
                        {
                            "id": "card-image-3",
                            "name": "Card Image",
                            "format": "png",
                            "local_path": "images/card-image-3.png",
                            "bounds": {"x": 100, "y": 80, "width": 240, "height": 180},
                        }
                    ],
                    "children": ["card-title-3", "card-image-3"],
                },
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        canonical = CanonicalModelBuilder(mode="static").build(model)
        text_classes = [text["class_name"] for text in canonical["texts"].values()]
        asset_classes = [asset["class_name"] for asset in canonical["assets"]]

        self.assertEqual(len(text_classes), len(set(text_classes)))
        self.assertEqual(len(asset_classes), len(set(asset_classes)))
        self.assertTrue(text_classes[0].startswith("text-card-title"))
        self.assertTrue(asset_classes[0].startswith("asset-card-image"))

        css = CssGenerator().generate(canonical)
        for class_name in text_classes + asset_classes:
            self.assertIn(f".{class_name} {{", css)


class StaticGeneratorTests(unittest.TestCase):
    def test_static_generator_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = StaticGenerator().generate(SAMPLE_MODEL, temp_dir)

            index_html = Path(temp_dir) / "index.html"
            styles_css = Path(temp_dir) / "styles.css"
            page_json = Path(temp_dir) / "page.json"

            self.assertTrue(index_html.exists())
            self.assertTrue(styles_css.exists())
            self.assertTrue(page_json.exists())
            self.assertTrue((Path(temp_dir) / "images").exists())
            self.assertGreaterEqual(len(result.written_files), 3)

            html_content = index_html.read_text(encoding="utf-8")
            self.assertIn("<header", html_content)
            self.assertIn("<footer", html_content)
            self.assertIn("Build faster<br>", html_content)
            self.assertIn('src="images/hero.png"', html_content)

    def test_static_generator_escapes_segment_style_attributes(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Hello world",
                            "style": {"fontFamily": "Inter", "fontSize": 48, "fontWeight": 400},
                            "styleRuns": [
                                {
                                    "start": 0,
                                    "end": 11,
                                    "style": {"fontFamily": "Inter", "fontSize": 48, "fontWeight": 700},
                                }
                            ],
                        }
                    ],
                    "children": ["hero-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")

            self.assertNotIn('style="font-family: "Inter", sans-serif;', html_content)
            self.assertRegex(
                html_content,
                re.compile(r'style="font-family: (?:&quot;|&#34;)Inter(?:&quot;|&#34;), sans-serif;'),
            )

    def test_static_generator_preserves_segment_line_height_overrides(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "breaker",
                    "name": "Breaker",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "breaker-copy",
                            "name": "Breaker Copy",
                            "role": "body",
                            "value": "First paragraph.\n\nSecond paragraph.",
                            "style": {"fontFamily": "Roboto Slab", "fontSize": 16, "lineHeight": 30},
                            "styleRuns": [
                                {
                                    "start": 0,
                                    "end": 17,
                                    "style": {"fontFamily": "Roboto", "fontWeight": 300, "lineHeight": 18.75},
                                }
                            ],
                        }
                    ],
                    "children": ["breaker-copy"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")

            self.assertIn("line-height: 18.75px;", html_content)

    def test_static_generator_preserves_unstyled_text_after_truncated_style_runs(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 960, "height": 480},
            "sections": [
                {
                    "id": "cta",
                    "name": "CTA",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 960, "height": 480},
                    "texts": [
                        {
                            "id": "cta-copy",
                            "name": "CTA Copy",
                            "role": "body",
                            "value": "Lead line\nBody copy continues after the styled prefix.",
                            "style": {"fontFamily": "Inter", "fontSize": 18, "fontWeight": 400},
                            "styleRuns": [
                                {
                                    "start": 0,
                                    "end": 9,
                                    "style": {"fontFamily": "Inter", "fontSize": 28, "fontWeight": 700},
                                }
                            ],
                        }
                    ],
                    "children": ["cta-copy"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")

            self.assertIn("Lead line", html_content)
            self.assertIn("Body copy continues after the styled prefix.", html_content)

    def test_static_generator_skips_mask_assets_in_markup(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "assets": [
                        {
                            "id": "hero-mask",
                            "name": "Hero Mask",
                            "nodeId": "hero-mask",
                            "format": "svg",
                            "purpose": "mask",
                            "local_path": "images/hero-mask.svg",
                            "bounds": {"x": 0, "y": 0, "width": 400, "height": 300},
                        }
                    ],
                    "children": ["hero-mask"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")

            self.assertNotIn("hero-mask.svg", html_content)
            self.assertNotIn(".asset-hero-mask", css_content)

    def test_static_generator_renders_shape_assets_without_img_tags(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "cta",
                    "name": "CTA",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "assets": [
                        {
                            "id": "cta-button-bg",
                            "name": "CTA Button BG",
                            "nodeId": "cta-button-bg",
                            "format": "shape",
                            "renderMode": "shape",
                            "purpose": "content",
                            "bounds": {"x": 120, "y": 220, "width": 180, "height": 48},
                            "style": {"background": "rgb(38 164 191)", "borderRadius": "8px"},
                        }
                    ],
                    "texts": [
                        {
                            "id": "cta-button-label",
                            "name": "CTA Button Label",
                            "role": "body",
                            "value": "read more",
                            "bounds": {"x": 160, "y": 233, "width": 100, "height": 22},
                        }
                    ],
                    "children": ["cta-button-bg", "cta-button-label"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")

            self.assertIn('class="content-asset asset-cta-button-bg"', html_content)
            self.assertNotIn("<img", html_content.split('asset-cta-button-bg', 1)[1].split("</figure>", 1)[0])
            self.assertIn("background: rgb(38 164 191);", css_content)
            self.assertIn("border-radius: 8px;", css_content)

    @unittest.skipIf(MODEL_IMPORT_ERROR is not None, f"Model dependencies unavailable: {MODEL_IMPORT_ERROR}")
    def test_static_generator_accepts_intermediate_document_models(self) -> None:
        document = IntermediateDocument(
            page=PageNode(id="3:964", name="Typed Page", width=1440, height=1800),
            sections=[
                SectionNode(
                    id="hero",
                    name="Hero",
                    role=SectionRole.HERO,
                    bounds=Bounds(x=0, y=0, width=1440, height=720),
                    texts=["hero-title"],
                    assets=["hero-image"],
                )
            ],
            texts={
                "hero-title": TextNode(
                    id="hero-title",
                    value="Typed content from models",
                    section_id="hero",
                )
            },
            assets=[
                AssetRef(
                    node_id="hero-image",
                    local_path="images/hero.png",
                    format="png",
                    role=AssetRole.CONTENT,
                )
            ],
            tokens=TokenBag(colors={"brand": "#1434cb"}),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(document, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")

            self.assertIn("Typed content from models", html_content)
            self.assertIn('src="images/hero.png"', html_content)


class HugoGeneratorTests(unittest.TestCase):
    def test_hugo_generator_writes_layouts_assets_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = HugoGenerator().generate(SAMPLE_MODEL, temp_dir)

            config_file = Path(temp_dir) / "hugo.toml"
            index_template = Path(temp_dir) / "layouts" / "index.html"
            section_partial = Path(temp_dir) / "layouts" / "partials" / "section.html"
            css_path = Path(temp_dir) / "assets" / "css" / "main.css"
            page_data = Path(temp_dir) / "data" / "page.json"

            self.assertTrue(config_file.exists())
            self.assertTrue(index_template.exists())
            self.assertTrue(section_partial.exists())
            self.assertTrue(css_path.exists())
            self.assertTrue(page_data.exists())
            self.assertTrue((Path(temp_dir) / "static" / "images").exists())
            self.assertGreaterEqual(len(result.written_files), 6)

            template_content = index_template.read_text(encoding="utf-8")
            self.assertIn("hugo.Data.page", template_content)
            self.assertIn('partial "section.html"', template_content)

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_escapes_segment_style_attributes(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Hello world",
                            "style": {"fontFamily": "Inter", "fontSize": 48, "fontWeight": 400},
                            "styleRuns": [
                                {
                                    "start": 0,
                                    "end": 11,
                                    "style": {"fontFamily": "Inter", "fontSize": 48, "fontWeight": 700},
                                }
                            ],
                        }
                    ],
                    "children": ["hero-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")

            self.assertNotIn('style="font-family: "Inter", sans-serif;', html_content)
            self.assertRegex(
                html_content,
                re.compile(r'style="font-family: (?:&quot;|&#34;)Inter(?:&quot;|&#34;), sans-serif;'),
            )

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_skips_mask_assets_in_markup(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "assets": [
                        {
                            "id": "hero-mask",
                            "name": "Hero Mask",
                            "nodeId": "hero-mask",
                            "format": "svg",
                            "purpose": "mask",
                            "local_path": "images/hero-mask.svg",
                            "bounds": {"x": 0, "y": 0, "width": 400, "height": 300},
                        }
                    ],
                    "children": ["hero-mask"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")

            self.assertNotIn("hero-mask.svg", html_content)

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_renders_shape_assets_without_img_tags(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "cta",
                    "name": "CTA",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "assets": [
                        {
                            "id": "cta-button-bg",
                            "name": "CTA Button BG",
                            "nodeId": "cta-button-bg",
                            "format": "shape",
                            "renderMode": "shape",
                            "purpose": "content",
                            "bounds": {"x": 120, "y": 220, "width": 180, "height": 48},
                            "style": {"background": "rgb(38 164 191)", "borderRadius": "8px"},
                        }
                    ],
                    "texts": [
                        {
                            "id": "cta-button-label",
                            "name": "CTA Button Label",
                            "role": "body",
                            "value": "read more",
                            "bounds": {"x": 160, "y": 233, "width": 100, "height": 22},
                        }
                    ],
                    "children": ["cta-button-bg", "cta-button-label"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")
            css_files = list((public_dir / "css").glob("main*.css"))
            css_content = css_files[0].read_text(encoding="utf-8")

            self.assertIn('class="content-asset asset-cta-button-bg"', html_content)
            self.assertNotIn("<img", html_content.split('asset-cta-button-bg', 1)[1].split("</figure>", 1)[0])
            self.assertIn("background:#26a4bf", css_content)
            self.assertIn("border-radius:8px", css_content)

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_renders_semantic_tags_without_escaping(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 960, "height": 1200},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 960, "height": 320},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Build faster\nwith shared templates",
                        }
                    ],
                    "children": ["hero-title"],
                },
                {
                    "id": "features",
                    "name": "Features",
                    "role": "section",
                    "bounds": {"x": 0, "y": 360, "width": 960, "height": 420},
                    "texts": [
                        {
                            "id": "features-copy",
                            "name": "Features Copy",
                            "role": "body",
                            "value": "Reusable content block",
                        }
                    ],
                    "children": ["features-copy"],
                },
                {
                    "id": "footer",
                    "name": "Footer",
                    "role": "footer",
                    "bounds": {"x": 0, "y": 980, "width": 960, "height": 160},
                    "texts": [
                        {
                            "id": "footer-copy",
                            "name": "Footer Copy",
                            "role": "body",
                            "value": "All rights reserved.",
                        }
                    ],
                    "children": ["footer-copy"],
                },
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")

            self.assertIn("<header", html_content)
            self.assertIn("<section", html_content)
            self.assertIn("<footer", html_content)
            self.assertNotIn("&lt;header", html_content)
            self.assertNotIn("&lt;section", html_content)
            self.assertNotIn("&lt;footer", html_content)
            self.assertIn("Build faster<br>", html_content)

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_uses_external_asset_references_instead_of_inline_svg(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 960, "height": 540},
            "sections": [
                {
                    "id": "showcase",
                    "name": "Showcase",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 960, "height": 540},
                    "assets": [
                        {
                            "id": "photo",
                            "name": "Feature Photo",
                            "nodeId": "photo",
                            "format": "png",
                            "purpose": "content",
                            "local_path": "images/feature-photo.png",
                            "bounds": {"x": 420, "y": 80, "width": 320, "height": 220},
                        }
                    ],
                    "decorative_assets": [
                        {
                            "id": "accent-shape",
                            "name": "Accent Shape",
                            "nodeId": "accent-shape",
                            "format": "svg",
                            "purpose": "decorative",
                            "local_path": "images/accent-shape.svg",
                            "bounds": {"x": 120, "y": 60, "width": 180, "height": 180},
                        }
                    ],
                    "children": ["photo", "accent-shape"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")

            self.assertIn('href="css/', html_content)
            self.assertIn('src="images/feature-photo.png"', html_content)
            self.assertIn('src="images/accent-shape.svg"', html_content)
            self.assertNotIn("<svg", html_content)


if __name__ == "__main__":
    unittest.main()
