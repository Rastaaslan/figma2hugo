from __future__ import annotations

import html
import json
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

    def test_css_generator_collapses_isolated_punctuation_breaks_in_headings(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 500},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 500},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "titre-hero",
                            "role": "hero-title",
                            "value": "Nom de la prestation\n-\nAccompagnement ",
                            "bounds": {"x": 120, "y": 90, "width": 792, "height": 312},
                            "renderBounds": {"x": 124, "y": 94, "width": 787, "height": 286.8},
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 80,
                                "lineHeight": 104,
                                "fontWeight": 700,
                                "fontStyle": "Bold Italic",
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "TOP",
                            },
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
        heading = canonical["sections"][0]["children"][0]["text"]
        css = CssGenerator().generate(canonical)

        self.assertEqual(heading["value"], "Nom de la prestation -\nAccompagnement ")
        self.assertEqual(heading["html"], "Nom de la prestation -<br>\nAccompagnement ")
        self.assertTrue(heading["normalized_break_lines"])
        self.assertIn("height: 208.00px;", css)
        self.assertNotIn("height: 312.00px;", css)

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
        self.assertRegex(
            css,
            re.compile(r"\.section-breaker \.page-section__inner \{\s*height: 465px;\s*width: 1440px;\s*\}", re.S),
        )

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

    def test_css_generator_places_explicit_top_layer_assets_above_content_assets(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "hero",
                    "name": "Hero",
                    "role": "hero",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    "texts": [
                        {
                            "id": "hero-title",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Build faster",
                            "bounds": {"x": 120, "y": 120, "width": 360, "height": 80},
                            "style": {"fontFamily": "Inter", "fontSize": 64, "fontWeight": 700},
                        }
                    ],
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
                            "id": "hero-overlay-top",
                            "name": "Hero Overlay",
                            "nodeId": "hero-overlay-top",
                            "format": "svg",
                            "purpose": "foreground",
                            "local_path": "images/hero-overlay-top.svg",
                            "bounds": {"x": 640, "y": 80, "width": 520, "height": 380},
                        },
                    ],
                    "children": ["hero-title", "hero-image", "hero-overlay-top"],
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
        self.assertIn(".asset-hero-overlay {", css)
        text_match = re.search(r"\.text-hero-title\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        image_match = re.search(r"\.asset-hero-image\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        foreground_match = re.search(r"\.asset-hero-overlay\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(text_match)
        self.assertIsNotNone(image_match)
        self.assertIsNotNone(foreground_match)
        self.assertGreater(int(foreground_match.group(1)), int(text_match.group(1)))
        self.assertGreater(int(foreground_match.group(1)), int(image_match.group(1)))

    def test_css_generator_promotes_local_background_panels_above_large_section_backgrounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 1200},
            "sections": [
                {
                    "id": "contact",
                    "name": "Contact",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 1200},
                    "assets": [],
                    "children": [
                        {
                            "kind": "asset",
                            "id": "section-background",
                            "asset": {
                                "id": "section-background",
                                "name": "Section Background",
                                "nodeId": "section-background",
                                "format": "png",
                                "purpose": "decorative",
                                "local_path": "images/section-backdrop.png",
                                "bounds": {"x": 0, "y": 420, "width": 1280, "height": 520},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "panel-background",
                            "asset": {
                                "id": "panel-background",
                                "name": "Panel Background",
                                "nodeId": "panel-background",
                                "format": "svg",
                                "purpose": "background",
                                "local_path": "images/panel-bg.svg",
                                "bounds": {"x": 620, "y": 470, "width": 420, "height": 320},
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

        section_bg_match = re.search(r"\.asset-section-background\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        panel_bg_match = re.search(r"\.asset-panel-background\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(section_bg_match)
        self.assertIsNotNone(panel_bg_match)
        self.assertGreater(int(panel_bg_match.group(1)), int(section_bg_match.group(1)))

    def test_css_generator_keeps_small_decorative_panel_elements_above_local_backgrounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 1200},
            "sections": [
                {
                    "id": "contact",
                    "name": "Contact",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 1200},
                    "assets": [],
                    "children": [
                        {
                            "kind": "asset",
                            "id": "section-backdrop",
                            "asset": {
                                "id": "section-backdrop",
                                "name": "Section Backdrop",
                                "nodeId": "section-backdrop",
                                "format": "png",
                                "purpose": "decorative",
                                "local_path": "images/section-backdrop.png",
                                "bounds": {"x": 0, "y": 420, "width": 1280, "height": 520},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "panel-background",
                            "asset": {
                                "id": "panel-background",
                                "name": "Panel Background",
                                "nodeId": "panel-background",
                                "format": "svg",
                                "purpose": "background",
                                "local_path": "images/panel-bg.svg",
                                "bounds": {"x": 620, "y": 470, "width": 420, "height": 320},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "field-shell",
                            "asset": {
                                "id": "field-shell",
                                "name": "Field Shell",
                                "nodeId": "field-shell",
                                "format": "svg",
                                "purpose": "decorative",
                                "local_path": "images/field-shell.svg",
                                "bounds": {"x": 660, "y": 540, "width": 320, "height": 72},
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

        panel_bg_match = re.search(r"\.asset-panel-background\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        field_shell_match = re.search(r"\.asset-field-shell\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(panel_bg_match)
        self.assertIsNotNone(field_shell_match)
        self.assertGreater(int(field_shell_match.group(1)), int(panel_bg_match.group(1)))

    def test_css_generator_keeps_prior_panel_content_above_local_backgrounds(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 1200},
            "sections": [
                {
                    "id": "contact",
                    "name": "Contact",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 1200},
                    "assets": [],
                    "children": [
                        {
                            "kind": "asset",
                            "id": "section-backdrop",
                            "asset": {
                                "id": "section-backdrop",
                                "name": "Section Backdrop",
                                "nodeId": "section-backdrop",
                                "format": "png",
                                "purpose": "decorative",
                                "local_path": "images/section-backdrop.png",
                                "bounds": {"x": 0, "y": 420, "width": 1280, "height": 520},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "panel-copy",
                            "asset": {
                                "id": "panel-copy",
                                "name": "Panel Copy",
                                "nodeId": "panel-copy",
                                "format": "svg",
                                "purpose": "decorative",
                                "local_path": "images/panel-copy.svg",
                                "bounds": {"x": 700, "y": 560, "width": 240, "height": 80},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "panel-background",
                            "asset": {
                                "id": "panel-background",
                                "name": "Panel Background",
                                "nodeId": "panel-background",
                                "format": "svg",
                                "purpose": "background",
                                "local_path": "images/panel-bg.svg",
                                "bounds": {"x": 620, "y": 470, "width": 420, "height": 320},
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

        panel_bg_match = re.search(r"\.asset-panel-background\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        panel_copy_match = re.search(r"\.asset-panel-copy\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(panel_bg_match)
        self.assertIsNotNone(panel_copy_match)
        self.assertGreater(int(panel_copy_match.group(1)), int(panel_bg_match.group(1)))

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

    def test_css_generator_promotes_overlapping_decorative_assets_before_content(self) -> None:
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

    def test_css_generator_promotes_large_decorative_overlays_after_content(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1920, "height": 1080},
            "sections": [
                {
                    "id": "showcase",
                    "name": "Showcase",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
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
                                "bounds": {"x": 1128, "y": 0, "width": 894.8, "height": 1041.83},
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "overlay-cluster",
                            "asset": {
                                "id": "overlay-cluster",
                                "name": "Overlay Cluster",
                                "nodeId": "overlay-cluster",
                                "format": "svg",
                                "purpose": "decorative",
                                "local_path": "images/overlay-cluster.svg",
                                "bounds": {"x": 0, "y": 122.1, "width": 2132.51, "height": 1405.19},
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
        overlay_match = re.search(r"\.asset-overlay-cluster\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

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
                                "name": "panel-background",
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
        bg_match = re.search(r"\.asset-panel-background\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(shadow_match)
        self.assertIsNotNone(bg_match)
        self.assertLess(int(shadow_match.group(1)), int(bg_match.group(1)))

    def test_css_generator_places_bg_named_assets_on_the_lowest_parent_layer(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1440, "height": 600},
            "sections": [
                {
                    "id": "contact",
                    "name": "Contact",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 600},
                    "children": [
                        {
                            "kind": "asset",
                            "id": "contact-bg",
                            "asset": {
                                "id": "contact-bg",
                                "name": "bg-contact",
                                "nodeId": "contact-bg",
                                "purpose": "background",
                                "local_path": "images/bg-contact.png",
                                "bounds": {"x": 0, "y": 0, "width": 1440, "height": 460},
                                "width": 1440,
                                "height": 460,
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "contact-accent",
                            "asset": {
                                "id": "contact-accent",
                                "name": "Accent",
                                "nodeId": "contact-accent",
                                "purpose": "decorative",
                                "local_path": "images/contact-accent.svg",
                                "bounds": {"x": 100, "y": 120, "width": 260, "height": 200},
                                "width": 260,
                                "height": 200,
                            },
                        },
                        {
                            "kind": "asset",
                            "id": "cta-bg",
                            "asset": {
                                "id": "cta-bg",
                                "name": "bg-accompagnement-cta",
                                "nodeId": "cta-bg",
                                "purpose": "decorative",
                                "local_path": "images/bg-accompagnement-cta.png",
                                "bounds": {"x": 380, "y": 260, "width": 620, "height": 180},
                                "width": 620,
                                "height": 180,
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

        section_bg_match = re.search(r"\.asset-bg-contact\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        accent_match = re.search(r"\.asset-accent\s*\{[^}]*z-index:\s*(\d+);", css, re.S)
        decorative_bg_match = re.search(r"\.asset-bg-accompagnement-cta\s*\{[^}]*z-index:\s*(\d+);", css, re.S)

        self.assertIsNotNone(section_bg_match)
        self.assertIsNotNone(accent_match)
        self.assertIsNotNone(decorative_bg_match)
        self.assertEqual(int(section_bg_match.group(1)), 0)
        self.assertEqual(int(decorative_bg_match.group(1)), 0)
        self.assertLess(int(section_bg_match.group(1)), int(accent_match.group(1)))
        self.assertLess(int(decorative_bg_match.group(1)), int(accent_match.group(1)))

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
            accordion_js = Path(temp_dir) / "accordion.js"
            page_json = Path(temp_dir) / "page.json"

            self.assertTrue(index_html.exists())
            self.assertTrue(styles_css.exists())
            self.assertTrue(accordion_js.exists())
            self.assertTrue(page_json.exists())
            self.assertTrue((Path(temp_dir) / "images").exists())
            self.assertGreaterEqual(len(result.written_files), 4)

            html_content = index_html.read_text(encoding="utf-8")
            self.assertIn("<header", html_content)
            self.assertIn("<footer", html_content)
            self.assertIn("Build faster<br>", html_content)
            self.assertIn('src="images/hero.png"', html_content)

    def test_static_generator_avoids_orphan_punctuation_lines_in_heading_html(self) -> None:
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
                            "name": "titre-hero",
                            "role": "hero-title",
                            "value": "Nom de la prestation\n-\nAccompagnement ",
                            "bounds": {"x": 120, "y": 90, "width": 792, "height": 312},
                            "renderBounds": {"x": 124, "y": 94, "width": 787, "height": 286.8},
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 80,
                                "lineHeight": 104,
                                "fontWeight": 700,
                                "fontStyle": "Bold Italic",
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "TOP",
                            },
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
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")

            self.assertIn("Nom de la prestation -<br>", html_content)
            self.assertNotIn("<br>\n-<br>", html_content)
            self.assertIn("height: 208.00px;", css_content)

    def test_static_generator_uses_sanitized_dom_ids_for_figma_node_ids(self) -> None:
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
                            "id": "6:1092",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Hello",
                            "bounds": {"x": 120, "y": 80, "width": 320, "height": 60},
                        }
                    ],
                    "assets": [
                        {
                            "id": "1:240",
                            "name": "bg-hero",
                            "nodeId": "1:240",
                            "format": "svg",
                            "purpose": "background",
                            "local_path": "images/hero-bg.svg",
                            "bounds": {"x": 0, "y": 0, "width": 800, "height": 260},
                        }
                    ],
                    "children": ["1:240", "6:1092"],
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

            self.assertIn('id="id-1-240"', html_content)
            self.assertIn('data-node-id="1:240"', html_content)
            self.assertIn('id="id-6-1092"', html_content)
            self.assertIn('data-node-id="6:1092"', html_content)

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

    def test_static_generator_preserves_named_form_and_button_nesting_without_shifting_layout(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1200, "height": 900},
            "sections": [
                {
                    "id": "contact",
                    "name": "Contact",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1200, "height": 900},
                    "texts": [
                        "contact-title",
                        "contact-email-label",
                        "contact-submit-label",
                    ],
                    "assets": ["contact-submit-bg"],
                    "children": [
                        "contact-title",
                        {
                            "id": "formulaire-contact",
                            "name": "formulaire-contact",
                            "bounds": {"x": 400, "y": 500, "width": 420, "height": 240},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "input-email",
                                    "name": "input-email",
                                    "bounds": {"x": 420, "y": 540, "width": 320, "height": 40},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": ["contact-email-label"],
                                },
                                {
                                    "id": "button-envoyer",
                                    "name": "button-envoyer",
                                    "bounds": {"x": 620, "y": 680, "width": 180, "height": 52},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": ["contact-submit-bg", "contact-submit-label"],
                                },
                            ],
                        },
                    ],
                }
            ],
            "texts": {
                "contact-title": {
                    "id": "contact-title",
                    "name": "Contact Title",
                    "role": "heading",
                    "value": "Parlons de votre projet",
                    "bounds": {"x": 120, "y": 120, "width": 420, "height": 60},
                    "style": {"fontFamily": "Inter", "fontSize": 48, "fontWeight": 700},
                },
                "contact-email-label": {
                    "id": "contact-email-label",
                    "name": "Contact Email Label",
                    "role": "label",
                    "value": "Votre email",
                    "bounds": {"x": 438, "y": 550, "width": 180, "height": 18},
                    "style": {"fontFamily": "Inter", "fontSize": 16},
                },
                "contact-submit-label": {
                    "id": "contact-submit-label",
                    "name": "Contact Submit Label",
                    "role": "body",
                    "value": "Envoyer",
                    "bounds": {"x": 660, "y": 696, "width": 100, "height": 20},
                    "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 700},
                },
            },
            "assets": [
                {
                    "id": "contact-submit-bg",
                    "name": "contact-submit-bg",
                    "nodeId": "contact-submit-bg",
                    "format": "shape",
                    "renderMode": "shape",
                    "purpose": "content",
                    "bounds": {"x": 620, "y": 680, "width": 180, "height": 52},
                    "style": {"background": "rgb(227 124 108)", "borderRadius": "4px"},
                }
            ],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")

            self.assertRegex(
                html_content,
                re.compile(
                    r'<form id="formulaire-contact"[^>]*>[\s\S]*<div id="input-email"[^>]*>[\s\S]*'
                    r'<label id="contact-email-label"[\s\S]*<button id="button-envoyer"[^>]*type="button"[\s\S]*'
                    r'asset-contact-submit-bg[\s\S]*id="contact-submit-label"',
                    re.S,
                ),
            )
            self.assertIn("button.content-node {", css_content)
            self.assertRegex(
                css_content,
                re.compile(
                    r"\.node-formulaire-contact\s*\{[^}]*left:\s*400\.00px;[^}]*top:\s*500\.00px;",
                    re.S,
                ),
            )
            self.assertRegex(
                css_content,
                re.compile(
                    r"\.node-button-envoyer\s*\{[^}]*left:\s*220\.00px;[^}]*top:\s*180\.00px;",
                    re.S,
                ),
            )
            self.assertRegex(
                css_content,
                re.compile(
                    r"\.asset-contact-submit-bg\s*\{[^}]*left:\s*0\.00px;[^}]*top:\s*0\.00px;",
                    re.S,
                ),
            )
            self.assertRegex(
                css_content,
                re.compile(
                    r"\.text-contact-submit-label\s*\{[^}]*left:\s*40\.00px;[^}]*top:\s*16\.00px;",
                    re.S,
                ),
            )

    def test_static_generator_renders_named_accordion_markup_and_script(self) -> None:
        model = {
            "page": {"id": "page", "name": "Page", "width": 1200, "height": 1100},
            "sections": [
                {
                    "id": "faq",
                    "name": "FAQ",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1200, "height": 1100},
                    "texts": [
                        "question-1",
                        "answer-1",
                        "question-2",
                        "answer-2",
                    ],
                    "children": [
                        {
                            "id": "accordion-faq",
                            "name": "accordion-single-faq",
                            "bounds": {"x": 200, "y": 180, "width": 760, "height": 500},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "accordion-item-1-open",
                                    "name": "accordion-item-1-open",
                                    "bounds": {"x": 200, "y": 180, "width": 760, "height": 180},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "accordion-panel-1",
                                            "name": "accordion-panel-1",
                                            "bounds": {"x": 200, "y": 260, "width": 760, "height": 100},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["answer-1"],
                                        },
                                        {
                                            "id": "accordion-trigger-1",
                                            "name": "accordion-trigger-1",
                                            "bounds": {"x": 200, "y": 180, "width": 760, "height": 60},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["question-1"],
                                        },
                                    ],
                                },
                                {
                                    "id": "accordion-item-2-closed",
                                    "name": "accordion-item-2-closed",
                                    "bounds": {"x": 200, "y": 390, "width": 760, "height": 210},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "accordion-panel-2",
                                            "name": "accordion-panel-2",
                                            "bounds": {"x": 200, "y": 470, "width": 760, "height": 130},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["answer-2"],
                                        },
                                        {
                                            "id": "accordion-trigger-2",
                                            "name": "accordion-trigger-2",
                                            "bounds": {"x": 200, "y": 390, "width": 760, "height": 60},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["question-2"],
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
            "texts": {
                "question-1": {
                    "id": "question-1",
                    "name": "Question 1",
                    "role": "body",
                    "value": "Quels services proposez-vous ?",
                    "bounds": {"x": 232, "y": 198, "width": 520, "height": 24},
                    "style": {"fontFamily": "Inter", "fontSize": 20, "fontWeight": 700},
                },
                "answer-1": {
                    "id": "answer-1",
                    "name": "Answer 1",
                    "role": "body",
                    "value": "Nous accompagnons le produit et l'embarque.",
                    "bounds": {"x": 232, "y": 280, "width": 620, "height": 52},
                    "style": {"fontFamily": "Inter", "fontSize": 18},
                },
                "question-2": {
                    "id": "question-2",
                    "name": "Question 2",
                    "role": "body",
                    "value": "Comment demarrer un projet ?",
                    "bounds": {"x": 232, "y": 408, "width": 520, "height": 24},
                    "style": {"fontFamily": "Inter", "fontSize": 20, "fontWeight": 700},
                },
                "answer-2": {
                    "id": "answer-2",
                    "name": "Answer 2",
                    "role": "body",
                    "value": "En cadrant le besoin, le budget et le planning.",
                    "bounds": {"x": 232, "y": 492, "width": 620, "height": 52},
                    "style": {"fontFamily": "Inter", "fontSize": 18},
                },
            },
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")
            js_content = (Path(temp_dir) / "accordion.js").read_text(encoding="utf-8")

            self.assertIn('<script src="accordion.js" defer></script>', html_content)
            self.assertIn('id="accordion-faq"', html_content)
            self.assertIn('data-accordion="true"', html_content)
            self.assertIn('data-accordion-mode="single"', html_content)
            self.assertIn('id="accordion-item-1-open"', html_content)
            self.assertIn('data-accordion-item="true"', html_content)
            self.assertIn('data-accordion-open="true"', html_content)
            self.assertIn('id="accordion-trigger-1"', html_content)
            self.assertIn('data-accordion-trigger="true"', html_content)
            self.assertIn('aria-controls="accordion-panel-1"', html_content)
            self.assertIn('aria-expanded="true"', html_content)
            self.assertIn('type="button"', html_content)
            self.assertIn('id="accordion-panel-1"', html_content)
            self.assertIn('data-accordion-panel="true"', html_content)
            self.assertIn('role="region"', html_content)
            self.assertIn('aria-labelledby="accordion-trigger-1"', html_content)
            self.assertIn('aria-hidden="false"', html_content)
            self.assertIn('id="accordion-item-2-closed"', html_content)
            self.assertIn('data-accordion-open="false"', html_content)
            self.assertIn('id="accordion-trigger-2"', html_content)
            self.assertIn('aria-labelledby="accordion-trigger-2"', html_content)
            self.assertIn('aria-hidden="true"', html_content)
            self.assertIn('hidden="hidden"', html_content)
            self.assertRegex(
                html_content,
                re.compile(
                    r'id="accordion-item-1-open"[\s\S]*id="accordion-trigger-1"[\s\S]*id="accordion-panel-1"',
                    re.S,
                ),
            )
            self.assertRegex(
                html_content,
                re.compile(
                    r'id="accordion-item-2-closed"[\s\S]*id="accordion-trigger-2"[\s\S]*id="accordion-panel-2"',
                    re.S,
                ),
            )
            self.assertIn('button.content-node[data-accordion-trigger="true"] {', css_content)
            self.assertIn('const SECTION_SELECTOR = ".page-section";', js_content)
            self.assertIn('data-accordion-trigger="true"', js_content)
            self.assertIn('item.dataset.accordionOpen = open ? "true" : "false";', js_content)
            self.assertIn('function isFlowLayoutContainer(element)', js_content)
            self.assertIn('element.dataset.linkGrid === "true"', js_content)
            self.assertIn('page.style.minHeight = pageHeight + "px";', js_content)
            self.assertNotIn('Math.max(pageHeight, getOriginalHeight(page))', js_content)

    def test_static_generator_renders_named_link_card_as_full_anchor(self) -> None:
        model = {
            "page": {"id": "page", "name": "Portfolio", "width": 1440, "height": 900},
            "sections": [
                {
                    "id": "projects",
                    "name": "Projects",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 900},
                    "children": [
                        {
                            "id": "link-grid-projects",
                            "name": "link-grid-projects",
                            "bounds": {"x": 80, "y": 120, "width": 520, "height": 420},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "href-card-blowfish",
                                    "name": "href-card-blowfish-external",
                                    "bounds": {"x": 80, "y": 120, "width": 520, "height": 420},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        "card-thumb",
                                        "card-url",
                                        "card-title",
                                        "card-copy",
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            "texts": {
                "card-url": {
                    "id": "card-url",
                    "name": "href-blowfish",
                    "role": "body",
                    "value": "https://blowfish-tutorial.web.app/",
                    "bounds": {"x": 120, "y": 500, "width": 320, "height": 18},
                    "style": {"fontFamily": "Inter", "fontSize": 14},
                },
                "card-title": {
                    "id": "card-title",
                    "name": "link-label-blowfish",
                    "role": "heading",
                    "value": "Blowfish Tutorial",
                    "bounds": {"x": 120, "y": 470, "width": 320, "height": 34},
                    "style": {"fontFamily": "Inter", "fontSize": 28, "fontWeight": 700},
                },
                "card-copy": {
                    "id": "card-copy",
                    "name": "texte-blowfish",
                    "role": "body",
                    "value": "A compact portfolio card.",
                    "bounds": {"x": 120, "y": 514, "width": 260, "height": 20},
                    "style": {"fontFamily": "Inter", "fontSize": 14},
                },
            },
            "assets": [
                {
                    "id": "card-thumb",
                    "name": "image-blowfish",
                    "nodeId": "card-thumb",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/blowfish-card.png",
                    "bounds": {"x": 80, "y": 120, "width": 520, "height": 320},
                }
            ],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")

            self.assertIn('data-link-grid="true"', html_content)
            self.assertRegex(
                html_content,
                re.compile(
                    r'<a id="href-card-blowfish"[^>]*data-link-card="true"[^>]*href="https://blowfish-tutorial\.web\.app/"'
                    r'[^>]*target="_blank"[^>]*rel="noopener noreferrer"',
                    re.S,
                ),
            )
            self.assertRegex(
                html_content,
                re.compile(r'<h2 id="card-title"[^>]*class="content-text text-link-label-blowfish"[^>]*>Blowfish Tutorial</h2>', re.S),
            )
            self.assertNotIn("https://blowfish-tutorial.web.app/</", html_content)
            self.assertIn("text-decoration: none;", css_content)
            self.assertIn("A compact portfolio card.", html_content)
            self.assertIn('a.content-node[data-link-card="true"] {', css_content)

    def test_static_generator_renders_named_carousel_markup_and_script(self) -> None:
        model = {
            "page": {"id": "page", "name": "Gallery", "width": 1280, "height": 960},
            "sections": [
                {
                    "id": "gallery",
                    "name": "Gallery",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1280, "height": 960},
                    "children": [
                        {
                            "id": "carousel-gallery",
                            "name": "carousel-gallery",
                            "bounds": {"x": 160, "y": 120, "width": 620, "height": 520},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "carousel-stage-gallery",
                                    "name": "carousel-stage-gallery",
                                    "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "carousel-slide-ocean-active",
                                            "name": "carousel-slide-ocean-active",
                                            "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["slide-ocean-image"],
                                        },
                                        {
                                            "id": "carousel-slide-forest",
                                            "name": "carousel-slide-forest",
                                            "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["slide-forest-image"],
                                        },
                                    ],
                                },
                                {
                                    "id": "carousel-thumbs-gallery",
                                    "name": "carousel-thumbs-gallery",
                                    "bounds": {"x": 160, "y": 510, "width": 620, "height": 90},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "carousel-thumb-ocean",
                                            "name": "carousel-thumb-ocean",
                                            "bounds": {"x": 160, "y": 510, "width": 140, "height": 90},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["thumb-ocean-image"],
                                        },
                                        {
                                            "id": "carousel-thumb-forest",
                                            "name": "carousel-thumb-forest",
                                            "bounds": {"x": 320, "y": 510, "width": 140, "height": 90},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["thumb-forest-image"],
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
            "texts": {},
            "assets": [
                {
                    "id": "slide-ocean-image",
                    "name": "image-ocean",
                    "nodeId": "slide-ocean-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/ocean.png",
                    "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                },
                {
                    "id": "slide-forest-image",
                    "name": "image-forest",
                    "nodeId": "slide-forest-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/forest.png",
                    "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                },
                {
                    "id": "thumb-ocean-image",
                    "name": "image-thumb-ocean",
                    "nodeId": "thumb-ocean-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/ocean-thumb.png",
                    "bounds": {"x": 160, "y": 510, "width": 140, "height": 90},
                },
                {
                    "id": "thumb-forest-image",
                    "name": "image-thumb-forest",
                    "nodeId": "thumb-forest-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/forest-thumb.png",
                    "bounds": {"x": 320, "y": 510, "width": 140, "height": 90},
                },
            ],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            StaticGenerator().generate(model, temp_dir)
            html_content = (Path(temp_dir) / "index.html").read_text(encoding="utf-8")
            css_content = (Path(temp_dir) / "styles.css").read_text(encoding="utf-8")
            js_content = (Path(temp_dir) / "accordion.js").read_text(encoding="utf-8")

            self.assertIn('data-carousel="true"', html_content)
            self.assertIn('data-carousel-stage="true"', html_content)
            self.assertIn('data-carousel-nav="true"', html_content)
            self.assertIn('data-carousel-slide="ocean"', html_content)
            self.assertIn('data-carousel-slide="forest"', html_content)
            self.assertIn('data-carousel-default="true"', html_content)
            self.assertIn('id="carousel-thumb-ocean"', html_content)
            self.assertIn('data-carousel-thumb="ocean"', html_content)
            self.assertIn('aria-controls="carousel-slide-ocean-active"', html_content)
            self.assertIn('id="carousel-thumb-forest"', html_content)
            self.assertIn('data-carousel-thumb="forest"', html_content)
            self.assertIn('aria-controls="carousel-slide-forest"', html_content)
            self.assertIn('[data-carousel-nav="true"] {', css_content)
            self.assertIn('[data-carousel-stage="true"] {', css_content)
            self.assertIn("overflow-x: auto;", css_content)
            self.assertIn("overflow-y: hidden;", css_content)
            self.assertIn("touch-action: pan-x;", css_content)
            self.assertIn("overflow: hidden;", css_content)
            self.assertIn("pointer-events: none;", css_content)
            self.assertIn('button.content-node[data-carousel-thumb] {', css_content)
            self.assertNotIn('button.content-node[data-carousel-thumb] {\n  position: relative;', css_content)
            self.assertIn('button.content-node[data-carousel-thumb]:focus-visible {', css_content)
            self.assertIn("function initializeCarouselRoot(root)", js_content)
            self.assertIn('thumb.addEventListener("click"', js_content)
            self.assertIn("data-carousel-slide", js_content)
            self.assertIn("data-carousel-thumb", js_content)

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
            home_content = Path(temp_dir) / "content" / "_index.md"
            base_template = Path(temp_dir) / "layouts" / "_default" / "baseof.html"
            index_template = Path(temp_dir) / "layouts" / "index.html"
            section_partial = Path(temp_dir) / "layouts" / "partials" / "section.html"
            css_path = Path(temp_dir) / "assets" / "css" / "main.css"
            link_grid_css_path = Path(temp_dir) / "assets" / "css" / "components" / "link-grid.css"
            accordion_css_path = Path(temp_dir) / "assets" / "css" / "components" / "accordion.css"
            carousel_css_path = Path(temp_dir) / "assets" / "css" / "components" / "carousel.css"
            js_path = Path(temp_dir) / "assets" / "js" / "accordion.js"
            page_data = Path(temp_dir) / "data" / "page.json"

            self.assertTrue(config_file.exists())
            self.assertTrue(home_content.exists())
            self.assertTrue(base_template.exists())
            self.assertTrue(index_template.exists())
            self.assertTrue(section_partial.exists())
            self.assertTrue(css_path.exists())
            self.assertTrue(link_grid_css_path.exists())
            self.assertTrue(accordion_css_path.exists())
            self.assertTrue(carousel_css_path.exists())
            self.assertTrue(js_path.exists())
            self.assertTrue(page_data.exists())
            self.assertTrue((Path(temp_dir) / "static" / "images").exists())
            self.assertGreaterEqual(len(result.written_files), 7)

            home_content_text = home_content.read_text(encoding="utf-8")
            self.assertIn('title: "Landing Page"', home_content_text)
            self.assertIn('page_key: "page"', home_content_text)
            self.assertIn('stylesheet: "css/main.css"', home_content_text)

            template_content = index_template.read_text(encoding="utf-8")
            self.assertIn('define "main"', template_content)
            self.assertIn('partial "page_region.html"', template_content)
            self.assertIn('partial "resolve_page_data.html"', template_content)

            base_template_content = base_template.read_text(encoding="utf-8")
            self.assertIn('resources.Get "css/site.css"', base_template_content)
            self.assertIn('resources.Get "css/components/link-grid.css"', base_template_content)
            self.assertIn('resources.Get "css/components/accordion.css"', base_template_content)
            self.assertIn('resources.Get "css/components/carousel.css"', base_template_content)
            self.assertIn('resources.Get "js/accordion.js"', base_template_content)

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_renders_valid_link_card_and_accordion_attributes(self) -> None:
        model = {
            "page": {"id": "page", "name": "Components", "width": 800, "height": 700},
            "sections": [
                {
                    "id": "faq",
                    "name": "FAQ",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 280},
                    "children": [
                        {
                            "id": "accordion-faq",
                            "name": "accordion-single-faq",
                            "bounds": {"x": 80, "y": 40, "width": 520, "height": 160},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "accordion-item-1-open",
                                    "name": "accordion-item-1-open",
                                    "bounds": {"x": 80, "y": 40, "width": 520, "height": 72},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "accordion-panel-1",
                                            "name": "accordion-panel-1",
                                            "bounds": {"x": 80, "y": 76, "width": 520, "height": 36},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["answer-1"],
                                        },
                                        {
                                            "id": "accordion-trigger-1",
                                            "name": "accordion-trigger-1",
                                            "bounds": {"x": 80, "y": 40, "width": 520, "height": 36},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["question-1"],
                                        },
                                    ],
                                },
                                {
                                    "id": "accordion-item-2-closed",
                                    "name": "accordion-item-2-closed",
                                    "bounds": {"x": 80, "y": 120, "width": 520, "height": 72},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "accordion-panel-2",
                                            "name": "accordion-panel-2",
                                            "bounds": {"x": 80, "y": 156, "width": 520, "height": 36},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["answer-2"],
                                        },
                                        {
                                            "id": "accordion-trigger-2",
                                            "name": "accordion-trigger-2",
                                            "bounds": {"x": 80, "y": 120, "width": 520, "height": 36},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["question-2"],
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                },
                {
                    "id": "cards",
                    "name": "Cards",
                    "role": "section",
                    "bounds": {"x": 0, "y": 320, "width": 800, "height": 280},
                    "children": [
                        {
                            "id": "href-card-demo",
                            "name": "href-card-demo-external",
                            "bounds": {"x": 80, "y": 360, "width": 320, "height": 160},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": ["card-copy", "card-href", "card-label"],
                        }
                    ],
                },
            ],
            "texts": {
                "question-1": {
                    "id": "question-1",
                    "name": "texte-question-1",
                    "role": "body",
                    "value": "Question 1",
                    "bounds": {"x": 96, "y": 48, "width": 240, "height": 24},
                },
                "answer-1": {
                    "id": "answer-1",
                    "name": "texte-reponse-1",
                    "role": "body",
                    "value": "Reponse 1",
                    "bounds": {"x": 96, "y": 84, "width": 240, "height": 24},
                },
                "question-2": {
                    "id": "question-2",
                    "name": "texte-question-2",
                    "role": "body",
                    "value": "Question 2",
                    "bounds": {"x": 96, "y": 128, "width": 240, "height": 24},
                },
                "answer-2": {
                    "id": "answer-2",
                    "name": "texte-reponse-2",
                    "role": "body",
                    "value": "Reponse 2",
                    "bounds": {"x": 96, "y": 164, "width": 240, "height": 24},
                },
                "card-copy": {
                    "id": "card-copy",
                    "name": "texte-demo",
                    "role": "body",
                    "value": "Project summary",
                    "bounds": {"x": 96, "y": 440, "width": 220, "height": 24},
                },
                "card-href": {
                    "id": "card-href",
                    "name": "href-demo",
                    "role": "body",
                    "value": "https://example.com/demo",
                    "bounds": {"x": 96, "y": 468, "width": 220, "height": 24},
                },
                "card-label": {
                    "id": "card-label",
                    "name": "link-label-demo",
                    "role": "heading",
                    "value": "Demo card",
                    "bounds": {"x": 96, "y": 404, "width": 220, "height": 28},
                },
            },
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")
            html_text = html.unescape(html_content)

            self.assertRegex(
                html_text,
                re.compile(r'<div[^>]*class="content-node node-accordion-single-faq"[^>]*data-accordion="true"', re.S),
            )
            self.assertRegex(
                html_text,
                re.compile(r'<div[^>]*class="content-node node-accordion-item-2-closed"[^>]*data-accordion-item="true"', re.S),
            )
            self.assertIn('data-accordion-open="false"', html_text)
            self.assertIn('aria-hidden="true"', html_text)
            self.assertIn('hidden="hidden"', html_text)
            self.assertRegex(
                html_text,
                re.compile(r'<a[^>]*class="content-node node-href-card-demo-external"[^>]*data-link-card="true"', re.S),
            )
            self.assertNotIn('data-accordion=&#34;true&#34;', html_content)
            self.assertNotIn('href=&#34;https://example.com/demo&#34;', html_content)
            self.assertRegex(
                html_text,
                re.compile(
                    r'<a[^>]*class="content-node node-href-card-demo-external"[^>]*id="href-card-demo"[^>]*data-link-card="true"'
                    r'[^>]*href="https://example.com/demo"[^>]*rel="noopener noreferrer"[^>]*target="_blank"',
                    re.S,
                ),
            )
            self.assertRegex(
                html_text,
                re.compile(r'<h2[^>]*class="content-text text-link-label-demo"[^>]*id="card-label"[^>]*>Demo card</h2>'),
            )
            self.assertIn('href="https://example.com/demo"', html_text)
            self.assertIn('target="_blank"', html_text)
            self.assertIn('rel="noopener noreferrer"', html_text)

    @unittest.skipIf(HUGO_BIN is None, "Hugo binary is required for integration tests")
    def test_hugo_site_renders_named_carousel_markup(self) -> None:
        model = {
            "page": {"id": "page", "name": "Gallery", "width": 1280, "height": 960},
            "sections": [
                {
                    "id": "gallery",
                    "name": "Gallery",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1280, "height": 960},
                    "children": [
                        {
                            "id": "carousel-gallery",
                            "name": "carousel-gallery",
                            "bounds": {"x": 160, "y": 120, "width": 620, "height": 520},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "carousel-stage-gallery",
                                    "name": "carousel-stage-gallery",
                                    "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "carousel-slide-ocean-active",
                                            "name": "carousel-slide-ocean-active",
                                            "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["slide-ocean-image"],
                                        },
                                        {
                                            "id": "carousel-slide-forest",
                                            "name": "carousel-slide-forest",
                                            "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["slide-forest-image"],
                                        },
                                    ],
                                },
                                {
                                    "id": "carousel-thumbs-gallery",
                                    "name": "carousel-thumbs-gallery",
                                    "bounds": {"x": 160, "y": 510, "width": 620, "height": 90},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "carousel-thumb-ocean",
                                            "name": "carousel-thumb-ocean",
                                            "bounds": {"x": 160, "y": 510, "width": 140, "height": 90},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["thumb-ocean-image"],
                                        },
                                        {
                                            "id": "carousel-thumb-forest",
                                            "name": "carousel-thumb-forest",
                                            "bounds": {"x": 320, "y": 510, "width": 140, "height": 90},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["thumb-forest-image"],
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
            "texts": {},
            "assets": [
                {
                    "id": "slide-ocean-image",
                    "name": "image-ocean",
                    "nodeId": "slide-ocean-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/ocean.png",
                    "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                },
                {
                    "id": "slide-forest-image",
                    "name": "image-forest",
                    "nodeId": "slide-forest-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/forest.png",
                    "bounds": {"x": 160, "y": 120, "width": 620, "height": 360},
                },
                {
                    "id": "thumb-ocean-image",
                    "name": "image-thumb-ocean",
                    "nodeId": "thumb-ocean-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/ocean-thumb.png",
                    "bounds": {"x": 160, "y": 510, "width": 140, "height": 90},
                },
                {
                    "id": "thumb-forest-image",
                    "name": "image-thumb-forest",
                    "nodeId": "thumb-forest-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/forest-thumb.png",
                    "bounds": {"x": 320, "y": 510, "width": 140, "height": 90},
                },
            ],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            public_dir = build_hugo_site(model, site_dir)
            html_content = (public_dir / "index.html").read_text(encoding="utf-8")
            css_dir = public_dir / "css"
            css_files = sorted(css_dir.rglob("*.css"))
            self.assertTrue(css_files)
            css_content = "".join(path.read_text(encoding="utf-8") for path in css_files)

            self.assertIn('data-carousel="true"', html_content)
            self.assertIn('data-carousel-stage="true"', html_content)
            self.assertIn('data-carousel-nav="true"', html_content)
            self.assertIn('data-carousel-slide="ocean"', html_content)
            self.assertIn('data-carousel-thumb="forest"', html_content)
            self.assertRegex(
                html_content,
                re.compile(r'<button[^>]*id="carousel-thumb-ocean"[^>]*data-carousel-thumb="ocean"', re.S),
            )
            self.assertIn('[data-carousel-stage=true]{overflow:hidden', css_content.replace('"', ""))
            self.assertIn('[data-carousel-nav=true]{position:relative', css_content.replace('"', ""))

    def test_hugo_generator_generates_component_partials_for_coherent_nodes(self) -> None:
        model = {
            "page": {"id": "page", "name": "Components Page", "width": 1440, "height": 1400},
            "sections": [
                {
                    "id": "content",
                    "name": "Content",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 1440, "height": 1400},
                    "children": [
                        {
                            "id": "accordion-faq",
                            "name": "accordion-single-faq",
                            "bounds": {"x": 120, "y": 120, "width": 800, "height": 260},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                {
                                    "id": "accordion-item-1-open",
                                    "name": "accordion-item-1-open",
                                    "bounds": {"x": 120, "y": 120, "width": 800, "height": 120},
                                    "coordinate_space": "section",
                                    "children_coordinate_space": "section",
                                    "children": [
                                        {
                                            "id": "accordion-panel-1",
                                            "name": "accordion-panel-1",
                                            "bounds": {"x": 120, "y": 120, "width": 800, "height": 40},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["answer-1"],
                                        },
                                        {
                                            "id": "accordion-trigger-1",
                                            "name": "accordion-trigger-1",
                                            "bounds": {"x": 120, "y": 180, "width": 800, "height": 60},
                                            "coordinate_space": "section",
                                            "children_coordinate_space": "section",
                                            "children": ["question-1"],
                                        },
                                    ],
                                }
                            ],
                        },
                        {
                            "id": "href-card-demo",
                            "name": "href-card-demo",
                            "bounds": {"x": 120, "y": 520, "width": 460, "height": 420},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": [
                                "card-copy",
                                "card-label",
                                "card-href",
                                "card-bg",
                                "card-image",
                            ],
                        },
                        {
                            "id": "card-service-demo",
                            "name": "card-service-demo",
                            "bounds": {"x": 640, "y": 520, "width": 420, "height": 320},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": ["service-title", "service-copy"],
                        },
                    ],
                }
            ],
            "texts": {
                "question-1": {
                    "id": "question-1",
                    "name": "texte-question-1",
                    "role": "body",
                    "value": "Question",
                    "bounds": {"x": 120, "y": 180, "width": 420, "height": 40},
                },
                "answer-1": {
                    "id": "answer-1",
                    "name": "texte-reponse-1",
                    "role": "body",
                    "value": "Answer",
                    "bounds": {"x": 120, "y": 120, "width": 420, "height": 40},
                },
                "card-copy": {
                    "id": "card-copy",
                    "name": "texte-demo",
                    "role": "body",
                    "value": "Project summary",
                    "bounds": {"x": 120, "y": 520, "width": 420, "height": 32},
                },
                "card-label": {
                    "id": "card-label",
                    "name": "link-label-demo",
                    "role": "heading",
                    "value": "Project title",
                    "bounds": {"x": 120, "y": 564, "width": 420, "height": 40},
                },
                "card-href": {
                    "id": "card-href",
                    "name": "href-demo",
                    "role": "body",
                    "value": "https://example.com",
                    "bounds": {"x": 120, "y": 612, "width": 420, "height": 20},
                },
                "service-title": {
                    "id": "service-title",
                    "name": "titre-service-demo",
                    "role": "heading",
                    "value": "Service card",
                    "bounds": {"x": 640, "y": 548, "width": 320, "height": 40},
                },
                "service-copy": {
                    "id": "service-copy",
                    "name": "texte-service-demo",
                    "role": "body",
                    "value": "A reusable content card.",
                    "bounds": {"x": 640, "y": 600, "width": 320, "height": 56},
                },
            },
            "assets": [
                {
                    "id": "card-bg",
                    "name": "bg-card-demo",
                    "nodeId": "card-bg",
                    "format": "shape",
                    "renderMode": "shape",
                    "purpose": "background",
                    "bounds": {"x": 120, "y": 640, "width": 460, "height": 280},
                    "style": {"background": "rgb(20 52 203)", "borderRadius": "12px"},
                },
                {
                    "id": "card-image",
                    "name": "image-card-demo",
                    "nodeId": "card-image",
                    "format": "png",
                    "purpose": "content",
                    "local_path": "images/card-demo.png",
                    "bounds": {"x": 120, "y": 640, "width": 460, "height": 280},
                },
            ],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            HugoGenerator().generate(model, temp_dir)

            page_data = json.loads((Path(temp_dir) / "data" / "page.json").read_text(encoding="utf-8"))
            node_template_content = (Path(temp_dir) / "layouts" / "partials" / "node.html").read_text(encoding="utf-8")
            components_root = Path(temp_dir) / "layouts" / "partials" / "components"
            page_css_content = (Path(temp_dir) / "assets" / "css" / "main.css").read_text(encoding="utf-8")
            link_grid_css_content = (
                Path(temp_dir) / "assets" / "css" / "components" / "link-grid.css"
            ).read_text(encoding="utf-8")
            accordion_css_content = (
                Path(temp_dir) / "assets" / "css" / "components" / "accordion.css"
            ).read_text(encoding="utf-8")
            carousel_css_content = (
                Path(temp_dir) / "assets" / "css" / "components" / "carousel.css"
            ).read_text(encoding="utf-8")

            self.assertTrue((components_root / "accordion.html").exists())
            self.assertTrue((components_root / "accordion-item.html").exists())
            self.assertTrue((components_root / "link-card.html").exists())
            self.assertTrue((components_root / "card.html").exists())
            self.assertIn("$node.partial_template", node_template_content)
            self.assertIn("components/accordion.html", json.dumps(page_data))
            self.assertIn("components/accordion-item.html", json.dumps(page_data))
            self.assertIn("components/link-card.html", json.dumps(page_data))
            self.assertIn("components/card.html", json.dumps(page_data))
            self.assertIn('"data-card": "true"', json.dumps(page_data))
            self.assertIn('a.content-node[data-link-card="true"] {', link_grid_css_content)
            self.assertIn('[data-card="true"]', link_grid_css_content)
            self.assertIn('[data-link-grid="true"]', link_grid_css_content)
            self.assertIn("grid-template-columns:", link_grid_css_content)
            self.assertIn("grid-auto-rows: auto;", link_grid_css_content)
            self.assertIn("grid-row: 1;", link_grid_css_content)
            self.assertIn("> figure.content-asset img", link_grid_css_content)
            self.assertIn('[data-accordion-item="true"]', accordion_css_content)
            self.assertIn('[data-carousel-nav="true"]', carousel_css_content)
            self.assertNotIn('a.content-node[data-link-card="true"] {', page_css_content)
            self.assertNotIn("--component-card-padding", link_grid_css_content)
            self.assertNotIn("--component-card-shadow", link_grid_css_content)

    def test_hugo_generator_prefers_custom_component_partial_without_overwriting_it(self) -> None:
        model = {
            "page": {"id": "page", "name": "Components Page", "width": 900, "height": 600},
            "sections": [
                {
                    "id": "content",
                    "name": "Content",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 900, "height": 600},
                    "children": [
                        {
                            "id": "href-card-demo",
                            "name": "href-card-demo",
                            "bounds": {"x": 80, "y": 80, "width": 420, "height": 280},
                            "coordinate_space": "section",
                            "children_coordinate_space": "section",
                            "children": ["card-copy", "card-label", "card-href"],
                        }
                    ],
                }
            ],
            "texts": {
                "card-copy": {
                    "id": "card-copy",
                    "name": "texte-demo",
                    "role": "body",
                    "value": "Project summary",
                    "bounds": {"x": 80, "y": 80, "width": 320, "height": 30},
                },
                "card-label": {
                    "id": "card-label",
                    "name": "link-label-demo",
                    "role": "heading",
                    "value": "Project title",
                    "bounds": {"x": 80, "y": 120, "width": 320, "height": 30},
                },
                "card-href": {
                    "id": "card-href",
                    "name": "href-demo",
                    "role": "body",
                    "value": "https://example.com",
                    "bounds": {"x": 80, "y": 160, "width": 320, "height": 20},
                },
            },
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_partial = (
                Path(temp_dir)
                / "layouts"
                / "partials"
                / "custom"
                / "components"
                / "components-page"
                / "href-card-demo.html"
            )
            custom_partial.parent.mkdir(parents=True, exist_ok=True)
            custom_partial.write_text("CUSTOM CARD PARTIAL\n", encoding="utf-8")

            HugoGenerator().generate(model, temp_dir)

            page_data = json.loads((Path(temp_dir) / "data" / "page.json").read_text(encoding="utf-8"))

            self.assertEqual("CUSTOM CARD PARTIAL\n", custom_partial.read_text(encoding="utf-8"))
            self.assertIn("custom/components/components-page/href-card-demo.html", json.dumps(page_data))

    def test_hugo_generator_preserves_customized_scaffold_templates_on_regenerate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            HugoGenerator().generate(SAMPLE_MODEL, temp_dir)

            node_partial = Path(temp_dir) / "layouts" / "partials" / "node.html"
            custom_content = "{{/* customized node partial */}}\n"
            node_partial.write_text(custom_content, encoding="utf-8")

            HugoGenerator().generate(SAMPLE_MODEL, temp_dir)

            manifest_path = Path(temp_dir) / ".figma2hugo" / "managed-hugo-files.json"
            self.assertEqual(custom_content, node_partial.read_text(encoding="utf-8"))
            self.assertTrue(manifest_path.exists())

    def test_hugo_generator_writes_multi_page_content_data_and_stylesheets(self) -> None:
        about_model = {
            "page": {"id": "about", "name": "About Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "about-hero",
                    "name": "About Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "about-title",
                            "name": "About Title",
                            "role": "heading",
                            "value": "About us",
                            "bounds": {"x": 80, "y": 80, "width": 320, "height": 56},
                        }
                    ],
                    "children": ["about-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }
        contact_model = {
            "page": {"id": "contact", "name": "Contact Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "contact-hero",
                    "name": "Contact Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "contact-title",
                            "name": "Contact Title",
                            "role": "heading",
                            "value": "Contact us",
                            "bounds": {"x": 80, "y": 80, "width": 320, "height": 56},
                        }
                    ],
                    "children": ["contact-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            result = HugoGenerator().generate_many([about_model, contact_model], temp_dir)

            self.assertTrue((Path(temp_dir) / "content" / "_index.md").exists())
            self.assertTrue((Path(temp_dir) / "content" / "about-page.md").exists())
            self.assertTrue((Path(temp_dir) / "content" / "contact-page.md").exists())
            self.assertTrue((Path(temp_dir) / "data" / "pages" / "about-page.json").exists())
            self.assertTrue((Path(temp_dir) / "data" / "pages" / "contact-page.json").exists())
            self.assertTrue((Path(temp_dir) / "data" / "site.json").exists())
            self.assertTrue((Path(temp_dir) / "assets" / "css" / "site.css").exists())
            self.assertTrue((Path(temp_dir) / "assets" / "css" / "pages" / "about-page.css").exists())
            self.assertTrue((Path(temp_dir) / "assets" / "css" / "pages" / "contact-page.css").exists())
            self.assertTrue((Path(temp_dir) / "layouts" / "_default" / "single.html").exists())
            self.assertGreaterEqual(len(result.written_files), 9)

            site_manifest = json.loads((Path(temp_dir) / "data" / "site.json").read_text(encoding="utf-8"))
            self.assertEqual(
                ["about-page", "contact-page"],
                [page["slug"] for page in site_manifest["pages"]],
            )

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_renders_multi_page_regular_pages(self) -> None:
        about_model = {
            "page": {"id": "about", "name": "About Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "about-hero",
                    "name": "About Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "about-title",
                            "name": "About Title",
                            "role": "heading",
                            "value": "About us",
                            "bounds": {"x": 80, "y": 80, "width": 320, "height": 56},
                        }
                    ],
                    "children": ["about-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }
        contact_model = {
            "page": {"id": "contact", "name": "Contact Page", "width": 800, "height": 400},
            "sections": [
                {
                    "id": "contact-hero",
                    "name": "Contact Hero",
                    "role": "section",
                    "bounds": {"x": 0, "y": 0, "width": 800, "height": 400},
                    "texts": [
                        {
                            "id": "contact-title",
                            "name": "Contact Title",
                            "role": "heading",
                            "value": "Contact us",
                            "bounds": {"x": 80, "y": 80, "width": 320, "height": 56},
                        }
                    ],
                    "children": ["contact-title"],
                }
            ],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            site_dir = Path(temp_dir) / "site"
            HugoGenerator().generate_many([about_model, contact_model], site_dir)
            public_dir = site_dir / "public"
            subprocess.run(
                [HUGO_BIN, "--source", str(site_dir), "--destination", str(public_dir), "--quiet"],
                check=True,
                capture_output=True,
                text=True,
            )

            home_html = (public_dir / "index.html").read_text(encoding="utf-8")
            about_html = (public_dir / "about-page" / "index.html").read_text(encoding="utf-8")
            contact_html = (public_dir / "contact-page" / "index.html").read_text(encoding="utf-8")

            self.assertIn("About Page", home_html)
            self.assertIn("Contact Page", home_html)
            self.assertIn("About us", about_html)
            self.assertIn("Contact us", contact_html)
            self.assertRegex(about_html, re.compile(r'href="/css/pages/about-page\.[^"]+\.css"'))

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_uses_sanitized_dom_ids_for_figma_node_ids(self) -> None:
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
                            "id": "6:1092",
                            "name": "Hero Title",
                            "role": "heading",
                            "value": "Hello",
                            "bounds": {"x": 120, "y": 80, "width": 320, "height": 60},
                        }
                    ],
                    "assets": [
                        {
                            "id": "1:240",
                            "name": "bg-hero",
                            "nodeId": "1:240",
                            "format": "svg",
                            "purpose": "background",
                            "local_path": "images/hero-bg.svg",
                            "bounds": {"x": 0, "y": 0, "width": 800, "height": 260},
                        }
                    ],
                    "children": ["1:240", "6:1092"],
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

            self.assertIn('id="id-1-240"', html_content)
            self.assertIn('data-node-id="1:240"', html_content)
            self.assertIn('id="id-6-1092"', html_content)
            self.assertIn('data-node-id="6:1092"', html_content)

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
    def test_hugo_build_uses_root_relative_urls_for_background_assets_in_css(self) -> None:
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
                            "id": "hero-bg",
                            "name": "bg-hero",
                            "nodeId": "hero-bg",
                            "format": "svg",
                            "purpose": "background",
                            "local_path": "images/hero-bg.svg",
                            "bounds": {"x": 0, "y": 0, "width": 800, "height": 260},
                        }
                    ],
                    "children": ["hero-bg"],
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
            css_files = list((public_dir / "css").glob("main*.css"))
            css_content = css_files[0].read_text(encoding="utf-8")

            self.assertIn("background-image:url(/images/hero-bg.svg)", css_content)
            self.assertNotIn("background-image:url(images/hero-bg.svg)", css_content)

    @unittest.skipIf(not HUGO_BIN, "Hugo CLI is not available")
    def test_hugo_build_renders_background_assets_without_escaped_inline_css_quotes(self) -> None:
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
                            "id": "hero-bg",
                            "name": "bg-hero",
                            "nodeId": "hero-bg",
                            "format": "png",
                            "purpose": "background",
                            "local_path": "images/hero-bg.png",
                            "bounds": {"x": 0, "y": 0, "width": 800, "height": 260},
                        }
                    ],
                    "children": ["hero-bg"],
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
            html_text = html.unescape(html_content)

            self.assertIn("style=\"background-image:url('/images/hero-bg.png');\"", html_text)
            self.assertNotIn('\\"/images/hero-bg.png\\"', html_text)

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

            self.assertIn('href="/css/', html_content)
            self.assertIn('src="/images/feature-photo.png"', html_content)
            self.assertIn('src="/images/accent-shape.svg"', html_content)
            self.assertNotIn("<svg", html_content)


if __name__ == "__main__":
    unittest.main()
