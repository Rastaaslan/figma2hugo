"""Regroupe les frames responsive Figma et decrit les liens entre variantes."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from figma2hugo.pipeline.models import IntermediatePipelineDocument, IssueSeverity, NormalizedNode
from figma2hugo.pipeline.naming import slugify as _slug

RESPONSIVE_PAGE_RE = re.compile(r"^(?P<family>.+)-(?P<width>\d{3,4})$")
WIDTH_SUFFIX_RE = re.compile(r"-\d{3,4}$")
GENERIC_NODE_NAME_ALIASES = {
    "section-hero-main": "section-hero",
}
GENERIC_BAND_NAMES = {
    "bandeau-content",
    "bandeau-droite",
    "bandeau-gauche",
}
ORDER_SENSITIVE_NAME_TOKENS = {
    "accordion",
    "accordeon",
    "card",
    "cards",
    "carrousel",
    "carousel",
    "carte",
    "cartes",
    "collection",
    "faq",
    "galerie",
    "gallery",
    "grid",
    "grille",
    "liste",
    "list",
    "slider",
    "swiper",
    "timeline",
}


class ResponsiveDecision(StrEnum):
    SHARED = "shared"
    BREAKPOINT_VARIANT = "breakpointVariant"
    BREAKPOINT_ONLY = "breakpointOnly"
    UNMATCHED = "unmatched"


@dataclass(frozen=True, slots=True)
class ResponsiveIssue:
    code: str
    message: str
    family: str
    severity: IssueSeverity = IssueSeverity.INFO
    key: str = ""
    width: int | None = None
    present_widths: tuple[int, ...] = ()
    missing_widths: tuple[int, ...] = ()
    signature_count: int = 0
    difference_kind: str = ""
    node_role: str = ""
    contract_rule: str = ""
    contract_action: str = ""
    contract_risk: str = ""


@dataclass(frozen=True, slots=True)
class ResponsiveNodeFamily:
    key: str
    decision: ResponsiveDecision
    widths: tuple[int, ...]
    content_signatures: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResponsiveManifest:
    family: str
    base_width: int
    breakpoints: tuple[int, ...]
    node_families: tuple[ResponsiveNodeFamily, ...]
    issues: tuple[ResponsiveIssue, ...] = ()


def build_responsive_manifest(documents: list[IntermediatePipelineDocument]) -> ResponsiveManifest:
    if not documents:
        raise ValueError("Responsive manifest requires at least one document.")
    variants = sorted(
        ((responsive_variant_identity(document), document) for document in documents),
        key=lambda item: item[0],
    )
    families = {family for (_, family), _ in variants}
    if len(families) != 1:
        raise ValueError(f"Responsive manifest received mixed families: {sorted(families)}")
    family = families.pop()
    widths = tuple(width for (width, _), _ in variants)
    duplicate_widths = sorted(width for width, count in Counter(widths).items() if count > 1)
    if duplicate_widths:
        raise ValueError(
            f"Responsive manifest received duplicate widths for family {family}: {duplicate_widths}"
        )
    base_width = max(widths)
    breakpoints = tuple(width for width in widths if width != base_width)
    node_signatures: dict[str, dict[int, str]] = {}
    for (width, _), document in variants:
        for section in document.sections:
            if not _has_responsive_content(section):
                continue
            key = _node_key(section)
            node_signatures.setdefault(key, {})[width] = _content_signature(section)

    issues: list[ResponsiveIssue] = []
    families_out: list[ResponsiveNodeFamily] = []
    all_widths = set(widths)
    node_signatures = _merge_responsive_equivalent_families(
        node_signatures,
        all_widths=all_widths,
        base_width=base_width,
    )
    for key, signatures_by_width in sorted(node_signatures.items()):
        present_widths = tuple(sorted(signatures_by_width))
        signature_set = set(signatures_by_width.values())
        if set(present_widths) != all_widths:
            decision = ResponsiveDecision.BREAKPOINT_ONLY
            missing = sorted(all_widths - set(present_widths))
            difference_kind = "missing-breakpoint-node"
            contract = _responsive_contract_fields(
                code="breakpoint-only",
                key=key,
                difference_kind=difference_kind,
            )
            issues.append(
                ResponsiveIssue(
                    code="breakpoint-only",
                    message=f"Node family is missing from widths {missing}.",
                    family=family,
                    key=key,
                    present_widths=present_widths,
                    missing_widths=tuple(missing),
                    signature_count=len(signature_set),
                    difference_kind=difference_kind,
                    node_role=contract["node_role"],
                    contract_rule=contract["contract_rule"],
                    contract_action=contract["contract_action"],
                    contract_risk=contract["contract_risk"],
                )
            )
        elif len(signature_set) > 1:
            difference_kind = _content_difference_kind(signatures_by_width)
            if difference_kind == "same-content-different-order" and not _is_order_sensitive_family(
                key
            ):
                decision = ResponsiveDecision.SHARED
            else:
                decision = ResponsiveDecision.BREAKPOINT_VARIANT
                contract = _responsive_contract_fields(
                    code="content-conflict",
                    key=key,
                    difference_kind=difference_kind,
                )
                issues.append(
                    ResponsiveIssue(
                        code="content-conflict",
                        message="Node family has different content/source signatures by width.",
                        family=family,
                        key=key,
                        present_widths=present_widths,
                        signature_count=len(signature_set),
                        difference_kind=difference_kind,
                        node_role=contract["node_role"],
                        contract_rule=contract["contract_rule"],
                        contract_action=contract["contract_action"],
                        contract_risk=contract["contract_risk"],
                    )
                )
        else:
            decision = ResponsiveDecision.SHARED
        families_out.append(
            ResponsiveNodeFamily(
                key=key,
                decision=decision,
                widths=present_widths,
                content_signatures=dict(signatures_by_width),
            )
        )
    return ResponsiveManifest(
        family=family,
        base_width=base_width,
        breakpoints=breakpoints,
        node_families=tuple(families_out),
        issues=tuple(issues),
    )


def responsive_variant_identity(document: IntermediatePipelineDocument) -> tuple[int, str]:
    slug = _slug(document.page.name)
    match = RESPONSIVE_PAGE_RE.match(slug)
    if match:
        return int(match.group("width")), match.group("family")
    return document.width, WIDTH_SUFFIX_RE.sub("", slug) or slug


def _node_key(node: NormalizedNode) -> str:
    return f"{node.kind.value}:{_canonical_node_slug(node.name) or node.id}"


def _content_signature(node: NormalizedNode) -> str:
    chunks: list[str] = [node.kind.value, _canonical_node_slug(node.name)]
    entries: list[tuple[tuple[float, float, float, float, int, int], str]] = []
    for index, descendant in enumerate(node.walk()):
        if _is_metadata_node(descendant):
            continue
        visual_key = _visual_content_sort_key(descendant, index)
        payload = descendant.payload
        value = payload.get("characters") or payload.get("value") or payload.get("rawValue")
        if value:
            entries.append(((*visual_key, 0), f"text:{_normalized_content_text(value)}"))
        source = payload.get("imageRef") or payload.get("image_ref") or payload.get("local_path")
        if source:
            entries.append(((*visual_key, 1), f"asset:{source}"))
    chunks.extend(token for _key, token in sorted(entries))
    return "\n".join(chunks)


def _canonical_node_slug(name: object) -> str:
    slug = WIDTH_SUFFIX_RE.sub("", _slug(name))
    if slug in GENERIC_BAND_NAMES:
        return "bandeau"
    if slug.startswith("section-embedded-"):
        return "section-embedded"
    if slug.endswith("-content") and slug not in {"content", "section-content"}:
        return slug.removesuffix("-content")
    return GENERIC_NODE_NAME_ALIASES.get(slug, slug)


def _merge_responsive_equivalent_families(
    node_signatures: dict[str, dict[int, str]],
    *,
    all_widths: set[int],
    base_width: int,
) -> dict[str, dict[int, str]]:
    merged = {key: dict(signatures) for key, signatures in node_signatures.items()}
    while True:
        merge_pair: tuple[str, str] | None = None
        for first_index, first_key in enumerate(sorted(merged)):
            for second_key in sorted(merged)[first_index + 1 :]:
                if _families_can_merge(
                    first_key,
                    merged[first_key],
                    second_key,
                    merged[second_key],
                    all_widths=all_widths,
                ):
                    merge_pair = (first_key, second_key)
                    break
            if merge_pair is not None:
                break
        if merge_pair is None:
            return merged
        first_key, second_key = merge_pair
        target_key = _preferred_merge_key(
            first_key,
            merged[first_key],
            second_key,
            merged[second_key],
            base_width=base_width,
        )
        source_key = second_key if target_key == first_key else first_key
        target_signatures = dict(merged[target_key])
        target_signatures.update(merged[source_key])
        merged[target_key] = target_signatures
        del merged[source_key]


def _families_can_merge(
    first_key: str,
    first_signatures: dict[int, str],
    second_key: str,
    second_signatures: dict[int, str],
    *,
    all_widths: set[int],
) -> bool:
    if first_key.split(":", 1)[0] != second_key.split(":", 1)[0]:
        return False
    if _responsive_node_role(first_key) in {"footer", "hero"}:
        return False
    if _responsive_node_role(second_key) in {"footer", "hero"}:
        return False
    first_widths = set(first_signatures)
    second_widths = set(second_signatures)
    if first_widths == all_widths or second_widths == all_widths:
        return False
    if first_widths == second_widths:
        return False
    if not first_widths.isdisjoint(second_widths):
        for width in first_widths & second_widths:
            if _signature_payload_tokens(first_signatures[width]) != _signature_payload_tokens(
                second_signatures[width]
            ):
                return False
    if (
        not (first_widths | second_widths) > first_widths
        and not (first_widths | second_widths) > second_widths
    ):
        return False
    return _family_payload_similarity(first_signatures, second_signatures) >= 0.6


def _preferred_merge_key(
    first_key: str,
    first_signatures: dict[int, str],
    second_key: str,
    second_signatures: dict[int, str],
    *,
    base_width: int,
) -> str:
    if first_key == "container:bandeau" and second_key != "container:bandeau":
        return second_key
    if second_key == "container:bandeau" and first_key != "container:bandeau":
        return first_key
    if base_width in first_signatures and base_width not in second_signatures:
        return first_key
    if base_width in second_signatures and base_width not in first_signatures:
        return second_key
    if _slug_specificity(first_key) != _slug_specificity(second_key):
        return (
            first_key
            if _slug_specificity(first_key) < _slug_specificity(second_key)
            else second_key
        )
    return min(first_key, second_key)


def _family_payload_similarity(
    first_signatures: dict[int, str],
    second_signatures: dict[int, str],
) -> float:
    first_tokens = _family_payload_token_set(first_signatures)
    second_tokens = _family_payload_token_set(second_signatures)
    if not first_tokens or not second_tokens:
        return 0.0
    shared = first_tokens & second_tokens
    if len(shared) < 2:
        return 0.0
    return len(shared) / min(len(first_tokens), len(second_tokens))


def _family_payload_token_set(signatures: dict[int, str]) -> set[str]:
    return {
        token for signature in signatures.values() for token in _signature_payload_tokens(signature)
    }


def _slug_specificity(key: str) -> int:
    _, _, name = key.partition(":")
    return len([chunk for chunk in name.split("-") if chunk])


def _is_metadata_node(node: NormalizedNode) -> bool:
    name = _canonical_node_slug(node.name)
    payload = node.payload
    value = str(payload.get("characters") or payload.get("value") or payload.get("rawValue") or "")
    return bool(
        name.startswith(("href-", "url-", "link-url-"))
        and value.strip().lower().startswith(("http://", "https://", "/"))
    )


def _normalized_content_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _visual_content_sort_key(
    node: NormalizedNode, index: int
) -> tuple[float, float, float, float, int]:
    bounds = node.render_bounds or node.page_bounds
    return (
        round(bounds.y, 2),
        round(bounds.x, 2),
        round(bounds.height, 2),
        round(bounds.width, 2),
        index,
    )


def _content_difference_kind(signatures_by_width: dict[int, str]) -> str:
    token_lists = [
        _signature_payload_tokens(signature) for signature in signatures_by_width.values()
    ]
    if len(token_lists) < 2:
        return ""
    token_counters = {tuple(sorted(Counter(tokens).items())) for tokens in token_lists}
    if len(token_counters) == 1:
        return "same-content-different-order"
    if any(token.startswith("asset:") for tokens in token_lists for token in tokens):
        return "asset-or-content-delta"
    return "content-delta"


def _responsive_contract_fields(
    *,
    code: str,
    key: str,
    difference_kind: str,
) -> dict[str, str]:
    node_role = _responsive_node_role(key, difference_kind=difference_kind)
    if difference_kind == "same-content-different-order":
        return {
            "node_role": node_role,
            "contract_rule": "stable-collection-order",
            "contract_action": "normalize-order-or-declare-carousel-variant",
            "contract_risk": _responsive_contract_risk(node_role, difference_kind),
        }
    if code == "breakpoint-only":
        return {
            "node_role": node_role,
            "contract_rule": "stable-breakpoint-presence",
            "contract_action": "add-missing-node-or-declare-breakpoint-only",
            "contract_risk": _responsive_contract_risk(node_role, difference_kind),
        }
    if difference_kind == "asset-or-content-delta":
        return {
            "node_role": node_role,
            "contract_rule": "stable-responsive-assets",
            "contract_action": "align-assets-or-declare-intentional-variant",
            "contract_risk": _responsive_contract_risk(node_role, difference_kind),
        }
    return {
        "node_role": node_role,
        "contract_rule": "stable-responsive-content",
        "contract_action": "align-copy-or-declare-intentional-variant",
        "contract_risk": _responsive_contract_risk(node_role, difference_kind),
    }


def _responsive_node_role(key: str, *, difference_kind: str = "") -> str:
    kind, _, raw_name = key.partition(":")
    name = raw_name or key
    if "footer" in name:
        return "footer"
    if "hero" in name:
        return "hero"
    if "faq" in name or "accordion" in name:
        return "faq"
    if _is_order_sensitive_family(key):
        return "collection"
    if "input-output" in name or "embedded" in name:
        return "embedded-content"
    if "bandeau" in name:
        return "band"
    if kind:
        return kind
    return "content"


def _responsive_contract_risk(node_role: str, difference_kind: str) -> str:
    if difference_kind == "missing-breakpoint-node":
        if node_role in {"hero", "footer", "embedded-content"}:
            return "possible-breakpoint-content-loss"
        return "intentional-breakpoint-structure-needs-declaration"
    if difference_kind == "same-content-different-order":
        return "responsive-order-or-carousel-intent-unclear"
    if node_role == "footer":
        return "footer-copy-drift"
    if node_role == "hero":
        return "primary-message-drift"
    if node_role == "collection":
        return "collection-content-drift"
    return "responsive-content-drift"


def _is_order_sensitive_family(key: str) -> bool:
    _kind, _separator, raw_name = key.partition(":")
    tokens = set(_slug(raw_name or key).split("-"))
    return bool(tokens & ORDER_SENSITIVE_NAME_TOKENS)


def _signature_payload_tokens(signature: str) -> list[str]:
    lines = [line for line in signature.splitlines() if line]
    if len(lines) <= 2:
        return []
    return lines[2:]


def _has_responsive_content(node: NormalizedNode) -> bool:
    for descendant in node.walk():
        payload = descendant.payload
        value = payload.get("characters") or payload.get("value") or payload.get("rawValue")
        if str(value or "").strip():
            return True
        source = (
            payload.get("pipelineImageUrl")
            or payload.get("imageUrl")
            or payload.get("imageURL")
            or payload.get("image_url")
            or payload.get("imageRef")
            or payload.get("image_ref")
            or payload.get("local_path")
        )
        if source:
            return True
        fills = payload.get("fills")
        if isinstance(fills, list) and any(
            isinstance(fill, dict)
            and fill.get("visible") is not False
            and str(fill.get("type", "")).upper() in {"SOLID", "GRADIENT_LINEAR", "IMAGE"}
            for fill in fills
        ):
            return True
    return False
