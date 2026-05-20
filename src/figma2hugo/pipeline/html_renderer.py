"""Rend une page HTML statique depuis un plan de rendu pour debug et smoke tests."""

from __future__ import annotations

from html import escape

from figma2hugo.pipeline.models import NodeKind, RenderNodePlan, RenderPlan, RenderSectionPlan

KNOWN_FONT_IMPORTS = {
    "Inter": (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Inter:ital,opsz,wght@0,14..32,100..900;"
        "1,14..32,100..900&display=swap');"
    )
}
BACKGROUND_IMAGE_EDGE_GUARD_PX = 12.0


def render_static_document(plan: RenderPlan, *, stylesheet_href: str | None = None) -> str:
    head_asset = (
        f'<link rel="stylesheet" href="{escape(stylesheet_href)}">'
        if stylesheet_href
        else "\n".join(["<style>", render_static_css(plan), "</style>"])
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="fr">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(plan.page_name)}</title>",
            head_asset,
            "</head>",
            "<body>",
            render_static_body(plan),
            "</body>",
            "</html>",
        ]
    )


def render_static_body(plan: RenderPlan) -> str:
    sections = "\n".join(_render_section(section) for section in plan.sections)
    return (
        f'<main class="pipeline-page" data-page-id="{escape(plan.page_id)}" '
        f'data-page-width="{plan.width}">\n{sections}\n</main>'
    )


