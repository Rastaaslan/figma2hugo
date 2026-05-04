from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from ._shared import ensure_text, slugify


RESPONSIVE_SLUG_RE = re.compile(r"^(?P<family>.+)-(?P<width>\d{3,4})$")


def detect_responsive_variant(page_data: dict[str, Any]) -> tuple[str, int] | None:
    page = as_mapping(page_data.get("page"))
    slug = ensure_text(page.get("slug")).strip().lower()
    if not slug:
        return None
    match = RESPONSIVE_SLUG_RE.match(slug)
    if not match:
        return None
    family = ensure_text(match.group("family")).strip("-")
    width_text = ensure_text(match.group("width"))
    if not family or not width_text:
        return None
    try:
        width = int(width_text)
    except ValueError:
        return None
    return family, width


def merge_responsive_family(page_datas: list[dict[str, Any]]) -> dict[str, Any]:
    prepared_variants: list[tuple[int, dict[str, Any]]] = []
    family_slug = ""
    responsive_warnings: list[str] = []
    for page_data in page_datas:
        detected = detect_responsive_variant(page_data)
        if not detected:
            raise ValueError("Responsive family merge requires width-suffixed page slugs.")
        family_slug, width = detected
        prepared = deepcopy(page_data)
        assign_responsive_keys(prepared)
        prepared_variants.append((width, prepared))

    prepared_variants.sort(key=lambda item: item[0], reverse=True)
    base_width, merged = prepared_variants[0]
    _initialize_presence_collection(merged.get("sections", []), base_width, default_hidden=False)

    merged_page = as_mapping(merged.get("page"))
    merged_page["slug"] = family_slug
    merged_page["name"] = _strip_width_suffix(ensure_text(merged_page.get("name")), family_slug)
    merged_page["title"] = _strip_width_suffix(ensure_text(merged_page.get("title")), family_slug)
    merged["page"] = merged_page

    for width, variant_page in prepared_variants[1:]:
        responsive_warnings.extend(_collect_variant_differences(merged.get("sections", []), variant_page.get("sections", []), width))
        _sync_variant_class_names(merged.get("sections", []), variant_page.get("sections", []))
        _merge_item_collection(merged.get("sections", []), variant_page.get("sections", []), width)

    merged["assets"] = _merge_assets(prepared_variants)
    merged["warnings"] = _dedupe_warnings(
        warning
        for warning in [
            *responsive_warnings,
            *[warning for _, page_data in prepared_variants for warning in page_data.get("warnings", [])],
        ]
    )
    merged["responsive"] = {
        "family": family_slug,
        "base_width": base_width,
        "breakpoints": [width for width, _ in prepared_variants[1:]],
        "variants": [
            {
                "width": width,
                "page": variant_page,
            }
            for width, variant_page in prepared_variants[1:]
        ],
    }
    return merged


def assign_responsive_keys(page_data: dict[str, Any]) -> None:
    sections = [section for section in page_data.get("sections", []) if isinstance(section, dict)]
    _assign_collection_keys(sections, parent_key="page", item_kind="section")


def as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _assign_collection_keys(items: list[dict[str, Any]], *, parent_key: str, item_kind: str) -> None:
    occurrence_counts: dict[str, int] = {}
    for item in items:
        token = _provisional_token(item, item_kind=item_kind)
        occurrence_counts[token] = occurrence_counts.get(token, 0) + 1
        item["responsive_key"] = f"{parent_key}/{token}#{occurrence_counts[token]}"
        children = item.get("children", [])
        if isinstance(children, list) and children:
            _assign_collection_keys(children, parent_key=item["responsive_key"], item_kind="node")


def _provisional_token(item: dict[str, Any], *, item_kind: str) -> str:
    if item_kind == "section":
        role = slugify(ensure_text(item.get("role")) or "section", "section")
        name = slugify(ensure_text(item.get("name")) or ensure_text(item.get("id")) or "section", "section")
        return f"section:{role}:{name}"

    kind = ensure_text(item.get("kind")).strip().lower()
    if kind == "text":
        text = as_mapping(item.get("text"))
        role = slugify(ensure_text(text.get("role")) or ensure_text(item.get("role")) or "text", "text")
        name = slugify(ensure_text(text.get("name")) or ensure_text(text.get("id")) or ensure_text(item.get("id")) or "text", "text")
        return f"text:{role}:{name}"
    if kind == "asset":
        asset = as_mapping(item.get("asset"))
        role = slugify(ensure_text(asset.get("purpose")) or ensure_text(item.get("role")) or "asset", "asset")
        name = slugify(ensure_text(asset.get("name")) or ensure_text(asset.get("id")) or ensure_text(item.get("id")) or "asset", "asset")
        return f"asset:{role}:{name}"

    role = slugify(ensure_text(item.get("role")) or "node", "node")
    name = slugify(ensure_text(item.get("name")) or ensure_text(item.get("id")) or "node", "node")
    return f"node:{role}:{name}"


