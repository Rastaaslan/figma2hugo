from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

import figma2hugo.workflow as workflow_module
from figma2hugo.config import OutputMode
from figma2hugo.validator import SiteValidator
from figma2hugo.workflow import GenerationOptions, run_generation

FIGMA_URL = "https://www.figma.com/design/AbCdEf1234567890/Test-Page?node-id=3-964"
HUGO_BIN = shutil.which("hugo")


class FailingExtractionService:
    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> dict[str, object]:
        del figma_url
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        Path(out_dir, "raw", "marker.txt").write_text("started", encoding="utf-8")
        raise RuntimeError("boom")


class SuccessfulExtractionService:
    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> dict[str, object]:
        del figma_url
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        Path(out_dir, "raw", "marker.txt").write_text("started", encoding="utf-8")
        return {
            "page": {"id": "page", "name": "Page", "width": 800, "height": 600, "meta": {}},
            "sections": [],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }


@dataclass
class FakeArtifacts:
    written_files: tuple[Path, ...]
    page_data: dict[str, object]


class FakeGenerator:
    def generate(self, document, out_dir: Path) -> FakeArtifacts:
        del document
        out_dir.mkdir(parents=True, exist_ok=True)
        index = out_dir / "index.html"
        index.write_text("<html></html>", encoding="utf-8")
        return FakeArtifacts(written_files=(index,), page_data={})


class StrictEnvCapturingGenerator(FakeGenerator):
    def __init__(self) -> None:
        self.strict_values: list[str | None] = []

    def generate(self, document, out_dir: Path) -> FakeArtifacts:
        self.strict_values.append(os.getenv("FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING"))
        return super().generate(document, out_dir)


class FakeMultiGenerator:
    def generate_many(self, documents, out_dir: Path) -> FakeArtifacts:
        del documents
        out_dir.mkdir(parents=True, exist_ok=True)
        index = out_dir / "index.html"
        about = out_dir / "about" / "index.html"
        about.parent.mkdir(parents=True, exist_ok=True)
        index.write_text("<html></html>", encoding="utf-8")
        about.write_text("<html></html>", encoding="utf-8")
        return FakeArtifacts(written_files=(index, about), page_data={})


class FakeValidator:
    def validate(
        self,
        target_dir: Path,
        *,
        mode: str,
        against_reference: Path | None = None,
    ) -> dict[str, object]:
        del target_dir, mode, against_reference
        return {
            "build_ok": True,
            "visual_score": None,
            "missing_assets": [],
            "missing_texts": [],
            "warnings": [],
        }


class FakeReportWriter:
    def write(self, target_dir: Path, payload: dict[str, object]) -> None:
        Path(target_dir, "report.json").write_text("{}", encoding="utf-8")
        del payload


class SuccessfulMultiExtractionService:
    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> dict[str, object]:
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        page_name = "About Page" if "about" in figma_url else "Contact Page"
        Path(out_dir, "raw", f"{page_name}.txt").write_text("started", encoding="utf-8")
        return {
            "page": {
                "id": page_name.lower().replace(" ", "-"),
                "name": page_name,
                "width": 800,
                "height": 600,
                "meta": {},
            },
            "sections": [],
            "texts": {},
            "assets": [],
            "tokens": {},
            "warnings": [],
        }


