"""Traduit les styles Figma en CSS sans inventer d'intention visuelle."""

from __future__ import annotations

from figma2hugo.pipeline.models import (
    NodeKind,
    NormalizedNode,
    RenderTextRun,
)

TEXT_STYLE_KEYS = (
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "line-height",
    "letter-spacing",
    "text-align",
    "color",
    "display",
    "flex-direction",
    "justify-content",
)
TEXT_RUN_LAYOUT_STYLE_KEYS = {"display", "flex-direction", "justify-content", "text-align"}


def payload_text_value(payload: dict[str, object]) -> str:
    value = payload.get("characters") or payload.get("value") or payload.get("rawValue") or ""
    return normalize_line_separators(str(value))


def normalize_line_separators(value: str) -> str:
    return value.replace("\u2028", "\n").replace("\u2029", "\n")


def render_style(node: NormalizedNode, *, asset_url: str = "") -> dict[str, str]:
    # Cette fonction traduit ce que Figma dit deja. Elle ne doit pas inventer
    # tailles, couleurs ou espacements : ces decisions restent dans la maquette.
    style: dict[str, str] = {}
    payload_style = (
        _effective_text_style_source(node.payload)
        if node.kind is NodeKind.TEXT
        else node.payload.get("style")
    )
    if isinstance(payload_style, dict):
        _copy_text_style(payload_style, style)
    fills = (
        _effective_text_fills_source(node.payload)
        if node.kind is NodeKind.TEXT
        else node.payload.get("fills")
    )
    node_opacity = _float(node.payload.get("opacity"), default=1.0)
    color = _paint_color(fills, node_opacity=1.0 if asset_url else node_opacity)
    if color:
        if node.kind is NodeKind.TEXT:
            style["color"] = color
        else:
            style["background-color"] = color
    return style


def _effective_text_fills_source(payload: dict[str, object]) -> object:
    # Figma peut stocker des couleurs par caractere. Le wrapper CSS a besoin
    # d'une couleur de base ; on choisit donc la couleur visible dominante,
    # puis les spans conservent les details plus fins.
    base_fills = payload.get("fills")
    characters = str(
        payload.get("characters") or payload.get("value") or payload.get("rawValue") or ""
    )
    overrides = payload.get("characterStyleOverrides")
    if not characters or not isinstance(overrides, list):
        return base_fills

    weighted_colors: dict[str, int] = {}
    sources_by_color: dict[str, object] = {}
    first_color_index: dict[str, int] = {}
    for index, char in enumerate(characters):
        if char.isspace():
            continue
        if index >= len(overrides):
            return base_fills
        source = _text_override_fills_source(payload, str(overrides[index]), base_fills)
        if not isinstance(source, list):
            continue
        color = _paint_color(source)
        if not color:
            continue
        weighted_colors[color] = weighted_colors.get(color, 0) + 1
        sources_by_color.setdefault(color, source)
        first_color_index.setdefault(color, index)
    if weighted_colors:
        color = max(
            weighted_colors,
            key=lambda value: (weighted_colors[value], -first_color_index[value]),
        )
        return sources_by_color[color]
    return base_fills


def _text_override_fills_source(
    payload: dict[str, object],
    override_id: str,
    base_fills: object,
) -> object:
    if override_id in {"", "0"}:
        return base_fills
    style_override_table = payload.get("styleOverrideTable")
    if isinstance(style_override_table, dict):
        override_style = style_override_table.get(override_id)
        if isinstance(override_style, dict):
            override_fills = override_style.get("fills")
            if isinstance(override_fills, list):
                return override_fills
    fill_override_table = payload.get("fillOverrideTable")
    if isinstance(fill_override_table, dict):
        override_fill = fill_override_table.get(override_id)
        if isinstance(override_fill, dict):
            override_fills = override_fill.get("fills")
            if isinstance(override_fills, list):
                return override_fills
    return base_fills


def _effective_text_style_source(payload: dict[str, object]) -> object:
    # Les blocs de texte mixtes ont besoin d'un style de base prudent. On garde
    # les plus grandes metriques utiles pour eviter le clipping dans le navigateur.
    base_style = payload.get("style")
    if not isinstance(base_style, dict):
        return base_style
    characters = str(
        payload.get("characters") or payload.get("value") or payload.get("rawValue") or ""
    )
    overrides = payload.get("characterStyleOverrides")
    table = payload.get("styleOverrideTable")
    if not characters or not isinstance(overrides, list) or not isinstance(table, dict):
        return base_style
    override_ids: list[str] = []
    for index, char in enumerate(characters):
        if char.isspace():
            continue
        if index >= len(overrides):
            return base_style
        override_id = str(overrides[index])
        if override_id in {"", "0"} or override_id not in table:
            return base_style
        override_ids.append(override_id)
    if not override_ids:
        return base_style

    merged_styles: list[dict[str, object]] = []
    for override_id in override_ids:
        override_style = table.get(override_id)
        if isinstance(override_style, dict):
            merged_styles.append({**base_style, **override_style})
    if not merged_styles:
        return base_style

    effective = dict(base_style)
    for key in ("fontSize", "lineHeightPx", "lineHeight"):
        values = [_float_or_none(style.get(key)) for style in merged_styles]
        numeric_values = [value for value in values if value is not None and value > 0]
        if numeric_values:
            effective[key] = max(numeric_values)
    letter_spacings = [_float_or_none(style.get("letterSpacing")) for style in merged_styles]
    numeric_spacings = [value for value in letter_spacings if value is not None]
    if numeric_spacings:
        effective["letterSpacing"] = max(numeric_spacings)
    return effective


