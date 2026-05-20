"""Copie, nomme et reference les assets generes dans l'arborescence Hugo."""

from __future__ import annotations

import concurrent.futures
import os
import re
import shutil
import urllib.parse
import urllib.request
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from figma2hugo.pipeline.models import RenderNodePlan, RenderPlan

CSS_URL_RE = re.compile(r"url\((?P<quote>['\"]?)(?P<url>.*?)(?P=quote)\)")


def localize_group_assets(
    groups: list[Any],
    out_dir: Path,
) -> tuple[list[Any], list[Path], dict[str, int]]:
    sources = _collect_group_asset_sources(groups)
    cache, written_assets, asset_cache = _localize_asset_sources(sources, out_dir)
    localized_groups: list[Any] = []
    for group in groups:
        localized_plans = [_localize_plan_assets(plan, cache=cache) for plan in group.plans]
        localized_groups.append(replace(group, plans=localized_plans))
    return localized_groups, written_assets, asset_cache


def _collect_group_asset_sources(groups: list[Any]) -> list[str]:
    seen: set[str] = set()
    sources: list[str] = []
    for group in groups:
        for plan in group.plans:
            for section in plan.sections:
                _collect_style_asset_sources(section.style, seen=seen, sources=sources)
                for node in section.nodes:
                    _collect_node_asset_sources(node, seen=seen, sources=sources)
    return sources


def _collect_node_asset_sources(
    node: RenderNodePlan,
    *,
    seen: set[str],
    sources: list[str],
) -> None:
    if _should_localize_asset_source(node.asset_url) and node.asset_url not in seen:
        seen.add(node.asset_url)
        sources.append(node.asset_url)
    _collect_style_asset_sources(node.style, seen=seen, sources=sources)
    for child in node.children:
        _collect_node_asset_sources(child, seen=seen, sources=sources)


def _collect_style_asset_sources(
    style: dict[str, str],
    *,
    seen: set[str],
    sources: list[str],
) -> None:
    for value in style.values():
        if "url(" not in value:
            continue
        for match in CSS_URL_RE.finditer(value):
            source = match.group("url").strip()
            if _should_localize_asset_source(source) and source not in seen:
                seen.add(source)
                sources.append(source)


def _localize_asset_sources(
    sources: list[str],
    out_dir: Path,
) -> tuple[dict[str, str], list[Path], dict[str, int]]:
    if not sources:
        return {}, [], _empty_asset_cache_stats()
    worker_count = min(16, len(sources))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(
            executor.map(lambda source: _localize_single_asset(source, out_dir), sources)
        )
    cache: dict[str, str] = {}
    written_assets: list[Path] = []
    seen_targets: set[Path] = set()
    stats = _empty_asset_cache_stats()
    stats["assetSources"] = len(sources)
    for source, public_url, target, status in results:
        cache[source] = public_url
        if status in stats:
            stats[status] += 1
        if target is not None and target not in seen_targets:
            seen_targets.add(target)
            written_assets.append(target)
    stats["localizedAssets"] = len(written_assets)
    return cache, written_assets, stats


def _empty_asset_cache_stats() -> dict[str, int]:
    return {
        "assetSources": 0,
        "localizedAssets": 0,
        "remoteCacheHits": 0,
        "remoteDownloads": 0,
        "localCopies": 0,
        "misses": 0,
    }


def _localize_single_asset(source: str, out_dir: Path) -> tuple[str, str, Path | None, str]:
    target = out_dir / "static" / "pipeline-assets" / asset_filename(source)
    try:
        if _copy_cached_remote_asset(source, target):
            return source, f"/pipeline-assets/{target.name}", target, "remoteCacheHits"
        if _copy_local_asset(source, target):
            return source, f"/pipeline-assets/{target.name}", target, "localCopies"
        if _download_remote_asset(source, target):
            _store_remote_asset_cache(source, target)
            return source, f"/pipeline-assets/{target.name}", target, "remoteDownloads"
    except OSError:
        return source, source, None, "misses"
    return source, source, None, "misses"


def _localize_plan_assets(plan: RenderPlan, *, cache: dict[str, str]) -> RenderPlan:
    return replace(
        plan,
        sections=tuple(
            replace(
                section,
                style=_localize_style_asset_urls(section.style, cache=cache),
                nodes=tuple(_localize_node_assets(node, cache=cache) for node in section.nodes),
            )
            for section in plan.sections
        ),
    )


