from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from figma2hugo.reporting import dedupe_warnings

from ._shared import ensure_text, items_form_repeated_component_group, slugify

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


def merge_responsive_family(
    page_datas: list[dict[str, Any]],
    *,
    strict_matching: bool = False,
) -> dict[str, Any]:
    if len(page_datas) < 2:
        raise ValueError(
            "Responsive family merge requires at least two width-suffixed page variants."
        )

    prepared_variants: list[tuple[int, dict[str, Any]]] = []
    family_slug = ""
    responsive_warnings: list[str] = []
    widths_by_slug: dict[int, str] = {}
    for page_data in page_datas:
        detected = detect_responsive_variant(page_data)
        if not detected:
            raise ValueError("Responsive family merge requires width-suffixed page slugs.")
        detected_family, width = detected
        page = as_mapping(page_data.get("page"))
        page_slug = ensure_text(page.get("slug")).strip().lower() or detected_family
        if family_slug and detected_family != family_slug:
            raise ValueError(
                "Responsive family merge received mixed families: "
                f"expected '{family_slug}', got '{detected_family}'."
            )
        family_slug = detected_family
        if width in widths_by_slug:
            raise ValueError(
                f"Responsive family '{family_slug}' contains duplicate width {width}px "
                f"for '{widths_by_slug[width]}' and '{page_slug}'."
            )
        widths_by_slug[width] = page_slug
        prepared = deepcopy(page_data)
        assign_responsive_keys(prepared)
        structure_warnings = _collect_structure_warnings(prepared.get("sections", []), width)
        strict_blocking_warnings = [
            warning
            for warning in structure_warnings
            if _is_strict_blocking_structure_warning(warning)
        ]
        if strict_matching and strict_blocking_warnings:
            raise ValueError(
                _strict_matching_error(
                    family_slug=family_slug or detected_family,
                    width=width,
                    warnings=strict_blocking_warnings,
                )
            )
        responsive_warnings.extend(structure_warnings)
        prepared_variants.append((width, prepared))

    prepared_variants.sort(key=lambda item: item[0], reverse=True)
    base_width, merged = prepared_variants[0]
    secondary_variants = [
        (width, page_data) for width, page_data in prepared_variants[1:] if width < base_width
    ]
    if not secondary_variants:
        raise ValueError(
            f"Responsive family '{family_slug}' requires at least one secondary width "
            f"smaller than {base_width}px."
        )
    _initialize_presence_collection(merged.get("sections", []), base_width, default_hidden=False)

    merged_page = as_mapping(merged.get("page"))
    merged_page["slug"] = family_slug
    merged_page["name"] = _strip_width_suffix(ensure_text(merged_page.get("name")), family_slug)
    merged_page["title"] = _strip_width_suffix(ensure_text(merged_page.get("title")), family_slug)
    merged["page"] = merged_page
    used_class_names, used_dom_ids = _collect_used_render_identities(merged.get("sections", []))

    for width, variant_page in secondary_variants:
        responsive_warnings.extend(
            _collect_variant_differences(
                merged.get("sections", []), variant_page.get("sections", []), width
            )
        )
        _sync_variant_class_names(merged.get("sections", []), variant_page.get("sections", []))
        _merge_item_collection(
            merged.get("sections", []),
            variant_page.get("sections", []),
            width,
            used_class_names=used_class_names,
            used_dom_ids=used_dom_ids,
        )

    merged["assets"] = _merge_assets(prepared_variants)
    merged["warnings"] = dedupe_warnings(
        warning
        for warning in [
            *responsive_warnings,
            *[
                warning
                for _, page_data in prepared_variants
                for warning in page_data.get("warnings", [])
            ],
        ]
    )
    merged["responsive"] = {
        "family": family_slug,
        "base_width": base_width,
        "breakpoints": [width for width, _ in secondary_variants],
        "variants": [
            {
                "width": width,
                "page": variant_page,
            }
            for width, variant_page in secondary_variants
        ],
    }
    return merged