def _initialize_presence_collection(
    items: list[dict[str, Any]],
    width: int,
    *,
    default_hidden: bool,
) -> None:
    for item in items:
        _mark_present(item, width)
        item["responsive_default_hidden"] = bool(default_hidden)
        children = item.get("children", [])
        if isinstance(children, list) and children:
            _initialize_presence_collection(children, width, default_hidden=default_hidden)


def _mark_present(item: dict[str, Any], width: int) -> None:
    present_widths = [int(value) for value in item.get("responsive_present_widths", []) if str(value).isdigit()]
    if width not in present_widths:
        present_widths.append(width)
        present_widths.sort(reverse=True)
    item["responsive_present_widths"] = present_widths


def _merge_item_collection(
    merged_items: list[dict[str, Any]],
    variant_items: list[dict[str, Any]],
    width: int,
) -> None:
    merged_by_key = {
        ensure_text(item.get("responsive_key")): item
        for item in merged_items
        if isinstance(item, dict) and ensure_text(item.get("responsive_key"))
    }
    variant_keys = [
        ensure_text(item.get("responsive_key"))
        for item in variant_items
        if isinstance(item, dict) and ensure_text(item.get("responsive_key"))
    ]

    for variant_item in variant_items:
        if not isinstance(variant_item, dict):
            continue
        key = ensure_text(variant_item.get("responsive_key"))
        if not key:
            continue
        if key in merged_by_key:
            merged_item = merged_by_key[key]
            _mark_present(merged_item, width)
            merged_children = merged_item.get("children", [])
            variant_children = variant_item.get("children", [])
            if isinstance(merged_children, list) and isinstance(variant_children, list) and variant_children:
                _merge_item_collection(merged_children, variant_children, width)
            continue

        cloned_item = deepcopy(variant_item)
        _initialize_presence_collection([cloned_item], width, default_hidden=True)
        insert_at = _insertion_index(merged_items, variant_items, key)
        merged_items.insert(insert_at, cloned_item)
        merged_by_key[key] = cloned_item

    for merged_item in merged_items:
        key = ensure_text(merged_item.get("responsive_key"))
        if key and key not in variant_keys:
            continue


def _insertion_index(
    merged_items: list[dict[str, Any]],
    variant_items: list[dict[str, Any]],
    candidate_key: str,
) -> int:
    variant_order = [
        ensure_text(item.get("responsive_key"))
        for item in variant_items
        if isinstance(item, dict) and ensure_text(item.get("responsive_key"))
    ]
    merged_order = [
        ensure_text(item.get("responsive_key"))
        for item in merged_items
        if isinstance(item, dict) and ensure_text(item.get("responsive_key"))
    ]
    try:
        variant_index = variant_order.index(candidate_key)
    except ValueError:
        return len(merged_items)

    for previous_index in range(variant_index - 1, -1, -1):
        previous_key = variant_order[previous_index]
        if previous_key in merged_order:
            return merged_order.index(previous_key) + 1
    for next_index in range(variant_index + 1, len(variant_order)):
        next_key = variant_order[next_index]
        if next_key in merged_order:
            return merged_order.index(next_key)
    return len(merged_items)


