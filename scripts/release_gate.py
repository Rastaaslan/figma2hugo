"""Gate de release en une commande : build, tests, Hugo et controles visuels."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _build_command(
    site: Path,
    page_file: Path | None,
    pages: list[str],
    raw_files: list[Path],
    token: str | None,
    *,
    cache_dir: Path | None,
    no_cache: bool,
    refresh_cache: bool,
    raw_dirs: list[Path] | None = None,
    responsive_contract: Path | None = None,
    responsive_contract_root: Path | None = None,
    responsive_contract_id: str | None = None,
) -> list[str]:
    command = [sys.executable, "-m", "figma2hugo.cli"]
    if raw_files or raw_dirs:
        command.extend(["build-site", str(site)])
        for raw_file in _collect_raw_files(raw_files, raw_dirs or []):
            command.extend(["--raw", str(raw_file)])
    else:
        command.extend(["build-site", str(site)])
        if page_file is not None:
            command.extend(["--page-file", str(page_file)])
        for page in pages:
            command.extend(["--page", page])
        if token:
            command.extend(["--token", token])
        if cache_dir is not None:
            command.extend(["--cache-dir", str(cache_dir)])
        if no_cache:
            command.append("--no-cache")
        if refresh_cache:
            command.append("--refresh-cache")

    if responsive_contract is not None:
        command.extend(["--responsive-contract", str(responsive_contract)])
    if responsive_contract_root is not None:
        command.extend(["--responsive-contract-root", str(responsive_contract_root)])
    if responsive_contract_id:
        command.extend(["--responsive-contract-id", responsive_contract_id])
    return command


def _collect_raw_files(raw_files: list[Path], raw_dirs: list[Path]) -> list[Path]:
    collected = list(raw_files)
    seen = {path.resolve() for path in collected if path.exists()}
    for raw_dir in raw_dirs:
        for candidate in sorted(raw_dir.glob("*.raw.json")):
            resolved = candidate.resolve()
            if resolved not in seen:
                collected.append(candidate)
                seen.add(resolved)
    return collected


def _visual_smoke_command(
    site: Path,
    smoke_out: Path,
    *,
    widths: str,
    screenshot_widths: str,
    baseline_dir: Path | None,
    baseline_root: Path | None,
    baseline_mode: str,
    baseline_id: str | None,
    diff_review_threshold: float,
    diff_fail_threshold: float,
    hugo_bin: str,
    token: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "figma2hugo.cli",
        "visual-smoke",
        str(site),
        "--out",
        str(smoke_out),
        "--widths",
        widths,
        "--screenshot-widths",
        screenshot_widths,
        "--baseline-mode",
        baseline_mode,
        "--diff-review-threshold",
        str(diff_review_threshold),
        "--diff-fail-threshold",
        str(diff_fail_threshold),
        "--hugo-bin",
        hugo_bin,
    ]
    if baseline_dir is not None:
        command.extend(["--baseline-dir", str(baseline_dir)])
    if baseline_root is not None:
        command.extend(["--baseline-root", str(baseline_root)])
    if baseline_id:
        command.extend(["--baseline-id", baseline_id])
    if token:
        command.extend(["--token", token])
    return command


def _site_report_checks(
    report: dict[str, Any],
    *,
    responsive_contract_expected: bool = False,
) -> list[dict[str, Any]]:
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), dict) else {}
    responsive = report.get("responsive") if isinstance(report.get("responsive"), dict) else {}
    review = report.get("review") if isinstance(report.get("review"), dict) else {}
    checks = [
        _check("pipeline is official", report.get("pipeline") == "pipeline"),
        _check("pageCount is positive", int(report.get("pageCount") or 0) > 0),
        _check("diagnostics issueCount is zero", int(diagnostics.get("issueCount") or 0) == 0),
        _check("responsive issueCount is zero", int(responsive.get("issueCount") or 0) == 0),
    ]
    by_classification = (
        review.get("byClassification") if isinstance(review.get("byClassification"), dict) else {}
    )
    by_priority = review.get("byPriority") if isinstance(review.get("byPriority"), dict) else {}
    blocking_candidates = review.get("blockingCandidates") or []
    checks.extend(
        [
            _check(
                "review blocking count is zero", int(by_classification.get("blocking") or 0) == 0
            ),
            _check(
                "review P0/P1 count is zero",
                int(by_priority.get("P0") or 0) + int(by_priority.get("P1") or 0) == 0,
            ),
            _check("review has no blocking candidates", len(blocking_candidates) == 0),
        ]
    )
    if responsive_contract_expected:
        contract = (
            review.get("responsiveContract")
            if isinstance(review.get("responsiveContract"), dict)
            else {}
        )
        checks.extend(
            [
                _check(
                    "responsive contract has no unused declarations",
                    int(contract.get("unusedCount") or 0) == 0,
                    unusedCount=int(contract.get("unusedCount") or 0),
                ),
                _check(
                    "responsive contract has no invalid declarations",
                    int(contract.get("invalidCount") or 0) == 0,
                    invalidCount=int(contract.get("invalidCount") or 0),
                ),
            ]
        )
    return checks


def _smoke_report_checks(
    report: dict[str, Any],
    *,
    baseline_expected: bool = False,
    baseline_mode: str = "compare",
) -> list[dict[str, Any]]:
    checks = [
        _check("smoke pipeline is official", report.get("pipeline") == "pipeline"),
        _check("smoke pageCount is positive", int(report.get("pageCount") or 0) > 0),
        _check("smoke issueCount is zero", int(report.get("issueCount") or 0) == 0),
        _check("smoke errorCount is zero", int(report.get("errorCount") or 0) == 0),
        _check("smoke warnCount is zero", int(report.get("warnCount") or 0) == 0),
        _check(
            "smoke captured screenshots",
            int((report.get("screenshots") or {}).get("count") or 0) > 0,
        ),
    ]
    visual = report.get("visualReview") if isinstance(report.get("visualReview"), dict) else {}
    bootstrap = (
        baseline_mode == "auto"
        and visual.get("resolvedMode") == "capture"
        and bool(visual.get("bootstrapRequired"))
        and bool(visual.get("baselineManifest"))
    )
    if baseline_expected and not bootstrap:
        by_status = visual.get("byStatus") if isinstance(visual.get("byStatus"), dict) else {}
        count = int(visual.get("count") or 0)
        pass_count = int(by_status.get("pass") or 0)
        checks.extend(
            [
                _check("visual baseline is enabled", bool(visual.get("enabled"))),
                _check(
                    "visual baseline has no missing baselines",
                    int(by_status.get("missing-baseline") or 0) == 0,
                ),
                _check(
                    "visual baseline has no review diffs", int(by_status.get("review") or 0) == 0
                ),
                _check("visual baseline has no failed diffs", int(by_status.get("fail") or 0) == 0),
                _check(
                    "visual baseline has no height delta reviews",
                    int(by_status.get("height-delta-review") or 0) == 0,
                ),
                _check(
                    "visual baseline has no capture-only screenshots",
                    int(by_status.get("capture-only") or 0) == 0,
                ),
                _check(
                    "visual baseline statuses are pass only",
                    count > 0 and pass_count == count,
                ),
            ]
        )
    return checks


def _review_baseline_checks(
    report: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    approvals = baseline.get("approvedActionableReviews", [])
    invalid_count = sum(1 for item in approvals if not isinstance(item, dict))
    approved = {_fingerprint(item) for item in approvals if isinstance(item, dict)}
    actionable = [
        item
        for item in (
            report.get("review", {}).get("items", [])
            if isinstance(report.get("review"), dict)
            else []
        )
        if isinstance(item, dict) and item.get("classification") == "actionable-review"
    ]
    unapproved = [item for item in actionable if _fingerprint(item) not in approved]
    return [
        _check(
            "review baseline approvals are objects",
            invalid_count == 0,
            invalidEntryCount=invalid_count,
        ),
        _check(
            "review baseline approves all actionable reviews",
            not unapproved,
            unapprovedCount=len(unapproved),
        ),
    ]


def _validate_reports(
    *,
    site: Path,
    smoke_out: Path,
    review_baseline: Path | None = None,
    review_baseline_root: Path | None = None,
    responsive_contract_expected: bool = False,
    baseline_expected: bool = False,
    baseline_mode: str = "compare",
) -> list[dict[str, Any]]:
    site_report = json.loads((site / "report.json").read_text(encoding="utf-8"))
    smoke_report = json.loads((smoke_out / "report.json").read_text(encoding="utf-8"))
    checks = [
        *_site_report_checks(
            site_report, responsive_contract_expected=responsive_contract_expected
        ),
        *_smoke_report_checks(
            smoke_report,
            baseline_expected=baseline_expected,
            baseline_mode=baseline_mode,
        ),
    ]
    baseline_payload: dict[str, Any] | None = None
    if review_baseline is not None:
        baseline_payload = json.loads(review_baseline.read_text(encoding="utf-8"))
    elif review_baseline_root is not None:
        baseline_payload, root_checks = _load_project_review_baseline(
            site_report, review_baseline_root
        )
        checks.extend(root_checks)
    if baseline_payload is not None:
        checks.extend(_review_baseline_checks(site_report, baseline_payload))
    return checks


def _load_project_review_baseline(
    report: dict[str, Any],
    root: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    project_id = str((report.get("sourceIdentity") or {}).get("projectId") or "").strip()
    if not project_id:
        return None, [_check("project review baseline projectId exists", False)]
    project_dir = root / project_id
    index_path = project_dir / "index.json"
    checks = [_check("project review baseline exists", index_path.exists())]
    if not index_path.exists():
        return None, checks
    index = json.loads(index_path.read_text(encoding="utf-8"))
    current = str(index.get("current") or "").strip()
    baseline_path = project_dir / f"{current}.json"
    checks.append(_check("project review baseline current exists", baseline_path.exists()))
    if not baseline_path.exists():
        return None, checks
    return json.loads(baseline_path.read_text(encoding="utf-8")), checks


def _fingerprint(item: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ignored = {"classification", "message", "nodeId", "relatedNodeId", "width"}
    return tuple(sorted((key, str(value)) for key, value in item.items() if key not in ignored))


def _check(label: str, ok: bool, **extra: Any) -> dict[str, Any]:
    return {"label": label, "ok": bool(ok), **extra}


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Release gate.")
    parser.add_argument("site", type=Path)
    parser.add_argument("--page-file", type=Path)
    parser.add_argument("--page", action="append", default=[])
    parser.add_argument("--raw", action="append", type=Path, default=[])
    parser.add_argument("--raw-dir", action="append", type=Path, default=[])
    parser.add_argument("--token")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--smoke-out", type=Path, required=True)
    parser.add_argument("--widths", default="402,834,1920")
    parser.add_argument("--screenshot-widths", default="402,834,1920")
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--baseline-mode", default="capture")
    parser.add_argument("--baseline-id")
    parser.add_argument("--diff-review-threshold", type=float, default=0.002)
    parser.add_argument("--diff-fail-threshold", type=float, default=0.01)
    parser.add_argument("--hugo-bin", default="hugo")
    parser.add_argument("--review-baseline", type=Path)
    parser.add_argument("--review-baseline-root", type=Path)
    parser.add_argument("--responsive-contract", type=Path)
    parser.add_argument("--responsive-contract-root", type=Path)
    parser.add_argument("--responsive-contract-id")
    args = parser.parse_args(argv)

    _run(
        _build_command(
            args.site,
            args.page_file,
            args.page,
            args.raw,
            args.token,
            cache_dir=args.cache_dir,
            no_cache=args.no_cache,
            refresh_cache=args.refresh_cache,
            raw_dirs=args.raw_dir,
            responsive_contract=args.responsive_contract,
            responsive_contract_root=args.responsive_contract_root,
            responsive_contract_id=args.responsive_contract_id,
        )
    )
    _run(
        _visual_smoke_command(
            args.site,
            args.smoke_out,
            widths=args.widths,
            screenshot_widths=args.screenshot_widths,
            baseline_dir=args.baseline_dir,
            baseline_root=args.baseline_root,
            baseline_mode=args.baseline_mode,
            baseline_id=args.baseline_id,
            diff_review_threshold=args.diff_review_threshold,
            diff_fail_threshold=args.diff_fail_threshold,
            hugo_bin=args.hugo_bin,
            token=args.token,
        )
    )
    checks = _validate_reports(
        site=args.site,
        smoke_out=args.smoke_out,
        review_baseline=args.review_baseline,
        review_baseline_root=args.review_baseline_root,
        responsive_contract_expected=bool(
            args.responsive_contract or args.responsive_contract_root
        ),
        baseline_expected=bool(args.baseline_dir or args.baseline_root),
        baseline_mode=args.baseline_mode,
    )
    print(json.dumps({"checks": checks}, indent=2, ensure_ascii=False))
    return 0 if all(check["ok"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
