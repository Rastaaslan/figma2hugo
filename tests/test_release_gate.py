from __future__ import annotations

from pathlib import Path

from scripts import release_gate


def test_release_gate_build_command_uses_raw_entrypoint(tmp_path: Path) -> None:
    raw_file = tmp_path / "page.raw.json"
    responsive_contract = tmp_path / "responsive-contract.json"

    command = release_gate._build_command(
        tmp_path / "site",
        None,
        [],
        [raw_file],
        None,
        cache_dir=None,
        no_cache=False,
        refresh_cache=False,
        responsive_contract=responsive_contract,
    )

    assert "build-site" in command
    assert "--raw" in command
    assert str(raw_file) in command
    assert command[command.index("--responsive-contract") + 1] == str(responsive_contract)


def test_release_gate_build_command_uses_official_pipeline_build_for_pages(tmp_path: Path) -> None:
    page_file = tmp_path / "pages.txt"

    command = release_gate._build_command(
        tmp_path / "site",
        page_file,
        ["https://www.figma.com/design/FILE/Page?node-id=1-1"],
        [],
        "secret",
        cache_dir=tmp_path / "cache",
        no_cache=False,
        refresh_cache=True,
    )

    assert "build-site" in command
    assert "--pipeline" not in command
    assert command[command.index("--page-file") + 1] == str(page_file)
    assert command[command.index("--token") + 1] == "secret"
    assert command[command.index("--cache-dir") + 1] == str(tmp_path / "cache")
    assert "--refresh-cache" in command


def test_release_gate_build_command_passes_project_contract_options(tmp_path: Path) -> None:
    contract_root = tmp_path / "review-baselines"

    command = release_gate._build_command(
        tmp_path / "site",
        tmp_path / "pages.txt",
        [],
        [],
        None,
        cache_dir=None,
        no_cache=False,
        refresh_cache=False,
        responsive_contract_root=contract_root,
        responsive_contract_id="accepted",
    )

    assert command[command.index("--responsive-contract-root") + 1] == str(contract_root)
    assert command[command.index("--responsive-contract-id") + 1] == "accepted"


def test_release_gate_collects_raw_dir_inputs(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    ignored_file = raw_dir / "notes.json"
    first_raw = raw_dir / "a.raw.json"
    second_raw = raw_dir / "b.raw.json"
    ignored_file.write_text("{}", encoding="utf-8")
    first_raw.write_text("{}", encoding="utf-8")
    second_raw.write_text("{}", encoding="utf-8")

    raw_files = release_gate._collect_raw_files([second_raw], [raw_dir])

    assert raw_files == [second_raw, first_raw]


def test_release_gate_report_checks_require_zero_issues() -> None:
    site_checks = release_gate._site_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "diagnostics": {"issueCount": 0},
            "responsive": {"issueCount": 1},
        }
    )
    smoke_checks = release_gate._smoke_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 1,
            "screenshots": {"count": 3},
        }
    )

    failed = [check["label"] for check in [*site_checks, *smoke_checks] if not check["ok"]]

    assert "responsive issueCount is zero" in failed
    assert "smoke warnCount is zero" in failed


def test_release_gate_site_checks_require_no_blocking_review_items() -> None:
    checks = release_gate._site_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "diagnostics": {"issueCount": 0},
            "responsive": {"issueCount": 0},
            "review": {
                "byClassification": {"blocking": 1},
                "byPriority": {"P0": 1, "P1": 0},
                "blockingCandidates": [{"code": "content-overlap"}],
            },
        }
    )

    failed = [check["label"] for check in checks if not check["ok"]]

    assert "review blocking count is zero" in failed
    assert "review has no blocking candidates" in failed
    assert "review P0/P1 count is zero" in failed


