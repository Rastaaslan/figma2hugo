"""Fonctions de build haut niveau utilisees par la CLI, l'UI, les tests et le gate."""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

from figma2hugo.pipeline.export import render_plan_to_dict, responsive_manifest_to_dict
from figma2hugo.pipeline.fetcher import fetch_raw_node_from_figma, parse_figma_pipeline_url
from figma2hugo.pipeline.figma_references import build_figma_reference_plan
from figma2hugo.pipeline.geometry import walk_render_nodes as _walk_nodes
from figma2hugo.pipeline.hugo_renderer import (
    PipelineHugoRenderGroup,
    write_pipeline_hugo_site,
    write_pipeline_hugo_site_groups,
)
from figma2hugo.pipeline.models import (
    IntermediatePipelineDocument,
    IssueSeverity,
    RenderNodePlan,
    RenderPlan,
)
from figma2hugo.pipeline.naming import slugify as _slug
from figma2hugo.pipeline.naming import unique_slug as _unique_slug
from figma2hugo.pipeline.options import PipelineRenderMode, normalize_render_mode
from figma2hugo.pipeline.orchestrator import Pipeline
from figma2hugo.pipeline.render_plan import build_render_plan
from figma2hugo.pipeline.responsive import (
    ResponsiveManifest,
    build_responsive_manifest,
    responsive_variant_identity,
)
from figma2hugo.pipeline.review_baselines import resolve_project_review_baseline
from figma2hugo.pipeline.review_contract import load_responsive_review_contract
from figma2hugo.pipeline.review_report import build_site_report as _build_site_report
from figma2hugo.pipeline.site_renderer import write_pipeline_static_site
from figma2hugo.pipeline.visual_baselines import build_source_identity

PAGE_VARIANT_RE = re.compile(r"^page-.+-\d{3,4}$")
CACHE_SCHEMA_VERSION = 1


