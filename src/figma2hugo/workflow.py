from __future__ import annotations

import os
import shutil
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from typing import Any

from figma2hugo.config import ContentMode, FidelityMode, OutputMode, parse_figma_url
from figma2hugo.figma_reader import FigmaExtractionService
from figma2hugo.generators import HugoGenerator, StaticGenerator
from figma2hugo.model import (
    GenerationReport,
    IntermediateDocument,
    intermediate_document_name,
    intermediate_document_names,
    intermediate_document_width,
    validate_intermediate_payload,
)
from figma2hugo.reporting import ReportWriter, dedupe_warnings
from figma2hugo.validator import SiteValidator


@dataclass(slots=True)
class GenerationOptions:
    figma_url: str
    out: Path
    mode: OutputMode = OutputMode.HUGO
    fidelity_mode: FidelityMode = FidelityMode.BALANCED
    content_mode: ContentMode = ContentMode.DATA_FILE
    figma_urls: tuple[str, ...] = ()
    strict_responsive_matching: bool = False


def validate_document(payload: dict[str, Any]) -> IntermediateDocument:
    return validate_intermediate_payload(payload)


def run_generation(
    options: GenerationOptions,
    *,
    extraction_service: FigmaExtractionService | None = None,
    validator: SiteValidator | None = None,
    report_writer: ReportWriter | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    figma_urls = _normalized_figma_urls(options)
    parsed_figma_urls = [parse_figma_url(figma_url) for figma_url in figma_urls]
    options.out.mkdir(parents=True, exist_ok=True)

    extraction_service = extraction_service or FigmaExtractionService()
    validator = validator or SiteValidator()
    report_writer = report_writer or ReportWriter()

    temp_path = _create_workspace_dir(options.out, "generate")
    stage = "initialization"

    def set_stage(value: str) -> str:
        nonlocal stage
        stage = value
        return stage

    try:
        _emit_progress(
            progress_callback,
            stage,
            f"Workspace initialise dans {temp_path}.",
            mode=options.mode.value,
            total_inputs=len(figma_urls),
            output_dir=str(options.out),
        )
        documents = _extract_and_validate_documents(
            extraction_service=extraction_service,
            figma_urls=figma_urls,
            parsed_figma_urls=parsed_figma_urls,
            temp_path=temp_path,
            mode=options.mode,
            progress_callback=progress_callback,
            set_stage=set_stage,
        )

        stage = "generating the output site"
        _emit_progress(
            progress_callback,
            stage,
            f"Generation du site {options.mode.value} a partir de {len(documents)} document(s).",
            document_total=len(documents),
            output_dir=str(options.out),
            document_names=_document_names(documents),
        )
        with _strict_responsive_matching_environment(options.strict_responsive_matching):
            generator = _select_generator(options.mode)
            if len(documents) == 1:
                artifacts = generator.generate(documents[0], options.out)
            else:
                if not hasattr(generator, "generate_many"):
                    raise RuntimeError("Selected generator does not support multi-page generation.")
                artifacts = generator.generate_many(documents, options.out)

        stage = "validating the generated site"
        _emit_progress(
            progress_callback,
            stage,
            "Validation du site genere et construction du rapport.",
            written_file_count=len(artifacts.written_files),
            output_dir=str(options.out),
        )
        reference_path = temp_path / "reference" / "figma-reference.png"
        against_reference = (
            reference_path
            if len(figma_urls) == 1 and len(documents) == 1 and reference_path.exists()
            else None
        )
        report_payload = validator.validate(
            options.out,
            mode=options.mode.value,
            against_reference=against_reference,
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

    report_payload["warnings"] = dedupe_warnings(
        list(report_payload.get("warnings", []))
        + [
            f"fidelityMode={options.fidelity_mode.value}",
            f"contentMode={options.content_mode.value}",
        ]
    )
    report = GenerationReport.model_validate(report_payload)
    _emit_progress(
        progress_callback,
        "writing generation report",
        "Ecriture du rapport final.",
        warning_count=len(report_payload.get("warnings", [])),
        output_dir=str(options.out),
        report_path=str(options.out / "report.json"),
    )
    _write_report_artifacts(
        report_writer,
        options.out,
        report.model_dump(by_alias=True, mode="json"),
    )
    return {
        "command": "generate",
        "mode": options.mode.value,
        "outDir": str(options.out),
        "writtenFiles": [str(path) for path in artifacts.written_files],
        "report": str(options.out / "report.json"),
        "buildOk": report.build_ok,
        "strictResponsiveMatching": options.strict_responsive_matching,
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
        with TemporaryDirectory(
            prefix="figma2hugo-validate-",
            dir=str(workspace_parent),
        ) as temp_dir:
            try:
                extraction_service.extract(parsed.source_url, temp_dir)
                candidate = Path(temp_dir) / "reference" / "figma-reference.png"
                if candidate.exists():
                    report_payload = validator.validate(
                        target_dir,
                        mode=mode,
                        against_reference=candidate,
                    )
                else:
                    additional_warnings.append(
                        "Reference screenshot is not available for visual validation."
                    )
                    report_payload = validator.validate(
                        target_dir,
                        mode=mode,
                        against_reference=None,
                    )
            except Exception as exc:  # pragma: no cover - network/setup dependent
                additional_warnings.append(f"Reference extraction failed: {exc}")
                report_payload = validator.validate(target_dir, mode=mode, against_reference=None)
            finally:
                _cleanup_workspace_parent(target_dir)
    else:
        report_payload = validator.validate(target_dir, mode=mode, against_reference=None)

    report_payload["warnings"] = dedupe_warnings(
        list(report_payload.get("warnings", [])) + additional_warnings
    )
    report = GenerationReport.model_validate(report_payload)
    _write_report_artifacts(
        report_writer,
        target_dir,
        report.model_dump(by_alias=True, mode="json"),
    )
    return report


def _write_report_artifacts(
    report_writer: ReportWriter,
    target_dir: Path,
    payload: dict[str, Any],
) -> None:
    report_writer.write(target_dir, payload)
    write_responsive_audit = getattr(report_writer, "write_responsive_audit", None)
    if callable(write_responsive_audit):
        write_responsive_audit(target_dir, payload)


def _select_generator(mode: OutputMode) -> HugoGenerator | StaticGenerator:
    if mode is OutputMode.HUGO:
        return HugoGenerator()
    return StaticGenerator()


@contextmanager
def _strict_responsive_matching_environment(enabled: bool):
    env_name = "FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING"
    previous = os.environ.get(env_name)
    if enabled:
        os.environ[env_name] = "1"
    try:
        yield
    finally:
        if enabled:
            if previous is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = previous


def _extract_and_validate_documents(
    *,
    extraction_service: FigmaExtractionService,
    figma_urls: list[str],
    parsed_figma_urls: list[Any],
    temp_path: Path,
    mode: OutputMode,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    set_stage: Callable[[str], str],
) -> list[IntermediateDocument]:
    if len(figma_urls) == 1:
        return _extract_single_input_documents(
            extraction_service=extraction_service,
            figma_url=figma_urls[0],
            parsed_figma_url=parsed_figma_urls[0],
            temp_path=temp_path,
            mode=mode,
            progress_callback=progress_callback,
            set_stage=set_stage,
        )
    return _extract_multi_input_documents(
        extraction_service=extraction_service,
        figma_urls=figma_urls,
        parsed_figma_urls=parsed_figma_urls,
        temp_path=temp_path,
        mode=mode,
        progress_callback=progress_callback,
        set_stage=set_stage,
    )


def _extract_single_input_documents(
    *,
    extraction_service: FigmaExtractionService,
    figma_url: str,
    parsed_figma_url: Any,
    temp_path: Path,
    mode: OutputMode,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    set_stage: Callable[[str], str],
) -> list[IntermediateDocument]:
    stage = set_stage("extracting Figma data")
    source_label = _describe_figma_target(parsed_figma_url)
    _emit_progress(
        progress_callback,
        stage,
        "Extraction Figma de l'entree unique en cours.",
        input_index=1,
        input_total=1,
        source_label=source_label,
    )
    document_payloads = _extract_documents(
        extraction_service,
        figma_url,
        temp_path,
    )
    _emit_progress(
        progress_callback,
        stage,
        f"{len(document_payloads)} document(s) extrait(s) depuis l'entree unique.",
        input_index=1,
        input_total=1,
        source_label=source_label,
        document_total=len(document_payloads),
        document_names=_document_names(document_payloads),
    )
    if len(document_payloads) > 1 and mode is not OutputMode.HUGO:
        raise ValueError("Multi-page generation is only supported in Hugo mode.")

    documents: list[IntermediateDocument] = []
    for index, document_payload in enumerate(document_payloads, start=1):
        stage = set_stage(
            f"validating the intermediate model for page {index}/{len(document_payloads)}"
        )
        _emit_progress(
            progress_callback,
            stage,
            f"Validation du document intermediaire {index}/{len(document_payloads)}.",
            input_index=index,
            input_total=len(document_payloads),
            source_label=source_label,
            document_name=_document_name(document_payload),
            breakpoint_width=_document_width(document_payload),
        )
        documents.append(validate_document(document_payload))
    return documents


def _extract_multi_input_documents(
    *,
    extraction_service: FigmaExtractionService,
    figma_urls: list[str],
    parsed_figma_urls: list[Any],
    temp_path: Path,
    mode: OutputMode,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    set_stage: Callable[[str], str],
) -> list[IntermediateDocument]:
    if mode is not OutputMode.HUGO:
        raise ValueError("Multi-page generation is only supported in Hugo mode.")

    documents: list[IntermediateDocument] = []
    input_total = len(figma_urls)
    for index, figma_url in enumerate(figma_urls):
        input_index = index + 1
        source_label = _describe_figma_target(parsed_figma_urls[index])
        stage = set_stage(
            f"extracting Figma data for page {input_index}/{input_total}"
        )
        _emit_progress(
            progress_callback,
            stage,
            f"Extraction Figma de la page {input_index}/{input_total}.",
            input_index=input_index,
            input_total=input_total,
            source_label=source_label,
        )
        document_payloads = _extract_documents(
            extraction_service,
            figma_url,
            temp_path / f"page-{input_index}",
        )
        extraction_message = (
            f"{len(document_payloads)} document(s) extrait(s) "
            f"pour la page {input_index}/{input_total}."
        )
        _emit_progress(
            progress_callback,
            stage,
            extraction_message,
            input_index=input_index,
            input_total=input_total,
            source_label=source_label,
            document_total=len(document_payloads),
            document_names=_document_names(document_payloads),
        )
        for variant_index, document_payload in enumerate(document_payloads, start=1):
            stage = set_stage(
                f"validating the intermediate model for page {input_index}/{input_total}"
                f" variant {variant_index}/{len(document_payloads)}"
            )
            _emit_progress(
                progress_callback,
                stage,
                "Validation d'un document intermediaire extrait.",
                input_index=input_index,
                input_total=input_total,
                variant_index=variant_index,
                variant_total=len(document_payloads),
                source_label=source_label,
                document_name=_document_name(document_payload),
                breakpoint_width=_document_width(document_payload),
            )
            documents.append(validate_document(document_payload))
    return documents


def _extract_documents(
    extraction_service: FigmaExtractionService,
    figma_url: str,
    out_dir: Path,
) -> list[dict[str, Any]]:
    extract_many = getattr(extraction_service, "extract_documents", None)
    if callable(extract_many):
        payloads = extract_many(figma_url, out_dir)
        if not isinstance(payloads, list) or not payloads:
            raise RuntimeError("Extraction service returned no intermediate documents.")
        return payloads
    return [extraction_service.extract(figma_url, out_dir)]


def _emit_progress(
    callback: Callable[[dict[str, Any]], None] | None,
    stage: str,
    message: str,
    **metadata: Any,
) -> None:
    if callback is None:
        return
    payload = {"stage": stage, "message": message, **metadata}
    callback(payload)


def _describe_figma_target(parsed_url: Any) -> str:
    slug = str(getattr(parsed_url, "slug", "") or "").strip("/")
    if slug:
        return f"{slug} (node {parsed_url.node_id})"
    return f"{parsed_url.file_key} (node {parsed_url.node_id})"


def _document_name(document_payload: Any) -> str | None:
    return intermediate_document_name(document_payload)


def _document_width(document_payload: Any) -> int | None:
    return intermediate_document_width(document_payload)


def _document_names(document_payloads: list[Any]) -> list[str]:
    return intermediate_document_names(document_payloads)


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
        "strictResponsiveMatching": options.strict_responsive_matching,
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


def _normalized_figma_urls(options: GenerationOptions) -> list[str]:
    urls = [figma_url for figma_url in options.figma_urls if figma_url]
    if urls:
        return urls
    return [options.figma_url]
