from __future__ import annotations

import shutil
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from typing import Any

from pydantic import ValidationError

from figma2hugo.config import ContentMode, FidelityMode, OutputMode, parse_figma_url
from figma2hugo.figma_reader import FigmaExtractionService
from figma2hugo.generators import HugoGenerator, StaticGenerator
from figma2hugo.model import GenerationReport, IntermediateDocument
from figma2hugo.reporting import ReportWriter
from figma2hugo.validator import SiteValidator


@dataclass(slots=True)
class GenerationOptions:
    figma_url: str
    out: Path
    mode: OutputMode = OutputMode.HUGO
    fidelity_mode: FidelityMode = FidelityMode.BALANCED
    content_mode: ContentMode = ContentMode.DATA_FILE
    figma_urls: tuple[str, ...] = ()


def validate_document(payload: dict[str, Any]) -> IntermediateDocument:
    try:
        return IntermediateDocument.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid intermediate model: {exc}") from exc


def run_generation(
    options: GenerationOptions,
    *,
    extraction_service: FigmaExtractionService | None = None,
    validator: SiteValidator | None = None,
    report_writer: ReportWriter | None = None,
) -> dict[str, Any]:
    figma_urls = _normalized_figma_urls(options)
    for figma_url in figma_urls:
        parse_figma_url(figma_url)
    options.out.mkdir(parents=True, exist_ok=True)

    extraction_service = extraction_service or FigmaExtractionService()
    validator = validator or SiteValidator()
    report_writer = report_writer or ReportWriter()

    temp_path = _create_workspace_dir(options.out, "generate")
    stage = "initialization"
    try:
        stage = "extracting Figma data"
        if len(figma_urls) == 1:
            document_payload = extraction_service.extract(
                figma_urls[0],
                temp_path,
            )

            stage = "validating the intermediate model"
            document = validate_document(document_payload)
            documents = [document]
        else:
            if options.mode is not OutputMode.HUGO:
                raise ValueError("Multi-page generation is only supported in Hugo mode.")
            documents = []
            for index, figma_url in enumerate(figma_urls):
                page_workspace = temp_path / f"page-{index + 1}"
                stage = f"extracting Figma data for page {index + 1}/{len(figma_urls)}"
                document_payload = extraction_service.extract(
                    figma_url,
                    page_workspace,
                )
                stage = f"validating the intermediate model for page {index + 1}/{len(figma_urls)}"
                documents.append(validate_document(document_payload))

        stage = "generating the output site"
        generator = _select_generator(options.mode)
        if len(documents) == 1:
            artifacts = generator.generate(documents[0], options.out)
        else:
            if not hasattr(generator, "generate_many"):
                raise RuntimeError("Selected generator does not support multi-page generation.")
            artifacts = generator.generate_many(documents, options.out)

        stage = "validating the generated site"
        reference_path = temp_path / "reference" / "figma-reference.png"
        report_payload = validator.validate(
            options.out,
            mode=options.mode.value,
            against_reference=reference_path if len(figma_urls) == 1 and reference_path.exists() else None,
        )
    except Exception as exc:
        debug_dir = _persist_generation_debug_artifacts(
            temp_path,
            base_dir=options.out,
            options=options,
            figma_urls=figma_urls,
            stage=stage,
            error=exc,
        )
        raise RuntimeError(
            f"Generation failed during {stage}: {exc}\n"
            f"Debug files written to: {debug_dir}"
        ) from exc
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)
        _cleanup_workspace_parent(options.out)

    report_payload["warnings"] = _dedupe_warnings(
        list(report_payload.get("warnings", []))
        + [
        f"fidelityMode={options.fidelity_mode.value}",
        f"contentMode={options.content_mode.value}",
        ]
    )
    report = GenerationReport.model_validate(report_payload)
    report_writer.write(options.out, report.model_dump(by_alias=True, mode="json"))
    return {
        "command": "generate",
        "mode": options.mode.value,
        "outDir": str(options.out),
        "writtenFiles": [str(path) for path in artifacts.written_files],
        "report": str(options.out / "report.json"),
        "buildOk": report.build_ok,
    }