class SuccessfulResponsiveBoardExtractionService:
    def extract_documents(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> list[dict[str, object]]:
        del figma_url
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        Path(out_dir, "raw", "board.txt").write_text("started", encoding="utf-8")
        return [
            {
                "page": {
                    "id": "legal-1920",
                    "name": "page-mentions-legales-1920",
                    "width": 1920,
                    "height": 1080,
                    "meta": {},
                },
                "sections": [],
                "texts": {},
                "assets": [],
                "tokens": {},
                "warnings": [],
            },
            {
                "page": {
                    "id": "legal-402",
                    "name": "page-mentions-legales-402",
                    "width": 402,
                    "height": 1600,
                    "meta": {},
                },
                "sections": [],
                "texts": {},
                "assets": [],
                "tokens": {},
                "warnings": [],
            },
        ]


class ProductionLikeBoardExtractionService:
    def extract_documents(
        self,
        figma_url: str,
        out_dir: str | Path,
    ) -> list[dict[str, object]]:
        del figma_url
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        Path(out_dir, "raw", "production-board.txt").write_text("started", encoding="utf-8")
        return [
            _production_page(
                slug="page-services-1920",
                title="Services",
                width=1920,
                height=920,
                headline="Services built for teams",
                copy="Strategy, design and delivery in one workflow.",
                x=160,
                y=96,
                text_width=780,
            ),
            _production_page(
                slug="page-services-402",
                title="Services",
                width=402,
                height=860,
                headline="Services built for teams",
                copy="Strategy, design and delivery in one workflow.",
                x=24,
                y=48,
                text_width=320,
            ),
            _production_page(
                slug="contact-page",
                title="Contact Page",
                width=1280,
                height=720,
                headline="Contact us",
                copy="Tell us where the next Figma page should go.",
                x=96,
                y=88,
                text_width=540,
            ),
        ]


def _production_page(
    *,
    slug: str,
    title: str,
    width: int,
    height: int,
    headline: str,
    copy: str,
    x: int,
    y: int,
    text_width: int,
) -> dict[str, object]:
    return {
        "page": {
            "id": slug,
            "name": slug,
            "width": width,
            "height": height,
            "meta": {"fixture": "production-like"},
        },
        "sections": [
            {
                "id": f"{slug}-hero",
                "name": f"{title} Hero",
                "role": "section",
                "bounds": {"x": 0, "y": 0, "width": width, "height": height},
                "texts": [f"{slug}-title", f"{slug}-copy"],
                "children": [f"{slug}-title", f"{slug}-copy"],
            }
        ],
        "texts": {
            f"{slug}-title": {
                "id": f"{slug}-title",
                "name": "Hero Title",
                "value": headline,
                "section_id": f"{slug}-hero",
                "bounds": {"x": x, "y": y, "width": text_width, "height": 88},
                "style": {"fontFamily": "Inter", "fontSize": 48, "fontWeight": 700},
            },
            f"{slug}-copy": {
                "id": f"{slug}-copy",
                "name": "Hero Copy",
                "value": copy,
                "section_id": f"{slug}-hero",
                "bounds": {"x": x, "y": y + 118, "width": text_width, "height": 72},
                "style": {"fontFamily": "Inter", "fontSize": 20, "fontWeight": 400},
            },
        },
        "assets": [],
        "tokens": {
            "colors": {"brand": {"value": "#1434cb"}},
            "spacing": {},
            "typography": {},
        },
        "warnings": [],
    }


def test_run_generation_persists_debug_artifacts_on_failure(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        with pytest.raises(RuntimeError) as exc_info:
            run_generation(
                GenerationOptions(
                    figma_url=FIGMA_URL,
                    out=temp_path / "site",
                    mode=OutputMode.STATIC,
                ),
                extraction_service=FailingExtractionService(),
            )

        message = str(exc_info.value)
        assert "Generation failed during extracting Figma data" in message
        assert "Debug files written to:" in message

        debug_root = temp_path / "site" / ".figma2hugo-debug"
        debug_runs = list(debug_root.glob("generation-*"))
        assert len(debug_runs) == 1

        debug_dir = debug_runs[0]
        assert (debug_dir / "summary.json").exists()
        assert (debug_dir / "traceback.txt").exists()
        assert (debug_dir / "workspace" / "raw" / "marker.txt").exists()
        assert not (temp_path / "site" / ".figma2hugo-tmp").exists()


def test_run_generation_cleans_destination_temp_workspace_on_success(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: FakeGenerator())

        result = run_generation(
            GenerationOptions(
                figma_url=FIGMA_URL,
                out=temp_path / "site",
                mode=OutputMode.STATIC,
            ),
            extraction_service=SuccessfulExtractionService(),
            validator=FakeValidator(),
            report_writer=FakeReportWriter(),
        )

        assert result["buildOk"] is True
        assert not (temp_path / "site" / ".figma2hugo-tmp").exists()
        assert (temp_path / "site" / "index.html").exists()


def test_run_generation_strict_responsive_matching_sets_env_temporarily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        generator = StrictEnvCapturingGenerator()
        monkeypatch.delenv("FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING", raising=False)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: generator)

        result = run_generation(
            GenerationOptions(
                figma_url=FIGMA_URL,
                out=temp_path / "site",
                mode=OutputMode.STATIC,
                strict_responsive_matching=True,
            ),
            extraction_service=SuccessfulExtractionService(),
            validator=FakeValidator(),
            report_writer=FakeReportWriter(),
        )

        assert result["strictResponsiveMatching"] is True
        assert generator.strict_values == ["1"]
        assert os.getenv("FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING") is None


def test_run_generation_supports_multi_page_hugo_sites(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: FakeMultiGenerator())

        result = run_generation(
            GenerationOptions(
                figma_url="https://www.figma.com/design/AbCdEf1234567890/About?node-id=1-1",
                figma_urls=(
                    "https://www.figma.com/design/AbCdEf1234567890/About?node-id=1-1",
                    "https://www.figma.com/design/AbCdEf1234567890/Contact?node-id=1-2",
                ),
                out=temp_path / "site",
                mode=OutputMode.HUGO,
            ),
            extraction_service=SuccessfulMultiExtractionService(),
            validator=FakeValidator(),
            report_writer=FakeReportWriter(),
        )

        assert result["buildOk"] is True
        assert not (temp_path / "site" / ".figma2hugo-tmp").exists()
        assert (temp_path / "site" / "index.html").exists()
        assert (temp_path / "site" / "about" / "index.html").exists()


def test_run_generation_supports_single_url_responsive_board_split(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: FakeMultiGenerator())

        result = run_generation(
            GenerationOptions(
                figma_url="https://www.figma.com/design/AbCdEf1234567890/Mentions?node-id=200-1",
                out=temp_path / "site",
                mode=OutputMode.HUGO,
            ),
            extraction_service=SuccessfulResponsiveBoardExtractionService(),
            validator=FakeValidator(),
            report_writer=FakeReportWriter(),
        )

        assert result["buildOk"] is True
        assert not (temp_path / "site" / ".figma2hugo-tmp").exists()
        assert (temp_path / "site" / "index.html").exists()
        assert (temp_path / "site" / "about" / "index.html").exists()


def test_run_generation_rejects_single_url_responsive_board_split_in_static_mode(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: FakeGenerator())

        with pytest.raises(
            RuntimeError,
            match="Multi-page generation is only supported in Hugo mode.",
        ):
            run_generation(
                GenerationOptions(
                    figma_url="https://www.figma.com/design/AbCdEf1234567890/Mentions?node-id=200-1",
                    out=temp_path / "site",
                    mode=OutputMode.STATIC,
                ),
                extraction_service=SuccessfulResponsiveBoardExtractionService(),
                validator=FakeValidator(),
                report_writer=FakeReportWriter(),
            )


def test_run_generation_deduplicates_report_warnings(monkeypatch) -> None:
    class WarningValidator:
        def validate(
            self,
            target_dir: Path,
            *,
            mode: str,
            against_reference: Path | None = None,
        ) -> dict[str, object]:
            del target_dir, mode, against_reference
            return {
                "build_ok": True,
                "visual_score": None,
                "missing_assets": [],
                "missing_texts": [],
                "warnings": ["duplicate", "duplicate", "contentMode=data_file"],
            }

    class CapturingReportWriter:
        def __init__(self) -> None:
            self.payload: dict[str, object] | None = None

        def write(self, target_dir: Path, payload: dict[str, object]) -> None:
            del target_dir
            self.payload = payload

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: FakeGenerator())
        report_writer = CapturingReportWriter()

        run_generation(
            GenerationOptions(
                figma_url=FIGMA_URL,
                out=temp_path / "site",
                mode=OutputMode.STATIC,
            ),
            extraction_service=SuccessfulExtractionService(),
            validator=WarningValidator(),
            report_writer=report_writer,
        )

        assert report_writer.payload is not None
        warnings = list(report_writer.payload.get("warnings", []))
        assert warnings.count("duplicate") == 1
        assert warnings.count("contentMode=data_file") == 1


