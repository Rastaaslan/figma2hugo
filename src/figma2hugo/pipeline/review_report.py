"""Construit le rapport global utilise par l'UI, la CLI et le gate de release."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from figma2hugo.pipeline.models import IssueSeverity
from figma2hugo.pipeline.options import PipelineRenderMode, normalize_render_mode
from figma2hugo.pipeline.review_baselines import ResolvedProjectReviewBaseline
from figma2hugo.pipeline.review_contract import (
    find_responsive_review_contract,
    responsive_review_contract_summary,
)

ACCEPTED_REVIEW_CODES = {
    "accordion-closed-panel-space",
    "accordion-open-items-stacked",
    "accordion-panel-shifted-for-trigger-space",
    "accordion-single-open-state-normalized",
    "band-background-snapped-to-section",
    "background-overflow-contained",
    "container-expanded-for-semantic-content",
    "content-component-contained-to-rail",
    "content-component-row-contained-to-rail",
    "content-column-row-contained-to-rail",
    "content-static-group-contained-to-rail",
    "content-text-contained-to-rail",
    "content-text-row-contained-to-rail",
    "content-visual-strip-contained-to-rail",
    "decorative-overflow-contained",
    "flow-sibling-shifted-for-overlap",
    "footer-strip-stacked-after-content",
    "footer-text-expanded-for-readability",
    "form-controls-expanded",
    "page-height-compacted-for-semantic-content",
    "page-height-expanded-for-semantic-content",
    "section-bottom-anchored-content-shifted",
    "section-compacted-for-semantic-content",
    "section-expanded-for-semantic-content",
    "section-shifted-for-semantic-content",
    "structure-wrapper-compacted-for-semantic-content",
    "text-intrinsic-height-expanded",
    "text-sibling-shifted-for-intrinsic-height",
}
ACTIONABLE_REVIEW_CODES = {
    "bounds-from-render-bounds",
    "breakpoint-only",
    "content-conflict",
    "content-overlap",
    "large-vertical-gap",
    "no-section-candidates",
    "node-out-of-section-horizontal",
    "section-after-page-bottom",
    "section-overlap",
}


def build_site_report(
    *,
    hugo_payload: dict[str, Any],
    diagnostics_path: Path,
    diagnostic_payloads: list[dict[str, Any]],
    responsive_manifest_records: list[dict[str, Any]],
    source_identity: dict[str, Any] | None = None,
    responsive_contract: dict[str, Any] | None = None,
    project_review_baseline: ResolvedProjectReviewBaseline | None = None,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    mode = normalize_render_mode(render_mode)
    review_report = _build_review_report(
        diagnostic_payloads=diagnostic_payloads,
        responsive_manifest_records=responsive_manifest_records,
        responsive_contract=responsive_contract,
        project_review_baseline=project_review_baseline,
    )
    issue_counts: Counter[str] = Counter(
        issue["code"]
        for page in diagnostic_payloads
        for issue in page.get("diagnostics", [])
        if isinstance(issue, dict) and "code" in issue and _is_blocking_pipeline_issue(issue)
    )
    diagnostic_review_counts: Counter[str] = Counter(
        issue["code"]
        for page in diagnostic_payloads
        for issue in page.get("diagnostics", [])
        if isinstance(issue, dict) and "code" in issue and not _is_blocking_pipeline_issue(issue)
    )
    responsive_issue_counts: Counter[str] = Counter(
        issue["code"]
        for family in responsive_manifest_records
        for issue in family.get("issues", [])
        if isinstance(issue, dict) and "code" in issue and _is_blocking_responsive_issue(issue)
    )
    responsive_review_counts: Counter[str] = Counter(
        issue["code"]
        for family in responsive_manifest_records
        for issue in family.get("issues", [])
        if isinstance(issue, dict) and "code" in issue and not _is_blocking_responsive_issue(issue)
    )
    return {
        "pipeline": "pipeline",
        "renderMode": mode.value,
        "buildOk": True,
        "pageCount": len(hugo_payload.get("pages", [])),
        "pages": hugo_payload.get("pages", []),
        "sourceIdentity": source_identity,
        "diagnostics": {
            "path": str(diagnostics_path),
            "issueCount": sum(issue_counts.values()),
            "byCode": dict(sorted(issue_counts.items())),
            "reviewCount": sum(diagnostic_review_counts.values()),
            "reviewByCode": dict(sorted(diagnostic_review_counts.items())),
        },
        "responsive": {
            "familyCount": len(responsive_manifest_records),
            "issueCount": sum(responsive_issue_counts.values()),
            "byCode": dict(sorted(responsive_issue_counts.items())),
            "reviewCount": sum(responsive_review_counts.values()),
            "reviewByCode": dict(sorted(responsive_review_counts.items())),
            "families": responsive_manifest_records,
        },
        "review": review_report,
    }


def _build_review_report(
    *,
    diagnostic_payloads: list[dict[str, Any]],
    responsive_manifest_records: list[dict[str, Any]],
    responsive_contract: dict[str, Any] | None = None,
    project_review_baseline: ResolvedProjectReviewBaseline | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    matched_responsive_contract_ids: set[str] = set()
    for page in diagnostic_payloads:
        raw_page_payload = page.get("page")
        page_payload = raw_page_payload if isinstance(raw_page_payload, dict) else {}
        page_name = str(page_payload.get("name") or page_payload.get("id") or "")
        page_width = _optional_int(page_payload.get("width"))
        for issue in page.get("diagnostics", []):
            if isinstance(issue, dict) and issue.get("code"):
                items.append(
                    _review_item(
                        source="diagnostics",
                        issue=issue,
                        page=page_name,
                        family="",
                        width=_optional_int(issue.get("width")) or page_width,
                    )
                )
    for family in responsive_manifest_records:
        family_name = str(family.get("family") or "")
        for issue in family.get("issues", []):
            if isinstance(issue, dict) and issue.get("code"):
                contract_declaration = find_responsive_review_contract(
                    issue,
                    family=family_name,
                    contract=responsive_contract,
                )
                if contract_declaration is not None:
                    matched_responsive_contract_ids.add(str(contract_declaration.get("id") or ""))
                items.append(
                    _review_item(
                        source="responsive",
                        issue=issue,
                        page="",
                        family=family_name,
                        width=_optional_int(issue.get("width")),
                        responsive_contract_declaration=contract_declaration,
                    )
                )

    groups = _review_groups(items)
    report = {
        "version": 1,
        "count": len(items),
        "bySource": _count_review_items(items, "source"),
        "byClassification": _classification_counts(items),
        "byPriority": _priority_counts(items),
        "byAction": _count_review_items(items, "action"),
        "byContractRule": _count_review_items(items, "contractRule"),
        "byNodeRole": _count_review_items(items, "nodeRole"),
        "byContractDecision": _count_review_items(items, "contractDecision"),
        "topReviewSignals": groups[:10],
        "acceptedAdjustments": [
            group for group in groups if group["classification"] == "accepted-info"
        ],
        "acceptedContracts": [
            group for group in groups if group["classification"] == "accepted-contract"
        ],
        "blockingCandidates": [group for group in groups if group["classification"] == "blocking"],
        "groups": groups,
        "items": items,
    }
    if responsive_contract is not None:
        report["responsiveContract"] = responsive_review_contract_summary(
            responsive_contract,
            matched_ids=matched_responsive_contract_ids,
        )
    if project_review_baseline is not None:
        report["projectReviewBaseline"] = project_review_baseline.to_report()
    return report


def _review_item(
    *,
    source: str,
    issue: dict[str, Any],
    page: str,
    family: str,
    width: int | None,
    responsive_contract_declaration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    classification = _classify_review_item(
        source,
        issue,
        responsive_contract_declaration=responsive_contract_declaration,
    )
    action = _review_action(source, issue, classification)
    owner = _review_owner(
        source,
        issue,
        classification,
        responsive_contract_declaration=responsive_contract_declaration,
    )
    item: dict[str, Any] = {
        "source": source,
        "code": str(issue.get("code") or ""),
        "severity": str(issue.get("severity") or IssueSeverity.INFO.value),
        "classification": classification,
        "priority": _review_priority(source, issue, classification),
        "confidence": _review_confidence(classification),
        "action": action,
        "owner": owner,
        "promotionCandidate": classification in {"accepted-contract", "accepted-info"},
        "message": str(issue.get("message") or ""),
    }
    if page:
        item["page"] = page
    if family:
        item["family"] = family
    if width is not None:
        item["width"] = width
    for key in (
        "nodeId",
        "relatedNodeId",
        "key",
        "presentWidths",
        "missingWidths",
        "differenceKind",
        "nodeRole",
        "contractRule",
        "contractAction",
        "contractRisk",
    ):
        if key in issue:
            item[key] = issue[key]
    raw_metrics = issue.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    for key in (
        "gapRatio",
        "gapOverThreshold",
        "gapKind",
        "previousSectionName",
        "nextSectionName",
        "previousSectionRole",
        "nextSectionRole",
    ):
        if key in metrics:
            item[key] = metrics[key]
    if responsive_contract_declaration is not None:
        item["contractDeclarationId"] = str(responsive_contract_declaration.get("id") or "")
        item["contractDecision"] = str(responsive_contract_declaration.get("decision") or "")
        item["contractRationale"] = str(responsive_contract_declaration.get("rationale") or "")
    return item


def _classify_review_item(
    source: str,
    issue: dict[str, Any],
    *,
    responsive_contract_declaration: dict[str, Any] | None = None,
) -> str:
    if source == "diagnostics" and _is_blocking_pipeline_issue(issue):
        return "blocking"
    if source == "responsive" and _is_blocking_responsive_issue(issue):
        return "blocking"
    if source == "responsive" and responsive_contract_declaration is not None:
        return "accepted-contract"
    code = str(issue.get("code") or "")
    if (
        source == "diagnostics"
        and code == "large-vertical-gap"
        and _is_minor_vertical_gap_review(issue)
    ):
        return "accepted-info"
    if code in ACCEPTED_REVIEW_CODES:
        return "accepted-info"
    return "actionable-review"


def _review_action(source: str, issue: dict[str, Any], classification: str) -> str:
    if classification == "blocking":
        return "fix-before-promotion"
    if classification == "accepted-contract":
        return "accept-responsive-contract"
    code = str(issue.get("code") or "")
    if classification == "accepted-info" and code == "large-vertical-gap":
        return "accept-near-threshold-visual-rhythm"
    if classification == "accepted-info":
        return "accept-deterministic-adjustment"
    if (
        source == "responsive"
        and str(issue.get("differenceKind") or "") == "same-content-different-order"
    ):
        return "inspect-responsive-order-or-carousel"
    if source == "responsive" or code in {"breakpoint-only", "content-conflict"}:
        return "inspect-responsive-contract"
    if code == "large-vertical-gap":
        return "inspect-empty-space-or-figma-intent"
    if code in ACTIONABLE_REVIEW_CODES:
        return "inspect-and-calibrate"
    return "inspect-review-signal"


def _review_owner(
    source: str,
    issue: dict[str, Any],
    classification: str,
    *,
    responsive_contract_declaration: dict[str, Any] | None = None,
) -> str:
    if classification == "accepted-info":
        if str(issue.get("code") or "") == "large-vertical-gap":
            return "visual-review"
        return "pipeline"
    if classification == "accepted-contract":
        return str((responsive_contract_declaration or {}).get("owner") or "figma-contract")
    code = str(issue.get("code") or "")
    if source == "responsive" or code in {"breakpoint-only", "content-conflict"}:
        return "figma-contract"
    if code == "large-vertical-gap":
        return "figma-or-code"
    return "code"


def _review_confidence(classification: str) -> str:
    if classification in {"accepted-contract", "accepted-info"}:
        return "high"
    if classification == "blocking":
        return "high"
    return "medium"


def _review_priority(source: str, issue: dict[str, Any], classification: str) -> str:
    if classification == "blocking":
        return "P0" if str(issue.get("severity")) == IssueSeverity.ERROR.value else "P1"
    if classification in {"accepted-contract", "accepted-info"}:
        return "P3"
    code = str(issue.get("code") or "")
    if code in {"content-overlap", "section-overlap"}:
        return "P1"
    if code == "large-vertical-gap":
        return "P3" if _is_minor_vertical_gap_review(issue) else "P2"
    if code == "node-out-of-section-horizontal":
        return "P2"
    if source == "responsive" or code in {"breakpoint-only", "content-conflict"}:
        return "P3"
    return "P2"


def _is_minor_vertical_gap_review(issue: dict[str, Any]) -> bool:
    raw_metrics = issue.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    try:
        gap_ratio = float(metrics.get("gapRatio") or 0)
    except (TypeError, ValueError):
        return False
    return 1.0 < gap_ratio <= 1.5


def _review_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    for item in items:
        key = (
            str(item.get("source") or ""),
            str(item.get("code") or ""),
            str(item.get("classification") or ""),
            str(item.get("priority") or ""),
            str(item.get("action") or ""),
            str(item.get("owner") or ""),
        )
        group = grouped.setdefault(
            key,
            {
                "source": key[0],
                "code": key[1],
                "classification": key[2],
                "priority": key[3],
                "action": key[4],
                "owner": key[5],
                "count": 0,
                "pages": set(),
                "families": set(),
                "widths": set(),
                "sampleMessages": [],
            },
        )
        group["count"] += 1
        if item.get("page"):
            group["pages"].add(item["page"])
        if item.get("family"):
            group["families"].add(item["family"])
        if item.get("width") is not None:
            group["widths"].add(item["width"])
        message = item.get("message")
        if message and len(group["sampleMessages"]) < 3 and message not in group["sampleMessages"]:
            group["sampleMessages"].append(message)

    normalized: list[dict[str, Any]] = []
    for group in grouped.values():
        normalized.append(
            {
                **{
                    key: value
                    for key, value in group.items()
                    if key not in {"pages", "families", "widths"}
                },
                "pages": sorted(group["pages"]),
                "families": sorted(group["families"]),
                "widths": sorted(group["widths"]),
            }
        )
    return sorted(normalized, key=lambda item: (-int(item["count"]), item["source"], item["code"]))


def _count_review_items(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter(str(item.get(key) or "") for item in items if item.get(key))
    return dict(sorted(counts.items()))


def _classification_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = _count_review_items(items, "classification")
    for classification in ("blocking", "actionable-review", "accepted-info"):
        counts.setdefault(classification, 0)
    return dict(sorted(counts.items()))


def _priority_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = _count_review_items(items, "priority")
    for priority in ("P0", "P1", "P2", "P3"):
        counts.setdefault(priority, 0)
    return dict(sorted(counts.items()))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_blocking_responsive_issue(issue: dict[str, Any]) -> bool:
    return str(issue.get("severity", IssueSeverity.INFO.value)) in {
        IssueSeverity.WARNING.value,
        IssueSeverity.ERROR.value,
    }


def _is_blocking_pipeline_issue(issue: dict[str, Any]) -> bool:
    return str(issue.get("severity", IssueSeverity.INFO.value)) in {
        IssueSeverity.WARNING.value,
        IssueSeverity.ERROR.value,
    }