def inspect_figma(
    figma_url: str,
    *,
    extraction_service: FigmaExtractionService | None = None,
) -> dict[str, Any]:
    parsed = parse_figma_url(figma_url)
    extraction_service = extraction_service or FigmaExtractionService()
    with TemporaryDirectory(prefix="figma2hugo-inspect-") as temp_dir:
        return extraction_service.inspect(parsed.source_url, temp_dir)


def validate_site(
    target_dir: Path,
    *,
    against_url: str | None = None,
    extraction_service: FigmaExtractionService | None = None,
    validator: SiteValidator | None = None,
    report_writer: ReportWriter | None = None,
) -> GenerationReport:
    extraction_service = extraction_service or FigmaExtractionService()
    validator = validator or SiteValidator()
    report_writer = report_writer or ReportWriter()
    mode = validator.detect_mode(target_dir)
    additional_warnings: list[str] = []
    report_payload: dict[str, Any]

    if against_url:
        parsed = parse_figma_url(against_url)
        workspace_parent = _workspace_parent(target_dir)
        workspace_parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="figma2hugo-validate-", dir=str(workspace_parent)) as temp_dir:
            try:
                extraction_service.extract(parsed.source_url, temp_dir)
                candidate = Path(temp_dir) / "reference" / "figma-reference.png"
                if candidate.exists():
                    report_payload = validator.validate(target_dir, mode=mode, against_reference=candidate)
                else:
                    additional_warnings.append("Reference screenshot is not available for visual validation.")
                    report_payload = validator.validate(target_dir, mode=mode, against_reference=None)
            except Exception as exc:  # pragma: no cover - network/setup dependent
                additional_warnings.append(f"Reference extraction failed: {exc}")
                report_payload = validator.validate(target_dir, mode=mode, against_reference=None)
            finally:
                _cleanup_workspace_parent(target_dir)
    else:
        report_payload = validator.validate(target_dir, mode=mode, against_reference=None)

    report_payload["warnings"] = _dedupe_warnings(list(report_payload.get("warnings", [])) + additional_warnings)
    report = GenerationReport.model_validate(report_payload)
    report_writer.write(target_dir, report.model_dump(by_alias=True, mode="json"))
    return report


def _select_generator(mode: OutputMode) -> HugoGenerator | StaticGenerator:
    if mode is OutputMode.HUGO:
        return HugoGenerator()
    return StaticGenerator()


def _persist_generation_debug_artifacts(
    temp_path: Path,
    *,
    base_dir: Path,
    options: GenerationOptions,
    figma_urls: list[str],
    stage: str,
    error: Exception,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    debug_dir = base_dir / ".figma2hugo-debug" / f"generation-{timestamp}"
    debug_dir.mkdir(parents=True, exist_ok=True)

    workspace_dir = debug_dir / "workspace"
    if temp_path.exists():
        shutil.copytree(temp_path, workspace_dir, dirs_exist_ok=True)

    summary = {
        "stage": stage,
        "mode": options.mode.value,
        "figmaUrl": options.figma_url,
        "figmaUrls": figma_urls,
        "outDir": str(options.out),
        "error": str(error),
        "workspace": str(workspace_dir),
    }
    (debug_dir / "summary.json").write_text(
        _json_dump(summary),
        encoding="utf-8",
        newline="\n",
    )
    (debug_dir / "traceback.txt").write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
        newline="\n",
    )
    return debug_dir


def _workspace_parent(base_dir: Path) -> Path:
    return base_dir / ".figma2hugo-tmp"


def _create_workspace_dir(base_dir: Path, prefix: str) -> Path:
    workspace_parent = _workspace_parent(base_dir)
    workspace_parent.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix=f"figma2hugo-{prefix}-", dir=str(workspace_parent)))


def _cleanup_workspace_parent(base_dir: Path) -> None:
    workspace_parent = _workspace_parent(base_dir)
    if not workspace_parent.exists():
        return
    try:
        next(workspace_parent.iterdir())
    except StopIteration:
        workspace_parent.rmdir()


def _json_dump(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        normalized = str(warning).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _normalized_figma_urls(options: GenerationOptions) -> list[str]:
    urls = [figma_url for figma_url in options.figma_urls if figma_url]
    if urls:
        return urls
    return [options.figma_url]