def render_static_css(plan: RenderPlan) -> str:
    font_imports = _font_imports_css(plan)
    base_css = f"""
* {{ box-sizing: border-box; }}
html, body {{ overflow-x: hidden; }}
body {{ margin: 0; background: #f4f6f8; color: #061d4f; font-family: 'Inter', 'Segoe UI', Arial, sans-serif; }}
.pipeline-page {{
  position: relative;
  width: min(100%, {plan.width}px);
  min-height: {max(plan.height, _content_bottom(plan))}px;
  margin: 0 auto;
  background: white;
  overflow-x: clip;
}}
.pipeline-section {{
  position: absolute;
  overflow: visible;
}}
.pipeline-node {{
  position: absolute;
  overflow: visible;
}}
.pipeline-layer-background {{ z-index: 0; }}
.pipeline-layer-decorative {{ z-index: 1; }}
.pipeline-layer-asset {{ z-index: 2; }}
.pipeline-layer-content {{ z-index: 3; }}
.pipeline-layer-foreground {{ z-index: 4; }}
.pipeline-text {{ white-space: pre-wrap; line-height: 1.25; overflow-wrap: break-word; word-break: normal; }}
.pipeline-text-content {{ display: block; width: 100%; white-space: inherit; }}
.pipeline-list-text {{ counter-reset: pipeline-list; white-space: normal; }}
.pipeline-list-line {{ display: block; min-height: 1em; position: relative; white-space: pre-wrap; }}
.pipeline-list-line[data-list-type="unordered"],
.pipeline-list-line[data-list-type="ordered"] {{
  padding-left: calc(1.05em + var(--pipeline-list-level, 0) * 0.75em);
}}
.pipeline-list-line[data-list-type="unordered"]::before {{
  background: currentColor;
  border-radius: 999px;
  content: "";
  height: 0.28em;
  left: calc(0.25em + var(--pipeline-list-level, 0) * 0.75em);
  position: absolute;
  top: 0.62em;
  transform: translateY(-50%);
  width: 0.28em;
}}
.pipeline-list-line[data-list-type="ordered"] {{
  counter-increment: pipeline-list;
}}
.pipeline-list-line[data-list-type="ordered"]::before {{
  content: counter(pipeline-list) ".";
  left: calc(var(--pipeline-list-level, 0) * 0.75em);
  position: absolute;
  text-align: right;
  width: 0.85em;
}}
.pipeline-svg {{ display: block; width: 100%; height: 100%; min-height: inherit; overflow: visible; }}
.pipeline-img {{ display: block; width: 100%; height: 100%; min-height: inherit; object-fit: cover; }}
.pipeline-layer-asset > .pipeline-img,
.pipeline-layer-decorative > .pipeline-img {{
  object-fit: fill;
}}
.pipeline-layer-background > .pipeline-img {{
  object-fit: fill;
  width: calc(100% + {BACKGROUND_IMAGE_EDGE_GUARD_PX:g}px);
  max-width: none;
  transform: translateX(-{BACKGROUND_IMAGE_EDGE_GUARD_PX / 2:g}px);
}}
.pipeline-form {{ display: block; }}
.pipeline-form-control, .pipeline-button {{
  box-sizing: border-box;
  display: block;
  width: 100%;
  min-height: 100%;
  border: 0;
  border-radius: 0;
  font: inherit;
  margin: 0;
}}
.pipeline-form-control {{ padding: 0; background: rgba(104, 126, 172, 0.92); color: inherit; }}
.pipeline-form-control::placeholder {{ color: currentColor; opacity: 1; }}
.pipeline-select-wrapper {{ overflow: visible; }}
.pipeline-select-control {{
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  background: transparent;
  color: inherit;
  font: inherit;
  height: 100%;
  inset: 0;
  letter-spacing: inherit;
  line-height: inherit;
  min-height: 100%;
  padding: 0;
  position: absolute;
  text-align: center;
  text-align-last: center;
  width: 100%;
}}
.pipeline-select-control::-ms-expand {{ display: none; }}
.pipeline-select-control option {{ text-align: center; }}
.pipeline-select-arrow {{
  align-items: center;
  color: inherit;
  display: flex;
  height: 1em;
  justify-content: center;
  pointer-events: none;
  position: absolute;
  right: 1em;
  top: 50%;
  transform: translateY(-50%);
  width: 1em;
}}
.pipeline-select-arrow::before {{
  border-bottom: 0.16em solid currentColor;
  border-right: 0.16em solid currentColor;
  content: "";
  display: block;
  height: 0.45em;
  transform: rotate(45deg) translate(-0.05em, -0.05em);
  width: 0.45em;
}}
.pipeline-button {{
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  appearance: none;
  cursor: pointer;
  color: white;
  background: #cf665f;
  text-align: center;
}}
.pipeline-link-card {{ color: inherit; text-decoration: none; }}
.pipeline-link-card:focus-visible {{ outline: 2px solid #cf665f; outline-offset: 3px; }}
.pipeline-accordion-trigger {{ cursor: pointer; list-style: none; }}
.pipeline-accordion-trigger::-webkit-details-marker {{ display: none; }}
.pipeline-accordion-item:not([open]) {{ overflow: hidden; height: auto !important; }}
.pipeline-accordion-item:not([open]) > .pipeline-accordion-panel {{ display: none; }}
.pipeline-carousel-stage {{ overflow: hidden; }}
.pipeline-carousel-slide {{ transition: opacity 160ms ease; }}
.pipeline-carousel-slide[hidden] {{ display: block; visibility: hidden; opacity: 0; pointer-events: none; }}
.pipeline-carousel-thumb {{
  appearance: none;
  border: 0;
  margin: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  text-align: inherit;
}}
.pipeline-carousel-thumb:focus-visible {{ outline: 2px solid #cf665f; outline-offset: 2px; }}
""".strip()
    return "\n".join(part for part in (font_imports, base_css) if part)


def _render_section(section: RenderSectionPlan) -> str:
    style = _box_style(
        section.bounds.x,
        section.bounds.y,
        section.bounds.width,
        section.bounds.height,
        section.style,
    )
    nodes = "\n".join(_render_node(node, section) for node in section.nodes)
    return (
        f'<section class="pipeline-section pipeline-section-{escape(section.layout_mode)}" '
        f'data-section-id="{escape(section.section_id)}" '
        f'data-section-name="{escape(section.name)}" style="{style}">\n{nodes}\n</section>'
    )


def _render_node(node: RenderNodePlan, section: RenderSectionPlan) -> str:
    left = node.bounds.x - section.bounds.x
    top = node.bounds.y - section.bounds.y
    return _render_node_at(node, left, top)


