"""Construit les references qui relient le rendu genere a sa source Figma."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from figma2hugo.pipeline.fetcher import FigmaPipelineRawClient, resolve_figma_pipeline_token
from figma2hugo.pipeline.naming import slugify as _slug

FIGMA_REFERENCE_VERSION = 1
DEFAULT_FIGMA_REFERENCE_WIDTHS = (1920, 1440, 1280, 1024, 834, 402)
RESPONSIVE_PAGE_RE = re.compile(r"^(?P<family>.+)-(?P<width>\d{3,4})$")
WIDTH_SUFFIX_RE = re.compile(r"-\d{3,4}$")


@dataclass(frozen=True, slots=True)
class PreparedFigmaReference:
    reference_dir: Path | None
    report: dict[str, Any]


def build_figma_reference_plan(
    *,
    groups: list[Any],
    hugo_pages: list[dict[str, Any]],
    raw_payloads: list[dict[str, Any]],
    source_targets: list[Any],
    widths: tuple[int, ...] = DEFAULT_FIGMA_REFERENCE_WIDTHS,
) -> dict[str, Any]:
    sources = _reference_sources(raw_payloads=raw_payloads, source_targets=source_targets)
    if not sources:
        return _empty_plan("site was not generated from Figma URLs")

    source_by_slug_width = {
        (str(source["slug"]), int(source["width"])): source for source in sources
    }
    source_by_family_width = {
        (str(source["family"]), int(source["width"])): source for source in sources
    }
    items: list[dict[str, Any]] = []
    page_matches = _match_hugo_pages(groups=groups, hugo_pages=hugo_pages)
    for group, page in page_matches:
        slug = str(page.get("slug") or "").strip("/")
        if not slug:
            continue
        manifest = getattr(group, "responsive_manifest", None)
        plans = list(getattr(group, "plans", []) or [])
        if manifest is not None and len(plans) > 1:
            family = str(getattr(manifest, "family", "") or slug)
            for viewport in widths:
                plan = _active_plan_for_viewport(plans, viewport)
                if plan is None:
                    continue
                source = source_by_family_width.get((family, int(plan.width)))
                if source is None:
                    continue
                items.append(
                    _reference_item(
                        slug=slug,
                        viewport=viewport,
                        source=source,
                        responsive=True,
                    )
                )
            continue
        for plan in plans[:1]:
            source = source_by_slug_width.get((_slug(str(plan.page_name)), int(plan.width)))
            if source is None:
                source = source_by_family_width.get(
                    (_variant_family(str(plan.page_name), int(plan.width)), int(plan.width))
                )
            if source is None:
                continue
            items.append(
                _reference_item(
                    slug=slug,
                    viewport=int(plan.width),
                    source=source,
                    responsive=False,
                )
            )

    return {
        "version": FIGMA_REFERENCE_VERSION,
        "pipeline": "pipeline",
        "enabled": bool(items),
        "source": "figma-render",
        "status": "planned" if items else "unavailable",
        "reason": "planned Figma render references" if items else "no matching Figma nodes",
        "widths": list(widths),
        "count": len(items),
        "items": items,
    }


def prepare_figma_reference_images(
    *,
    source_dir: Path,
    out_dir: Path,
    token: str | None = None,
) -> PreparedFigmaReference:
    plan = _load_figma_reference_plan(source_dir)
    if not plan.get("enabled"):
        return PreparedFigmaReference(
            reference_dir=None,
            report={**plan, "prepared": False},
        )
    resolved_token = token or resolve_figma_pipeline_token()
    if not resolved_token:
        return PreparedFigmaReference(
            reference_dir=None,
            report={
                **plan,
                "prepared": False,
                "status": "unavailable",
                "reason": "Figma token missing for visual reference export",
            },
        )

    reference_dir = out_dir / "figma-reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    items = [item for item in plan.get("items", []) if isinstance(item, dict)]
    urls_by_key = _fetch_render_urls(items, token=resolved_token)
    source_cache: dict[tuple[str, str], Path] = {}
    prepared_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("fileKey") or ""), str(item.get("nodeId") or ""))
        url = urls_by_key.get(key)
        if not url:
            errors.append({"item": _item_label(item), "error": "missing Figma render URL"})
            continue
        try:
            source_path = source_cache.get(key)
            if source_path is None:
                source_path = (
                    reference_dir / f"_source-{_safe_filename(key[0])}-{_safe_filename(key[1])}.png"
                )
                source_path.write_bytes(_download_image_bytes(url))
                source_cache[key] = source_path
            output_path = reference_dir / str(item["fileName"])
            _write_viewport_reference(source_path, output_path, item)
            prepared_items.append(
                {
                    **item,
                    "path": output_path.name,
                    "absolutePath": str(output_path),
                    "status": "ready",
                }
            )
        except Exception as exc:  # pragma: no cover - defensive network/image path
            errors.append({"item": _item_label(item), "error": str(exc)})

    manifest = {
        **plan,
        "prepared": True,
        "status": "ready" if prepared_items else "unavailable",
        "reason": "Figma references exported" if prepared_items else "No Figma references exported",
        "referenceDir": str(reference_dir),
        "preparedCount": len(prepared_items),
        "errorCount": len(errors),
        "items": prepared_items,
        "errors": errors,
    }
    (reference_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return PreparedFigmaReference(
        reference_dir=reference_dir if prepared_items else None,
        report=manifest,
    )


def _fetch_render_urls(items: list[dict[str, Any]], *, token: str) -> dict[tuple[str, str], str]:
    node_ids_by_file: dict[str, set[str]] = {}
    for item in items:
        file_key = str(item.get("fileKey") or "")
        node_id = str(item.get("nodeId") or "")
        if file_key and node_id:
            node_ids_by_file.setdefault(file_key, set()).add(node_id)

    urls: dict[tuple[str, str], str] = {}
    client = FigmaPipelineRawClient(token=token)
    for file_key, node_ids in node_ids_by_file.items():
        render_urls = client.get_node_render_urls(file_key, sorted(node_ids))
        for node_id, url in render_urls.items():
            urls[(file_key, str(node_id))] = url
    return urls


def _download_image_bytes(url: str) -> bytes:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _write_viewport_reference(source_path: Path, output_path: Path, item: dict[str, Any]) -> None:
    viewport = int(item.get("viewport") or 0)
    source_width = int(item.get("sourceWidth") or viewport)
    if viewport <= 0 or source_width <= 0:
        raise ValueError("Figma reference item has invalid widths.")
    with Image.open(source_path) as image:
        source = image.convert("RGB")
        target_width = viewport if viewport <= source_width else source_width
        scale = target_width / max(1, source.width)
        target_height = max(1, int(round(source.height * scale)))
        resized = source.resize((target_width, target_height), Image.Resampling.LANCZOS)
        if viewport > target_width:
            canvas = Image.new("RGB", (viewport, target_height), "white")
            canvas.paste(resized, ((viewport - target_width) // 2, 0))
            canvas.save(output_path)
            return
        resized.save(output_path)


def _load_figma_reference_plan(source_dir: Path) -> dict[str, Any]:
    report_path = source_dir / "report.json"
    if not report_path.exists():
        return _empty_plan("missing site report")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return _empty_plan("invalid site report JSON")
    plan = report.get("figmaReference")
    return (
        plan if isinstance(plan, dict) else _empty_plan("site report has no Figma reference plan")
    )


def _reference_sources(
    *,
    raw_payloads: list[dict[str, Any]],
    source_targets: list[Any],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for index, raw_payload in enumerate(raw_payloads):
        if index >= len(source_targets):
            continue
        target = source_targets[index]
        file_key = str(getattr(target, "file_key", "") or "")
        if not file_key:
            continue
        for payload in _expand_raw_payload(raw_payload):
            node_id = str(payload.get("id") or "")
            bounds = payload.get("absoluteBoundingBox")
            if not node_id or not isinstance(bounds, dict):
                continue
            width = _positive_int(bounds.get("width"))
            height = _positive_int(bounds.get("height"))
            if width is None or height is None:
                continue
            name = str(payload.get("name") or "")
            sources.append(
                {
                    "fileKey": file_key,
                    "nodeId": node_id,
                    "rawRootName": name,
                    "slug": _slug(name),
                    "family": _variant_family(name, width),
                    "width": width,
                    "height": height,
                }
            )
    return sources


def _expand_raw_payload(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    child_pages = [
        child
        for child in raw_payload.get("children", [])
        if isinstance(child, dict) and _looks_like_page_variant_root(child)
    ]
    return child_pages or [raw_payload]


def _looks_like_page_variant_root(node: dict[str, Any]) -> bool:
    name = _slug(str(node.get("name") or ""))
    if not RESPONSIVE_PAGE_RE.match(name):
        return False
    bounds = node.get("absoluteBoundingBox")
    return isinstance(bounds, dict) and _positive_int(bounds.get("width")) is not None


def _match_hugo_pages(
    *, groups: list[Any], hugo_pages: list[dict[str, Any]]
) -> list[tuple[Any, dict[str, Any]]]:
    remaining = list(hugo_pages)
    matches: list[tuple[Any, dict[str, Any]]] = []
    for group in groups:
        manifest = getattr(group, "responsive_manifest", None)
        plans = list(getattr(group, "plans", []) or [])
        matched: dict[str, Any] | None = None
        if manifest is not None and len(plans) > 1:
            family = str(getattr(manifest, "family", "") or "")
            matched = _pop_matching_page(remaining, responsive=True, title=f"{family} responsive")
        elif plans:
            matched = _pop_matching_page(remaining, responsive=False, title=str(plans[0].page_name))
        if matched is not None:
            matches.append((group, matched))
    return matches


def _pop_matching_page(
    pages: list[dict[str, Any]],
    *,
    responsive: bool,
    title: str,
) -> dict[str, Any] | None:
    for index, page in enumerate(pages):
        if bool(page.get("responsive")) == responsive and str(page.get("title") or "") == title:
            return pages.pop(index)
    for index, page in enumerate(pages):
        if bool(page.get("responsive")) == responsive:
            return pages.pop(index)
    return None


def _active_plan_for_viewport(plans: list[Any], viewport: int) -> Any | None:
    if not plans:
        return None
    sorted_plans = sorted(plans, key=lambda plan: int(plan.width))
    active = sorted_plans[-1]
    for index in range(len(sorted_plans) - 2, -1, -1):
        plan = sorted_plans[index]
        next_width = int(sorted_plans[index + 1].width)
        boundary = int((int(plan.width) + next_width) / 2)
        if viewport <= boundary:
            active = plan
    return active


def _reference_item(
    *,
    slug: str,
    viewport: int,
    source: dict[str, Any],
    responsive: bool,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "viewport": viewport,
        "fileName": f"{slug}-{viewport}.png",
        "fileKey": source["fileKey"],
        "nodeId": source["nodeId"],
        "rawRootName": source["rawRootName"],
        "sourceWidth": source["width"],
        "sourceHeight": source["height"],
        "derivedFromWidth": source["width"],
        "responsive": responsive,
    }


def _variant_family(name: str, width: int) -> str:
    slug = _slug(name)
    match = RESPONSIVE_PAGE_RE.match(slug)
    if match and int(match.group("width")) == width:
        return match.group("family")
    return WIDTH_SUFFIX_RE.sub("", slug) or slug


def _positive_int(value: object) -> int | None:
    if not isinstance(value, int | float | str):
        return None
    try:
        parsed = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _item_label(item: dict[str, Any]) -> str:
    return f"{item.get('slug', '')}-{item.get('viewport', '')}"


def _safe_filename(value: str) -> str:
    return _slug(value.replace(":", "-")) or "node"


def _empty_plan(reason: str) -> dict[str, Any]:
    return {
        "version": FIGMA_REFERENCE_VERSION,
        "pipeline": "pipeline",
        "enabled": False,
        "source": "figma-render",
        "status": "unavailable",
        "reason": reason,
        "count": 0,
        "items": [],
    }