def merge_responsive_page_groups(
    page_datas: list[dict[str, Any]],
    *,
    strict_matching: bool = False,
) -> list[dict[str, Any]]:
    grouped: list[tuple[str, list[dict[str, Any]], str | None]] = []
    grouped_index: dict[str, int] = {}

    for page_data in page_datas:
        detected = detect_responsive_variant(page_data)
        if detected is None:
            group_key = f"single::{len(grouped)}"
            grouped_index[group_key] = len(grouped)
            grouped.append((group_key, [page_data], None))
            continue

        family_slug, _ = detected
        group_key = f"responsive::{family_slug}"
        if group_key not in grouped_index:
            grouped_index[group_key] = len(grouped)
            grouped.append((group_key, [page_data], family_slug))
            continue
        grouped[grouped_index[group_key]][1].append(page_data)

    merged_pages: list[dict[str, Any]] = []
    for _, pages, family_slug in grouped:
        if family_slug and len(pages) > 1:
            merged_pages.append(
                merge_responsive_family(pages, strict_matching=strict_matching)
            )
        else:
            merged_pages.extend(pages)
    return merged_pages


def assign_responsive_keys(page_data: dict[str, Any]) -> None:
    sections = [section for section in page_data.get("sections", []) if isinstance(section, dict)]
    _assign_collection_keys(sections, parent_key="page", item_kind="section")


def _collect_structure_warnings(
    items: list[dict[str, Any]],
    width: int,
    *,
    parent_key: str = "page",
    item_kind: str = "section",
) -> list[str]:
    warnings: list[str] = []
    items_by_token: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        token = _provisional_token(item, item_kind=item_kind)
        items_by_token.setdefault(token, []).append(item)

    for token, token_items in sorted(items_by_token.items()):
        if len(token_items) <= 1:
            continue
        if items_form_repeated_component_group(token_items):
            warnings.append(
                f"Responsive variant {width}px treats repeated sibling token '{token}' "
                f"under '{parent_key}' as a repeated component group with "
                f"{len(token_items)} items."
            )
            continue
        warnings.append(
            f"Responsive variant {width}px reuses sibling token '{token}' under '{parent_key}'. "
            "Matching will rely on sibling order; keep ordering stable or rename duplicates."
        )

    for item in items:
        children = item.get("children", [])
        if not isinstance(children, list) or not children:
            continue
        warnings.extend(
            _collect_structure_warnings(
                children,
                width,
                parent_key=ensure_text(item.get("responsive_key")) or parent_key,
                item_kind="node",
            )
        )
    return warnings


def _is_strict_blocking_structure_warning(warning: str) -> bool:
    return " reuses sibling token " in warning


def _strict_matching_error(
    *,
    family_slug: str,
    width: int,
    warnings: list[str],
) -> str:
    first_warning = warnings[0] if warnings else "duplicate responsive sibling token"
    return (
        f"Responsive family '{family_slug}' has ambiguous responsive sibling tokens "
        f"at {width}px. {first_warning}"
    )


def as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _assign_collection_keys(
    items: list[dict[str, Any]], *, parent_key: str, item_kind: str
) -> None:
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
        name = slugify(
            ensure_text(item.get("name")) or ensure_text(item.get("id")) or "section", "section"
        )
        return f"section:{role}:{name}"

    kind = ensure_text(item.get("kind")).strip().lower()
    if kind == "text":
        text = as_mapping(item.get("text"))
        role = slugify(
            ensure_text(text.get("role")) or ensure_text(item.get("role")) or "text", "text"
        )
        name = slugify(
            ensure_text(text.get("name"))
            or ensure_text(text.get("id"))
            or ensure_text(item.get("id"))
            or "text",
            "text",
        )
        return f"text:{role}:{name}"
    if kind == "asset":
        asset = as_mapping(item.get("asset"))
        role = slugify(
            ensure_text(asset.get("purpose")) or ensure_text(item.get("role")) or "asset", "asset"
        )
        name = slugify(
            ensure_text(asset.get("name"))
            or ensure_text(asset.get("id"))
            or ensure_text(item.get("id"))
            or "asset",
            "asset",
        )
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
    present_widths = [
        int(value) for value in item.get("responsive_present_widths", []) if str(value).isdigit()
    ]
    if width not in present_widths:
        present_widths.append(width)
        present_widths.sort(reverse=True)
    item["responsive_present_widths"] = present_widths