def text_runs(
    payload: dict[str, object], *, base_style: dict[str, str]
) -> tuple[RenderTextRun, ...]:
    characters = payload_text_value(payload)
    if not characters:
        return ()
    overrides = payload.get("characterStyleOverrides")
    style_override_table = payload.get("styleOverrideTable")
    fill_override_table = payload.get("fillOverrideTable")
    if not isinstance(overrides, list):
        return ()
    if not isinstance(style_override_table, dict) and not isinstance(fill_override_table, dict):
        return ()

    runs: list[RenderTextRun] = []
    current_text: list[str] = []
    current_style: dict[str, str] | None = None
    for index, character in enumerate(characters):
        override_id = str(overrides[index]) if index < len(overrides) else "0"
        style = _text_run_style(payload, override_id)
        if current_style is None:
            current_style = style
            current_text = [character]
            continue
        if style == current_style:
            current_text.append(character)
            continue
        runs.append(RenderTextRun(text="".join(current_text), style=current_style))
        current_style = style
        current_text = [character]
    if current_style is not None:
        runs.append(RenderTextRun(text="".join(current_text), style=current_style))

    base_text_style = {
        key: value for key, value in base_style.items() if key not in TEXT_RUN_LAYOUT_STYLE_KEYS
    }
    if len(runs) == 1 and runs[0].style == base_text_style:
        return ()
    if all(run.style == base_text_style for run in runs):
        return ()
    return tuple(runs)


def _text_run_style(payload: dict[str, object], override_id: str) -> dict[str, str]:
    source = payload.get("style")
    text_style = dict(source) if isinstance(source, dict) else {}
    style_override_table = payload.get("styleOverrideTable")
    if (
        override_id not in {"", "0"}
        and isinstance(style_override_table, dict)
        and isinstance(style_override_table.get(override_id), dict)
    ):
        text_style.update(style_override_table[override_id])

    style: dict[str, str] = {}
    _copy_text_style(text_style, style)
    for key in TEXT_RUN_LAYOUT_STYLE_KEYS:
        style.pop(key, None)

    color = _paint_color(
        _text_override_fills_source(payload, override_id, payload.get("fills")),
        node_opacity=_float(payload.get("opacity"), default=1.0),
    )
    if color:
        style["color"] = color
    return style


def _copy_text_style(source: dict[str, object], target: dict[str, str]) -> None:
    font_family = source.get("fontFamily")
    if font_family:
        target["font-family"] = _font_family_stack(str(font_family))
    font_size = _css_px(source.get("fontSize"))
    if font_size:
        target["font-size"] = font_size
    font_weight = source.get("fontWeight")
    if font_weight:
        target["font-weight"] = str(font_weight)
    italic = source.get("italic")
    if italic is True:
        target["font-style"] = "italic"
    text_decoration = str(source.get("textDecoration") or "").upper()
    if text_decoration == "UNDERLINE":
        target["text-decoration"] = "underline"
    elif text_decoration == "STRIKETHROUGH":
        target["text-decoration"] = "line-through"
    line_height = _css_px(
        source.get("lineHeightPx") or source.get("lineHeight") or source.get("line_height")
    )
    if line_height:
        target["line-height"] = line_height
    letter_spacing = _css_px(source.get("letterSpacing"))
    if letter_spacing:
        target["letter-spacing"] = letter_spacing
    text_align = source.get("textAlignHorizontal")
    if text_align:
        target["text-align"] = str(text_align).lower()
    text_align_vertical = str(source.get("textAlignVertical") or "").upper()
    if text_align_vertical in {"CENTER", "BOTTOM"}:
        target["display"] = "flex"
        target["flex-direction"] = "column"
        target["justify-content"] = "center" if text_align_vertical == "CENTER" else "flex-end"


def _font_family_stack(font_family: str) -> str:
    families = [
        _quote_font_family(family) for family in str(font_family).split(",") if str(family).strip()
    ]
    if not families:
        return ""

    normalized = {family.strip().strip("\"'").lower() for family in families}
    has_generic = bool(
        normalized
        & {
            "serif",
            "sans-serif",
            "monospace",
            "cursive",
            "fantasy",
            "system-ui",
        }
    )
    if not has_generic:
        first_family = next(iter(normalized), "")
        if any(token in first_family for token in ("mono", "code", "consol")):
            families.extend(["'Cascadia Mono'", "Consolas", "monospace"])
        elif any(token in first_family for token in ("serif", "slab", "georgia", "times")):
            families.extend(["Georgia", "serif"])
        else:
            families.extend(["'Segoe UI'", "Arial", "sans-serif"])

    deduped: list[str] = []
    seen: set[str] = set()
    for family in families:
        key = family.strip().strip("\"'").lower()
        if key and key not in seen:
            deduped.append(family)
            seen.add(key)
    return ",".join(deduped)


