from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, ValidationError

from figma2hugo import __version__
from figma2hugo.config import AssetMode, ContentMode, FidelityMode, FigmaUrl, OutputMode, parse_figma_url
from figma2hugo.figma_reader import FigmaExtractionService
from figma2hugo.model import GenerationReport
from figma2hugo.reporting import ReportWriter
from figma2hugo.validator import SiteValidator
from figma2hugo.workflow import GenerationOptions, inspect_figma, run_generation, validate_document, validate_site

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Figma to Hugo CLI.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    del version


def _emit_json(payload: BaseModel | dict[str, Any]) -> None:
    if isinstance(payload, BaseModel):
        typer.echo(payload.model_dump_json(by_alias=True, exclude_none=True, indent=2))
        return
    typer.echo(json.dumps(payload, indent=2))


def _parse_or_bad_parameter(figma_url: str) -> FigmaUrl:
    try:
        return parse_figma_url(figma_url)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _make_extraction_service() -> FigmaExtractionService:
    return FigmaExtractionService()


def _make_site_validator() -> SiteValidator:
    return SiteValidator()


def _make_report_writer() -> ReportWriter:
    return ReportWriter()


def _launch_ui() -> None:
    from figma2hugo.gui import launch_app

    launch_app()


@app.command()
def inspect(
    figma_url: Annotated[str, typer.Argument(help="Figma file/design URL with node-id.")],
) -> None:
    _parse_or_bad_parameter(figma_url)
    _emit_json(inspect_figma(figma_url, extraction_service=_make_extraction_service()))


@app.command()
def extract(
    figma_url: Annotated[str, typer.Argument(help="Figma file/design URL with node-id.")],
    out: Annotated[Path, typer.Option("--out", help="Directory for extracted artifacts.")] = Path("./figma-extract"),
    asset_mode: Annotated[
        AssetMode, typer.Option("--asset-mode", help="Asset extraction strategy.")
    ] = AssetMode.MIXED,
) -> None:
    figma = _parse_or_bad_parameter(figma_url)
    out.mkdir(parents=True, exist_ok=True)
    payload = _make_extraction_service().extract(
        figma.source_url,
        out,
        asset_mode=asset_mode.value,
    )
    document = validate_document(payload)
    (out / "page.json").write_text(
        document.model_dump_json(by_alias=True, exclude_none=True, indent=2) + "\n",
        encoding="utf-8",
    )

    _emit_json(
        {
            "command": "extract",
            "outDir": str(out),
            "pageJson": str(out / "page.json"),
            "sectionCount": len(document.sections),
            "textCount": len(document.texts),
            "assetCount": len(document.assets),
            "warnings": document.warnings,
        }
    )


@app.command()
def generate(
    figma_url: Annotated[str, typer.Argument(help="Figma file/design URL with node-id.")],
    out: Annotated[Path, typer.Argument(help="Directory for generated output.")],
    mode: Annotated[OutputMode, typer.Option("--mode", help="Output mode.")] = OutputMode.HUGO,
    fidelity_mode: Annotated[
        FidelityMode, typer.Option("--fidelity-mode", help="Rendering fidelity strategy.")
    ] = FidelityMode.BALANCED,
    asset_mode: Annotated[
        AssetMode, typer.Option("--asset-mode", help="Asset extraction strategy.")
    ] = AssetMode.MIXED,
    content_mode: Annotated[
        ContentMode, typer.Option("--content-mode", help="Content placement strategy.")
    ] = ContentMode.DATA_FILE,
) -> None:
    _parse_or_bad_parameter(figma_url)
    _emit_json(
        run_generation(
            GenerationOptions(
                figma_url=figma_url,
                out=out,
                mode=mode,
                fidelity_mode=fidelity_mode,
                asset_mode=asset_mode,
                content_mode=content_mode,
            ),
            extraction_service=_make_extraction_service(),
            validator=_make_site_validator(),
            report_writer=_make_report_writer(),
        )
    )


@app.command()
def build(
    figma_url: Annotated[str, typer.Argument(help="Figma file/design URL with node-id.")],
    out: Annotated[Path, typer.Argument(help="Directory for generated output.")],
) -> None:
    _parse_or_bad_parameter(figma_url)
    _emit_json(
        run_generation(
            GenerationOptions(figma_url=figma_url, out=out),
            extraction_service=_make_extraction_service(),
            validator=_make_site_validator(),
            report_writer=_make_report_writer(),
        )
    )


@app.command()
def ui() -> None:
    _launch_ui()


@app.command()
def validate(
    target_dir: Annotated[Path, typer.Argument(help="Generated site directory.")],
    against: Annotated[
        str | None,
        typer.Option("--against", help="Original Figma URL used as comparison target."),
    ] = None,
) -> None:
    if against:
        _parse_or_bad_parameter(against)
    report = validate_site(
        target_dir,
        against_url=against,
        extraction_service=_make_extraction_service(),
        validator=_make_site_validator(),
        report_writer=_make_report_writer(),
    )
    _emit_json(report)


@app.command()
def report(
    target_dir: Annotated[Path, typer.Argument(help="Generated site directory.")],
) -> None:
    report_path = target_dir / "report.json"
    if not report_path.exists():
        raise typer.BadParameter(f"Missing report file: {report_path}")

    try:
        parsed_report = GenerationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise typer.BadParameter(f"Invalid report file: {exc}") from exc

    _emit_json(parsed_report)


if __name__ == "__main__":
    app()