def _localize_node_assets(
    node: RenderNodePlan,
    *,
    cache: dict[str, str],
) -> RenderNodePlan:
    children = tuple(_localize_node_assets(child, cache=cache) for child in node.children)
    asset_url = _local_asset_url(node.asset_url, cache=cache)
    style = _localize_style_asset_urls(node.style, cache=cache)
    if children == node.children and asset_url == node.asset_url and style == node.style:
        return node
    return replace(node, children=children, asset_url=asset_url, style=style)


def _local_asset_url(source: str, *, cache: dict[str, str]) -> str:
    return cache.get(source, source)


def _localize_style_asset_urls(style: dict[str, str], *, cache: dict[str, str]) -> dict[str, str]:
    if not style:
        return style
    localized: dict[str, str] = {}
    changed = False
    for key, value in style.items():
        next_value = _localize_css_url_value(value, cache=cache)
        localized[key] = next_value
        changed = changed or next_value != value
    return localized if changed else style


def _localize_css_url_value(value: str, *, cache: dict[str, str]) -> str:
    if "url(" not in value:
        return value

    def replace_match(match: re.Match[str]) -> str:
        source = match.group("url").strip()
        localized = _local_asset_url(source, cache=cache)
        quote = match.group("quote") or '"'
        return f"url({quote}{localized}{quote})"

    return CSS_URL_RE.sub(replace_match, value)


def _should_localize_asset_source(source: str) -> bool:
    return bool(source and not source.startswith(("/", "#", "data:")))


def _copy_cached_remote_asset(source: str, target: Path) -> bool:
    if not _is_remote_asset(source):
        return False
    cache_path = next((path for path in _remote_asset_cache_paths(source) if path.is_file()), None)
    if cache_path is None:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or cache_path.stat().st_size != target.stat().st_size:
        shutil.copy2(cache_path, target)
    return True


def _store_remote_asset_cache(source: str, target: Path) -> None:
    if not _is_remote_asset(source) or not target.is_file():
        return
    cache_path = _remote_asset_cache_path(source)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache_path.exists() or target.stat().st_size != cache_path.stat().st_size:
        shutil.copy2(target, cache_path)


def _remote_asset_cache_path(source: str) -> Path:
    return _remote_asset_cache_paths(source)[0]


def _remote_asset_cache_paths(source: str) -> list[Path]:
    configured_cache = os.getenv("FIGMA2HUGO_PIPELINE_ASSET_CACHE")
    cache_dir = (
        Path(configured_cache)
        if configured_cache
        else Path.cwd() / ".figma2hugo-scratch" / "pipeline-asset-cache"
    )
    candidates = [cache_dir / asset_filename(source)]
    compatibility_name = cache_dir / _compatibility_asset_filename(source)
    if compatibility_name != candidates[0]:
        candidates.append(compatibility_name)
    return candidates


def _is_remote_asset(source: str) -> bool:
    return urllib.parse.urlparse(source).scheme in {"http", "https"}


def _copy_local_asset(source: str, target: Path) -> bool:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme == "file":
        source_path = Path(urllib.request.url2pathname(parsed.path))
    else:
        source_path = Path(source)
        if parsed.scheme and not source_path.is_file():
            return False
    if not source_path.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or source_path.stat().st_mtime_ns != target.stat().st_mtime_ns:
        shutil.copy2(source_path, target)
    return True


def _download_remote_asset(source: str, target: Path) -> bool:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return True
    with urllib.request.urlopen(source, timeout=20) as response:
        target.write_bytes(response.read())
    return True


def asset_filename(source: str) -> str:
    parsed = urllib.parse.urlparse(source)
    suffix = Path(parsed.path).suffix.lower()
    if not suffix or len(suffix) > 8:
        suffix = ".png" if _is_remote_asset(source) else ".bin"
    return f"{sha256(source.encode('utf-8')).hexdigest()[:16]}{suffix}"


def _compatibility_asset_filename(source: str) -> str:
    parsed = urllib.parse.urlparse(source)
    suffix = Path(parsed.path).suffix.lower()
    if not suffix or len(suffix) > 8:
        suffix = ".bin"
    return f"{sha256(source.encode('utf-8')).hexdigest()[:16]}{suffix}"