def _render_child_node(node: RenderNodePlan, parent_x: float, parent_y: float) -> str:
    left = node.bounds.x - parent_x
    top = node.bounds.y - parent_y
    return _render_node_at(node, left, top)


def _render_node_at(node: RenderNodePlan, left: float, top: float) -> str:
    style = _box_style(left, top, node.bounds.width, node.bounds.height, node.style)
    if node.kind is NodeKind.ASSET or node.asset_url:
        style += f"height:{node.bounds.height:g}px;"
    if node.kind is NodeKind.TEXT:
        style += f"height:{node.bounds.height:g}px;"
    classes = f"pipeline-node pipeline-layer-{escape(node.layer)}"
    if node.kind is NodeKind.TEXT:
        classes += " pipeline-text"
    children = "\n".join(
        _render_child_node(child, node.bounds.x, node.bounds.y) for child in node.children
    )
    body = _node_body(node, children)
    attrs = _base_node_attrs(node, classes, style)
    if node.component == "form":
        method = escape(node.attributes.get("method", "post"))
        return f'<form {attrs} method="{method}">{body}</form>'
    if node.component == "field":
        attrs = _base_node_attrs(node, f"{classes} pipeline-form-control", style)
        field_type = escape(node.attributes.get("type", "text"))
        return f'<input {attrs} type="{field_type}"{_form_attrs(node)}>'
    if node.component == "textarea":
        attrs = _base_node_attrs(node, f"{classes} pipeline-form-control", style)
        return f"<textarea {attrs}{_form_attrs(node)}></textarea>"
    if node.component == "select":
        attrs = _base_node_attrs(node, f"{classes} pipeline-select-wrapper", style)
        select_attrs = _select_control_attrs(node)
        label = escape(str(node.attributes.get("placeholder", "")))
        return (
            f"<div {attrs}>"
            f"<select {select_attrs}>"
            f'<option value="" style="{_select_option_style()}">{label}</option>'
            f"{_select_options_html(node)}</select>"
            '<span class="pipeline-select-arrow" aria-hidden="true"></span></div>'
        )
    if node.component == "submit":
        attrs = _base_node_attrs(node, f"{classes} pipeline-button", style)
        label = escape(node.attributes.get("label") or node.text or node.name)
        button_type = escape(node.attributes.get("type", "submit"))
        return f'<button {attrs} type="{button_type}">{label}</button>'
    if node.component == "link-card":
        attrs = _base_node_attrs(node, f"{classes} pipeline-link-card", style)
        return f"<a {attrs}{_link_attrs(node)}>{body}</a>"
    if node.component == "carousel":
        attrs = _base_node_attrs(node, f"{classes} pipeline-carousel", style)
        return f'<div {attrs} data-carousel="true">{body}</div>'
    if node.component == "carousel-stage":
        attrs = _base_node_attrs(node, f"{classes} pipeline-carousel-stage", style)
        return f'<div {attrs} data-carousel-stage="true">{body}</div>'
    if node.component == "carousel-nav":
        attrs = _base_node_attrs(node, f"{classes} pipeline-carousel-nav", style)
        return f'<div {attrs} data-carousel-nav="true">{body}</div>'
    if node.component == "carousel-slide":
        attrs = _base_node_attrs(node, f"{classes} pipeline-carousel-slide", style)
        key = escape(node.attributes.get("key") or node.node_id)
        default_attr = _carousel_default_attr(node)
        hidden_attr = "" if default_attr else " hidden"
        aria_hidden = "false" if default_attr else "true"
        return (
            f'<div {attrs} data-carousel-slide="{key}"{default_attr}{hidden_attr} '
            f'aria-hidden="{aria_hidden}">{body}</div>'
        )
    if node.component == "carousel-thumb":
        attrs = _base_node_attrs(node, f"{classes} pipeline-carousel-thumb", style)
        key = escape(node.attributes.get("key") or node.node_id)
        default_attr = _carousel_default_attr(node)
        pressed = "true" if default_attr else "false"
        return (
            f'<button {attrs} type="button" data-carousel-thumb="{key}"'
            f'{default_attr} aria-pressed="{pressed}">{body}</button>'
        )
    if node.component == "accordion-item":
        attrs = _base_node_attrs(node, f"{classes} pipeline-accordion-item", style)
        open_attr = " open" if node.attributes.get("open") else ""
        return f"<details {attrs}{open_attr}>{body}</details>"
    if node.component == "accordion-trigger":
        attrs = _base_node_attrs(node, f"{classes} pipeline-accordion-trigger", style)
        return f"<summary {attrs}>{body}</summary>"
    if node.component == "accordion-panel":
        attrs = _base_node_attrs(node, f"{classes} pipeline-accordion-panel", style)
        return f"<div {attrs}>{body}</div>"
    return f"<div {attrs}>{body}</div>"