def _quote_font_family(font_family: str) -> str:
    normalized = font_family.strip().strip("\"'")
    if not normalized:
        return ""
    if normalized.lower() in {
        "serif",
        "sans-serif",
        "monospace",
        "cursive",
        "fantasy",
        "system-ui",
    }:
        return normalized.lower()
    return "'" + normalized.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _paint_color(fills: object, *, node_opacity: float = 1.0) -> str:
    if not isinstance(fills, list):
        return ""
    composited: tuple[float, float, float, float] | None = None
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        if fill.get("visible") is False:
            continue
        paint = _fill_rgba(fill)
        if paint is None:
            continue
        r, g, b, a = paint
        a *= _float(fill.get("opacity"), default=1.0) * node_opacity
        composited = _alpha_composite(composited, (r, g, b, a))
    if composited is None:
        return ""
    return _rgba_tuple_color(composited)


def _fill_rgba(fill: dict[str, object]) -> tuple[float, float, float, float] | None:
    fill_type = str(fill.get("type", "")).upper()
    if fill_type == "SOLID":
        color = fill.get("color")
        return _color_rgba(color) if isinstance(color, dict) else None
    if fill_type.startswith("GRADIENT_"):
        stops = fill.get("gradientStops")
        if not isinstance(stops, list):
            return None
        colors: list[tuple[float, float, float, float]] = []
        for stop in stops:
            if not isinstance(stop, dict):
                continue
            stop_color = stop.get("color")
            if isinstance(stop_color, dict):
                colors.append(_color_rgba(stop_color))
        if not colors:
            return None
        count = float(len(colors))
        return (
            sum(color[0] for color in colors) / count,
            sum(color[1] for color in colors) / count,
            sum(color[2] for color in colors) / count,
            sum(color[3] for color in colors) / count,
        )
    return None


def _color_rgba(color: dict[str, object]) -> tuple[float, float, float, float]:
    return (
        _float(color.get("r")),
        _float(color.get("g")),
        _float(color.get("b")),
        _float(color.get("a"), default=1.0),
    )


def _alpha_composite(
    base: tuple[float, float, float, float] | None,
    overlay: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if base is None:
        return overlay
    br, bg, bb, ba = base
    or_, og, ob, oa = overlay
    out_a = oa + ba * (1 - oa)
    if out_a <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        ((or_ * oa) + (br * ba * (1 - oa))) / out_a,
        ((og * oa) + (bg * ba * (1 - oa))) / out_a,
        ((ob * oa) + (bb * ba * (1 - oa))) / out_a,
        out_a,
    )


def _rgba_tuple_color(color: tuple[float, float, float, float]) -> str:
    r, g, b, a = color
    return _rgba_components_color(r, g, b, a)


def _rgba_color(color: dict[str, object], opacity: float) -> str:
    r = _float(color.get("r"))
    g = _float(color.get("g"))
    b = _float(color.get("b"))
    a = _float(color.get("a"), default=1.0) * opacity
    return _rgba_components_color(r, g, b, a)


def visible_drop_shadow_filter(payload: dict[str, object]) -> str:
    effects = payload.get("effects")
    if not isinstance(effects, list):
        return ""
    filters: list[str] = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        if effect.get("visible") is False:
            continue
        if str(effect.get("type", "")).upper() != "DROP_SHADOW":
            continue
        offset = effect.get("offset")
        color = effect.get("color")
        if not isinstance(offset, dict) or not isinstance(color, dict):
            continue
        x = _float(offset.get("x"))
        y = _float(offset.get("y"))
        radius = _float(effect.get("radius"))
        shadow_color = _rgba_color(color, 1.0)
        filters.append(
            f"drop-shadow({_format_px(x)} {_format_px(y)} {_format_px(radius)} {shadow_color})"
        )
    return " ".join(filters)


def _rgba_components_color(r: float, g: float, b: float, a: float) -> str:
    css_r = round(r * 255)
    css_g = round(g * 255)
    css_b = round(b * 255)
    css_a = max(0.0, min(1.0, a))
    if css_a >= 0.999:
        return f"rgb({css_r}, {css_g}, {css_b})"
    return f"rgba({css_r}, {css_g}, {css_b}, {css_a:.3g})"


def _css_px(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        return stripped if any(char.isalpha() for char in stripped) else f"{stripped}px"
    number = _float_or_none(value)
    return f"{number:g}px" if number is not None else ""


def _format_px(value: float) -> str:
    return f"{value:g}px"


def _float(value: object, default: float | None = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        if default is None:
            raise
        return default


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