def test_run_generation_emits_progress_events(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        monkeypatch.setattr(workflow_module, "_select_generator", lambda mode: FakeGenerator())
        progress_events: list[dict[str, object]] = []

        result = run_generation(
            GenerationOptions(
                figma_url=FIGMA_URL,
                out=temp_path / "site",
                mode=OutputMode.STATIC,
            ),
            extraction_service=SuccessfulExtractionService(),
            validator=FakeValidator(),
            report_writer=FakeReportWriter(),
            progress_callback=progress_events.append,
        )

        assert result["buildOk"] is True
        stages = [str(event.get("stage")) for event in progress_events]
        assert stages == [
            "initialization",
            "extracting Figma data",
            "extracting Figma data",
            "validating the intermediate model for page 1/1",
            "generating the output site",
            "validating the generated site",
            "writing generation report",
        ]
        assert any("Workspace initialise" in str(event.get("message")) for event in progress_events)
        assert any(
            "Validation du site genere" in str(event.get("message"))
            for event in progress_events
        )
        assert progress_events[0]["output_dir"] == str(temp_path / "site")
        assert progress_events[1]["source_label"] == "Test-Page (node 3:964)"
        assert progress_events[2]["document_names"] == ["Page"]
        assert progress_events[3]["document_name"] == "Page"
        assert progress_events[3]["breakpoint_width"] == 800
        assert progress_events[-1]["report_path"] == str(temp_path / "site" / "report.json")


@pytest.mark.skipif(not HUGO_BIN, reason="Hugo CLI is not available")
def test_run_generation_production_like_responsive_board_with_real_hugo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SiteValidator, "_playwright_is_available", lambda self: False)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        progress_events: list[dict[str, object]] = []

        result = run_generation(
            GenerationOptions(
                figma_url="https://www.figma.com/design/AbCdEf1234567890/Production?node-id=9-9",
                out=temp_path / "site",
                mode=OutputMode.HUGO,
            ),
            extraction_service=ProductionLikeBoardExtractionService(),
            progress_callback=progress_events.append,
        )

        site_dir = temp_path / "site"
        site_manifest = json.loads((site_dir / "data" / "site.json").read_text(encoding="utf-8"))
        services_payload = json.loads(
            (site_dir / "data" / "pages" / "page-services.json").read_text(encoding="utf-8")
        )
        report_payload = json.loads((site_dir / "report.json").read_text(encoding="utf-8"))
        audit_path = site_dir / "responsive-audit.md"

        assert result["buildOk"] is True
        assert [page["slug"] for page in site_manifest["pages"]] == [
            "page-services",
            "contact-page",
        ]
        assert services_payload["responsive"]["family"] == "page-services"
        assert services_payload["responsive"]["base_width"] == 1920
        assert services_payload["responsive"]["breakpoints"] == [402]
        assert (site_dir / "public" / "page-services" / "index.html").exists()
        assert (site_dir / "public" / "contact-page" / "index.html").exists()
        assert report_payload["buildOk"] is True
        assert report_payload["missingTexts"] == []
        assert report_payload["missingAssets"] == []
        assert report_payload["responsive"]["summary"]["familyCount"] == 1
        assert audit_path.exists()
        assert "page-services" in audit_path.read_text(encoding="utf-8")
        assert "fidelityMode=balanced" in report_payload["warnings"]
        assert "contentMode=data-file" in report_payload["warnings"]
        assert not (site_dir / ".figma2hugo-tmp").exists()
        assert any(
            event.get("document_names")
            == ["page-services-1920", "page-services-402", "contact-page"]
            for event in progress_events
        )