def _node_body(node: RenderNodePlan, children: str) -> str:
    if vector_paths := _vector_paths(node):
        return _vector_shape_svg(node, vector_paths)
    if node.asset_url:
        return (
            f'<img class="pipeline-img" src="{escape(node.asset_url)}" alt="{escape(node.name)}">'
        )
    text_lines = _text_lines(node)
    if text_lines:
        return (
            '<span class="pipeline-text-content pipeline-list-text">'
            + "".join(_text_line_html(line) for line in text_lines)
            + "</span>"
        )
    if node.text_runs:
        return (
            '<span class="pipeline-text-content">'
            + "".join(
                f'<span style="{_inline_style(run.style)}">{escape(run.text)}</span>'
                if run.style
                else f"<span>{escape(run.text)}</span>"
                for run in node.text_runs
            )
            + "</span>"
        )
    if node.text:
        return escape(node.text)
    return children


def _vector_paths(node: RenderNodePlan) -> list[dict[str, object]]:
    paths = node.attributes.get("vectorPaths")
    if not isinstance(paths, list):
        return []
    return [path for path in paths if isinstance(path, dict) and path.get("path")]


def _vector_shape_svg(node: RenderNodePlan, paths: list[dict[str, object]]) -> str:
    fill = escape(str(node.attributes.get("shapeFill") or "currentColor"))
    path_html = "".join(
        (
            f'<path d="{escape(str(path.get("path") or ""))}" '
            f'fill="{fill}" fill-rule="{escape(_svg_fill_rule(path.get("fillRule")))}">'
            "</path>"
        )
        for path in paths
    )
    return (
        '<svg class="pipeline-svg" '
        f'viewBox="0 0 {node.bounds.width:g} {node.bounds.height:g}" '
        f'preserveAspectRatio="none" aria-hidden="true">{path_html}</svg>'
    )


def _svg_fill_rule(value: object) -> str:
    normalized = str(value or "nonzero").strip().lower()
    return normalized if normalized in {"nonzero", "evenodd"} else "nonzero"


def _text_lines(node: RenderNodePlan) -> list[dict[str, object]]:
    lines = node.attributes.get("textLines")
    if not isinstance(lines, list):
        return []
    return [line for line in lines if isinstance(line, dict)]


def _text_line_html(line: dict[str, object]) -> str:
    line_type = _text_line_type(line.get("type"))
    indent = _text_line_indent(line.get("indent"))
    style = f"--pipeline-list-level:{indent:g};"
    return (
        '<span class="pipeline-list-line" '
        f'data-list-type="{escape(line_type)}" '
        f'style="{style}">{escape(str(line.get("text") or ""))}</span>'
    )


def _text_line_type(value: object) -> str:
    normalized = str(value or "none").strip().lower()
    return normalized if normalized in {"none", "ordered", "unordered"} else "none"


