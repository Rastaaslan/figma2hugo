"""Localise et gere les baselines visuelles validees humainement."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

PROJECT_REVIEW_BASELINE_VERSION = 1
PROJECT_ID_RE = re.compile(r"[^a-z0-9]+")
REVIEW_BASELINE_MATCH_FIELDS = (
    "source",
    "code",
    "priority",
    "action",
    "owner",
    "page",
    "family",
    "width",
    "nodeId",
    "relatedNodeId",
    "key",
    "differenceKind",
)


@dataclass(frozen=True, slots=True)
class ResolvedProjectReviewBaseline:
    baseline_path: Path | None
    baseline_root: Path | None
    baseline_id: str | None
    project_id: str | None
    compatible: bool | None
    reason: str

    def to_report(self) -> dict[str, Any]:
        return {
            "baselinePath": str(self.baseline_path) if self.baseline_path is not None else None,
            "baselineRoot": str(self.baseline_root) if self.baseline_root is not None else None,
            "baselineId": self.baseline_id,
            "projectId": self.project_id,
            "compatible": self.compatible,
            "reason": self.reason,
        }


def resolve_project_review_baseline(
    *,
    source_identity: dict[str, Any] | None,
    baseline_root: Path | None,
    baseline_id: str | None = None,
) -> ResolvedProjectReviewBaseline:
    project_id = _identity_project_id(source_identity)
    resolved_root = baseline_root.resolve() if baseline_root is not None else None
    if resolved_root is None:
        return ResolvedProjectReviewBaseline(
            baseline_path=None,
            baseline_root=None,
            baseline_id=None,
            project_id=project_id,
            compatible=None,
            reason="project review baseline root is disabled",
        )
    if not project_id:
        return ResolvedProjectReviewBaseline(
            baseline_path=None,
            baseline_root=resolved_root,
            baseline_id=None,
            project_id=None,
            compatible=None,
            reason="source identity has no project id",
        )

    project_dir = resolved_root / project_id
    resolved_id = baseline_id or _current_baseline_id(project_dir)
    candidates = _baseline_candidates(project_dir, resolved_id)
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        compatible = _baseline_compatible(candidate, source_identity)
        if compatible is False:
            return ResolvedProjectReviewBaseline(
                baseline_path=candidate,
                baseline_root=resolved_root,
                baseline_id=resolved_id or candidate.stem,
                project_id=project_id,
                compatible=False,
                reason="project review baseline belongs to another source identity",
            )
        return ResolvedProjectReviewBaseline(
            baseline_path=candidate,
            baseline_root=resolved_root,
            baseline_id=resolved_id or candidate.stem,
            project_id=project_id,
            compatible=compatible,
            reason="using compatible project review baseline",
        )

    return ResolvedProjectReviewBaseline(
        baseline_path=None,
        baseline_root=resolved_root,
        baseline_id=resolved_id,
        project_id=project_id,
        compatible=None,
        reason="no project review baseline exists yet",
    )


def promote_project_review_baseline(
    site_report_or_dir: Path,
    baseline_root: Path,
    *,
    baseline_id: str | None = None,
    label: str | None = None,
    approve_actionable_reviews: bool = False,
) -> dict[str, Any]:
    report_path = _site_report_path(site_report_or_dir.resolve())
    if not report_path.exists():
        raise ValueError(f"Missing site report: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    source_identity = report.get("sourceIdentity")
    if not isinstance(source_identity, dict):
        raise ValueError("Site report has no sourceIdentity to promote.")
    project_id = _identity_project_id(source_identity)
    if not project_id:
        raise ValueError("Site report sourceIdentity has no project id.")

    snapshot_id = _safe_project_id(baseline_id or _default_snapshot_id(source_identity))
    baseline_root = baseline_root.resolve()
    project_dir = baseline_root / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = project_dir / f"{snapshot_id}.json"
    if baseline_path.exists():
        raise ValueError(f"Project review baseline already exists: {baseline_path}")

    actionable_items = _actionable_review_items(report)
    responsive_contracts = _responsive_contracts_from_items(actionable_items)
    approvals = _approved_actionable_reviews(actionable_items) if approve_actionable_reviews else []
    created_at = datetime.now(UTC).isoformat()
    payload = {
        "version": PROJECT_REVIEW_BASELINE_VERSION,
        "pipeline": "pipeline",
        "projectIdentity": source_identity,
        "snapshotId": snapshot_id,
        "label": label,
        "createdAt": created_at,
        "sourceReport": str(report_path),
        "responsiveContracts": responsive_contracts,
        "approvedActionableReviews": approvals,
    }
    baseline_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    index_path = project_dir / "index.json"
    index = _read_index(index_path)
    snapshots = [
        item
        for item in index.get("snapshots", [])
        if isinstance(item, dict) and item.get("id") != snapshot_id
    ]
    snapshots.append(
        {
            "id": snapshot_id,
            "label": label,
            "createdAt": created_at,
            "sourceHash": source_identity.get("sourceHash"),
            "responsiveContractCount": len(responsive_contracts),
            "approvedActionableReviewCount": len(approvals),
        }
    )
    index_payload = {
        "version": PROJECT_REVIEW_BASELINE_VERSION,
        "projectId": project_id,
        "current": snapshot_id,
        "snapshots": snapshots,
    }
    index_path.write_text(
        json.dumps(index_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "pipeline": "pipeline",
        "command": "promote-review-baseline",
        "projectId": project_id,
        "baselineId": snapshot_id,
        "baselinePath": str(baseline_path),
        "index": str(index_path),
        "responsiveContractCount": len(responsive_contracts),
        "approvedActionableReviewCount": len(approvals),
    }


def _site_report_path(path: Path) -> Path:
    if path.is_dir():
        return path / "report.json"
    return path


def _current_baseline_id(project_dir: Path) -> str | None:
    index = _read_index(project_dir / "index.json")
    current = str(index.get("current") or "")
    return current or None


def _baseline_candidates(project_dir: Path, baseline_id: str | None) -> list[Path]:
    if baseline_id:
        safe_id = _safe_project_id(baseline_id)
        return [
            project_dir / f"{safe_id}.json",
            project_dir / safe_id / "review-baseline.json",
            project_dir / safe_id / "contract.json",
        ]
    return [
        project_dir / "current.json",
        project_dir / "review-baseline.json",
        project_dir / "contract.json",
    ]


def _baseline_compatible(
    baseline_path: Path,
    source_identity: dict[str, Any] | None,
) -> bool | None:
    if source_identity is None:
        return None
    payload = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    project_identity = payload.get("projectIdentity")
    if not isinstance(project_identity, dict):
        return None
    return _identity_project_id(project_identity) == _identity_project_id(source_identity)


def _read_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": PROJECT_REVIEW_BASELINE_VERSION, "snapshots": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {"version": PROJECT_REVIEW_BASELINE_VERSION}


def _actionable_review_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw_review = report.get("review")
    review: dict[str, Any] = raw_review if isinstance(raw_review, dict) else {}
    raw_review_items = review.get("items")
    raw_items: list[Any] = raw_review_items if isinstance(raw_review_items, list) else []
    return [
        item
        for item in raw_items
        if isinstance(item, dict) and item.get("classification") == "actionable-review"
    ]


def _responsive_contracts_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contracts = [
        _responsive_contract_from_item(item) for item in items if item.get("source") == "responsive"
    ]
    return sorted(
        (contract for contract in contracts if contract is not None),
        key=lambda contract: (
            str(contract.get("family") or ""),
            str(contract.get("key") or ""),
            str(contract.get("code") or ""),
            str(contract.get("differenceKind") or ""),
        ),
    )


def _responsive_contract_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    required = ("family", "code", "key", "differenceKind", "contractRule", "presentWidths")
    if any(not _has_value(item.get(field)) for field in required):
        return None
    contract: dict[str, Any] = {
        "id": _contract_id(item),
        "family": str(item.get("family") or ""),
        "code": str(item.get("code") or ""),
        "key": str(item.get("key") or ""),
        "differenceKind": str(item.get("differenceKind") or ""),
        "contractRule": str(item.get("contractRule") or ""),
        "presentWidths": _widths(item.get("presentWidths")),
        "decision": _contract_decision(item),
        "rationale": _contract_rationale(item),
        "owner": str(item.get("owner") or "figma-contract"),
    }
    for key in ("nodeRole", "contractAction", "contractRisk", "missingWidths"):
        if _has_value(item.get(key)):
            contract[key] = _widths(item.get(key)) if key == "missingWidths" else item.get(key)
    return contract


def _contract_decision(item: dict[str, Any]) -> str:
    code = str(item.get("code") or "")
    difference_kind = str(item.get("differenceKind") or "")
    if code == "breakpoint-only" or difference_kind == "missing-breakpoint-node":
        return "intentional-breakpoint-only"
    if difference_kind == "same-content-different-order":
        return "intentional-carousel-or-order-variant"
    if difference_kind in {"asset-delta", "image-delta"}:
        return "intentional-asset-variant"
    return "intentional-content-variant"


def _contract_rationale(item: dict[str, Any]) -> str:
    node_role = str(item.get("nodeRole") or "responsive block")
    decision = _contract_decision(item)
    if decision == "intentional-breakpoint-only":
        return f"{node_role} is intentionally present only on selected breakpoints in Figma."
    if decision == "intentional-carousel-or-order-variant":
        return f"{node_role} order is intentionally adapted by responsive breakpoint."
    if decision == "intentional-asset-variant":
        return f"{node_role} asset is intentionally adapted by responsive breakpoint."
    return f"{node_role} content is intentionally adapted by responsive breakpoint."


def _contract_id(item: dict[str, Any]) -> str:
    parts = {
        "family": item.get("family"),
        "code": item.get("code"),
        "key": item.get("key"),
        "differenceKind": item.get("differenceKind"),
        "contractRule": item.get("contractRule"),
        "presentWidths": item.get("presentWidths"),
        "missingWidths": item.get("missingWidths"),
    }
    digest = sha256(
        json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:8]
    slug = _safe_project_id(
        "-".join(
            str(parts.get(field) or "") for field in ("family", "key", "code", "differenceKind")
        )
    )
    return f"{slug[:72]}-{digest}"


def _approved_actionable_reviews(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    approvals: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("priority") or "") in {"P0", "P1"}:
            continue
        approvals.append(
            {
                field: item[field]
                for field in REVIEW_BASELINE_MATCH_FIELDS
                if field in item and item[field] not in (None, "")
            }
        )
    return approvals


def _widths(value: Any) -> list[int]:
    if isinstance(value, list):
        raw_values = value
    elif isinstance(value, tuple):
        raw_values = list(value)
    else:
        raw_values = [value]
    widths: list[int] = []
    for raw_value in raw_values:
        try:
            widths.append(int(raw_value))
        except (TypeError, ValueError):
            continue
    return widths


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | tuple):
        return bool(value)
    return value is not None


def _identity_project_id(identity: Any) -> str | None:
    if not isinstance(identity, dict):
        return None
    project_id = str(identity.get("projectId") or "")
    return project_id or None


def _default_snapshot_id(source_identity: dict[str, Any]) -> str:
    source_hash = str(source_identity.get("sourceHash") or "")[:8]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{source_hash or 'review'}"


def _safe_project_id(value: str) -> str:
    safe = PROJECT_ID_RE.sub("-", value.lower()).strip("-")
    return safe[:96] or "project"
