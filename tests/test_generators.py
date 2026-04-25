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
        self.assertIn("white-space: nowrap;", css)

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
            self.assertIn("site.Data.page", template_content)
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

            self.assertIn('src="/images/feature-photo.png"', html_content)
            self.assertIn('src="/images/accent-shape.svg"', html_content)
            self.assertNotIn("<svg", html_content)


if __name__ == "__main__":
    unittest.main()
