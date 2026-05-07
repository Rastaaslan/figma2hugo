from __future__ import annotations

import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from figma2hugo.generators import HugoGenerator, StaticGenerator
from figma2hugo.validator import SiteValidator

HUGO_BIN = shutil.which("hugo")
ROOT = Path(__file__).resolve().parents[1]


def test_validator_accepts_generated_canonical_page_model_without_intermediate_warning() -> None:
    model = {
        "page": {"id": "page", "name": "Page", "width": 960, "height": 480},
        "sections": [
            {
                "id": "intro",
                "name": "Intro",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 960, "height": 480},
                "texts": [
                    {
                        "id": "intro-copy",
                        "name": "Intro Copy",
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
                "children": ["intro-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        StaticGenerator().generate(model, target_dir)

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["buildOk"] is True
        assert report["missingTexts"] == []
        assert all("Intermediate document validation failed" not in warning for warning in report["warnings"])


def test_validator_matches_visible_text_split_across_spans_before_punctuation() -> None:
    model = {
        "page": {"id": "page", "name": "Page", "width": 960, "height": 480},
        "sections": [
            {
                "id": "contact",
                "name": "Contact",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 960, "height": 480},
                "texts": [
                    {
                        "id": "contact-copy",
                        "name": "Contact Copy",
                        "role": "body",
                        "value": "Office hours: 7.30am to 4.30pm, Mon - Fri",
                        "style": {"fontFamily": "Inter", "fontSize": 18, "fontWeight": 400},
                        "styleRuns": [
                            {
                                "start": 0,
                                "end": 12,
                                "style": {"fontFamily": "Inter", "fontSize": 24, "fontWeight": 700},
                            }
                        ],
                    }
                ],
                "children": ["contact-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        StaticGenerator().generate(model, target_dir)

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["missingTexts"] == []


def test_validator_accepts_form_placeholder_and_option_text_as_rendered_controls() -> None:
    html_content = """
    <!DOCTYPE html>
    <html>
      <body>
        <form>
          <input placeholder="Nom et Prénom">
          <select>
            <option value="formation">Formation</option>
          </select>
        </form>
      </body>
    </html>
    """
    page_model = {
        "texts": {
            "placeholder-name": {
                "id": "placeholder-name",
                "name": "placeholder-nom-prenom",
                "value": "Nom et Prénom",
            },
            "option-training": {
                "id": "option-training",
                "name": "option-demande-formation",
                "value": "formation|Formation",
            },
            "missing-copy": {
                "id": "missing-copy",
                "name": "texte-missing",
                "value": "Plain visible copy",
            },
        }
    }

    assert SiteValidator()._missing_texts(html_content, page_model) == ["missing-copy"]


def test_validator_accepts_inline_span_splits_and_href_attributes() -> None:
    html_content = """
    <!DOCTYPE html>
    <html>
      <body>
        <h3>Qui de mieux que nos projets <span>pour parler de n</span><span>otre expertise ?</span></h3>
        <a href="https://example.com/projet">Voir le projet</a>
      </body>
    </html>
    """
    page_model = {
        "texts": {
            "split-heading": {
                "id": "split-heading",
                "name": "titre-split",
                "value": "Qui de mieux que nos projets pour parler de notre expertise ?",
            },
            "href-project": {
                "id": "href-project",
                "name": "href-projet",
                "value": "https://example.com/projet",
            },
        }
    }

    assert SiteValidator()._missing_texts(html_content, page_model) == []


@pytest.mark.skipif(not HUGO_BIN, reason="Hugo CLI is not available")
def test_validator_reads_real_hugo_build_output_in_public_directory() -> None:
    model = {
        "page": {"id": "page", "name": "Page", "width": 960, "height": 480},
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "hero",
                "bounds": {"x": 0, "y": 0, "width": 960, "height": 240},
                "texts": [
                    {
                        "id": "hero-copy",
                        "name": "Hero Copy",
                        "role": "heading",
                        "value": "Build faster\nwith Hugo",
                        "style": {"fontFamily": "Inter", "fontSize": 18, "fontWeight": 400},
                        "styleRuns": [
                            {
                                "start": 0,
                                "end": 12,
                                "style": {"fontFamily": "Inter", "fontSize": 28, "fontWeight": 700},
                            }
                        ],
                    }
                ],
                "children": ["hero-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        HugoGenerator().generate(model, target_dir)

        report = SiteValidator().validate(target_dir, mode="hugo")

        assert report["buildOk"] is True
        assert report["missingTexts"] == []
        assert (target_dir / "public" / "index.html").exists()


def test_validator_serves_generated_pages_over_http_for_visual_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = SiteValidator()

    with tempfile.TemporaryDirectory() as temp_dir:
        public_dir = Path(temp_dir) / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        html_path = public_dir / "index.html"
        html_path.write_text(
            '<!DOCTYPE html><html><body><img src="/images/example.png" alt="example"></body></html>',
            encoding="utf-8",
        )

        captured: dict[str, str] = {}

        def fake_capture(url: str, screenshot_path: Path) -> None:
            captured["url"] = url
            captured["html"] = urllib.request.urlopen(url).read().decode("utf-8")
            screenshot_path.write_bytes(b"placeholder")

        monkeypatch.setattr(validator, "_capture_url", fake_capture)

        validator._capture_page(html_path, Path(temp_dir) / "capture.png")

        assert captured["url"].startswith("http://127.0.0.1:")
        assert captured["url"].endswith("/index.html")
        assert 'src="/images/example.png"' in captured["html"]


def test_validator_serves_relative_html_paths_over_http_for_visual_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = SiteValidator()

    scratch_root = ROOT / ".figma2hugo-scratch" / "tests"
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(scratch_root)) as temp_dir:
        public_dir = Path(temp_dir) / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        html_path = public_dir / "index.html"
        html_path.write_text("<!DOCTYPE html><html><body>hello</body></html>", encoding="utf-8")

        captured: dict[str, str] = {}

        def fake_capture(url: str, screenshot_path: Path) -> None:
            captured["url"] = url
            captured["html"] = urllib.request.urlopen(url).read().decode("utf-8")
            screenshot_path.write_bytes(b"placeholder")

        monkeypatch.setattr(validator, "_capture_url", fake_capture)

        relative_html_path = html_path.relative_to(ROOT)
        validator._capture_page(relative_html_path, Path(temp_dir) / "capture.png")

        assert captured["url"].startswith("http://127.0.0.1:")
        assert captured["url"].endswith("/index.html")
        assert "hello" in captured["html"]


def test_validator_reports_supported_scope_and_responsive_viewports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = {
        "page": {"id": "page", "name": "Responsive Probe", "width": 960, "height": 480},
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 960, "height": 480},
                "texts": [
                    {
                        "id": "hero-copy",
                        "name": "Hero Copy",
                        "role": "heading",
                        "value": "Responsive probe",
                    }
                ],
                "children": ["hero-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        StaticGenerator().generate(model, target_dir)

        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: True)
        monkeypatch.setattr(
            SiteValidator,
            "_probe_responsive_page",
            lambda self, html_path, viewport: {
                "scrollWidth": int(viewport["width"]),
                "clientWidth": int(viewport["width"]),
                "horizontalOverflow": False,
                "brokenImages": 0,
                "pageShell": "fixed",
                "pageFlow": "false",
            },
        )
        monkeypatch.setattr(
            SiteValidator,
            "_probe_interactions_page",
            lambda self, html_path, viewport: {"checks": []},
        )

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["supportedScope"]["strategy"] == "desktop-first-with-flow-components"
        assert any(
            "responsive multi-variant Hugo pages are merged" in item
            for item in report["supportedScope"]["guarantees"]
        )
        assert any(
            "fixed responsive shells compact sparse sections" in item
            for item in report["supportedScope"]["guarantees"]
        )
        assert "breakpoint merging from multiple Figma page variants" not in report["supportedScope"]["notGuaranteedYet"]
        assert report["responsive"]["available"] is True
        assert report["responsive"]["checked"] is True
        assert len(report["responsive"]["viewports"]) == len(SiteValidator.RESPONSIVE_VIEWPORTS)
        assert report["responsive"]["summary"]["totalViewports"] == len(SiteValidator.RESPONSIVE_VIEWPORTS)
        assert report["responsive"]["summary"]["familyCount"] == 0
        assert report["responsive"]["warnings"] == []


def test_validator_flags_horizontal_overflow_in_responsive_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = {
        "page": {"id": "page", "name": "Responsive Overflow", "width": 960, "height": 480},
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 960, "height": 480},
                "texts": [{"id": "hero-copy", "name": "Hero Copy", "role": "heading", "value": "Overflow"}],
                "children": ["hero-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        StaticGenerator().generate(model, target_dir)

        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: True)

        def fake_responsive_probe(self: SiteValidator, html_path: Path, viewport: dict[str, int | str]) -> dict[str, object]:
            is_mobile = int(viewport["width"]) == 402
            return {
                "scrollWidth": 520 if is_mobile else int(viewport["width"]),
                "clientWidth": int(viewport["width"]),
                "horizontalOverflow": is_mobile,
                "brokenImages": 0,
                "pageShell": "fixed",
                "pageFlow": "false",
            }

        monkeypatch.setattr(SiteValidator, "_probe_responsive_page", fake_responsive_probe)
        monkeypatch.setattr(
            SiteValidator,
            "_probe_interactions_page",
            lambda self, html_path, viewport: {"checks": []},
        )

        report = SiteValidator().validate(target_dir, mode="static")
        mobile_rows = [row for row in report["responsive"]["viewports"] if row["width"] == 402]

        assert mobile_rows
        assert "horizontal-overflow" in mobile_rows[0]["issues"]
        assert report["responsive"]["summary"]["horizontalOverflowCount"] == 1


def test_validator_collects_interaction_probe_results(monkeypatch: pytest.MonkeyPatch) -> None:
    model = {
        "page": {"id": "page", "name": "Interaction Probe", "width": 960, "height": 480},
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 960, "height": 480},
                "texts": [{"id": "hero-copy", "name": "Hero Copy", "role": "heading", "value": "Interactions"}],
                "children": ["hero-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        StaticGenerator().generate(model, target_dir)

        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: True)
        monkeypatch.setattr(
            SiteValidator,
            "_probe_responsive_page",
            lambda self, html_path, viewport: {
                "scrollWidth": int(viewport["width"]),
                "clientWidth": int(viewport["width"]),
                "horizontalOverflow": False,
                "brokenImages": 0,
                "pageShell": "fixed",
                "pageFlow": "false",
            },
        )
        monkeypatch.setattr(
            SiteValidator,
            "_probe_interactions_page",
            lambda self, html_path, viewport: {
                "checks": [
                    {"component": "accordion", "status": "pass", "issues": []},
                    {"component": "link-card", "status": "pass", "issues": []},
                    {"component": "carousel", "status": "skipped", "issues": ["not-present"]},
                ]
            },
        )

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["interactions"]["available"] is True
        assert report["interactions"]["checked"] is True
        assert len(report["interactions"]["pages"]) == 1
        first_viewport = report["interactions"]["pages"][0]["viewports"][0]
        assert any(check["component"] == "accordion" and check["status"] == "pass" for check in first_viewport["checks"])
        assert report["interactions"]["summary"]["passedChecks"] >= 2


def test_validator_reports_responsive_family_metadata_for_merged_hugo_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop_model = {
        "page": {"id": "landing-1920", "name": "Landing Page 1920", "width": 1920, "height": 900},
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 520},
                "texts": [
                    {
                        "id": "hero-title",
                        "name": "Hero Title",
                        "role": "heading",
                        "value": "Hello shared",
                        "bounds": {"x": 120, "y": 72, "width": 560, "height": 88},
                    },
                    {
                        "id": "hero-copy",
                        "name": "Hero Copy",
                        "role": "body",
                        "value": "Shared layout copy",
                        "bounds": {"x": 120, "y": 188, "width": 420, "height": 60},
                    },
                ],
                "children": ["hero-title", "hero-copy"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }
    mobile_model = {
        "page": {"id": "landing-390", "name": "Landing Page 390", "width": 390, "height": 900},
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": 390, "height": 620},
                "texts": [
                    {
                        "id": "hero-title",
                        "name": "Hero Title",
                        "role": "heading",
                        "value": "Hello shared",
                        "bounds": {"x": 24, "y": 40, "width": 240, "height": 92},
                    },
                    {
                        "id": "hero-copy",
                        "name": "Hero Copy",
                        "role": "body",
                        "value": "Shared layout copy",
                        "bounds": {"x": 24, "y": 152, "width": 240, "height": 72},
                    },
                    {
                        "id": "hero-mobile-note",
                        "name": "Hero Mobile Note",
                        "role": "body",
                        "value": "Visible only on mobile",
                        "bounds": {"x": 24, "y": 252, "width": 220, "height": 48},
                    },
                ],
                "children": ["hero-title", "hero-copy", "hero-mobile-note"],
            }
        ],
        "texts": {},
        "assets": [],
        "tokens": {},
        "warnings": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        HugoGenerator().generate_many([desktop_model, mobile_model], target_dir)

        def fake_hugo_build(self: SiteValidator, site_dir: Path, warnings: list[str]) -> bool:
            page_dir = site_dir / "public" / "landing-page"
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(
                "<html><body>Hello shared Shared layout copy Visible only on mobile</body></html>",
                encoding="utf-8",
            )
            return True

        monkeypatch.setattr(SiteValidator, "_validate_hugo_build", fake_hugo_build)
        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: False)

        report = SiteValidator().validate(target_dir, mode="hugo")

        assert report["buildOk"] is True
        assert report["missingTexts"] == []
        assert report["responsive"]["available"] is False
        assert report["responsive"]["checked"] is False
        assert report["responsive"]["summary"]["familyCount"] == 1
        assert report["responsive"]["summary"]["familiesWithWarnings"] == 0
        assert report["responsive"]["summary"]["strictReadyFamilyCount"] == 1
        assert report["responsive"]["families"] == [
            {
                "page": "landing-page",
                "family": "landing-page",
                "baseWidth": 1920,
                "breakpoints": [390],
                "sourceWidths": [1920, 390],
                "variantCount": 1,
                "warnings": [],
                "issues": [],
                "strictReady": True,
            }
        ]


def test_validator_classifies_responsive_warning_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate_warning = (
        "Responsive variant 402px reuses sibling token 'text:heading:titre-h2-hero' "
        "under 'page/section:header:section-hero#1'. Matching will rely on sibling "
        "order; keep ordering stable or rename duplicates."
    )
    text_change_warning = (
        "Responsive variant 402px changes text content for "
        "page/section:section:hero#1/text:body:copy#1. Duplicate the item as a "
        "breakpoint-specific layer if different copy is intended."
    )
    board_split_warning = (
        "Responsive board split from selected node into variant landing-page-402."
    )
    repeated_component_warning = (
        "Responsive variant 402px treats repeated sibling token 'node:card:feature-card' "
        "under 'page/section:section:features#1' as a repeated component group with 3 items."
    )
    page_model = {
        "page": {"id": "landing-page", "slug": "landing-page", "width": 1920},
        "sections": [],
        "texts": {},
        "assets": [],
        "warnings": [
            duplicate_warning,
            text_change_warning,
            board_split_warning,
            repeated_component_warning,
        ],
        "responsive": {
            "family": "landing-page",
            "base_width": 1920,
            "breakpoints": [402],
            "variants": [{"width": 402, "page": {"page": {"slug": "landing-page-402"}}}],
        },
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        (target_dir / "index.html").write_text(
            "<!DOCTYPE html><html><body>ok</body></html>",
            encoding="utf-8",
        )
        (target_dir / "page.json").write_text(json.dumps(page_model), encoding="utf-8")
        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: False)

        report = SiteValidator().validate(target_dir, mode="static")

    family = report["responsive"]["families"][0]
    issue_types = [issue["type"] for issue in family["issues"]]

    assert family["strictReady"] is False
    assert issue_types == [
        "duplicate-sibling-token",
        "text-content-change",
        "board-split",
        "repeated-component-token",
    ]
    assert family["issues"][0]["severity"] == "strict-blocker"
    assert family["issues"][0]["width"] == 402
    assert family["issues"][0]["token"] == "text:heading:titre-h2-hero"
    assert family["issues"][1]["severity"] == "review"
    assert family["issues"][2]["variant"] == "landing-page-402"
    assert family["issues"][3]["severity"] == "info"
    assert family["issues"][3]["count"] == 3
    assert report["responsive"]["summary"]["issueCount"] == 4
    assert report["responsive"]["summary"]["strictBlockingIssueCount"] == 1
    assert report["responsive"]["summary"]["strictBlockingFamilyCount"] == 1
    assert report["responsive"]["summary"]["strictReadyFamilyCount"] == 0
    assert report["responsive"]["summary"]["duplicateSiblingTokenCount"] == 1
    assert report["responsive"]["summary"]["repeatedComponentTokenCount"] == 1
    assert report["responsive"]["summary"]["textContentChangeCount"] == 1
    assert report["responsive"]["summary"]["boardSplitCount"] == 1


def test_validator_handles_missing_html_without_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        (target_dir / "page.json").write_text(
            '{"page":{"id":"page","slug":"page"},"sections":[],"texts":{},"assets":[],"warnings":[]}',
            encoding="utf-8",
        )

        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: False)

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["missingTexts"] == ["html-missing"]
        assert any("Generated HTML file is missing" in warning for warning in report["warnings"])


def test_validator_handles_missing_page_model_without_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        (target_dir / "index.html").write_text("<!DOCTYPE html><html><body>ok</body></html>", encoding="utf-8")

        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: False)

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["buildOk"] is True
        assert any("Missing generated page model" in warning for warning in report["warnings"])
        assert any("No generated page model is available for validation." in warning for warning in report["warnings"])


def test_validator_handles_invalid_page_model_json_without_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        (target_dir / "page.json").write_text("{ invalid", encoding="utf-8")
        (target_dir / "index.html").write_text("<!DOCTYPE html><html><body>ok</body></html>", encoding="utf-8")

        monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: False)

        report = SiteValidator().validate(target_dir, mode="static")

        assert report["buildOk"] is True
        assert any("Invalid JSON in generated page model" in warning for warning in report["warnings"])


def test_validator_serves_nested_public_pages_from_public_root(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = SiteValidator()

    with tempfile.TemporaryDirectory() as temp_dir:
        public_dir = Path(temp_dir) / "public"
        nested_dir = public_dir / "page-slug"
        nested_dir.mkdir(parents=True, exist_ok=True)
        html_path = nested_dir / "index.html"
        html_path.write_text("<!DOCTYPE html><html><body>nested</body></html>", encoding="utf-8")

        captured: dict[str, str] = {}

        def fake_capture(url: str, screenshot_path: Path) -> None:
            captured["url"] = url
            screenshot_path.write_bytes(b"placeholder")

        monkeypatch.setattr(validator, "_capture_url", fake_capture)

        validator._capture_page(html_path, Path(temp_dir) / "capture.png")

        assert captured["url"].startswith("http://127.0.0.1:")
        assert captured["url"].endswith("/page-slug/index.html")
