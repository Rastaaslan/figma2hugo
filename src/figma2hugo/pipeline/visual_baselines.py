"""Cree des identites stables pour que les comparaisons visuelles restent pertinentes."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from PIL import Image

from figma2hugo.pipeline.fetcher import FigmaPipelineTarget, parse_figma_pipeline_url

SOURCE_IDENTITY_VERSION = 1
VISUAL_BASELINE_VERSION = 1
PROJECT_ID_RE = re.compile(r"[^a-z0-9]+")
VALID_BASELINE_MODES = {"off", "capture", "compare", "auto"}


@dataclass(frozen=True, slots=True)
class ResolvedVisualBaseline:
    requested_mode: str
    resolved_mode: str
    baseline_dir: Path | None
    baseline_root: Path | None
    baseline_id: str | None
    project_id: str | None
    bootstrap_required: bool
    compatible: bool | None
    reason: str

    def to_report(self) -> dict[str, Any]:
        return {
            "mode": self.requested_mode,
            "resolvedMode": self.resolved_mode,
            "baselineDir": str(self.baseline_dir) if self.baseline_dir is not None else None,
            "baselineRoot": str(self.baseline_root) if self.baseline_root is not None else None,
            "baselineId": self.baseline_id,
            "projectId": self.project_id,
            "bootstrapRequired": self.bootstrap_required,
            "compatible": self.compatible,
            "reason": self.reason,
        }


def build_source_identity(
    raw_payloads: list[dict[str, Any]],
    *,
    figma_urls: list[str] | None = None,
    raw_files: list[str] | None = None,
) -> dict[str, Any]:
    targets: list[FigmaPipelineTarget | None] = []
    for figma_url in figma_urls or []:
        try:
            targets.append(parse_figma_pipeline_url(figma_url))
        except ValueError:
            targets.append(None)

    source_nodes: list[dict[str, Any]] = []
    stable_keys: list[str] = []
    figma_file_keys: set[str] = set()
    figma_node_ids: set[str] = set()
    raw_root_ids: set[str] = set()
    raw_root_names: set[str] = set()
    raw_file_names = [Path(raw_file).name for raw_file in raw_files or []]

    for index, raw_payload in enumerate(raw_payloads):
        target = targets[index] if index < len(targets) else None
        raw_id = str(raw_payload.get("id") or "")
        raw_name = str(raw_payload.get("name") or "")
        raw_root_ids.add(raw_id)
        raw_root_names.add(raw_name)
        node: dict[str, Any] = {
            "index": index + 1,
            "rawRootId": raw_id,
            "rawRootName": raw_name,
        }
        if index < len(raw_file_names):
            node["rawFile"] = raw_file_names[index]
        if target is not None:
            node.update(
                {
                    "sourceKind": "figma",
                    "sourceUrl": target.source_url,
                    "fileKey": target.file_key,
                    "nodeId": target.node_id,
                }
            )
            figma_file_keys.add(target.file_key)
            figma_node_ids.add(target.node_id)
            stable_keys.append(f"figma:{target.file_key}:{target.node_id}")
        else:
            node["sourceKind"] = "raw"
            stable_keys.append(f"raw:{raw_id}:{raw_name}")
        source_nodes.append(node)

    stable_source_key = "\n".join(sorted(stable_keys))
    project_hash = sha256(stable_source_key.encode("utf-8")).hexdigest()
    source_hash = _hash_json(raw_payloads)
    source_kind = "figma" if figma_file_keys else "raw"
    if figma_file_keys:
        prefix = "figma-" + "-".join(sorted(figma_file_keys)[:2])
    else:
        raw_prefix = next((name for name in sorted(raw_root_names) if name), "raw")
        prefix = f"raw-{raw_prefix}"

    return {
        "version": SOURCE_IDENTITY_VERSION,
        "pipeline": "pipeline",
        "sourceKind": source_kind,
        "projectId": _safe_project_id(f"{prefix}-{project_hash[:12]}"),
        "projectHash": project_hash,
        "sourceHash": source_hash,
        "pageCount": len(raw_payloads),
        "figmaFileKeys": sorted(figma_file_keys),
        "figmaNodeIds": sorted(figma_node_ids),
        "rawRootIds": sorted(raw_root_ids),
        "rawRootNames": sorted(raw_root_names),
        "sourceNodes": source_nodes,
    }


def load_site_source_identity(source_dir: Path) -> dict[str, Any] | None:
    report_path = source_dir / "report.json"
    if not report_path.exists():
        return None
    payload = json.loads(report_path.read_text(encoding="utf-8-sig"))
    identity = payload.get("sourceIdentity")
    return identity if isinstance(identity, dict) else None


def resolve_visual_baseline(
    *,
    source_dir: Path,
    baseline_mode: str | None,
    baseline_dir: Path | None,
    baseline_root: Path | None,
    baseline_id: str | None = None,
) -> ResolvedVisualBaseline:
    requested_mode = _normalize_mode(
        baseline_mode,
        baseline_dir=baseline_dir,
        baseline_root=baseline_root,
    )
    source_identity = load_site_source_identity(source_dir)
    project_id = _identity_project_id(source_identity)

    if requested_mode == "off":
        return ResolvedVisualBaseline(
            requested_mode=requested_mode,
            resolved_mode="capture",
            baseline_dir=None,
            baseline_root=baseline_root.resolve() if baseline_root is not None else None,
            baseline_id=None,
            project_id=project_id,
            bootstrap_required=False,
            compatible=None,
            reason="visual baseline comparison is disabled",
        )

    if baseline_dir is not None:
        resolved_dir = baseline_dir.resolve()
        compatible = _baseline_dir_compatible(resolved_dir, source_identity)
        return ResolvedVisualBaseline(
            requested_mode=requested_mode,
            resolved_mode="compare",
            baseline_dir=resolved_dir,
            baseline_root=baseline_root.resolve() if baseline_root is not None else None,
            baseline_id=baseline_id,
            project_id=project_id,
            bootstrap_required=False,
            compatible=compatible,
            reason="using explicit visual baseline directory",
        )

    if requested_mode == "capture":
        return ResolvedVisualBaseline(
            requested_mode=requested_mode,
            resolved_mode="capture",
            baseline_dir=None,
            baseline_root=baseline_root.resolve() if baseline_root is not None else None,
            baseline_id=None,
            project_id=project_id,
            bootstrap_required=False,
            compatible=None,
            reason="capture mode records screenshots for future promotion",
        )

    if baseline_root is None:
        if requested_mode == "compare":
            raise ValueError(
                "Visual baseline compare mode requires --baseline-dir or --baseline-root."
            )
        return ResolvedVisualBaseline(
            requested_mode=requested_mode,
            resolved_mode="capture",
            baseline_dir=None,
            baseline_root=None,
            baseline_id=None,
            project_id=project_id,
            bootstrap_required=True,
            compatible=None,
            reason="no visual baseline root was provided",
        )

    if not project_id:
        if requested_mode == "compare":
            raise ValueError(
                "Visual baseline compare mode requires a sourceIdentity in site report."
            )
        return ResolvedVisualBaseline(
            requested_mode=requested_mode,
            resolved_mode="capture",
            baseline_dir=None,
            baseline_root=baseline_root.resolve(),
            baseline_id=None,
            project_id=None,
            bootstrap_required=True,
            compatible=None,
            reason="site report has no sourceIdentity; capture a bootstrap baseline first",
        )

    resolved = _resolve_project_baseline(
        baseline_root.resolve(),
        project_id=project_id,
        baseline_id=baseline_id,
    )
    if resolved is not None:
        resolved_dir, resolved_id = resolved
        return ResolvedVisualBaseline(
            requested_mode=requested_mode,
            resolved_mode="compare",
            baseline_dir=resolved_dir,
            baseline_root=baseline_root.resolve(),
            baseline_id=resolved_id,
            project_id=project_id,
            bootstrap_required=False,
            compatible=True,
            reason="using compatible project visual baseline",
        )

    if requested_mode == "compare":
        raise ValueError(f"No visual baseline snapshot exists for project {project_id}.")
    return ResolvedVisualBaseline(
        requested_mode=requested_mode,
        resolved_mode="capture",
        baseline_dir=None,
        baseline_root=baseline_root.resolve(),
        baseline_id=None,
        project_id=project_id,
        bootstrap_required=True,
        compatible=None,
        reason="no compatible project visual baseline exists yet",
    )


def visual_baseline_manifest(
    report: dict[str, Any],
    *,
    source_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    screenshots_payload = report.get("screenshots")
    screenshots = screenshots_payload if isinstance(screenshots_payload, dict) else {}
    raw_items = screenshots.get("items")
    items = (
        [item for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    return {
        "version": VISUAL_BASELINE_VERSION,
        "pipeline": "pipeline",
        "projectIdentity": source_identity,
        "screenshotCount": len(items),
        "screenshots": [
            {
                "slug": str(item.get("slug") or ""),
                "viewport": item.get("viewport"),
                "path": str(item.get("path") or ""),
                "fullPage": item.get("fullPage") is True,
                "viewportSize": item.get("viewportSize"),
            }
            for item in items
        ],
    }


def promote_visual_baseline(
    smoke_out: Path,
    baseline_root: Path,
    *,
    baseline_id: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    smoke_out = smoke_out.resolve()
    baseline_root = baseline_root.resolve()
    report_path = smoke_out / "report.json"
    if not report_path.exists():
        raise ValueError(f"Missing visual smoke report: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    source_identity = _report_source_identity(report)
    project_id = _identity_project_id(source_identity)
    if source_identity is None or not project_id:
        raise ValueError("Visual smoke report has no project identity to promote.")

    snapshot_id = baseline_id or _default_snapshot_id(source_identity)
    project_dir = baseline_root / project_id
    snapshot_dir = project_dir / _safe_project_id(snapshot_id)
    if snapshot_dir.exists():
        raise ValueError(f"Visual baseline snapshot already exists: {snapshot_dir}")
    snapshot_dir.mkdir(parents=True)

    copied = _copy_screenshots(report, smoke_out=smoke_out, snapshot_dir=snapshot_dir)
    manifest = {
        "version": VISUAL_BASELINE_VERSION,
        "pipeline": "pipeline",
        "projectIdentity": source_identity,
        "snapshotId": snapshot_dir.name,
        "label": label,
        "createdAt": datetime.now(UTC).isoformat(),
        "sourceSmokeReport": str(report_path),
        "screenshotCount": len(copied),
        "screenshots": copied,
    }
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    index = _read_baseline_index(project_dir / "index.json")
    snapshots = [
        item
        for item in index.get("snapshots", [])
        if isinstance(item, dict) and item.get("id") != snapshot_dir.name
    ]
    snapshots.append(
        {
            "id": snapshot_dir.name,
            "label": label,
            "createdAt": manifest["createdAt"],
            "sourceHash": source_identity.get("sourceHash"),
            "screenshotCount": len(copied),
        }
    )
    index_payload = {
        "version": VISUAL_BASELINE_VERSION,
        "projectId": project_id,
        "current": snapshot_dir.name,
        "snapshots": snapshots,
    }
    (project_dir / "index.json").write_text(
        json.dumps(index_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "pipeline": "pipeline",
        "command": "promote-visual-baseline",
        "projectId": project_id,
        "baselineId": snapshot_dir.name,
        "baselineDir": str(snapshot_dir),
        "index": str(project_dir / "index.json"),
        "screenshotCount": len(copied),
    }


def _normalize_mode(
    baseline_mode: str | None,
    *,
    baseline_dir: Path | None,
    baseline_root: Path | None,
) -> str:
    if baseline_mode is None:
        if baseline_dir is not None:
            return "compare"
        if baseline_root is not None:
            return "auto"
        return "off"
    mode = baseline_mode.strip().lower()
    if mode not in VALID_BASELINE_MODES:
        raise ValueError(
            "Visual baseline mode must be one of: " + ", ".join(sorted(VALID_BASELINE_MODES)) + "."
        )
    return mode


def _baseline_dir_compatible(
    baseline_dir: Path,
    source_identity: dict[str, Any] | None,
) -> bool | None:
    manifest_path = baseline_dir / "manifest.json"
    if not manifest_path.exists() or source_identity is None:
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    baseline_identity = manifest.get("projectIdentity")
    if not isinstance(baseline_identity, dict):
        return None
    return _identity_project_id(baseline_identity) == _identity_project_id(source_identity)


def _resolve_project_baseline(
    baseline_root: Path,
    *,
    project_id: str,
    baseline_id: str | None,
) -> tuple[Path, str] | None:
    project_dir = baseline_root / project_id
    index = _read_baseline_index(project_dir / "index.json")
    snapshot_id = baseline_id or str(index.get("current") or "")
    if not snapshot_id:
        return None
    snapshot_dir = project_dir / _safe_project_id(snapshot_id)
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if _identity_project_id(manifest.get("projectIdentity")) != project_id:
        return None
    return snapshot_dir, snapshot_dir.name


def _read_baseline_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": VISUAL_BASELINE_VERSION, "snapshots": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {"version": VISUAL_BASELINE_VERSION}


def _copy_screenshots(
    report: dict[str, Any],
    *,
    smoke_out: Path,
    snapshot_dir: Path,
) -> list[dict[str, Any]]:
    screenshots_payload = report.get("screenshots")
    screenshots = screenshots_payload if isinstance(screenshots_payload, dict) else {}
    raw_items = screenshots.get("items")
    items = (
        [item for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    copied: list[dict[str, Any]] = []
    for item in items:
        relative_path = str(item.get("path") or "")
        if not relative_path:
            continue
        source_path = smoke_out / relative_path
        if not source_path.exists():
            raise ValueError(f"Missing screenshot for baseline promotion: {source_path}")
        target_name = Path(relative_path).name
        shutil.copy2(source_path, snapshot_dir / target_name)
        screenshot_record = {
            "slug": str(item.get("slug") or ""),
            "viewport": item.get("viewport"),
            "path": target_name,
            "fullPage": item.get("fullPage") is True,
            "viewportSize": item.get("viewportSize"),
        }
        try:
            with Image.open(source_path) as image:
                screenshot_record["imageSize"] = {"width": image.width, "height": image.height}
        except OSError:
            pass
        copied.append(screenshot_record)
    return copied


def _report_source_identity(report: dict[str, Any]) -> dict[str, Any] | None:
    identity = report.get("sourceIdentity")
    if isinstance(identity, dict):
        return identity
    visual_review = report.get("visualReview")
    if isinstance(visual_review, dict) and isinstance(visual_review.get("sourceIdentity"), dict):
        return visual_review["sourceIdentity"]
    return None


def _identity_project_id(identity: Any) -> str | None:
    if not isinstance(identity, dict):
        return None
    project_id = str(identity.get("projectId") or "")
    return project_id or None


def _default_snapshot_id(source_identity: dict[str, Any] | None) -> str:
    source_hash = ""
    if isinstance(source_identity, dict):
        source_hash = str(source_identity.get("sourceHash") or "")[:8]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{source_hash or 'snapshot'}"


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _safe_project_id(value: str) -> str:
    safe = PROJECT_ID_RE.sub("-", value.lower()).strip("-")
    return safe[:96] or "project"
