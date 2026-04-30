from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import figma2hugo.workflow as workflow_module
from figma2hugo.config import OutputMode
from figma2hugo.workflow import GenerationOptions, run_generation


FIGMA_URL = "https://www.figma.com/design/AbCdEf1234567890/Test-Page?node-id=3-964"


class FailingExtractionService:
    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
        *,
        asset_mode: str = "mixed",
    ) -> dict[str, object]:
        del figma_url, asset_mode
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        Path(out_dir, "raw", "marker.txt").write_text("started", encoding="utf-8")
        raise RuntimeError("boom")


class SuccessfulExtractionService:
    def extract(
        self,
        figma_url: str,
        out_dir: str | Path,
        *,
        asset_mode: str = "mixed",
    ) -> dict[str, object]:
        del figma_url, asset_mode
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
    def validate(self, target_dir: Path, *, mode: str, against_reference: Path | None = None) -> dict[str, object]:
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
        *,
        asset_mode: str = "mixed",
    ) -> dict[str, object]:
        del asset_mode
        Path(out_dir, "raw").mkdir(parents=True, exist_ok=True)
        page_name = "About Page" if "about" in figma_url else "Contact Page"
        Path(out_dir, "raw", f"{page_name}.txt").write_text("started", encoding="utf-8")
        return {
            "page": {"id": page_name.lower().replace(" ", "-"), "name": page_name, "width": 800, "height": 600, "meta": {}},
            "sections": [],
            "texts": {},
            "assets": [],
            "tokens": {},
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


def test_run_generation_deduplicates_report_warnings(monkeypatch) -> None:
    class WarningValidator:
        def validate(self, target_dir: Path, *, mode: str, against_reference: Path | None = None) -> dict[str, object]:
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
