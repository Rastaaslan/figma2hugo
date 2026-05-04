from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import figma2hugo.cli as cli_module
from figma2hugo.cli import app

FIGMA_URL = "https://www.figma.com/design/AbCdEf1234567890/Test-Page?node-id=3-964"


def _sample_document(asset_source: str) -> dict[str, object]:
    return {
        "page": {
            "id": "3:964",
            "name": "Landing Page",
            "width": 1440,
            "height": 1800,
            "meta": {
                "figmaUrl": FIGMA_URL,
                "fileKey": "AbCdEf1234567890",
                "nodeId": "3:964",
            },
        },
        "sections": [
            {
                "id": "hero",
                "name": "Hero",
                "role": "header",
                "bounds": {"x": 0, "y": 0, "width": 1440, "height": 720},
                "children": [],
                "texts": ["hero-title"],
                "assets": ["hero-image"],
                "decorativeAssets": [],
            }
        ],
        "texts": {
            "hero-title": {
                "id": "hero-title",
                "name": "Hero Title",
                "value": "Build faster\nwith Hugo",
                "rawValue": "Build faster\nwith Hugo",
                "sectionId": "hero",
                "bounds": {"x": 80, "y": 160, "width": 600, "height": 140},
                "styleRuns": [],
                "tag": "h1",
                "role": "hero-title",
                "style": {"fontFamily": "Georgia", "fontSize": 56},
            }
        },
        "assets": [
            {
                "nodeId": "hero-image",
                "name": "Hero Image",
                "sectionId": "hero",
                "format": "png",
                "localPath": asset_source,
                "function": "content",
                "bounds": {"x": 820, "y": 180, "width": 420, "height": 300},
                "isVector": False,
            }
        ],
        "tokens": {"colors": {}, "spacing": {}, "typography": {}, "shadows": {}, "radii": {}},
        "warnings": [],
    }


class StubExtractionService:
    def __init__(self, document: dict[str, object]) -> None:
        self.document = document

    def inspect(self, figma_url: str, out_dir: str | Path) -> dict[str, object]:
        del figma_url, out_dir
        return {
            "page": self.document["page"],
            "sectionCount": 1,
            "textCount": 1,
            "assetCount": 1,
            "warnings": [],
        }

    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> dict[str, object]:
        del figma_url, out_dir
        return self.document


class MultiPageExtractionService:
    def __init__(self, asset_source: str) -> None:
        self.asset_source = asset_source

    def inspect(self, figma_url: str, out_dir: str | Path) -> dict[str, object]:
        del figma_url, out_dir
        return {"page": {}, "sectionCount": 0, "textCount": 0, "assetCount": 0, "warnings": []}

    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> dict[str, object]:
        del out_dir
        if "About" in figma_url:
            document = _sample_document(self.asset_source)
            document["page"]["name"] = "About Page"
            document["page"]["title"] = "About Page"
            return document
        document = _sample_document(self.asset_source)
        document["page"]["name"] = "Contact Page"
        document["page"]["title"] = "Contact Page"
        return document


def test_inspect_outputs_summary(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli_module,
        "_make_extraction_service",
        lambda: StubExtractionService(_sample_document("C:/tmp/hero.png")),
    )

    result = runner.invoke(app, ["inspect", FIGMA_URL])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["page"]["meta"]["fileKey"] == "AbCdEf1234567890"
    assert payload["sectionCount"] == 1
    assert payload["textCount"] == 1


def test_extract_writes_intermediate_document(monkeypatch) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        asset_source = Path("hero.png")
        asset_source.write_bytes(b"png")
        monkeypatch.setattr(
            cli_module,
            "_make_extraction_service",
            lambda: StubExtractionService(_sample_document(str(asset_source.resolve()))),
        )

        result = runner.invoke(app, ["extract", FIGMA_URL, "--out", "run"])

        assert result.exit_code == 0
        page_json = Path("run/page.json")
        assert page_json.exists()

        document = json.loads(page_json.read_text(encoding="utf-8"))
        assert document["page"]["id"] == "3:964"
        assert document["sections"][0]["id"] == "hero"


def test_generate_validate_and_report_static_site(monkeypatch) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        asset_source = Path("hero.png")
        asset_source.write_bytes(b"png")
        monkeypatch.setattr(
            cli_module,
            "_make_extraction_service",
            lambda: StubExtractionService(_sample_document(str(asset_source.resolve()))),
        )

        generate_result = runner.invoke(
            app,
            ["generate", FIGMA_URL, "dist", "--mode", "static"],
        )
        assert generate_result.exit_code == 0
        assert Path("dist/index.html").exists()
        assert Path("dist/styles.css").exists()
        assert Path("dist/page.json").exists()
        assert Path("dist/report.json").exists()
        assert Path("dist/images/hero.png").exists()

        validate_result = runner.invoke(app, ["validate", "dist"])
        assert validate_result.exit_code == 0
        validate_payload = json.loads(validate_result.stdout)
        assert validate_payload["buildOk"] is True
        assert validate_payload["missingAssets"] == []

        report_result = runner.invoke(app, ["report", "dist"])
        assert report_result.exit_code == 0
        report_payload = json.loads(report_result.stdout)
        assert report_payload["buildOk"] is True


def test_build_generates_hugo_site_with_url_and_destination_only(monkeypatch) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        asset_source = Path("hero.png")
        asset_source.write_bytes(b"png")
        monkeypatch.setattr(
            cli_module,
            "_make_extraction_service",
            lambda: StubExtractionService(_sample_document(str(asset_source.resolve()))),
        )

        result = runner.invoke(app, ["build", FIGMA_URL, "site"])

        assert result.exit_code == 0
        assert Path("site/layouts/index.html").exists()
        assert Path("site/assets/css/main.css").exists()
        assert Path("site/data/page.json").exists()
        assert Path("site/report.json").exists()


def test_build_site_generates_multi_page_hugo_output(monkeypatch) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        asset_source = Path("hero.png")
        asset_source.write_bytes(b"png")
        monkeypatch.setattr(
            cli_module,
            "_make_extraction_service",
            lambda: MultiPageExtractionService(str(asset_source.resolve())),
        )

        result = runner.invoke(
            app,
            [
                "build-site",
                "site",
                "--page",
                "https://www.figma.com/design/AbCdEf1234567890/About?node-id=1-1",
                "--page",
                "https://www.figma.com/design/AbCdEf1234567890/Contact?node-id=1-2",
            ],
        )

        assert result.exit_code == 0
        assert Path("site/layouts/_default/single.html").exists()
        assert Path("site/assets/css/site.css").exists()
        assert Path("site/assets/css/pages/about-page.css").exists()
        assert Path("site/assets/css/pages/contact-page.css").exists()
        assert Path("site/content/about-page.md").exists()
        assert Path("site/content/contact-page.md").exists()
        assert Path("site/data/pages/about-page.json").exists()
        assert Path("site/data/pages/contact-page.json").exists()
        assert Path("site/data/site.json").exists()
        assert Path("site/report.json").exists()


def test_ui_command_launches_desktop_app(monkeypatch) -> None:
    runner = CliRunner()
    launched = {"called": False}

    monkeypatch.setattr(
        cli_module,
        "_launch_ui",
        lambda: launched.__setitem__("called", True),
    )

    result = runner.invoke(app, ["ui"])

    assert result.exit_code == 0
    assert launched["called"] is True