def _merge_item_collection(
    merged_items: list[dict[str, Any]],
    variant_items: list[dict[str, Any]],
    width: int,
    *,
    used_class_names: set[str],
    used_dom_ids: set[str],
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
        matching_item = _find_matching_merged_item_for_variant(merged_items, variant_item)
        if matching_item is not None:
            _mark_present(matching_item, width)
            merged_children = matching_item.get("children", [])
            variant_children = variant_item.get("children", [])
            if (
                isinstance(merged_children, list)
                and isinstance(variant_children, list)
                and variant_children
            ):
                _merge_item_collection(
                    merged_children,
                    variant_children,
                    width,
                    used_class_names=used_class_names,
                    used_dom_ids=used_dom_ids,
                )
            continue

        if key in merged_by_key:
            cloned_item = deepcopy(variant_item)
            _initialize_presence_collection([cloned_item], width, default_hidden=True)
            _uniquify_inserted_render_identity(
                cloned_item,
                width,
                used_class_names=used_class_names,
                used_dom_ids=used_dom_ids,
            )
            insert_at = _insertion_index_after_same_key(merged_items, key)
            merged_items.insert(insert_at, cloned_item)
            continue

        cloned_item = deepcopy(variant_item)
        _initialize_presence_collection([cloned_item], width, default_hidden=True)
        _uniquify_inserted_render_identity(
            cloned_item,
            width,
            used_class_names=used_class_names,
            used_dom_ids=used_dom_ids,
        )
        insert_at = _insertion_index(merged_items, variant_items, key)
        merged_items.insert(insert_at, cloned_item)
        merged_by_key[key] = cloned_item

    for merged_item in merged_items:
        key = ensure_text(merged_item.get("responsive_key"))
        if key and key not in variant_keys:
            continue


def _find_matching_merged_item_for_variant(
    merged_items: list[dict[str, Any]],
    variant_item: dict[str, Any],
) -> dict[str, Any] | None:
    key = ensure_text(variant_item.get("responsive_key")).strip()
    if not key:
        return None
    kind = ensure_text(variant_item.get("kind")).strip().lower()
    for merged_item in merged_items:
        if ensure_text(merged_item.get("responsive_key")).strip() != key:
            continue
        if kind == "asset":
            if _responsive_asset_source(merged_item) == _responsive_asset_source(variant_item):
                return merged_item
            continue
        return merged_item
    return None


def _responsive_asset_source(item: dict[str, Any]) -> str:
    asset = as_mapping(item.get("asset"))
    return ensure_text(
        asset.get("source_local_path")
        or asset.get("local_path")
        or asset.get("public_path")
        or asset.get("id")
    ).strip()


def _insertion_index_after_same_key(merged_items: list[dict[str, Any]], key: str) -> int:
    last_match_index = -1
    for index, item in enumerate(merged_items):
        if ensure_text(item.get("responsive_key")).strip() == key:
            last_match_index = index
    if last_match_index >= 0:
        return last_match_index + 1
    return len(merged_items)


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
            asset_key = ensure_text(
                asset.get("id")
                or asset.get("nodeId")
                or asset.get("node_id")
                or asset.get("local_path")
            )
            if not asset_key or asset_key in seen_keys:
                continue
            merged_assets.append(deepcopy(asset))
            seen_keys.add(asset_key)
    return merged_assets


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


def _collect_used_render_identities(items: Any) -> tuple[set[str], set[str]]:
    used_class_names: set[str] = set()
    used_dom_ids: set[str] = set()
    for item in items if isinstance(items, list) else []:
        _collect_item_render_identities(
            item, used_class_names=used_class_names, used_dom_ids=used_dom_ids
        )
    return used_class_names, used_dom_ids


def _collect_item_render_identities(
    item: Any,
    *,
    used_class_names: set[str],
    used_dom_ids: set[str],
) -> None:
    if not isinstance(item, dict):
        return
    _register_render_identity(item, used_class_names=used_class_names, used_dom_ids=used_dom_ids)
    _register_render_identity(
        as_mapping(item.get("text")), used_class_names=used_class_names, used_dom_ids=used_dom_ids
    )
    _register_render_identity(
        as_mapping(item.get("asset")), used_class_names=used_class_names, used_dom_ids=used_dom_ids
    )
    control = as_mapping(item.get("form_control"))
    if control:
        class_name = ensure_text(control.get("class_name")).strip()
        if class_name:
            used_class_names.add(class_name)
        control_id = ensure_text(control.get("id")).strip()
        if control_id:
            used_dom_ids.add(control_id)
    for child in item.get("children", []):
        _collect_item_render_identities(
            child, used_class_names=used_class_names, used_dom_ids=used_dom_ids
        )


def _register_render_identity(
    payload: dict[str, Any],
    *,
    used_class_names: set[str],
    used_dom_ids: set[str],
) -> None:
    if not payload:
        return
    class_name = ensure_text(payload.get("class_name")).strip()
    if class_name:
        used_class_names.add(class_name)
    dom_id = ensure_text(payload.get("dom_id")).strip()
    if dom_id:
        used_dom_ids.add(dom_id)


def _uniquify_inserted_render_identity(
    item: dict[str, Any],
    width: int,
    *,
    used_class_names: set[str],
    used_dom_ids: set[str],
) -> None:
    dom_id_mapping: dict[str, str] = {}
    suffix = f"w{width}"
    _rename_item_render_identity(
        item,
        suffix=suffix,
        used_class_names=used_class_names,
        used_dom_ids=used_dom_ids,
        dom_id_mapping=dom_id_mapping,
    )
    if dom_id_mapping:
        _rewrite_dom_id_references(item, dom_id_mapping)


def _rename_item_render_identity(
    item: dict[str, Any],
    *,
    suffix: str,
    used_class_names: set[str],
    used_dom_ids: set[str],
    dom_id_mapping: dict[str, str],
) -> None:
    _rename_payload_render_identity(
        item,
        suffix=suffix,
        used_class_names=used_class_names,
        used_dom_ids=used_dom_ids,
        dom_id_mapping=dom_id_mapping,
        dom_id_field="dom_id",
    )
    _rename_payload_render_identity(
        as_mapping(item.get("text")),
        suffix=suffix,
        used_class_names=used_class_names,
        used_dom_ids=used_dom_ids,
        dom_id_mapping=dom_id_mapping,
        dom_id_field="dom_id",
    )
    _rename_payload_render_identity(
        as_mapping(item.get("asset")),
        suffix=suffix,
        used_class_names=used_class_names,
        used_dom_ids=used_dom_ids,
        dom_id_mapping=dom_id_mapping,
        dom_id_field="dom_id",
    )
    _rename_payload_render_identity(
        as_mapping(item.get("form_control")),
        suffix=suffix,
        used_class_names=used_class_names,
        used_dom_ids=used_dom_ids,
        dom_id_mapping=dom_id_mapping,
        dom_id_field="id",
    )
    for child in item.get("children", []):
        if isinstance(child, dict):
            _rename_item_render_identity(
                child,
                suffix=suffix,
                used_class_names=used_class_names,
                used_dom_ids=used_dom_ids,
                dom_id_mapping=dom_id_mapping,
            )


def _rename_payload_render_identity(
    payload: dict[str, Any],
    *,
    suffix: str,
    used_class_names: set[str],
    used_dom_ids: set[str],
    dom_id_mapping: dict[str, str],
    dom_id_field: str,
) -> None:
    if not payload:
        return
    class_name = ensure_text(payload.get("class_name")).strip()
    if class_name:
        payload["class_name"] = _unique_render_name(
            class_name, suffix=suffix, used_names=used_class_names
        )
    dom_id = ensure_text(payload.get(dom_id_field)).strip()
    if dom_id:
        renamed_dom_id = _unique_render_name(dom_id, suffix=suffix, used_names=used_dom_ids)
        payload[dom_id_field] = renamed_dom_id
        dom_id_mapping[dom_id] = renamed_dom_id


def _unique_render_name(name: str, *, suffix: str, used_names: set[str]) -> str:
    candidate_base = f"{ensure_text(name).strip()}-{suffix}"
    candidate = candidate_base
    index = 2
    while candidate in used_names:
        candidate = f"{candidate_base}-{index}"
        index += 1
    used_names.add(candidate)
    return candidate


def _rewrite_dom_id_references(value: Any, dom_id_mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            value[key] = _rewrite_dom_id_references(item, dom_id_mapping)
        return value
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = _rewrite_dom_id_references(item, dom_id_mapping)
        return value
    if isinstance(value, str):
        return dom_id_mapping.get(value, value)
    return value


def _variant_difference_warning(
    merged_item: dict[str, Any], variant_item: dict[str, Any], width: int
) -> str:
    key = ensure_text(merged_item.get("responsive_key")) or ensure_text(
        variant_item.get("responsive_key")
    )
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