def build_pipeline_from_raw_files(
    raw_files: list[Path],
    out_dir: Path,
    *,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    # Les builds raw sont le chemin le plus deterministe : pas de reseau ni token
    # Figma, seulement des donnees sauvegardees transformees en site Hugo.
    if not raw_files:
        raise ValueError("Pipeline requires at least one raw JSON file.")
    mode = normalize_render_mode(render_mode)
    out_dir.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(render_mode=mode)
    raw_payloads = _expand_raw_payloads(_read_raw_json(raw_file) for raw_file in raw_files)
    render_plan_paths: list[Path] = []
    html_paths: list[Path] = []
    diagnostic_payloads: list[dict[str, Any]] = []
    plans = []
    used_slugs: set[str] = set()

    for index, raw_payload in enumerate(raw_payloads, start=1):
        plan = pipeline.render_plan(raw_payload)
        plans.append(plan)
        slug = _unique_slug(_slug(plan.page_name) or f"page-{index}", used_slugs)
        render_plan_payload = pipeline.render_plan_payload(raw_payload)
        render_plan_path = out_dir / f"{slug}.render-plan.json"
        html_path = out_dir / f"{slug}.html"
        render_plan_path.write_text(
            json.dumps(render_plan_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        html_path.write_text(pipeline.render_static_html(raw_payload) + "\n", encoding="utf-8")
        render_plan_paths.append(render_plan_path)
        html_paths.append(html_path)
        diagnostic_payloads.append(
            {
                "page": render_plan_payload["page"],
                "diagnostics": render_plan_payload["diagnostics"],
            }
        )

    diagnostics_path = out_dir / "diagnostics.json"
    diagnostics_path.write_text(
        json.dumps({"pages": diagnostic_payloads}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    responsive_manifest_path: Path | None = None
    responsive_manifest: ResponsiveManifest | None = None
    if len(raw_payloads) > 1:
        responsive_manifest = pipeline.responsive_manifest(raw_payloads)
        responsive_manifest_path = out_dir / "responsive-manifest.json"
        responsive_manifest_path.write_text(
            json.dumps(
                responsive_manifest_to_dict(responsive_manifest), indent=2, ensure_ascii=False
            )
            + "\n",
            encoding="utf-8",
        )

    written_files = [*render_plan_paths, *html_paths, diagnostics_path]
    if responsive_manifest_path is not None:
        written_files.append(responsive_manifest_path)
    site_payload = write_pipeline_static_site(
        plans,
        out_dir / "site",
        responsive_manifest=responsive_manifest,
    )
    site_files = [Path(site_payload["index"])]
    site_files.extend(
        Path(page_file)
        for page in site_payload["pages"]
        for page_file in (page["html"], page["css"])
    )
    if "responsivePage" in site_payload:
        site_files.extend(Path(site_payload["responsivePage"][key]) for key in ("html", "css"))
    written_files.extend(site_files)
    hugo_payload = write_pipeline_hugo_site(
        plans,
        out_dir / "hugo",
        responsive_manifest=responsive_manifest,
    )
    written_files.extend(Path(path) for path in hugo_payload["files"])
    return {
        "command": "build-raw",
        "pipeline": "pipeline",
        "renderMode": mode.value,
        "rawFiles": [str(raw_file) for raw_file in raw_files],
        "outDir": str(out_dir),
        "writtenFiles": [str(path) for path in written_files],
        "renderPlans": [str(path) for path in render_plan_paths],
        "htmlFiles": [str(path) for path in html_paths],
        "diagnostics": str(diagnostics_path),
        "responsiveManifest": str(responsive_manifest_path) if responsive_manifest_path else None,
        "site": site_payload,
        "hugo": hugo_payload,
    }


def build_pipeline_from_figma_urls(
    figma_urls: list[str],
    out_dir: Path,
    *,
    token: str | None = None,
    cache_dir: Path | None = None,
    no_cache: bool = False,
    refresh_cache: bool = False,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    # Les builds par URL materialisent d'abord des snapshots raw, puis reutilisent
    # le chemin raw. L'acces Figma reste separe du rendu et les bugs sont rejouables.
    if not figma_urls:
        raise ValueError("Pipeline requires at least one Figma URL.")
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_files: list[Path] = []
    used_raw_slugs: set[str] = set()
    for index, figma_url in enumerate(figma_urls, start=1):
        target, raw_payload, _cache_stats = _cached_or_fetch_raw_payload(
            figma_url,
            token=token,
            cache_dir=cache_dir,
            no_cache=no_cache,
            refresh_cache=refresh_cache,
        )
        raw_name = _unique_slug(
            _slug(f"{target.file_key}-{target.node_id}") or f"figma-node-{index}",
            used_raw_slugs,
        )
        raw_file = raw_dir / f"{raw_name}.raw.json"
        raw_file.write_text(
            json.dumps(raw_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        raw_files.append(raw_file)
    result = build_pipeline_from_raw_files(raw_files, out_dir, render_mode=render_mode)
    result["command"] = "build-figma"
    result["figmaUrls"] = list(figma_urls)
    return result


def build_pipeline_hugo_site_from_raw_files(
    raw_files: list[Path],
    out_dir: Path,
    *,
    debug_dir: Path | None = None,
    responsive_contract: Path | None = None,
    responsive_contract_root: Path | None = None,
    responsive_contract_id: str | None = None,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    if not raw_files:
        raise ValueError("Pipeline final site requires at least one raw JSON file.")
    mode = normalize_render_mode(render_mode)
    raw_payloads = [_read_raw_json(raw_file) for raw_file in raw_files]
    resolved_debug_dir = debug_dir or out_dir / ".figma2hugo-pipeline-debug"
    source_identity = build_source_identity(
        raw_payloads,
        raw_files=[str(raw_file) for raw_file in raw_files],
    )
    return _build_pipeline_hugo_site(
        raw_payloads,
        out_dir,
        debug_dir=resolved_debug_dir,
        command="build-site",
        raw_files=[str(raw_file) for raw_file in raw_files],
        source_identity=source_identity,
        responsive_contract=responsive_contract,
        responsive_contract_root=responsive_contract_root,
        responsive_contract_id=responsive_contract_id,
        render_mode=mode,
    )


def build_pipeline_hugo_site_from_figma_urls(
    figma_urls: list[str],
    out_dir: Path,
    *,
    token: str | None = None,
    debug_dir: Path | None = None,
    cache_dir: Path | None = None,
    no_cache: bool = False,
    refresh_cache: bool = False,
    responsive_contract: Path | None = None,
    responsive_contract_root: Path | None = None,
    responsive_contract_id: str | None = None,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    if not figma_urls:
        raise ValueError("Pipeline final site requires at least one Figma URL.")
    mode = normalize_render_mode(render_mode)
    resolved_debug_dir = debug_dir or out_dir / ".figma2hugo-pipeline-debug"
    raw_dir = resolved_debug_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_payloads: list[dict[str, Any]] = []
    raw_files: list[Path] = []
    source_targets: list[Any] = []
    used_raw_slugs: set[str] = set()
    fetch_started_at = perf_counter()
    raw_cache = _empty_raw_cache_stats(cache_dir=cache_dir, no_cache=no_cache)
    for index, figma_url in enumerate(figma_urls, start=1):
        target, raw_payload, raw_cache_record = _cached_or_fetch_raw_payload(
            figma_url,
            token=token,
            cache_dir=cache_dir,
            no_cache=no_cache,
            refresh_cache=refresh_cache,
        )
        _merge_raw_cache_stats(raw_cache, raw_cache_record)
        source_targets.append(target)
        raw_payloads.append(raw_payload)
        raw_name = _unique_slug(
            _slug(f"{target.file_key}-{target.node_id}") or f"figma-node-{index}",
            used_raw_slugs,
        )
        raw_file = raw_dir / f"{raw_name}.raw.json"
        raw_file.write_text(
            json.dumps(raw_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        raw_files.append(raw_file)
    return _build_pipeline_hugo_site(
        raw_payloads,
        out_dir,
        debug_dir=resolved_debug_dir,
        command="build-site",
        raw_files=[str(raw_file) for raw_file in raw_files],
        figma_urls=list(figma_urls),
        source_identity=build_source_identity(raw_payloads, figma_urls=list(figma_urls)),
        source_targets=source_targets,
        cache_info=raw_cache,
        responsive_contract=responsive_contract,
        responsive_contract_root=responsive_contract_root,
        responsive_contract_id=responsive_contract_id,
        render_mode=mode,
        pre_performance={
            "fetchSeconds": _elapsed_seconds(fetch_started_at),
            "cacheReadSeconds": raw_cache.pop("_cacheReadSeconds", 0.0),
        },
    )


def _build_pipeline_hugo_site(
    raw_payloads: list[dict[str, Any]],
    out_dir: Path,
    *,
    debug_dir: Path,
    command: str,
    raw_files: list[str],
    figma_urls: list[str] | None = None,
    source_identity: dict[str, Any] | None = None,
    source_targets: list[Any] | None = None,
    cache_info: dict[str, Any] | None = None,
    responsive_contract: Path | None = None,
    responsive_contract_root: Path | None = None,
    responsive_contract_id: str | None = None,
    pre_performance: dict[str, float] | None = None,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> dict[str, Any]:
    mode = normalize_render_mode(render_mode)
    total_started_at = perf_counter()
    performance: dict[str, float] = {
        "fetchSeconds": 0.0,
        "cacheReadSeconds": 0.0,
        **(pre_performance or {}),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(render_mode=mode)
    source_raw_payloads = list(raw_payloads)
    raw_payloads = _expand_raw_payloads(raw_payloads)
    project_review_baseline = (
        resolve_project_review_baseline(
            source_identity=source_identity,
            baseline_root=responsive_contract_root,
            baseline_id=responsive_contract_id,
        )
        if responsive_contract_root is not None
        else None
    )
    resolved_responsive_contract = responsive_contract
    if (
        resolved_responsive_contract is None
        and project_review_baseline is not None
        and project_review_baseline.baseline_path is not None
        and project_review_baseline.compatible is not False
    ):
        resolved_responsive_contract = project_review_baseline.baseline_path
    responsive_contract_payload = load_responsive_review_contract(resolved_responsive_contract)

    phase_started_at = perf_counter()
    documents = [pipeline.normalize(raw_payload) for raw_payload in raw_payloads]
    performance["normalizeSeconds"] = _elapsed_seconds(phase_started_at)

    phase_started_at = perf_counter()
    plans = [build_render_plan(document, render_mode=mode) for document in documents]
    plans = _propagate_link_card_hrefs(plans)
    performance["renderPlanSeconds"] = _elapsed_seconds(phase_started_at)

    render_plan_paths: list[Path] = []
    diagnostic_payloads: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    for index, plan in enumerate(plans, start=1):
        slug = _unique_slug(_slug(plan.page_name) or f"page-{index}", used_slugs)
        render_plan_payload = render_plan_to_dict(plan)
        render_plan_path = debug_dir / f"{slug}.render-plan.json"
        render_plan_path.write_text(
            json.dumps(render_plan_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        render_plan_paths.append(render_plan_path)
        diagnostic_payloads.append(
            {
                "page": render_plan_payload["page"],
                "diagnostics": render_plan_payload["diagnostics"],
            }
        )

    diagnostics_path = debug_dir / "diagnostics.json"
    diagnostics_path.write_text(
        json.dumps({"pages": diagnostic_payloads}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    phase_started_at = perf_counter()
    groups = _build_render_groups(documents, plans)
    responsive_manifest_records = _write_responsive_manifests(groups, debug_dir)
    performance["responsiveSeconds"] = _elapsed_seconds(phase_started_at)

    phase_started_at = perf_counter()
    hugo_payload = write_pipeline_hugo_site_groups(
        groups,
        out_dir,
        include_debug_pages=False,
    )
    performance["hugoWriteSeconds"] = _elapsed_seconds(phase_started_at)
    figma_reference_plan = (
        build_figma_reference_plan(
            groups=groups,
            hugo_pages=[page for page in hugo_payload.get("pages", []) if isinstance(page, dict)],
            raw_payloads=source_raw_payloads,
            source_targets=source_targets or [],
        )
        if source_targets
        else None
    )

    report_path = out_dir / "report.json"
    phase_started_at = perf_counter()
    report_payload = _build_site_report(
        hugo_payload=hugo_payload,
        diagnostics_path=diagnostics_path,
        diagnostic_payloads=diagnostic_payloads,
        responsive_manifest_records=responsive_manifest_records,
        source_identity=source_identity,
        responsive_contract=responsive_contract_payload,
        project_review_baseline=project_review_baseline,
        render_mode=mode,
    )
    if figma_reference_plan is not None:
        report_payload["figmaReference"] = figma_reference_plan
    performance["reportSeconds"] = _elapsed_seconds(phase_started_at)
    performance["totalSeconds"] = _elapsed_seconds(total_started_at)
    report_payload["performance"] = performance
    report_payload["cache"] = _build_cache_report(cache_info, hugo_payload.get("assetCache"))
    report_path.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    written_files = [
        *render_plan_paths,
        diagnostics_path,
        report_path,
        *(Path(path) for path in hugo_payload["files"]),
    ]
    written_files.extend(Path(record["path"]) for record in responsive_manifest_records)

    payload: dict[str, Any] = {
        "command": command,
        "pipeline": "pipeline",
        "renderMode": mode.value,
        "rawFiles": raw_files,
        "outDir": str(out_dir),
        "debugDir": str(debug_dir),
        "writtenFiles": [str(path) for path in written_files],
        "renderPlans": [str(path) for path in render_plan_paths],
        "diagnostics": str(diagnostics_path),
        "responsiveManifest": (
            responsive_manifest_records[0]["path"]
            if len(responsive_manifest_records) == 1
            else None
        ),
        "responsiveManifests": responsive_manifest_records,
        "report": str(report_path),
        "hugo": hugo_payload,
    }
    if figma_urls is not None:
        payload["figmaUrls"] = figma_urls
    return payload


def _cached_or_fetch_raw_payload(
    figma_url: str,
    *,
    token: str | None,
    cache_dir: Path | None,
    no_cache: bool,
    refresh_cache: bool,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    target = parse_figma_pipeline_url(figma_url)
    stats = _empty_raw_cache_stats(cache_dir=cache_dir, no_cache=no_cache)
    cache_path = _raw_cache_path(target, cache_dir=cache_dir)
    if not no_cache and not refresh_cache and cache_path.exists():
        started_at = perf_counter()
        payload = _read_raw_json(cache_path)
        stats["rawHits"] += 1
        stats["_cacheReadSeconds"] += _elapsed_seconds(started_at)
        return target, payload, stats

    payload = fetch_raw_node_from_figma(figma_url, token=token)
    stats["rawMisses"] += 1
    if not no_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        stats["rawWrites"] += 1
    return target, payload, stats


def _raw_cache_path(target: Any, *, cache_dir: Path | None) -> Path:
    root = _resolved_raw_cache_dir(cache_dir)
    node_slug = _slug(target.node_id.replace(":", "-")) or "node"
    digest = sha256(f"{target.file_key}:{target.node_id}".encode()).hexdigest()[:12]
    return root / f"v{CACHE_SCHEMA_VERSION}-{target.file_key}-{node_slug}-{digest}.raw.json"


def _resolved_raw_cache_dir(cache_dir: Path | None) -> Path:
    if cache_dir is not None:
        return cache_dir
    configured = os.getenv("FIGMA2HUGO_PIPELINE_RAW_CACHE")
    if configured:
        return Path(configured)
    return Path.cwd() / ".figma2hugo-scratch" / "pipeline-raw-cache"


def _empty_raw_cache_stats(*, cache_dir: Path | None, no_cache: bool) -> dict[str, Any]:
    return {
        "enabled": not no_cache,
        "rawCacheDir": str(_resolved_raw_cache_dir(cache_dir)),
        "rawHits": 0,
        "rawMisses": 0,
        "rawWrites": 0,
        "_cacheReadSeconds": 0.0,
    }


def _merge_raw_cache_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("rawHits", "rawMisses", "rawWrites"):
        target[key] += int(source.get(key) or 0)
    target["_cacheReadSeconds"] += float(source.get("_cacheReadSeconds") or 0.0)


def _build_cache_report(
    raw_cache: dict[str, Any] | None,
    asset_cache: Any,
) -> dict[str, Any]:
    assets = asset_cache if isinstance(asset_cache, dict) else {}
    asset_enabled = any(
        int(assets.get(key) or 0)
        for key in (
            "assetSources",
            "localizedAssets",
            "remoteCacheHits",
            "remoteDownloads",
            "localCopies",
            "misses",
        )
    )
    raw_payload = {
        "enabled": bool(raw_cache.get("enabled")) if raw_cache else False,
        "cacheDir": raw_cache.get("rawCacheDir") if raw_cache else None,
        "hits": int(raw_cache.get("rawHits") or 0) if raw_cache else 0,
        "misses": int(raw_cache.get("rawMisses") or 0) if raw_cache else 0,
        "writes": int(raw_cache.get("rawWrites") or 0) if raw_cache else 0,
    }
    payload = {
        "enabled": bool(raw_payload["enabled"] or asset_enabled),
        "raw": raw_payload,
        "assets": assets,
    }
    return payload


def _elapsed_seconds(started_at: float) -> float:
    return round(max(0.0, perf_counter() - started_at), 6)


def _build_render_groups(
    documents: list[IntermediatePipelineDocument],
    plans: list[RenderPlan],
) -> list[PipelineHugoRenderGroup]:
    grouped: dict[str, list[tuple[IntermediatePipelineDocument, RenderPlan]]] = {}
    for document, plan in zip(documents, plans, strict=True):
        _, family = responsive_variant_identity(document)
        grouped.setdefault(family, []).append((document, plan))

    groups: list[PipelineHugoRenderGroup] = []
    for group_items in grouped.values():
        group_documents = [document for document, _ in group_items]
        group_plans = [plan for _, plan in group_items]
        manifest: ResponsiveManifest | None = None
        if len(group_documents) > 1:
            manifest = build_responsive_manifest(group_documents)
        groups.append(PipelineHugoRenderGroup(plans=group_plans, responsive_manifest=manifest))
    return groups


def _expand_raw_payloads(raw_payloads: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_payload in raw_payloads:
        for expanded_payload in _expand_raw_payload(raw_payload):
            key = _expanded_raw_payload_key(expanded_payload)
            if key in seen:
                continue
            seen.add(key)
            expanded.append(expanded_payload)
    return expanded


def _expand_raw_payload(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    child_pages = [
        child
        for child in raw_payload.get("children", [])
        if isinstance(child, dict) and _looks_like_page_variant_root(child)
    ]
    if not child_pages:
        return [raw_payload]
    return child_pages


def _looks_like_page_variant_root(node: dict[str, Any]) -> bool:
    name = _slug(str(node.get("name") or ""))
    if not PAGE_VARIANT_RE.match(name):
        return False
    bounds = node.get("absoluteBoundingBox")
    if not isinstance(bounds, dict):
        return False
    try:
        width = float(bounds.get("width", 0) or 0)
        height = float(bounds.get("height", 0) or 0)
    except (TypeError, ValueError):
        return False
    return width > 0 and height > 0


def _expanded_raw_payload_key(raw_payload: dict[str, Any]) -> str:
    node_id = str(raw_payload.get("id") or "").strip()
    slug = _slug(str(raw_payload.get("name") or ""))
    width = _raw_payload_width(raw_payload)
    if node_id:
        return f"id:{node_id}:name:{slug}:width:{width}"
    return f"name:{slug}:width:{width}"


def _raw_payload_width(raw_payload: dict[str, Any]) -> str:
    bounds = raw_payload.get("absoluteBoundingBox")
    if not isinstance(bounds, dict):
        return ""
    try:
        return str(int(round(float(bounds.get("width", 0) or 0))))
    except (TypeError, ValueError):
        return ""


def _propagate_link_card_hrefs(plans: list[RenderPlan]) -> list[RenderPlan]:
    hrefs_by_signature: dict[str, str] = {}
    for plan in plans:
        for node in _walk_render_nodes(plan):
            if node.component != "link-card":
                continue
            href = node.attributes.get("href", "")
            if href and href != "#":
                hrefs_by_signature.setdefault(_link_card_signature(node), href)
    if not hrefs_by_signature:
        return plans
    return [_replace_plan_link_hrefs(plan, hrefs_by_signature) for plan in plans]


def _replace_plan_link_hrefs(plan: RenderPlan, hrefs_by_signature: dict[str, str]) -> RenderPlan:
    return replace(
        plan,
        sections=tuple(
            replace(
                section,
                nodes=tuple(
                    _replace_node_link_href(node, hrefs_by_signature) for node in section.nodes
                ),
            )
            for section in plan.sections
        ),
    )


def _replace_node_link_href(
    node: RenderNodePlan,
    hrefs_by_signature: dict[str, str],
) -> RenderNodePlan:
    children = tuple(_replace_node_link_href(child, hrefs_by_signature) for child in node.children)
    attributes = dict(node.attributes)
    if node.component == "link-card" and attributes.get("href") in {"", "#"}:
        href = hrefs_by_signature.get(_link_card_signature(node))
        if href:
            attributes["href"] = href
            if href.startswith(("http://", "https://")):
                attributes["target"] = "_blank"
                attributes["rel"] = "noopener noreferrer"
    return replace(node, attributes=attributes, children=children)


def _walk_render_nodes(plan: RenderPlan) -> list[RenderNodePlan]:
    nodes: list[RenderNodePlan] = []
    for section in plan.sections:
        nodes.extend(_walk_nodes(section.nodes))
    return nodes


def _link_card_signature(node: RenderNodePlan) -> str:
    texts = [
        _slug(descendant.text) for descendant in _walk_nodes((node,)) if descendant.text.strip()
    ]
    return "|".join(text for text in texts if text) or _slug(node.name)


def _write_responsive_manifests(
    groups: list[PipelineHugoRenderGroup],
    debug_dir: Path,
) -> list[dict[str, Any]]:
    manifest_groups = [group for group in groups if group.responsive_manifest is not None]
    records: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    for index, group in enumerate(manifest_groups, start=1):
        manifest = group.responsive_manifest
        if manifest is None:
            continue
        if len(manifest_groups) == 1:
            path = debug_dir / "responsive-manifest.json"
        else:
            manifest_slug = _unique_slug(
                _slug(manifest.family) or f"responsive-{index}", used_slugs
            )
            path = debug_dir / f"{manifest_slug}.responsive-manifest.json"
        manifest_payload = responsive_manifest_to_dict(manifest)
        path.write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        blocking_count = sum(
            1
            for issue in manifest.issues
            if issue.severity in {IssueSeverity.WARNING, IssueSeverity.ERROR}
        )
        records.append(
            {
                "family": manifest.family,
                "baseWidth": manifest.base_width,
                "breakpoints": list(manifest.breakpoints),
                "path": str(path),
                "issueCount": blocking_count,
                "reviewCount": len(manifest.issues) - blocking_count,
                "signalCount": len(manifest.issues),
                "issues": manifest_payload["issues"],
            }
        )
    return records


def _read_raw_json(raw_file: Path) -> dict[str, Any]:
    try:
        payload = json.loads(raw_file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Unable to read raw JSON file: {raw_file} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid raw JSON file: {raw_file} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Raw JSON root must be an object: {raw_file}")
    return payload
