"""Points d'entree en ligne de commande pour generer les sites Hugo et lancer les diagnostics."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from figma2hugo import __version__
from figma2hugo.config import FidelityMode, FigmaUrl, parse_figma_url
from figma2hugo.pipeline.options import PipelineRenderMode, normalize_render_mode

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Figma to Hugo CLI. The official generation pipeline is enabled.",
)


class VisualBaselineMode(StrEnum):
    OFF = "off"
    CAPTURE = "capture"
    COMPARE = "compare"
    AUTO = "auto"


class VisualSmokeBrowserEngine(StrEnum):
    AUTO = "auto"
    PLAYWRIGHT = "playwright"
    STATIC = "static"


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


def _parse_many_or_bad_parameter(figma_urls: list[str]) -> list[FigmaUrl]:
    cleaned_urls = [
        figma_url.strip().lstrip("\ufeff")
        for figma_url in figma_urls
        if figma_url.strip().lstrip("\ufeff")
    ]
    if not cleaned_urls:
        raise typer.BadParameter("Provide at least one Figma URL with --page or --page-file.")
    parsed_urls: list[FigmaUrl] = []
    for figma_url in cleaned_urls:
        parsed_urls.append(_parse_or_bad_parameter(figma_url))
    return parsed_urls


def _read_page_file_urls(page_file: Path | None) -> list[str]:
    if page_file is None:
        return []
    try:
        return _split_page_url_text(page_file.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise typer.BadParameter(f"Unable to read --page-file: {page_file} ({exc})") from exc


def _split_page_url_text(content: str) -> list[str]:
    normalized = content.replace(";", "\n").replace(",", "\n")
    urls: list[str] = []
    for line in normalized.splitlines():
        candidate = line.strip().lstrip("\ufeff")
        if not candidate or candidate.startswith("#"):
            continue
        urls.append(candidate)
    return urls


def _launch_ui() -> None:
    from figma2hugo.gui import launch_app

    launch_app()


def _pipeline_render_mode_from_fidelity(
    render_mode: PipelineRenderMode | str | None,
    fidelity_mode: FidelityMode,
) -> PipelineRenderMode:
    if render_mode is not None:
        return normalize_render_mode(render_mode)
    if fidelity_mode is FidelityMode.EXACT:
        return PipelineRenderMode.STRICT
    return PipelineRenderMode.USABLE


@app.command()
def build(
    figma_url: Annotated[str, typer.Argument(help="Figma file/design URL with node-id.")],
    out: Annotated[Path, typer.Argument(help="Directory for generated output.")],
    token: Annotated[
        str | None,
        typer.Option("--token", help="Figma REST token."),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Pipeline raw Figma cache directory."),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable pipeline raw Figma cache."),
    ] = False,
    refresh_cache: Annotated[
        bool,
        typer.Option("--refresh-cache", help="Refresh pipeline raw Figma cache."),
    ] = False,
    render_mode: Annotated[
        PipelineRenderMode,
        typer.Option(
            "--render-mode",
            case_sensitive=False,
            help="Pipeline rendering mode: usable or strict.",
        ),
    ] = PipelineRenderMode.USABLE,
) -> None:
    parsed_url = _parse_or_bad_parameter(figma_url)
    _emit_json(
        _run_build_site_command(
            [parsed_url.source_url],
            out,
            token=token,
            cache_dir=cache_dir,
            no_cache=no_cache,
            refresh_cache=refresh_cache,
            render_mode=render_mode,
        )
    )


@app.command("build-raw")
def build_pipeline(
    raw: Annotated[
        list[Path],
        typer.Argument(help="One or more raw Figma-like JSON root files for pipeline."),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Directory for pipeline artifacts."),
    ] = Path("./figma2hugo-pipeline"),
    render_mode: Annotated[
        PipelineRenderMode,
        typer.Option(
            "--render-mode",
            case_sensitive=False,
            help="Pipeline rendering mode: usable or strict.",
        ),
    ] = PipelineRenderMode.USABLE,
) -> None:
    from figma2hugo.pipeline.runner import build_pipeline_from_raw_files

    try:
        _emit_json(build_pipeline_from_raw_files(raw, out, render_mode=render_mode))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("build-figma")
def build_figma_pipeline(
    figma_url: Annotated[
        list[str],
        typer.Argument(
            help="One or more Figma URLs with node-id for the standalone pipeline path."
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", help="Directory for pipeline artifacts."),
    ] = Path("./figma2hugo-pipeline"),
    token: Annotated[
        str | None,
        typer.Option(
            "--token", help="Figma REST token. Defaults to FIGMA_ACCESS_TOKEN/FIGMA_TOKEN."
        ),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Pipeline raw Figma cache directory."),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable pipeline raw Figma cache."),
    ] = False,
    refresh_cache: Annotated[
        bool,
        typer.Option("--refresh-cache", help="Refresh pipeline raw Figma cache."),
    ] = False,
    render_mode: Annotated[
        PipelineRenderMode,
        typer.Option(
            "--render-mode",
            case_sensitive=False,
            help="Pipeline rendering mode: usable or strict.",
        ),
    ] = PipelineRenderMode.USABLE,
) -> None:
    from figma2hugo.pipeline.runner import build_pipeline_from_figma_urls

    try:
        _emit_json(
            build_pipeline_from_figma_urls(
                figma_url,
                out,
                token=token,
                cache_dir=cache_dir,
                no_cache=no_cache,
                refresh_cache=refresh_cache,
                render_mode=render_mode,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("build-site")
def build_site(
    out: Annotated[Path, typer.Argument(help="Directory for generated Hugo output.")],
    page: Annotated[
        list[str] | None,
        typer.Option("--page", help="Repeat this option for each Figma page URL."),
    ] = None,
    page_file: Annotated[
        Path | None,
        typer.Option(
            "--page-file",
            help="Text file containing one or more Figma page URLs.",
        ),
    ] = None,
    fidelity_mode: Annotated[
        FidelityMode, typer.Option("--fidelity-mode", help="Rendering fidelity strategy.")
    ] = FidelityMode.BALANCED,
    render_mode: Annotated[
        PipelineRenderMode | None,
        typer.Option(
            "--render-mode",
            case_sensitive=False,
            help=(
                "Pipeline rendering mode: usable or strict. "
                "Defaults to strict when --fidelity-mode exact is used."
            ),
        ),
    ] = None,
    raw: Annotated[
        list[Path] | None,
        typer.Option("--raw", help="Repeat this option for raw Figma-like JSON files."),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", help="Figma REST token."),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option("--cache-dir", help="Pipeline raw Figma cache directory."),
    ] = None,
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Disable pipeline raw Figma cache."),
    ] = False,
    refresh_cache: Annotated[
        bool,
        typer.Option("--refresh-cache", help="Refresh pipeline raw Figma cache."),
    ] = False,
    responsive_contract: Annotated[
        Path | None,
        typer.Option(
            "--responsive-contract",
            help="JSON file declaring intentional pipeline responsive review contracts.",
        ),
    ] = None,
    responsive_contract_root: Annotated[
        Path | None,
        typer.Option(
            "--responsive-contract-root",
            help="Root directory containing project review/responsive contracts.",
        ),
    ] = None,
    responsive_contract_id: Annotated[
        str | None,
        typer.Option(
            "--responsive-contract-id",
            help="Project review/responsive contract snapshot id.",
        ),
    ] = None,
) -> None:
    from figma2hugo.pipeline.runner import build_pipeline_hugo_site_from_raw_files

    raw_files = list(raw or [])
    figma_url_inputs = [*(page or []), *_read_page_file_urls(page_file)]
    if raw_files and figma_url_inputs:
        raise typer.BadParameter("Use either --raw files or --page/--page-file URLs, not both.")

    try:
        if raw_files:
            _emit_json(
                build_pipeline_hugo_site_from_raw_files(
                    raw_files,
                    out,
                    responsive_contract=responsive_contract,
                    responsive_contract_root=responsive_contract_root,
                    responsive_contract_id=responsive_contract_id,
                    render_mode=_pipeline_render_mode_from_fidelity(render_mode, fidelity_mode),
                )
            )
            return
        parsed_pages = _parse_many_or_bad_parameter(figma_url_inputs)
        figma_urls = tuple(parsed.source_url for parsed in parsed_pages)
        _emit_json(
            _run_build_site_command(
                list(figma_urls),
                out,
                token=token,
                cache_dir=cache_dir,
                no_cache=no_cache,
                refresh_cache=refresh_cache,
                responsive_contract=responsive_contract,
                responsive_contract_root=responsive_contract_root,
                responsive_contract_id=responsive_contract_id,
                render_mode=_pipeline_render_mode_from_fidelity(render_mode, fidelity_mode),
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _run_build_site_command(
    figma_urls: list[str],
    out: Path,
    *,
    token: str | None = None,
    cache_dir: Path | None = None,
    no_cache: bool = False,
    refresh_cache: bool = False,
    responsive_contract: Path | None = None,
    responsive_contract_root: Path | None = None,
    responsive_contract_id: str | None = None,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    from figma2hugo.pipeline.runner import build_pipeline_hugo_site_from_figma_urls

    return build_pipeline_hugo_site_from_figma_urls(
        figma_urls,
        out,
        token=token,
        cache_dir=cache_dir,
        no_cache=no_cache,
        refresh_cache=refresh_cache,
        responsive_contract=responsive_contract,
        responsive_contract_root=responsive_contract_root,
        responsive_contract_id=responsive_contract_id,
        render_mode=render_mode,
    )


@app.command("visual-smoke")
def visual_smoke_pipeline(
    source: Annotated[Path, typer.Argument(help="Generated Hugo pipeline source directory.")],
    out: Annotated[
        Path,
        typer.Option("--out", help="Directory for smoke reports and screenshots."),
    ] = Path("./figma2hugo-pipeline-smoke"),
    public_dir: Annotated[
        Path | None,
        typer.Option("--public-dir", help="Use an already-built Hugo public directory."),
    ] = None,
    widths: Annotated[
        str | None,
        typer.Option("--widths", help="Comma-separated viewport widths to test."),
    ] = None,
    screenshot_widths: Annotated[
        str | None,
        typer.Option("--screenshot-widths", help="Comma-separated viewport widths to capture."),
    ] = None,
    baseline_dir: Annotated[
        Path | None,
        typer.Option("--baseline-dir", help="Optional directory of baseline screenshots."),
    ] = None,
    baseline_root: Annotated[
        Path | None,
        typer.Option("--baseline-root", help="Root directory containing project visual baselines."),
    ] = None,
    baseline_mode: Annotated[
        VisualBaselineMode | None,
        typer.Option(
            "--baseline-mode",
            case_sensitive=False,
            help="Visual baseline mode: off, capture, compare, or auto.",
        ),
    ] = None,
    baseline_id: Annotated[
        str | None,
        typer.Option(
            "--baseline-id", help="Project baseline snapshot id when using --baseline-root."
        ),
    ] = None,
    diff_review_threshold: Annotated[
        float,
        typer.Option("--diff-review-threshold", help="Pixel diff ratio that marks visual review."),
    ] = 0.005,
    diff_fail_threshold: Annotated[
        float,
        typer.Option("--diff-fail-threshold", help="Pixel diff ratio that marks visual fail."),
    ] = 0.05,
    hugo_bin: Annotated[
        str,
        typer.Option("--hugo-bin", help="Hugo executable used when --public-dir is not provided."),
    ] = "hugo",
    token: Annotated[
        str | None,
        typer.Option("--token", help="Figma REST token for automatic Figma visual references."),
    ] = None,
    browser_engine: Annotated[
        VisualSmokeBrowserEngine,
        typer.Option(
            "--browser-engine",
            case_sensitive=False,
            help="Browser smoke engine: auto, playwright, or static.",
        ),
    ] = VisualSmokeBrowserEngine.AUTO,
) -> None:
    from figma2hugo.pipeline.visual_smoke import (
        DEFAULT_SCREENSHOT_WIDTHS,
        DEFAULT_VIEWPORT_WIDTHS,
        parse_widths,
        run_pipeline_visual_smoke,
    )

    try:
        _emit_json(
            run_pipeline_visual_smoke(
                source,
                out,
                public_dir=public_dir,
                widths=parse_widths(widths, default=DEFAULT_VIEWPORT_WIDTHS),
                screenshot_widths=parse_widths(
                    screenshot_widths,
                    default=DEFAULT_SCREENSHOT_WIDTHS,
                ),
                baseline_dir=baseline_dir,
                baseline_root=baseline_root,
                baseline_mode=str(baseline_mode) if baseline_mode is not None else None,
                baseline_id=baseline_id,
                diff_review_threshold=diff_review_threshold,
                diff_fail_threshold=diff_fail_threshold,
                hugo_bin=hugo_bin,
                token=token,
                browser_engine=str(browser_engine),
            )
        )
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("promote-visual-baseline")
def promote_visual_baseline_pipeline(
    smoke_out: Annotated[Path, typer.Argument(help="Visual smoke output directory.")],
    baseline_root: Annotated[
        Path,
        typer.Option("--baseline-root", help="Root directory for project visual baselines."),
    ],
    baseline_id: Annotated[
        str | None,
        typer.Option("--baseline-id", help="Optional snapshot id to create."),
    ] = None,
    label: Annotated[
        str | None,
        typer.Option("--label", help="Optional human label for the promoted snapshot."),
    ] = None,
) -> None:
    from figma2hugo.pipeline.visual_baselines import promote_visual_baseline

    try:
        _emit_json(
            promote_visual_baseline(
                smoke_out,
                baseline_root,
                baseline_id=baseline_id,
                label=label,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("promote-review-baseline")
def promote_review_baseline_pipeline(
    site_report_or_dir: Annotated[
        Path,
        typer.Argument(help="Pipeline site directory or report.json to promote."),
    ],
    baseline_root: Annotated[
        Path,
        typer.Option("--baseline-root", help="Root directory for project review baselines."),
    ],
    baseline_id: Annotated[
        str | None,
        typer.Option("--baseline-id", help="Optional snapshot id to create."),
    ] = None,
    label: Annotated[
        str | None,
        typer.Option("--label", help="Optional human label for the promoted snapshot."),
    ] = None,
    approve_actionable_reviews: Annotated[
        bool,
        typer.Option(
            "--approve-actionable-reviews",
            help="Also approve remaining non-responsive P2/P3 actionable review items.",
        ),
    ] = False,
) -> None:
    from figma2hugo.pipeline.review_baselines import promote_project_review_baseline

    try:
        _emit_json(
            promote_project_review_baseline(
                site_report_or_dir,
                baseline_root,
                baseline_id=baseline_id,
                label=label,
                approve_actionable_reviews=approve_actionable_reviews,
            )
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def ui() -> None:
    _launch_ui()


@app.command()
def report(
    target_dir: Annotated[Path, typer.Argument(help="Generated site directory.")],
) -> None:
    report_path = target_dir / "report.json"
    if not report_path.exists():
        raise typer.BadParameter(f"Missing report file: {report_path}")

    try:
        report_text = report_path.read_text(encoding="utf-8-sig")
        raw_report_payload = json.loads(report_text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid report file: {exc}") from exc

    _emit_json(raw_report_payload)


if __name__ == "__main__":
    app()