def test_release_gate_visual_smoke_command_passes_baseline_options(
    tmp_path: Path,
) -> None:
    baseline_dir = tmp_path / "baseline"
    baseline_root = tmp_path / "project-baselines"

    command = release_gate._visual_smoke_command(
        tmp_path / "site",
        tmp_path / "smoke",
        widths="402,834",
        screenshot_widths="402",
        baseline_dir=baseline_dir,
        baseline_root=baseline_root,
        baseline_mode="auto",
        baseline_id="current",
        diff_review_threshold=0.002,
        diff_fail_threshold=0.01,
        hugo_bin="hugo",
        token="secret",
    )

    assert "visual-smoke" in command
    assert command[command.index("--token") + 1] == "secret"
    assert command[command.index("--baseline-dir") + 1] == str(baseline_dir)
    assert command[command.index("--baseline-root") + 1] == str(baseline_root)
    assert command[command.index("--baseline-mode") + 1] == "auto"
    assert command[command.index("--baseline-id") + 1] == "current"
    assert command[command.index("--diff-review-threshold") + 1] == "0.002"
    assert command[command.index("--diff-fail-threshold") + 1] == "0.01"


def test_release_gate_report_checks_pass_visual_baseline_when_all_pass() -> None:
    checks = release_gate._smoke_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 0,
            "screenshots": {"count": 3},
            "visualReview": {"enabled": True, "count": 3, "byStatus": {"pass": 3}},
        },
        baseline_expected=True,
    )

    assert all(check["ok"] for check in checks)


def test_release_gate_report_checks_fail_visual_baseline_statuses() -> None:
    checks = release_gate._smoke_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 0,
            "screenshots": {"count": 4},
            "visualReview": {
                "enabled": True,
                "count": 4,
                "byStatus": {
                    "pass": 1,
                    "review": 1,
                    "fail": 1,
                    "missing-baseline": 1,
                },
            },
        },
        baseline_expected=True,
    )

    failed = [check["label"] for check in checks if not check["ok"]]

    assert "visual baseline has no missing baselines" in failed
    assert "visual baseline has no review diffs" in failed
    assert "visual baseline has no failed diffs" in failed
    assert "visual baseline statuses are pass only" in failed


def test_release_gate_report_checks_require_baseline_when_expected() -> None:
    checks = release_gate._smoke_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 0,
            "screenshots": {"count": 1},
            "visualReview": {"enabled": False, "count": 1, "byStatus": {"capture-only": 1}},
        },
        baseline_expected=True,
    )

    failed = [check["label"] for check in checks if not check["ok"]]

    assert "visual baseline is enabled" in failed
    assert "visual baseline has no capture-only screenshots" in failed


def test_release_gate_report_checks_allow_auto_baseline_bootstrap() -> None:
    checks = release_gate._smoke_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 0,
            "screenshots": {"count": 1},
            "visualReview": {
                "enabled": False,
                "mode": "auto",
                "resolvedMode": "capture",
                "bootstrapRequired": True,
                "baselineManifest": "visual-baseline-manifest.json",
                "count": 1,
                "byStatus": {"capture-only": 1},
            },
        },
        baseline_mode="auto",
    )

    assert all(check["ok"] for check in checks)


def test_release_gate_report_checks_treat_height_delta_as_non_pass_baseline() -> None:
    checks = release_gate._smoke_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 0,
            "screenshots": {"count": 1},
            "visualReview": {
                "enabled": True,
                "count": 1,
                "byStatus": {"height-delta-review": 1},
            },
        },
        baseline_expected=True,
    )
    failed = [check["label"] for check in checks if not check["ok"]]

    assert "visual baseline has no height delta reviews" in failed
    assert "visual baseline statuses are pass only" in failed


def test_release_gate_review_baseline_accepts_known_actionable_review() -> None:
    report = {
        "review": {
            "items": [
                {
                    "classification": "actionable-review",
                    "source": "responsive",
                    "code": "content-conflict",
                    "priority": "P3",
                    "action": "inspect-responsive-contract",
                    "owner": "figma-contract",
                    "family": "page-example",
                    "key": "section:footer",
                    "differenceKind": "content-delta",
                }
            ]
        }
    }
    baseline = {
        "version": 1,
        "approvedActionableReviews": [
            {
                "source": "responsive",
                "code": "content-conflict",
                "priority": "P3",
                "action": "inspect-responsive-contract",
                "owner": "figma-contract",
                "family": "page-example",
                "key": "section:footer",
                "differenceKind": "content-delta",
            }
        ],
    }

    checks = release_gate._review_baseline_checks(report, baseline)

    assert all(check["ok"] for check in checks)