def _text_line_indent(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _base_node_attrs(node: RenderNodePlan, classes: str, style: str) -> str:
    attrs = [
        f'class="{classes}"',
        f'data-node-id="{escape(node.node_id)}"',
        f'data-node-name="{escape(node.name)}"',
        f'data-kind="{node.kind.value}"',
        f'style="{style}"',
    ]
    if node.component:
        attrs.append(f'data-component="{escape(node.component)}"')
    return " ".join(attrs)


def _select_control_attrs(node: RenderNodePlan) -> str:
    attrs = [
        'class="pipeline-form-control pipeline-select-control"',
        f'data-node-id="{escape(node.node_id)}"',
        f'data-node-name="{escape(node.name)}"',
        f'data-kind="{node.kind.value}"',
        'data-component="select"',
    ]
    if node.attributes.get("name"):
        attrs.append(f'name="{escape(str(node.attributes["name"]))}"')
    if node.attributes.get("placeholder"):
        attrs.append(f'aria-label="{escape(str(node.attributes["placeholder"]))}"')
    if node.attributes.get("required"):
        attrs.append("required")
    return " ".join(attrs)


def _form_attrs(node: RenderNodePlan) -> str:
    attrs = []
    if node.attributes.get("name"):
        attrs.append(f'name="{escape(str(node.attributes["name"]))}"')
    if node.attributes.get("placeholder"):
        attrs.append(f'placeholder="{escape(str(node.attributes["placeholder"]))}"')
    if node.attributes.get("required"):
        attrs.append("required")
    return (" " + " ".join(attrs)) if attrs else ""


def _select_options_html(node: RenderNodePlan) -> str:
    options = node.attributes.get("options")
    if not isinstance(options, list):
        return ""
    chunks: list[str] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        value = escape(str(option.get("value") or ""))
        label = escape(str(option.get("label") or value))
        if label:
            chunks.append(
                f'<option value="{value}" style="{_select_option_style()}">{label}</option>'
            )
    return "".join(chunks)


def _select_option_style() -> str:
    return "color:#111;background-color:#fff"


def _link_attrs(node: RenderNodePlan) -> str:
    attrs = [f'href="{escape(str(node.attributes.get("href", "#")))}"']
    if node.attributes.get("target"):
        attrs.append(f'target="{escape(str(node.attributes["target"]))}"')
    if node.attributes.get("rel"):
        attrs.append(f'rel="{escape(str(node.attributes["rel"]))}"')
    if node.attributes.get("label"):
        attrs.append(f'aria-label="{escape(str(node.attributes["label"]))}"')
    return " " + " ".join(attrs)


def _carousel_default_attr(node: RenderNodePlan) -> str:
    return ' data-carousel-default="true"' if node.attributes.get("default") == "true" else ""


def _box_style(
    x: float,
    y: float,
    width: float,
    height: float,
    declarations: dict[str, str] | None = None,
) -> str:
    chunks = [f"left:{x:g}px", f"top:{y:g}px", f"width:{width:g}px", f"min-height:{height:g}px"]
    if declarations:
        chunks.extend(f"{name}:{value}" for name, value in sorted(declarations.items()))
    return ";".join(chunks) + ";"


def _inline_style(declarations: dict[str, str]) -> str:
    return ";".join(f"{name}:{value}" for name, value in sorted(declarations.items())) + ";"


def _content_bottom(plan: RenderPlan) -> int:
    bottom = max((section.bounds.bottom for section in plan.sections), default=0)
    return int(round(bottom))


def _font_imports_css(plan: RenderPlan) -> str:
    families = sorted(_font_families_for_plan(plan))
    imports = [KNOWN_FONT_IMPORTS[family] for family in families if family in KNOWN_FONT_IMPORTS]
    return "\n".join(imports)


def _font_families_for_plan(plan: RenderPlan) -> set[str]:
    families: set[str] = set()
    for section in plan.sections:
        _collect_font_family(section.style, families)
        for node in section.nodes:
            families.update(_font_families_for_node(node))
    return families


def _font_families_for_node(node: RenderNodePlan) -> set[str]:
    families: set[str] = set()
    _collect_font_family(node.style, families)
    for run in node.text_runs:
        _collect_font_family(run.style, families)
    for child in node.children:
        families.update(_font_families_for_node(child))
    return families


def _collect_font_family(style: dict[str, str], families: set[str]) -> None:
    raw_family = style.get("font-family")
    if not raw_family:
        return
    for family in raw_family.split(","):
        normalized = family.strip().strip("\"'")
        if normalized:
            families.add(normalized)