def _merge_assets(prepared_variants: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    merged_assets: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for _, page_data in prepared_variants:
        for asset in page_data.get("assets", []):
            if not isinstance(asset, dict):
                continue
            asset_key = ensure_text(asset.get("id") or asset.get("nodeId") or asset.get("node_id") or asset.get("local_path"))
            if not asset_key or asset_key in seen_keys:
                continue
            merged_assets.append(deepcopy(asset))
            seen_keys.add(asset_key)
    return merged_assets


def _dedupe_warnings(values: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = ensure_text(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _strip_width_suffix(value: str, family_slug: str) -> str:
    text = ensure_text(value).strip()
    if not text:
        return text
    slug_text = slugify(text, "page")
    match = RESPONSIVE_SLUG_RE.match(slug_text)
    if match and ensure_text(match.group("family")) == family_slug:
        width_text = ensure_text(match.group("width"))
        for separator in (" - ", "-", " "):
            suffix = f"{separator}{width_text}"
            if text.endswith(suffix):
                return text[: -len(suffix)].rstrip()
    return text


def _sync_variant_class_names(
    merged_items: list[dict[str, Any]],
    variant_items: list[dict[str, Any]],
) -> None:
    merged_by_key = {
        ensure_text(item.get("responsive_key")): item
        for item in merged_items
        if isinstance(item, dict) and ensure_text(item.get("responsive_key"))
    }
    for variant_item in variant_items:
        if not isinstance(variant_item, dict):
            continue
        key = ensure_text(variant_item.get("responsive_key"))
        if not key:
            continue
        merged_item = merged_by_key.get(key)
        if merged_item is None:
            continue
        _copy_render_identity(merged_item, variant_item)
        merged_children = merged_item.get("children", [])
        variant_children = variant_item.get("children", [])
        if isinstance(merged_children, list) and isinstance(variant_children, list):
            _sync_variant_class_names(merged_children, variant_children)


def _copy_render_identity(merged_item: dict[str, Any], variant_item: dict[str, Any]) -> None:
    merged_class_name = ensure_text(merged_item.get("class_name"))
    if merged_class_name:
        variant_item["class_name"] = merged_class_name

    merged_dom_id = ensure_text(merged_item.get("dom_id"))
    if merged_dom_id:
        variant_item["dom_id"] = merged_dom_id

    merged_text = as_mapping(merged_item.get("text"))
    variant_text = as_mapping(variant_item.get("text"))
    if merged_text and variant_text:
        merged_text_class = ensure_text(merged_text.get("class_name"))
        if merged_text_class:
            variant_text["class_name"] = merged_text_class
        merged_text_dom_id = ensure_text(merged_text.get("dom_id"))
        if merged_text_dom_id:
            variant_text["dom_id"] = merged_text_dom_id

    merged_asset = as_mapping(merged_item.get("asset"))
    variant_asset = as_mapping(variant_item.get("asset"))
    if merged_asset and variant_asset:
        merged_asset_class = ensure_text(merged_asset.get("class_name"))
        if merged_asset_class:
            variant_asset["class_name"] = merged_asset_class
        merged_asset_dom_id = ensure_text(merged_asset.get("dom_id"))
        if merged_asset_dom_id:
            variant_asset["dom_id"] = merged_asset_dom_id

    merged_control = as_mapping(merged_item.get("form_control"))
    variant_control = as_mapping(variant_item.get("form_control"))
    if merged_control and variant_control:
        merged_control_class = ensure_text(merged_control.get("class_name"))
        if merged_control_class:
            variant_control["class_name"] = merged_control_class
        merged_control_id = ensure_text(merged_control.get("id"))
        if merged_control_id:
            variant_control["id"] = merged_control_id


def _collect_variant_differences(
    merged_items: list[dict[str, Any]],
    variant_items: list[dict[str, Any]],
    width: int,
) -> list[str]:
    warnings: list[str] = []
    merged_by_key = {
        ensure_text(item.get("responsive_key")): item
        for item in merged_items
        if isinstance(item, dict) and ensure_text(item.get("responsive_key"))
    }
    for variant_item in variant_items:
        if not isinstance(variant_item, dict):
            continue
        key = ensure_text(variant_item.get("responsive_key"))
        if not key:
            continue
        merged_item = merged_by_key.get(key)
        if merged_item is None:
            continue
        warning = _variant_difference_warning(merged_item, variant_item, width)
        if warning:
            warnings.append(warning)
        merged_children = merged_item.get("children", [])
        variant_children = variant_item.get("children", [])
        if isinstance(merged_children, list) and isinstance(variant_children, list):
            warnings.extend(_collect_variant_differences(merged_children, variant_children, width))
    return warnings


def _variant_difference_warning(merged_item: dict[str, Any], variant_item: dict[str, Any], width: int) -> str:
    key = ensure_text(merged_item.get("responsive_key")) or ensure_text(variant_item.get("responsive_key"))
    kind = ensure_text(merged_item.get("kind") or variant_item.get("kind")).strip().lower()

    if kind == "text":
        merged_text = as_mapping(merged_item.get("text"))
        variant_text = as_mapping(variant_item.get("text"))
        merged_value = ensure_text(merged_text.get("value")).strip()
        variant_value = ensure_text(variant_text.get("value")).strip()
        if merged_value and variant_value and merged_value != variant_value:
            return (
                f"Responsive variant {width}px changes text content for {key}. "
                "Duplicate the item as a breakpoint-specific layer if different copy is intended."
            )
        return ""

    if kind == "asset":
        merged_asset = as_mapping(merged_item.get("asset"))
        variant_asset = as_mapping(variant_item.get("asset"))
        merged_source = ensure_text(
            merged_asset.get("source_local_path")
            or merged_asset.get("local_path")
            or merged_asset.get("public_path")
            or merged_asset.get("id")
        ).strip()
        variant_source = ensure_text(
            variant_asset.get("source_local_path")
            or variant_asset.get("local_path")
            or variant_asset.get("public_path")
            or variant_asset.get("id")
        ).strip()
        if merged_source and variant_source and merged_source != variant_source:
            return (
                f"Responsive variant {width}px changes asset source for {key}. "
                "Use a breakpoint-specific asset layer if the visual must differ by width."
            )
        return ""

    merged_control = as_mapping(merged_item.get("form_control"))
    variant_control = as_mapping(variant_item.get("form_control"))
    if merged_control and variant_control:
        merged_tag = ensure_text(merged_control.get("tag")).strip().lower()
        variant_tag = ensure_text(variant_control.get("tag")).strip().lower()
        if merged_tag and variant_tag and merged_tag != variant_tag:
            return (
                f"Responsive variant {width}px changes form control type for {key}. "
                "Duplicate the control as a breakpoint-specific item if this is intentional."
            )
    return ""