def test_release_gate_review_baseline_rejects_unapproved_actionable_review() -> None:
    report = {
        "review": {
            "items": [
                {
                    "classification": "actionable-review",
                    "source": "diagnostics",
                    "code": "large-vertical-gap",
                    "priority": "P2",
                    "action": "inspect-empty-space-or-figma-intent",
                    "owner": "figma-or-code",
                    "page": "page-example-1920",
                    "width": 1920,
                    "nodeId": "1:2",
                    "relatedNodeId": "1:1",
                    "message": "Large vertical gap.",
                }
            ]
        }
    }
    baseline = {"version": 1, "approvedActionableReviews": []}

    checks = release_gate._review_baseline_checks(report, baseline)
    failed = {check["label"]: check for check in checks if not check["ok"]}

    assert "review baseline approves all actionable reviews" in failed
    assert failed["review baseline approves all actionable reviews"]["unapprovedCount"] == 1


def test_release_gate_review_baseline_rejects_non_object_approvals() -> None:
    checks = release_gate._review_baseline_checks(
        {"review": {"items": []}},
        {"version": 1, "approvedActionableReviews": ["not-an-object"]},
    )
    failed = {check["label"]: check for check in checks if not check["ok"]}

    assert "review baseline approvals are objects" in failed
    assert failed["review baseline approvals are objects"]["invalidEntryCount"] == 1


def test_release_gate_validates_project_review_baseline_root(tmp_path: Path) -> None:
    site = tmp_path / "site"
    smoke = tmp_path / "smoke"
    baseline_root = tmp_path / "review-baselines"
    project_dir = baseline_root / "figma-example"
    site.mkdir()
    smoke.mkdir()
    project_dir.mkdir(parents=True)
    item = {
        "classification": "actionable-review",
        "source": "responsive",
        "code": "content-conflict",
        "priority": "P3",
        "action": "inspect-responsive-contract",
        "owner": "figma-contract",
        "family": "page-example",
        "key": "section:footer",
        "differenceKind": "content-delta",
    }
    (site / "report.json").write_text(
        release_gate.json.dumps(
            {
                "pipeline": "pipeline",
                "pageCount": 1,
                "sourceIdentity": {"projectId": "figma-example"},
                "diagnostics": {"issueCount": 0},
                "responsive": {"issueCount": 0},
                "review": {
                    "byClassification": {"blocking": 0},
                    "byPriority": {"P0": 0, "P1": 0},
                    "blockingCandidates": [],
                    "items": [item],
                },
            }
        ),
        encoding="utf-8",
    )
    (smoke / "report.json").write_text(
        release_gate.json.dumps(
            {
                "pipeline": "pipeline",
                "pageCount": 1,
                "issueCount": 0,
                "errorCount": 0,
                "warnCount": 0,
                "screenshots": {"count": 1},
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "index.json").write_text(
        release_gate.json.dumps({"version": 1, "current": "accepted"}),
        encoding="utf-8",
    )
    (project_dir / "accepted.json").write_text(
        release_gate.json.dumps(
            {
                "version": 1,
                "projectIdentity": {"projectId": "figma-example"},
                "responsiveContracts": [],
                "approvedActionableReviews": [item],
            }
        ),
        encoding="utf-8",
    )

    checks = release_gate._validate_reports(
        site=site,
        smoke_out=smoke,
        review_baseline_root=baseline_root,
    )

    assert all(check["ok"] for check in checks)
    assert "project review baseline exists" in [check["label"] for check in checks]


def test_release_gate_site_checks_reject_stale_responsive_contracts() -> None:
    checks = release_gate._site_report_checks(
        {
            "pipeline": "pipeline",
            "pageCount": 1,
            "diagnostics": {"issueCount": 0},
            "responsive": {"issueCount": 0},
            "review": {
                "byClassification": {"blocking": 0},
                "byPriority": {"P0": 0, "P1": 0},
                "blockingCandidates": [],
                "responsiveContract": {
                    "declarationCount": 1,
                    "matchedCount": 0,
                    "unusedCount": 1,
                    "invalidCount": 0,
                    "unusedDeclarations": [{"family": "page-example"}],
                },
            },
        },
        responsive_contract_expected=True,
    )
    failed = {check["label"]: check for check in checks if not check["ok"]}

    assert "responsive contract has no unused declarations" in failed
    assert failed["responsive contract has no unused declarations"]["unusedCount"] == 1
