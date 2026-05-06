from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.reporting import ReportWriter, dedupe_warnings, responsive_audit_markdown


def test_dedupe_warnings_keeps_first_non_empty_occurrence() -> None:
    assert dedupe_warnings(["", " duplicate ", "other", "duplicate", None, "other"]) == [
        "duplicate",
        "other",
    ]


def test_responsive_audit_markdown_prioritizes_strict_and_text_reviews() -> None:
    report = {
        "responsive": {
            "summary": {
                "familyCount": 2,
                "strictReadyFamilyCount": 1,
                "strictBlockingFamilyCount": 1,
                "strictBlockingIssueCount": 2,
                "repeatedComponentTokenCount": 1,
                "textContentChangeCount": 1,
                "boardSplitCount": 2,
                "horizontalOverflowCount": 0,
            },
            "families": [
                {
                    "family": "landing-page",
                    "strictReady": False,
                    "issues": [
                        {
                            "type": "duplicate-sibling-token",
                            "severity": "strict-blocker",
                            "width": 402,
                            "token": "text:heading:title",
                            "parent": "page/section:hero#1",
                        },
                        {
                            "type": "text-content-change",
                            "severity": "review",
                            "width": 402,
                            "path": "page/section:hero#1/text:body:copy#1",
                        },
                        {
                            "type": "repeated-component-token",
                            "severity": "info",
                            "width": 402,
                            "token": "node:card:feature-card",
                            "parent": "page/section:features#1",
                            "count": 3,
                        },
                        {
                            "type": "duplicate-sibling-token",
                            "severity": "strict-blocker",
                            "width": 834,
                            "token": "text:heading:title",
                            "parent": "page/section:hero#1",
                        },
                    ],
                },
                {
                    "family": "legal-page",
                    "strictReady": True,
                    "issues": [
                        {
                            "type": "board-split",
                            "severity": "info",
                            "variant": "legal-page-402",
                        }
                    ],
                },
            ],
        }
    }

    markdown = responsive_audit_markdown(report)

    assert "# Audit responsive" in markdown
    assert "- Familles responsive: 2" in markdown
    assert "Priorite 1 - Debloquer le mode strict" in markdown
    assert "`text:heading:title`" in markdown
    assert "834px, 402px" in markdown
    assert "Composants repetitifs detectes" in markdown
    assert "`node:card:feature-card`" in markdown
    assert "Priorite 2 - Arbitrer les textes par breakpoint" in markdown
    assert "`page/section:hero#1/text:body:copy#1`" in markdown
    assert "- legal-page" in markdown
    assert "Verification apres corrections Figma" in markdown


def test_report_writer_writes_responsive_audit_when_families_exist() -> None:
    report = {
        "buildOk": True,
        "responsive": {
            "summary": {"familyCount": 1, "strictReadyFamilyCount": 1},
            "families": [{"family": "landing-page", "strictReady": True, "issues": []}],
        },
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        writer = ReportWriter()
        report_path = writer.write(target_dir, report)
        audit_path = writer.write_responsive_audit(target_dir, report)

        assert report_path == target_dir / "report.json"
        assert audit_path == target_dir / "responsive-audit.md"
        assert "landing-page" in audit_path.read_text(encoding="utf-8")
