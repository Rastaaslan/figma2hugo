from __future__ import annotations

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
