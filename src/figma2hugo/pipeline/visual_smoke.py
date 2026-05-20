"""Capture les pages generees dans un navigateur et detecte les problemes visibles."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from os import PathLike
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageChops

from figma2hugo.pipeline.figma_references import prepare_figma_reference_images
from figma2hugo.pipeline.visual_baselines import (
    load_site_source_identity,
    resolve_visual_baseline,
    visual_baseline_manifest,
)
from figma2hugo.pipeline.visual_smoke_report import (
    render_review_html as _render_review_html,
)
from figma2hugo.pipeline.visual_smoke_report import (
    write_contact_sheet as _write_contact_sheet,
)

DEFAULT_VIEWPORT_WIDTHS = (1920, 1440, 1280, 1024, 834, 402)
DEFAULT_SCREENSHOT_WIDTHS = (1920, 834, 402)
VISUAL_DIFF_PIXEL_TOLERANCE = 24
BROWSER_ENGINES = {"auto", "playwright", "static"}
TEMPLATE_ARTIFACT_RE = re.compile(r"ZgotmplZ|%![A-Za-z]|undefined", re.IGNORECASE)


class _BrowserSmokeResult(NamedTuple):
    issues: list[dict[str, Any]]
    summaries: list[dict[str, Any]]
    screenshots: list[dict[str, Any]]
    visual_reviews: list[dict[str, Any]]
    browser: dict[str, Any]


class _StaticHtmlSnapshot(NamedTuple):
    html: str
    text: str
    images: list[str]
    stylesheet_links: list[str]
    script_links: list[str]
    variants: int
    forms: int
    controls: int
    accordions: int
    carousels: int
    link_cards: int


def parse_widths(value: str | None, *, default: tuple[int, ...]) -> tuple[int, ...]:
    if value is None or not value.strip():
        return default
    widths: list[int] = []
    for chunk in value.replace(";", ",").split(","):
        candidate = chunk.strip()
        if not candidate:
            continue
        width = int(candidate)
        if width <= 0:
            raise ValueError("Viewport widths must be positive integers.")
        widths.append(width)
    if not widths:
        raise ValueError("Provide at least one viewport width.")
    return tuple(dict.fromkeys(widths))


def _normalize_browser_engine(value: str) -> str:
    engine = str(value or "auto").strip().lower()
    if engine not in BROWSER_ENGINES:
        expected = ", ".join(sorted(BROWSER_ENGINES))
        raise ValueError(f"Browser engine must be one of: {expected}.")
    return engine


def run_pipeline_visual_smoke(
    source_dir: Path,
    out_dir: Path,
    *,
    public_dir: Path | None = None,
    widths: tuple[int, ...] = DEFAULT_VIEWPORT_WIDTHS,
    screenshot_widths: tuple[int, ...] = DEFAULT_SCREENSHOT_WIDTHS,
    baseline_dir: Path | None = None,
    baseline_root: Path | None = None,
    baseline_mode: str | None = None,
    baseline_id: str | None = None,
    diff_review_threshold: float = 0.005,
    diff_fail_threshold: float = 0.05,
    hugo_bin: str = "hugo",
    token: str | None = None,
    browser_engine: str = "auto",
) -> dict[str, Any]:
    source_dir = source_dir.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = _load_page_slugs(source_dir)
    public_root = public_dir.resolve() if public_dir is not None else out_dir / "public"
    hugo_result = (
        None
        if public_dir is not None
        else _build_hugo_site(source_dir=source_dir, public_dir=public_root, hugo_bin=hugo_bin)
    )

    normalized_browser_engine = _normalize_browser_engine(browser_engine)
    source_identity = load_site_source_identity(source_dir)
    resolved_baseline = resolve_visual_baseline(
        source_dir=source_dir,
        baseline_mode=baseline_mode,
        baseline_dir=baseline_dir,
        baseline_root=baseline_root,
        baseline_id=baseline_id,
    )
    resolved_baseline_dir = resolved_baseline.baseline_dir
    prepared_figma_reference = (
        prepare_figma_reference_images(source_dir=source_dir, out_dir=out_dir, token=token)
        if resolved_baseline_dir is None
        else None
    )
    comparison_dir = resolved_baseline_dir
    comparison_kind = "visual-baseline" if resolved_baseline_dir is not None else "capture"
    if (
        comparison_dir is None
        and prepared_figma_reference is not None
        and prepared_figma_reference.reference_dir is not None
    ):
        comparison_dir = prepared_figma_reference.reference_dir
        comparison_kind = "figma-reference"
    smoke_result = _run_browser_or_static_smoke(
        public_root=public_root,
        out_dir=out_dir,
        pages=pages,
        widths=widths,
        screenshot_widths=screenshot_widths,
        comparison_dir=comparison_dir,
        comparison_kind=comparison_kind,
        diff_review_threshold=diff_review_threshold,
        diff_fail_threshold=diff_fail_threshold,
        browser_engine=normalized_browser_engine,
    )
    issues = smoke_result.issues
    summaries = smoke_result.summaries
    screenshots = smoke_result.screenshots
    visual_reviews = smoke_result.visual_reviews

    review_html_path = out_dir / "review.html"
    contact_sheet_path = _write_contact_sheet(screenshots, out_dir=out_dir)
    visual_review_payload = {
        "enabled": comparison_dir is not None,
        **resolved_baseline.to_report(),
        "comparisonKind": comparison_kind,
        "comparisonDir": str(comparison_dir) if comparison_dir is not None else None,
        "figmaReference": (
            prepared_figma_reference.report
            if prepared_figma_reference is not None
            else {"prepared": False, "reason": "visual baseline comparison was used"}
        ),
        "sourceIdentity": source_identity,
        "reviewHtml": _relative_output_path(review_html_path, out_dir),
        "contactSheet": (
            _relative_output_path(contact_sheet_path, out_dir) if contact_sheet_path else None
        ),
        "baselineManifest": None,
        "count": len(visual_reviews),
        "byStatus": _count_by(visual_reviews, "status"),
        "items": visual_reviews,
    }
    report: dict[str, Any] = {
        "pipeline": "pipeline",
        "command": "visual-smoke",
        "sourceDir": str(source_dir),
        "publicDir": str(public_root),
        "outDir": str(out_dir),
        "sourceIdentity": source_identity,
        "hugo": hugo_result,
        "browser": smoke_result.browser,
        "pageCount": len(pages),
        "viewportCount": len(widths),
        "issueCount": len(issues),
        "errorCount": sum(1 for issue in issues if issue["severity"] == "error"),
        "warnCount": sum(1 for issue in issues if issue["severity"] != "error"),
        "byCode": _count_by(issues, "code"),
        "byPage": _count_by(issues, "slug"),
        "screenshots": {
            "count": len(screenshots),
            "byPage": _count_by(screenshots, "slug"),
            "items": screenshots,
        },
        "artifacts": {
            "reviewHtml": _relative_output_path(review_html_path, out_dir),
            "contactSheet": (
                _relative_output_path(contact_sheet_path, out_dir) if contact_sheet_path else None
            ),
        },
        "visualReview": visual_review_payload,
        "summaries": summaries,
        "issues": issues,
    }
    baseline_manifest_path = out_dir / "visual-baseline-manifest.json"
    baseline_manifest_path.write_text(
        json.dumps(
            visual_baseline_manifest(report, source_identity=source_identity),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    visual_review_report = report["visualReview"]
    artifacts_report = report["artifacts"]
    assert isinstance(visual_review_report, dict)
    assert isinstance(artifacts_report, dict)
    visual_review_report["baselineManifest"] = _relative_output_path(
        baseline_manifest_path,
        out_dir,
    )
    artifacts_report["baselineManifest"] = visual_review_report["baselineManifest"]
    review_html_path.write_text(_render_review_html(report), encoding="utf-8")
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "issues.json").write_text(
        json.dumps(issues, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def _run_browser_or_static_smoke(
    *,
    public_root: Path,
    out_dir: Path,
    pages: list[str],
    widths: tuple[int, ...],
    screenshot_widths: tuple[int, ...],
    comparison_dir: Path | None,
    comparison_kind: str,
    diff_review_threshold: float,
    diff_fail_threshold: float,
    browser_engine: str,
) -> _BrowserSmokeResult:
    if browser_engine == "static":
        return _run_static_html_smoke(
            public_root=public_root,
            pages=pages,
            widths=widths,
            requested_engine=browser_engine,
            reason="browser engine set to static",
        )
    if browser_engine == "auto" and "playwright.sync_api" not in sys.modules:
        preflight_ok, preflight_reason, preflight_exception_type = _playwright_driver_preflight()
        if not preflight_ok:
            return _run_static_html_smoke(
                public_root=public_root,
                pages=pages,
                widths=widths,
                requested_engine=browser_engine,
                reason=preflight_reason,
                exception_type=preflight_exception_type,
            )
    try:
        return _run_playwright_browser_smoke(
            public_root=public_root,
            out_dir=out_dir,
            pages=pages,
            widths=widths,
            screenshot_widths=screenshot_widths,
            comparison_dir=comparison_dir,
            comparison_kind=comparison_kind,
            diff_review_threshold=diff_review_threshold,
            diff_fail_threshold=diff_fail_threshold,
            requested_engine=browser_engine,
        )
    except Exception as exc:
        if browser_engine == "playwright":
            raise RuntimeError(f"Playwright browser smoke failed: {exc}") from exc
        return _run_static_html_smoke(
            public_root=public_root,
            pages=pages,
            widths=widths,
            requested_engine=browser_engine,
            reason=str(exc),
            exception_type=type(exc).__name__,
        )


def _playwright_driver_preflight() -> tuple[bool, str, str | None]:
    try:
        from playwright._impl._driver import compute_driver_executable

        executable_path, entrypoint_path = compute_driver_executable()

        async def check_driver() -> tuple[int, bytes, bytes]:
            proc = await asyncio.create_subprocess_exec(
                str(executable_path),
                str(entrypoint_path),
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode if proc.returncode is not None else -1, stdout, stderr

        returncode, stdout, stderr = asyncio.run(check_driver())
        if returncode != 0:
            message = (
                stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
            )
            return False, message or f"Playwright driver exited with {returncode}.", None
    except Exception as exc:
        return False, str(exc), type(exc).__name__
    return True, "", None


def _run_playwright_browser_smoke(
    *,
    public_root: Path,
    out_dir: Path,
    pages: list[str],
    widths: tuple[int, ...],
    screenshot_widths: tuple[int, ...],
    comparison_dir: Path | None,
    comparison_kind: str,
    diff_review_threshold: float,
    diff_fail_threshold: float,
    requested_engine: str,
) -> _BrowserSmokeResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("Playwright is not installed in the current environment.") from exc

    issues: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    screenshots: list[dict[str, Any]] = []
    visual_reviews: list[dict[str, Any]] = []
    screenshot_width_set = set(screenshot_widths)
    with _served_directory(public_root) as base_url:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for slug in pages:
                    for width in widths:
                        viewport = _viewport_for_width(width)
                        viewport_arg: Any = viewport
                        page = browser.new_page(viewport=viewport_arg, device_scale_factor=1)
                        try:
                            page.goto(
                                f"{base_url}/{slug}/", wait_until="networkidle", timeout=30000
                            )
                            page.evaluate(_IMAGE_DECODE_SCRIPT, {})
                            page.wait_for_timeout(250)
                            result = page.evaluate(
                                _SMOKE_SCRIPT, {"slug": slug, "viewport": viewport}
                            )
                            annotated_issues = [
                                {"slug": slug, "viewport": width, **issue}
                                for issue in result["issues"]
                            ]
                            issues.extend(annotated_issues)
                            summary = {
                                "slug": slug,
                                "viewport": width,
                                "issueCount": len(annotated_issues),
                                "errorCount": sum(
                                    1 for issue in annotated_issues if issue["severity"] == "error"
                                ),
                                "warnCount": sum(
                                    1 for issue in annotated_issues if issue["severity"] != "error"
                                ),
                                "metrics": result["metrics"],
                            }
                            if width in screenshot_width_set:
                                screenshot_path = out_dir / f"{slug}-{width}.png"
                                page.screenshot(
                                    path=str(screenshot_path),
                                    full_page=True,
                                )
                                screenshot_record = {
                                    "slug": slug,
                                    "viewport": width,
                                    "path": _relative_output_path(screenshot_path, out_dir),
                                    "fullPage": True,
                                    "viewportSize": viewport,
                                }
                                visual_review = _visual_review_record(
                                    screenshot_path,
                                    out_dir=out_dir,
                                    baseline_dir=comparison_dir,
                                    slug=slug,
                                    width=width,
                                    review_threshold=diff_review_threshold,
                                    fail_threshold=diff_fail_threshold,
                                    reference_kind=comparison_kind,
                                )
                                screenshot_record["visualReview"] = visual_review
                                visual_reviews.append(visual_review)
                                screenshots.append(screenshot_record)
                                summary["screenshot"] = screenshot_record["path"]
                                summary["visualReview"] = visual_review
                            summaries.append(summary)
                        finally:
                            page.close()
            finally:
                browser.close()
    return _BrowserSmokeResult(
        issues=issues,
        summaries=summaries,
        screenshots=screenshots,
        visual_reviews=visual_reviews,
        browser={
            "requestedEngine": requested_engine,
            "engine": "playwright",
            "status": "ok",
            "checks": "browser",
            "screenshotsAvailable": True,
        },
    )


def _run_static_html_smoke(
    *,
    public_root: Path,
    pages: list[str],
    widths: tuple[int, ...],
    requested_engine: str,
    reason: str,
    exception_type: str | None = None,
) -> _BrowserSmokeResult:
    issues: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for slug in pages:
        html_path = public_root / slug / "index.html"
        page_issues: list[dict[str, Any]] = []
        if not html_path.exists():
            page_issues.append(
                {
                    "slug": slug,
                    "code": "missing-page-html",
                    "severity": "error",
                    "path": str(html_path),
                }
            )
            snapshot = None
        else:
            snapshot = _read_static_html_snapshot(html_path)
            page_issues.extend(
                _static_html_issues(
                    snapshot,
                    html_path=html_path,
                    public_root=public_root,
                    slug=slug,
                )
            )
        issues.extend(page_issues)
        for width in widths:
            annotated_issues = [dict(issue, viewport=width) for issue in page_issues]
            metrics = _static_html_metrics(snapshot, slug=slug, width=width)
            summaries.append(
                {
                    "slug": slug,
                    "viewport": width,
                    "issueCount": len(annotated_issues),
                    "errorCount": sum(
                        1 for issue in annotated_issues if issue["severity"] == "error"
                    ),
                    "warnCount": sum(
                        1 for issue in annotated_issues if issue["severity"] != "error"
                    ),
                    "metrics": metrics,
                }
            )
    browser: dict[str, Any] = {
        "requestedEngine": requested_engine,
        "engine": "static-fallback",
        "status": "fallback" if requested_engine == "auto" else "ok",
        "checks": "static-html",
        "screenshotsAvailable": False,
        "reason": reason,
    }
    if exception_type:
        browser["exceptionType"] = exception_type
    return _BrowserSmokeResult(
        issues=issues,
        summaries=summaries,
        screenshots=[],
        visual_reviews=[],
        browser=browser,
    )


def _read_static_html_snapshot(html_path: Path) -> _StaticHtmlSnapshot:
    content = html_path.read_text(encoding="utf-8-sig", errors="replace")
    parser = _StaticHtmlParser()
    parser.feed(content)
    return _StaticHtmlSnapshot(
        html=content,
        text=parser.text(),
        images=parser.images,
        stylesheet_links=parser.stylesheet_links,
        script_links=parser.script_links,
        variants=parser.variants,
        forms=parser.forms,
        controls=parser.controls,
        accordions=parser.accordions,
        carousels=parser.carousels,
        link_cards=parser.link_cards,
    )


def _static_html_issues(
    snapshot: _StaticHtmlSnapshot,
    *,
    html_path: Path,
    public_root: Path,
    slug: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if snapshot.variants <= 0:
        issues.append(
            {
                "slug": slug,
                "code": "missing-responsive-variant",
                "severity": "error",
                "path": str(html_path),
            }
        )
    for match in TEMPLATE_ARTIFACT_RE.finditer(snapshot.text):
        issues.append(
            {
                "slug": slug,
                "code": "template-artifact-visible",
                "severity": "error",
                "match": match.group(0),
                "path": str(html_path),
            }
        )
    for asset_url in [
        *snapshot.images,
        *snapshot.stylesheet_links,
        *snapshot.script_links,
    ]:
        asset_path = _local_public_asset_path(
            asset_url, html_path=html_path, public_root=public_root
        )
        if asset_path is None or asset_path.exists():
            continue
        issues.append(
            {
                "slug": slug,
                "code": "missing-static-asset",
                "severity": "error",
                "asset": asset_url,
                "path": str(asset_path),
            }
        )
    return issues


def _static_html_metrics(
    snapshot: _StaticHtmlSnapshot | None,
    *,
    slug: str,
    width: int,
) -> dict[str, Any]:
    if snapshot is None:
        return {
            "slug": slug,
            "viewport": width,
            "engine": "static-html",
            "htmlPresent": False,
        }
    return {
        "slug": slug,
        "viewport": width,
        "engine": "static-html",
        "htmlPresent": True,
        "responsiveVariants": snapshot.variants,
        "visibleImages": len(snapshot.images),
        "forms": snapshot.forms,
        "controls": snapshot.controls,
        "accordions": snapshot.accordions,
        "carousels": snapshot.carousels,
        "linkCards": snapshot.link_cards,
    }


def _local_public_asset_path(
    url: str,
    *,
    html_path: Path,
    public_root: Path,
) -> Path | None:
    parsed = urlsplit(str(url))
    if parsed.scheme in {"http", "https", "data", "mailto", "tel"}:
        return None
    if not parsed.path:
        return None
    path = unquote(parsed.path)
    if path.startswith("/"):
        return public_root / path.lstrip("/")
    return html_path.parent / path


class _StaticHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.stylesheet_links: list[str] = []
        self.script_links: list[str] = []
        self.variants = 0
        self.forms = 0
        self.controls = 0
        self.accordions = 0
        self.carousels = 0
        self.link_cards = 0
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        class_name = attr.get("class", "")
        if tag == "img" and attr.get("src"):
            self.images.append(attr["src"])
        if tag == "link" and attr.get("rel", "").lower() == "stylesheet" and attr.get("href"):
            self.stylesheet_links.append(attr["href"])
        if tag == "script" and attr.get("src"):
            self.script_links.append(attr["src"])
        if "pipeline-responsive-variant" in class_name.split():
            self.variants += 1
        if tag == "form" or attr.get("data-component") == "form":
            self.forms += 1
        if tag in {"input", "textarea", "select", "button"}:
            self.controls += 1
        if tag == "details" and attr.get("data-component") == "accordion-item":
            self.accordions += 1
        if attr.get("data-carousel") == "true":
            self.carousels += 1
        if attr.get("data-component") == "link-card":
            self.link_cards += 1

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._text_parts.append(data)

    def text(self) -> str:
        return " ".join(part.strip() for part in self._text_parts if part.strip())


def _load_page_slugs(source_dir: Path) -> list[str]:
    report_path = source_dir / "report.json"
    if not report_path.exists():
        raise ValueError(f"Missing pipeline report file: {report_path}")
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if payload.get("pipeline") != "pipeline":
        raise ValueError(f"Expected a pipeline report: {report_path}")
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"Pipeline report does not list any pages: {report_path}")
    slugs = [str(page.get("slug") or "").strip("/") for page in pages if isinstance(page, dict)]
    slugs = [slug for slug in slugs if slug]
    if not slugs:
        raise ValueError(f"Pipeline report pages do not contain slugs: {report_path}")
    return slugs


def _build_hugo_site(*, source_dir: Path, public_dir: Path, hugo_bin: str) -> dict[str, Any]:
    public_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            hugo_bin,
            "--source",
            str(source_dir),
            "--destination",
            str(public_dir),
            "--cleanDestinationDir",
            "--quiet",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    result = {
        "command": hugo_bin,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise RuntimeError(f"Hugo build failed for visual smoke: {completed.stderr.strip()}")
    return result


def _viewport_for_width(width: int) -> dict[str, int]:
    if width <= 402:
        height = 874
    elif width <= 834:
        height = 1112
    else:
        height = 920
    return {"width": width, "height": height}


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _relative_output_path(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path
    return relative.as_posix()


def _visual_review_record(
    screenshot_path: Path,
    *,
    out_dir: Path,
    baseline_dir: Path | None,
    slug: str,
    width: int,
    review_threshold: float,
    fail_threshold: float,
    reference_kind: str = "visual-baseline",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "slug": slug,
        "viewport": width,
        "screenshot": _relative_output_path(screenshot_path, out_dir),
        "referenceKind": reference_kind,
        "status": "capture-only",
        "baseline": None,
        "diff": None,
        "pixelDiffRatio": None,
        "sizeMismatch": False,
    }
    if baseline_dir is None:
        return record

    baseline_path = baseline_dir / screenshot_path.name
    record["baseline"] = str(baseline_path)
    if not baseline_path.exists():
        record["status"] = (
            "missing-figma-reference" if reference_kind == "figma-reference" else "missing-baseline"
        )
        return record

    with Image.open(screenshot_path) as current_image, Image.open(baseline_path) as baseline_image:
        current = current_image.convert("RGB")
        baseline = baseline_image.convert("RGB")
        if current.size != baseline.size:
            record["sizeMismatch"] = True
            record["baselineSize"] = {"width": baseline.width, "height": baseline.height}
            record["actualSize"] = {"width": current.width, "height": current.height}
            record["sizeDelta"] = {
                "width": current.width - baseline.width,
                "height": current.height - baseline.height,
            }
            common_width = min(current.width, baseline.width)
            common_height = min(current.height, baseline.height)
            if common_width <= 0 or common_height <= 0:
                record["status"] = "fail"
                record["sizeMismatchKind"] = "empty-common-area"
                return record
            current_crop = current.crop((0, 0, common_width, common_height))
            baseline_crop = baseline.crop((0, 0, common_width, common_height))
            diff = ImageChops.difference(current_crop, baseline_crop)
            pixel_diff_ratio = _pixel_diff_ratio(diff)
            record["pixelDiffRatio"] = pixel_diff_ratio
            record["commonCropPixelDiffRatio"] = pixel_diff_ratio
            if pixel_diff_ratio > 0:
                diff_path = out_dir / f"{slug}-{width}-diff.png"
                diff.save(diff_path)
                record["diff"] = _relative_output_path(diff_path, out_dir)
            if current.width == baseline.width and current.height != baseline.height:
                record["sizeMismatchKind"] = "height-only"
                if pixel_diff_ratio > fail_threshold:
                    record["status"] = "fail"
                elif pixel_diff_ratio > review_threshold:
                    record["status"] = "review"
                else:
                    record["status"] = "height-delta-review"
                return record
            record["sizeMismatchKind"] = "width-or-both"
            record["status"] = "fail" if pixel_diff_ratio > fail_threshold else "review"
            return record
        diff = ImageChops.difference(current, baseline)
        pixel_diff_ratio = _pixel_diff_ratio(diff)
        record["pixelDiffRatio"] = pixel_diff_ratio
        if pixel_diff_ratio > 0:
            diff_path = out_dir / f"{slug}-{width}-diff.png"
            diff.save(diff_path)
            record["diff"] = _relative_output_path(diff_path, out_dir)
        if pixel_diff_ratio > fail_threshold:
            record["status"] = "fail"
        elif pixel_diff_ratio > review_threshold:
            record["status"] = "review"
        else:
            record["status"] = "pass"
    return record


def _pixel_diff_ratio(diff: Image.Image) -> float:
    red, green, blue = diff.convert("RGB").split()
    max_channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = max_channel.point(lambda value: 255 if value > VISUAL_DIFF_PIXEL_TOLERANCE else 0)
    histogram = mask.histogram()
    different_pixels = histogram[255]
    total_pixels = mask.width * mask.height
    if total_pixels <= 0:
        return 0.0
    return round(different_pixels / total_pixels, 6)


@contextmanager
def _served_directory(directory: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def guess_type(self, path: str | PathLike[str]) -> str:
            path_text = str(path)
            translated = Path(self.translate_path(path_text))
            if translated.suffix.lower() == ".bin":
                detected = _image_mime_type(translated)
                if detected:
                    return detected
            return super().guess_type(path_text)

    def handler(*args: Any, **kwargs: Any) -> QuietHandler:
        return QuietHandler(*args, directory=str(directory), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _image_mime_type(path: Path) -> str:
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return ""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    return ""


_SMOKE_SCRIPT = """
({ slug, viewport }) => {
  const issues = [];
  const isVisible = (el) => {
    if (!(el instanceof Element)) return false;
    const cs = window.getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity || "1") < 0.03) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  };
  const rectOf = (el) => {
    const rect = el.getBoundingClientRect();
    return {
      x: Math.round(rect.left * 100) / 100,
      y: Math.round((rect.top + window.scrollY) * 100) / 100,
      w: Math.round(rect.width * 100) / 100,
      h: Math.round(rect.height * 100) / 100,
      right: Math.round(rect.right * 100) / 100,
      bottom: Math.round((rect.bottom + window.scrollY) * 100) / 100,
    };
  };
  const selectorOf = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const classes = [...el.classList].slice(0, 4).map((name) => `.${CSS.escape(name)}`).join("");
    return `${el.tagName.toLowerCase()}${classes}`;
  };
  const textOf = (el) => (el.textContent || el.getAttribute("placeholder") || "").replace(/\\s+/g, " ").trim();
  const vw = document.documentElement.clientWidth;
  const scrollWidth = Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0);
  const scrollHeight = Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight || 0);
  const overflowX = scrollWidth - vw;
  if (overflowX > 2) {
    issues.push({
      code: "horizontal-overflow",
      severity: overflowX > 20 ? "error" : "warn",
      overflowX: Math.round(overflowX),
    });
  }

  const visibleVariants = [...document.querySelectorAll(".pipeline-responsive-variant")]
    .filter(isVisible)
    .map((el) => Number(el.getAttribute("data-pipeline-width")));
  const expectedVariant = viewport.width <= 618 ? 402 : viewport.width <= 1377 ? 834 : 1920;
  if (visibleVariants.length !== 1 || visibleVariants[0] !== expectedVariant) {
    issues.push({
      code: "responsive-variant-mismatch",
      severity: "error",
      expectedVariant,
      visibleVariants,
    });
  }

  for (const el of [...document.querySelectorAll(".pipeline-text, input, textarea, select, button")].filter(isVisible)) {
    const rect = el.getBoundingClientRect();
    if (rect.left < -2 || rect.right > vw + 2) {
      issues.push({
        code: "visible-text-overflow",
        severity: Math.max(-rect.left, rect.right - vw) > 20 ? "error" : "warn",
        selector: selectorOf(el),
        text: textOf(el).slice(0, 120),
        rect: rectOf(el),
      });
    }
    const cs = window.getComputedStyle(el);
    const clips = /(hidden|clip)/.test(`${cs.overflow} ${cs.overflowX} ${cs.overflowY}`);
    const clipX = el.scrollWidth - el.clientWidth;
    const clipY = el.scrollHeight - el.clientHeight;
    if (clips && (clipX > 3 || clipY > 3)) {
      issues.push({
        code: "visible-text-clipped",
        severity: clipX > 12 || clipY > 12 ? "error" : "warn",
        selector: selectorOf(el),
        text: textOf(el).slice(0, 120),
        clipX: Math.round(clipX),
        clipY: Math.round(clipY),
        rect: rectOf(el),
      });
    }
  }

  const visibleImages = [...document.images].filter(isVisible);
  const brokenImages = visibleImages.filter((img) => img.complete && img.naturalWidth === 0);
  for (const img of brokenImages) {
    issues.push({
      code: "broken-visible-image",
      severity: "error",
      selector: selectorOf(img),
      src: img.currentSrc || img.src || img.getAttribute("src"),
      rect: rectOf(img),
    });
  }

  const linkCards = [...document.querySelectorAll("[data-component='link-card']")].filter(isVisible);
  const linkCardsWithoutHref = linkCards.filter((el) => !(el.getAttribute("href") || "").trim());
  for (const card of linkCardsWithoutHref) {
    issues.push({
      code: "link-card-missing-href",
      severity: "error",
      selector: selectorOf(card),
      text: textOf(card).slice(0, 120),
      rect: rectOf(card),
    });
  }

  const bodyText = document.body.innerText || "";
  for (const pattern of [/ZgotmplZ/, /%![A-Za-z]/, /https?:\\/\\/unsplash\\.com\\//]) {
    const match = bodyText.match(pattern);
    if (match) {
      issues.push({
        code: "template-or-url-text-visible",
        severity: "error",
        match: match[0],
      });
    }
  }

  const forms = [...document.querySelectorAll("form[data-component='form']")].filter(isVisible);
  const controls = [...document.querySelectorAll("input, textarea, select, button[type='submit']")].filter(isVisible);
  const accordions = [...document.querySelectorAll("details[data-component='accordion-item']")].filter(isVisible);
  const summaries = [...document.querySelectorAll("summary[data-component='accordion-trigger']")].filter(isVisible);

  return {
    issues,
    metrics: {
      slug,
      scrollWidth,
      scrollHeight,
      clientWidth: vw,
      overflowX: Math.max(0, Math.round(overflowX)),
      visibleVariants,
      expectedVariant,
      visibleImages: visibleImages.length,
      brokenImages: brokenImages.length,
      linkCards: linkCards.length,
      linkCardsWithoutHref: linkCardsWithoutHref.length,
      forms: forms.length,
      controls: controls.length,
      accordions: accordions.length,
      summaries: summaries.length,
    },
  };
}
"""


_IMAGE_DECODE_SCRIPT = """
async () => {
  const isVisible = (el) => {
    if (!(el instanceof Element)) return false;
    const cs = window.getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity || "1") < 0.03) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  };
  const images = [...document.images].filter(isVisible);
  const decodeAll = Promise.all(images.map(async (img) => {
    if (img.complete && img.naturalWidth > 0) {
      return;
    }
    try {
      await img.decode();
    } catch (_error) {
      // Keep real broken images visible to the smoke checks below.
    }
  }));
  const timeout = new Promise((resolve) => window.setTimeout(resolve, 5000));
  await Promise.race([decodeAll, timeout]);
}
"""
