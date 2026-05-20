"""Construit le plan de rendu navigateur en gardant Figma comme source de verite."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from figma2hugo.pipeline.components import FORM_CONTROL_COMPONENTS
from figma2hugo.pipeline.diagnostics import analyze_render_plan
from figma2hugo.pipeline.geometry import GEOMETRY_EPSILON
from figma2hugo.pipeline.geometry import walk_render_nodes as _walk_render_nodes
from figma2hugo.pipeline.models import (
    GeometryBox,
    IntermediatePipelineDocument,
    NodeKind,
    NormalizedNode,
    RenderNodePlan,
    RenderPlan,
    RenderSectionPlan,
)
from figma2hugo.pipeline.naming import (
    is_background_name as _is_background_name,
)
from figma2hugo.pipeline.naming import (
    is_foreground_name as _is_foreground_name,
)
from figma2hugo.pipeline.naming import (
    name_key as _name_key,
)
from figma2hugo.pipeline.naming import (
    slugify as _slug,
)
from figma2hugo.pipeline.options import PipelineRenderMode, normalize_render_mode
from figma2hugo.pipeline.render_styles import (
    TEXT_STYLE_KEYS,
    payload_text_value,
    render_style,
    text_runs,
    visible_drop_shadow_filter,
)
from figma2hugo.pipeline.semantic_adjustments import apply_semantic_adjustments

FIELD_PREFIX_RE = re.compile(r"^(?:input|field|champ)[-_]")
FORM_TOKEN_RE = re.compile(r"(?:^|[-_])(form|formulaire)(?:[-_]|$)")
SUBMIT_TEXT_RE = re.compile(r"\b(?:envoyer|devis|decouvrir|discover|submit|send)\b")
CONTROL_VISUAL_PREFIXES = ("zone-", "surface-")
CONTROL_VISUAL_SUFFIXES = ("-zone", "-surface")
CAROUSEL_DEFAULT_TOKENS = {"active", "current", "default", "selected"}
CAROUSEL_ITEM_PREFIXES = {
    "carousel-slide": ("carousel-slide-", "slide-"),
    "carousel-thumb": ("carousel-thumb-", "thumb-", "thumbnail-"),
}
DUPLICATE_WRAPPER_COMPONENTS = {"accordion-trigger"}
CONTROL_LABEL_BOUNDS_TOLERANCE_PX = 2.0


def build_render_plan(
    document: IntermediatePipelineDocument,
    *,
    render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE,
) -> RenderPlan:
    # La premiere passe reste litterale : sections et enfants viennent de Figma.
    # La passe utilisable ne traite que les contraintes web que Figma ne peut
    # pas exprimer directement, comme les accordions ou les garde-fous overflow.
    mode = normalize_render_mode(render_mode)
    section_candidates = tuple(
        sorted(
            (_section_plan(section) for section in document.sections),
            key=lambda section: (section.bounds.y, section.bounds.x),
        )
    )
    sections = tuple(section for section in section_candidates if section.nodes)
    if not sections:
        sections = section_candidates
    plan = RenderPlan(
        page_id=document.page.id,
        page_name=document.page.name,
        width=int(round(document.page.page_bounds.width)),
        height=int(round(document.page.page_bounds.height)),
        sections=sections,
        diagnostics=document.diagnostics,
    )
    if mode is PipelineRenderMode.USABLE:
        adjusted_plan, adjustment_issues = apply_semantic_adjustments(plan)
    else:
        adjusted_plan = plan
        adjustment_issues = ()
    return RenderPlan(
        page_id=adjusted_plan.page_id,
        page_name=adjusted_plan.page_name,
        width=adjusted_plan.width,
        height=adjusted_plan.height,
        sections=adjusted_plan.sections,
        diagnostics=(
            *document.diagnostics,
            *adjustment_issues,
            *analyze_render_plan(adjusted_plan),
        ),
    )


def _section_plan(section: NormalizedNode) -> RenderSectionPlan:
    nodes = tuple(
        child_plan
        for child in section.children
        if (child_plan := _node_plan_or_none(child)) is not None
    )
    return RenderSectionPlan(
        section_id=section.id,
        name=section.name,
        bounds=section.page_bounds,
        layout_mode=_section_layout_mode(section),
        style=render_style(section),
        nodes=tuple(_fit_node_tree_to_parent(node, section.page_bounds) for node in nodes),
    )


def _node_plan_or_none(node: NormalizedNode) -> RenderNodePlan | None:
    if _is_metadata_node(node):
        return None
    children = tuple(
        child_plan
        for child in node.children
        if (child_plan := _node_plan_or_none(child)) is not None
    )
    text = _text_value(node)
    asset_url = _asset_url(node)
    style = render_style(node, asset_url=asset_url)
    component = _component_for(node, text, children)
    attributes = _component_attributes(node, component, text, children)
    if node.kind is NodeKind.TEXT:
        attributes = {**attributes, **_text_line_attributes(node.payload, text)}
    if node.kind is NodeKind.ASSET and not asset_url:
        vector_attributes = _vector_shape_attributes(node.payload, style=style)
        if vector_attributes:
            attributes = {**attributes, **vector_attributes}
            style = {name: value for name, value in style.items() if name != "background-color"}
            if shape_filter := visible_drop_shadow_filter(node.payload):
                style = {**style, "filter": shape_filter}
    style = _component_render_style(component, style, attributes, text, children)
    bounds = _component_render_bounds(component, node.page_bounds, children)
    render_children = _component_render_children(component, children)
    plan = RenderNodePlan(
        node_id=node.id,
        name=node.name,
        kind=node.kind,
        bounds=bounds,
        layer=_layer_for(node),
        text=text,
        asset_url=asset_url,
        style=style,
        component=component,
        attributes=attributes,
        text_runs=text_runs(node.payload, base_style=style) if node.kind is NodeKind.TEXT else (),
        children=render_children,
    )
    plan = _collapse_duplicate_component_wrapper(plan)
    return plan if _is_renderable(plan) else None


def _is_renderable(node: RenderNodePlan) -> bool:
    return bool(
        node.text.strip()
        or node.asset_url
        or node.style
        or node.component
        or node.children
        or node.attributes.get("vectorPaths")
    )


def _is_metadata_node(node: NormalizedNode) -> bool:
    if node.kind is not NodeKind.TEXT:
        return False
    name = _name_key(node.name)
    text = _text_value(node).strip().lower()
    return bool(
        name.startswith(("href-", "url-", "link-url-"))
        and text.startswith(("http://", "https://", "/"))
    )


def _descendant_metadata_url(node: NormalizedNode) -> str:
    for descendant in node.walk():
        if _is_metadata_node(descendant):
            return _text_value(descendant).strip()
    return ""


def _component_for(
    node: NormalizedNode,
    text: str,
    children: tuple[RenderNodePlan, ...],
) -> str:
    # La detection des composants repose volontairement sur les noms. Figma garde
    # la main sur la forme visuelle ; ici on decide seulement si le navigateur
    # a besoin d'un comportement interactif.
    name = _name_key(node.name)
    child_text = _descendant_text(children)
    if node.kind is NodeKind.TEXT:
        return "submit" if _looks_like_submit(name, text, child_text) else ""
    if node.kind not in {NodeKind.CONTAINER, NodeKind.ASSET, NodeKind.UNKNOWN}:
        return ""
    if node.kind is NodeKind.ASSET and _is_background_name(name):
        return ""
    if name.startswith("link-grid") or name.startswith("case-grid"):
        return "link-grid"
    if name.startswith("link-row"):
        return "link-row"
    if name.startswith(("href-card", "case-card")) or (
        "card" in name and _descendant_metadata_url(node)
    ):
        return "link-card"
    if name.startswith(("carousel-stage", "slider-stage")):
        return "carousel-stage"
    if name.startswith(("carousel-thumbs", "carousel-nav", "carousel-track", "slider-nav")):
        return "carousel-nav"
    if name.startswith(("carousel-slide", "slide-")):
        return "carousel-slide"
    if name.startswith(("carousel-thumb", "thumb-", "thumbnail-")):
        return "carousel-thumb"
    if name.startswith(("carousel", "slider")):
        return "carousel"
    if name.startswith("accordion-single") or name.startswith("accordion-list"):
        return "accordion"
    if name.startswith("accordion-item"):
        return "accordion-item"
    if name.startswith("accordion-trigger"):
        return "accordion-trigger"
    if name.startswith("accordion-panel"):
        return "accordion-panel"
    if (
        node.kind is NodeKind.CONTAINER
        and not _is_background_name(name)
        and FORM_TOKEN_RE.search(name)
    ):
        return "form"
    if _looks_like_submit(name, text, child_text):
        return "submit"
    if _looks_like_select(name, text, child_text):
        return "select"
    if _looks_like_textarea(name, text, child_text):
        return "textarea"
    if _looks_like_field(name):
        return "field"
    return ""


def _component_attributes(
    node: NormalizedNode,
    component: str,
    text: str,
    children: tuple[RenderNodePlan, ...],
) -> dict[str, Any]:
    if not component:
        return {}
    name = _name_key(node.name)
    child_texts = _descendant_texts(children)
    label = _best_label(component, text, child_texts, node.name)
    if component == "form":
        return {"method": "post"}
    if component == "link-card":
        href = _descendant_metadata_url(node) or "#"
        link_attributes: dict[str, Any] = {"href": href, "label": label}
        if href.startswith(("http://", "https://")):
            link_attributes["target"] = "_blank"
            link_attributes["rel"] = "noopener noreferrer"
        return link_attributes
    if component == "accordion-item":
        return {"open": "open"} if "open" in name else {}
    if component in {"carousel-stage", "carousel-nav"}:
        return {}
    if component in {"carousel-slide", "carousel-thumb"}:
        key = _carousel_item_key(name, component)
        attributes = {"key": key}
        if _carousel_item_starts_active(name) or key in {"1", "01", "first"}:
            attributes["default"] = "true"
        return attributes
    if component == "carousel":
        return {"label": label}
    if component == "submit":
        return {
            "type": "submit",
            "label": label,
            "name": _field_name(label, node.name),
        }
    form_attributes: dict[str, Any] = {
        "name": _field_name(label, node.name),
        "placeholder": label,
    }
    if "required" in name or "obligatoire" in name:
        form_attributes["required"] = "required"
    if component == "field":
        form_attributes["type"] = _input_type(name, label)
    if component == "select":
        options = _select_options(children, placeholder=label)
        if options:
            form_attributes["options"] = options
    return form_attributes


def _component_render_style(
    component: str,
    style: dict[str, str],
    attributes: dict[str, Any],
    text: str,
    children: tuple[RenderNodePlan, ...],
) -> dict[str, str]:
    if component not in FORM_CONTROL_COMPONENTS:
        return style
    visual = _descendant_control_visual_style(children)
    label = attributes.get("label") or attributes.get("placeholder") or text
    label_style = _descendant_text_style_for_label(children, label)
    if not label_style:
        return {**visual, **style}
    inherited = {key: value for key, value in label_style.items() if key in TEXT_STYLE_KEYS}
    if not inherited:
        return {**visual, **style}
    return {**visual, **inherited, **style}


def _descendant_control_visual_style(children: tuple[RenderNodePlan, ...]) -> dict[str, str]:
    for child in children:
        if _is_control_visual_background(child):
            visual = _control_visual_style(child)
            if visual:
                return visual
    for child in children:
        visual = _descendant_control_visual_style(child.children)
        if visual:
            return visual
    return {}


def _is_control_visual_background(node: RenderNodePlan) -> bool:
    name = _name_key(node.name)
    return (
        node.layer == "background"
        or _is_background_name(name)
        or name.startswith(CONTROL_VISUAL_PREFIXES)
        or name.endswith(CONTROL_VISUAL_SUFFIXES)
    )


def _control_visual_style(node: RenderNodePlan) -> dict[str, str]:
    visual: dict[str, str] = {}
    if node.asset_url:
        visual.update(
            {
                "background-image": f'url("{node.asset_url}")',
                "background-position": "center",
                "background-repeat": "no-repeat",
                "background-size": "100% 100%",
                "background-color": "transparent",
            }
        )
    background_color = node.style.get("background-color")
    if background_color and not node.asset_url:
        visual["background-color"] = background_color
    return visual


def _component_render_bounds(
    component: str,
    bounds: GeometryBox,
    children: tuple[RenderNodePlan, ...],
) -> GeometryBox:
    if component not in FORM_CONTROL_COMPONENTS:
        return bounds
    visual = _direct_control_visual_node(children)
    if visual is None:
        return bounds
    if component == "submit" and _submit_visual_is_actual_button(bounds, visual.bounds, children):
        return visual.bounds
    if not _control_visual_bounds_replace_frame(component, bounds, visual.bounds):
        return bounds
    return visual.bounds


def _component_render_children(
    component: str,
    children: tuple[RenderNodePlan, ...],
) -> tuple[RenderNodePlan, ...]:
    if component in FORM_CONTROL_COMPONENTS:
        return ()
    return children


def _direct_control_visual_node(children: tuple[RenderNodePlan, ...]) -> RenderNodePlan | None:
    for child in children:
        if _is_control_visual_background(child):
            return child
    return None


def _submit_visual_is_actual_button(
    frame_bounds: GeometryBox,
    visual_bounds: GeometryBox,
    children: tuple[RenderNodePlan, ...],
) -> bool:
    frame_width = max(frame_bounds.width, GEOMETRY_EPSILON)
    if visual_bounds.width / frame_width >= 0.75:
        return False
    if visual_bounds.width < 24 or visual_bounds.height < 8:
        return False
    label = _direct_control_label_node(children)
    if label is None:
        return False
    label_bounds = label.bounds
    if label_bounds.width > visual_bounds.width + CONTROL_LABEL_BOUNDS_TOLERANCE_PX:
        return False
    if label_bounds.height > visual_bounds.height * 2 + CONTROL_LABEL_BOUNDS_TOLERANCE_PX:
        return False
    return (
        _bounds_overlap_ratio(label_bounds, visual_bounds, axis="x") >= 0.65
        and _bounds_overlap_ratio(label_bounds, visual_bounds, axis="y") >= 0.65
    )


def _direct_control_label_node(children: tuple[RenderNodePlan, ...]) -> RenderNodePlan | None:
    for child in children:
        if child.kind is NodeKind.TEXT and child.text.strip():
            return child
    for child in children:
        nested = _direct_control_label_node(child.children)
        if nested is not None:
            return nested
    return None


def _bounds_overlap_ratio(a: GeometryBox, b: GeometryBox, *, axis: str) -> float:
    if axis == "x":
        overlap = min(a.right, b.right) - max(a.x, b.x)
        size = min(a.width, b.width)
    else:
        overlap = min(a.bottom, b.bottom) - max(a.y, b.y)
        size = min(a.height, b.height)
    if overlap <= 0:
        return 0.0
    return overlap / max(size, GEOMETRY_EPSILON)


def _control_visual_bounds_replace_frame(
    component: str,
    frame_bounds: GeometryBox,
    visual_bounds: GeometryBox,
) -> bool:
    frame_height = max(frame_bounds.height, GEOMETRY_EPSILON)
    frame_width = max(frame_bounds.width, GEOMETRY_EPSILON)
    visual_height_ratio = visual_bounds.height / frame_height
    visual_width_ratio = visual_bounds.width / frame_width
    if component == "submit":
        visual_is_larger = visual_height_ratio > 1.05 or visual_width_ratio > 1.05
        visual_has_usable_height = visual_height_ratio >= 0.35 or visual_bounds.height >= 12
        visual_is_close = visual_has_usable_height and visual_width_ratio >= 0.5
        visual_is_bounded = visual_height_ratio <= 3.0 and visual_width_ratio <= 3.0
        if visual_is_larger and visual_is_close and visual_is_bounded:
            return True
    return visual_height_ratio < 0.75 and visual_width_ratio <= 1.1


def _descendant_text_style_for_label(
    children: tuple[RenderNodePlan, ...],
    label: str,
) -> dict[str, str]:
    styled_texts = _descendant_styled_texts(children)
    target = _slug(label)
    if target:
        for value, style in styled_texts:
            for candidate in _label_candidates(value):
                if _slug(candidate) == target:
                    return style
    for value, style in styled_texts:
        if value.strip():
            return style
    return {}


def _descendant_styled_texts(
    children: tuple[RenderNodePlan, ...],
) -> list[tuple[str, dict[str, str]]]:
    styled: list[tuple[str, dict[str, str]]] = []
    for child in children:
        if child.text.strip() and child.style:
            styled.append((child.text.strip(), child.style))
        styled.extend(_descendant_styled_texts(child.children))
    return styled


def _collapse_duplicate_component_wrapper(node: RenderNodePlan) -> RenderNodePlan:
    if node.component not in DUPLICATE_WRAPPER_COMPONENTS:
        return node
    if node.text.strip() or node.asset_url or len(node.children) != 1:
        return node
    child = node.children[0]
    if child.component != node.component:
        return node
    style = {**child.style, **node.style}
    attributes = {**child.attributes, **node.attributes}
    return replace(node, style=style, attributes=attributes, children=child.children)


def _fit_node_tree_to_parent(node: RenderNodePlan, parent_bounds: GeometryBox) -> RenderNodePlan:
    children = tuple(_fit_node_tree_to_parent(child, node.bounds) for child in node.children)
    if children != node.children:
        node = replace(node, children=children)
    if node.kind is not NodeKind.TEXT:
        return node
    bounds = _snap_text_bounds_to_parent(node, parent_bounds)
    return replace(node, bounds=bounds) if bounds != node.bounds else node


def _snap_text_bounds_to_parent(
    node: RenderNodePlan,
    parent_bounds: GeometryBox,
) -> GeometryBox:
    _ = parent_bounds
    return node.bounds


def _looks_like_field(name: str) -> bool:
    return bool(FIELD_PREFIX_RE.search(name) or "-input-" in name or "_input_" in name)


def _looks_like_select(name: str, text: str, child_text: str) -> bool:
    haystack = f"{name} {text} {child_text}".lower()
    return bool(
        _looks_like_field(name)
        and any(token in haystack for token in ("select", "sujet", "demande", "choisissez"))
    )


def _looks_like_textarea(name: str, text: str, child_text: str) -> bool:
    haystack = f"{name} {text} {child_text}".lower()
    return bool(
        _looks_like_field(name)
        and any(token in haystack for token in ("message", "textarea", "commentaire"))
    )


def _looks_like_submit(name: str, text: str, child_text: str) -> bool:
    haystack = f"{name} {text} {child_text}".lower()
    if any(token in name for token in ("button", "bouton", "submit", "envoyer", "devis")):
        return True
    return bool(("action-" in name or name.startswith("cta-")) and SUBMIT_TEXT_RE.search(haystack))


def _descendant_text(children: tuple[RenderNodePlan, ...]) -> str:
    return " ".join(_descendant_texts(children))


def _descendant_texts(children: tuple[RenderNodePlan, ...]) -> list[str]:
    parts: list[str] = []
    for child in children:
        if child.text.strip():
            parts.append(child.text.strip())
        parts.extend(_descendant_texts(child.children))
    return parts


def _select_options(
    children: tuple[RenderNodePlan, ...],
    *,
    placeholder: str,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    placeholder_key = _slug(placeholder)
    for child in _walk_render_nodes(children):
        if child.kind is not NodeKind.TEXT:
            continue
        raw_text = child.text.strip()
        if not raw_text:
            continue
        name = _name_key(child.name)
        candidates = _label_candidates(raw_text)
        if not candidates:
            continue
        candidate_key = _slug(candidates[-1])
        raw_key = _slug(raw_text)
        is_option_node = name.startswith("option-") or "-option-" in name or "|" in raw_text
        is_placeholder = (
            "selected" in name
            or "placeholder" in name
            or "choix" in name
            or candidate_key == placeholder_key
            or raw_key == placeholder_key
            or any(token in candidate_key for token in ("choisir", "choisissez"))
        )
        if not is_option_node or is_placeholder:
            continue
        value = _slug(candidates[0]) if len(candidates) >= 2 else _slug(candidates[-1])
        label = candidates[-1]
        if not value or not label:
            continue
        if value in seen:
            continue
        seen.add(value)
        options.append({"value": value, "label": label})
    return options


def _best_label(component: str, text: str, child_texts: list[str], fallback_name: str) -> str:
    values = [text, *child_texts]
    if component == "submit":
        for value in values:
            for label in _label_candidates(value):
                if SUBMIT_TEXT_RE.search(_slug(label).replace("-", " ")):
                    return label
    if component == "select":
        for value in reversed(values):
            for label in reversed(_label_candidates(value)):
                key = _slug(label)
                if any(token in key for token in ("choisir", "choisissez", "sujet", "demande")):
                    return label
    for value in values:
        for label in _label_candidates(value):
            if label:
                return label
    return _human_label(fallback_name)


def _label_candidates(value: str) -> list[str]:
    return [" ".join(part.split()) for part in value.split("|") if part.strip()]


def _field_name(label: str, fallback_name: str) -> str:
    return _slug(label) or _slug(_human_label(fallback_name)) or "field"


def _input_type(name: str, label: str) -> str:
    haystack = f"{name} {label}".lower()
    if any(token in haystack for token in ("mail", "email", "e-mail")):
        return "email"
    if any(token in haystack for token in ("tel", "telephone", "phone")):
        return "tel"
    return "text"


def _human_label(name: str) -> str:
    chunks = [
        chunk
        for chunk in _name_key(name).split("-")
        if chunk
        and chunk
        not in {
            "input",
            "field",
            "champ",
            "zone",
            "required",
            "obligatoire",
            "bg",
            "background",
            "fond",
            "button",
            "bouton",
            "formulaire",
            "post",
        }
    ]
    return " ".join(chunks).strip() or str(name).strip()


def _carousel_item_key(name: str, component: str) -> str:
    key = name
    for prefix in CAROUSEL_ITEM_PREFIXES.get(component, ()):
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break
    tokens = [token for token in key.split("-") if token and token not in CAROUSEL_DEFAULT_TOKENS]
    return "-".join(tokens) or key or name


def _carousel_item_starts_active(name: str) -> bool:
    return any(token in CAROUSEL_DEFAULT_TOKENS for token in name.split("-"))


def _section_layout_mode(section: NormalizedNode) -> str:
    if section.kind is NodeKind.SECTION:
        return "flow"
    return "absolute"


def _layer_for(node: NormalizedNode) -> str:
    name = _name_key(node.name)
    if _is_background_name(name):
        return "background"
    if _is_foreground_name(name):
        return "foreground"
    if name.startswith(("decor-", "decoration-")):
        return "decorative"
    if node.kind in {NodeKind.TEXT, NodeKind.CONTAINER}:
        return "content"
    return "asset"


def _text_value(node: NormalizedNode) -> str:
    if node.kind is not NodeKind.TEXT:
        return ""
    return payload_text_value(node.payload)


def _text_line_attributes(payload: dict[str, object], text: str) -> dict[str, object]:
    line_types = payload.get("lineTypes")
    if not isinstance(line_types, list):
        return {}
    normalized_types = [_normalize_line_type(value) for value in line_types]
    if not any(line_type != "none" for line_type in normalized_types):
        return {}

    line_indentations = payload.get("lineIndentations")
    lines = text.split("\n")
    text_lines: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        line_type = normalized_types[index] if index < len(normalized_types) else "none"
        indentation = _line_indentation(line_indentations, index)
        text_lines.append({"text": line, "type": line_type, "indent": indentation})
    return {"textLines": text_lines}


def _vector_shape_attributes(
    payload: dict[str, object],
    *,
    style: dict[str, str],
) -> dict[str, object]:
    fill_color = style.get("background-color")
    if not fill_color:
        return {}
    fill_geometry = payload.get("fillGeometry")
    if not isinstance(fill_geometry, list):
        return {}
    paths = [
        {
            "path": path,
            "fillRule": _svg_fill_rule(geometry.get("windingRule")),
        }
        for geometry in fill_geometry
        if isinstance(geometry, dict) and (path := str(geometry.get("path") or "").strip())
    ]
    if not paths:
        return {}
    if all(_path_is_axis_aligned_rectangle(path["path"]) for path in paths):
        return {}
    return {
        "shapeFill": fill_color,
        "vectorPaths": paths,
    }


def _svg_fill_rule(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    return "evenodd" if normalized == "evenodd" else "nonzero"


def _path_is_axis_aligned_rectangle(path: str) -> bool:
    points = _path_points(path)
    if len(points) < 4:
        return False
    xs = sorted({round(x, 3) for x, _ in points})
    ys = sorted({round(y, 3) for _, y in points})
    if len(xs) != 2 or len(ys) != 2:
        return False
    corners = {(xs[0], ys[0]), (xs[0], ys[1]), (xs[1], ys[0]), (xs[1], ys[1])}
    return {point for point in points if point in corners} == corners and all(
        point in corners for point in points
    )


def _path_points(path: str) -> list[tuple[float, float]]:
    values: list[float] = []
    current = ""
    for char in path:
        if char.isdigit() or char in ".-+eE":
            current += char
            continue
        if current:
            try:
                values.append(float(current))
            except ValueError:
                pass
            current = ""
    if current:
        try:
            values.append(float(current))
        except ValueError:
            pass
    return list(zip(values[0::2], values[1::2], strict=False))


def _normalize_line_type(value: object) -> str:
    normalized = str(value or "NONE").strip().lower()
    if normalized == "unordered":
        return "unordered"
    if normalized == "ordered":
        return "ordered"
    return "none"


def _line_indentation(value: object, index: int) -> int:
    if not isinstance(value, list) or index >= len(value):
        return 0
    try:
        return max(0, int(value[index]))
    except (TypeError, ValueError):
        return 0


def _asset_url(node: NormalizedNode) -> str:
    value = (
        node.payload.get("pipelineImageUrl")
        or node.payload.get("imageUrl")
        or node.payload.get("imageURL")
        or node.payload.get("image_url")
        or ""
    )
    return str(value)
