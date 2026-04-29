from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path, PurePosixPath
from shutil import copy2
from typing import Any
from urllib.parse import urlparse

import html
import json
import re
import unicodedata


DECORATIVE_PURPOSES = {"background", "decorative", "foreground", "mask"}
HEADING_ROLES = {"display", "eyebrow", "headline", "heading", "hero-title", "title"}
TEXT_VALUE_KEYS = ("value", "text", "characters", "content", "raw_value")
GENERIC_CONTAINER_ROLES = {"", "container", "group", "frame", "node", "wrapper", "div"}
SECTION_COORDINATE_SPACE = "section"
PARENT_COORDINATE_SPACE = "parent"
PUNCTUATION_ONLY_LINE_RE = re.compile(r"^[-\u2010-\u2015/:|+*·•]+$")


@dataclass(slots=True)
class GenerationArtifacts:
    output_dir: Path
    written_files: tuple[Path, ...]
    page_data: dict[str, Any]


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text_file(path: Path, content: str) -> Path:
    ensure_directory(path.parent)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def write_json_file(path: Path, data: Any) -> Path:
    ensure_directory(path.parent)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def copy_tree(source: Path, destination: Path) -> list[Path]:
    written: list[Path] = []
    for item in sorted(source.rglob("*")):
        if item.is_dir():
            continue
        relative_path = item.relative_to(source)
        target = destination / relative_path
        ensure_directory(target.parent)
        target.write_text(item.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        written.append(target)
    return written


def copy_assets(page_data: dict[str, Any], output_dir: Path, *, mode: str) -> list[Path]:
    written: list[Path] = []
    for asset in coerce_list(page_data.get("assets")):
        asset_data = as_mapping(asset)
        source_path = ensure_text(coalesce(asset_data, "source_local_path", "sourceLocalPath")).strip()
        relative_path = ensure_text(coalesce(asset_data, "local_path", "localPath")).strip()
        if not source_path or not relative_path:
            continue
        source = Path(source_path)
        if not source.exists() or source.is_dir():
            continue
        destination = output_dir / relative_path if mode == "static" else output_dir / "static" / relative_path
        ensure_directory(destination.parent)
        copy2(source, destination)
        written.append(destination)
    return written


def locate_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "SPEC.md").exists():
            return parent
    raise FileNotFoundError("Unable to locate repository root from generators package.")


def locate_templates_root() -> Path:
    templates_root = locate_repo_root() / "templates"
    if not templates_root.exists():
        raise FileNotFoundError("Templates directory is missing from the repository root.")
    return templates_root


def read_template_text(*relative_parts: str) -> str:
    return locate_templates_root().joinpath(*relative_parts).read_text(encoding="utf-8")


def to_primitive(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return to_primitive(value.model_dump(mode="python"))
    if is_dataclass(value):
        return to_primitive(asdict(value))
    if hasattr(value, "dict") and callable(value.dict):
        return to_primitive(value.dict())
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_primitive(item) for item in value]
    if hasattr(value, "__dict__") and not isinstance(value, (str, bytes, int, float, bool)):
        public_attrs = {
            key: item for key, item in vars(value).items() if not key.startswith("_")
        }
        return to_primitive(public_attrs)
    return value


def as_mapping(value: Any) -> dict[str, Any]:
    primitive = to_primitive(value)
    if isinstance(primitive, dict):
        return primitive
    return {}


def coalesce(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def coerce_list(value: Any) -> list[Any]:
    primitive = to_primitive(value)
    if primitive is None:
        return []
    if isinstance(primitive, list):
        return primitive
    if isinstance(primitive, tuple):
        return list(primitive)
    if isinstance(primitive, dict):
        return list(primitive.values())
    return [primitive]


def ensure_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def slugify(value: Any, default: str = "item") -> str:
    text = ensure_text(value, default=default).strip()
    if not text:
        return default
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return normalized or default


def css_escape_identifier(value: Any, default: str = "item") -> str:
    identifier = slugify(value, default=default)
    if identifier[0].isdigit():
        return f"id-{identifier}"
    return identifier


def dom_identifier(value: Any, default: str = "item") -> str:
    return css_escape_identifier(value, default=default)


def normalize_bounds(value: Any) -> dict[str, float]:
    data = as_mapping(value)
    if not data:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    if "absoluteBoundingBox" in data:
        return normalize_bounds(data["absoluteBoundingBox"])
    return {
        "x": float(coalesce(data, "x", "left", default=0) or 0),
        "y": float(coalesce(data, "y", "top", default=0) or 0),
        "width": float(coalesce(data, "width", "w", default=0) or 0),
        "height": float(coalesce(data, "height", "h", default=0) or 0),
    }


def sort_by_bounds(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            float(as_mapping(item.get("bounds")).get("y", 0.0)),
            float(as_mapping(item.get("bounds")).get("x", 0.0)),
            ensure_text(item.get("id")),
        ),
    )


def html_with_line_breaks(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u2028", "\n").replace("\u2029", "\n")
    return html.escape(normalized).replace("\n", "<br>\n")


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = ensure_text(value).strip()
        if not text or text in seen:
            continue
        ordered.append(text)
        seen.add(text)
    return ordered


def class_name(*parts: str) -> str:
    names = [css_escape_identifier(part) for part in parts if ensure_text(part).strip()]
    return "-".join(dedupe_strings(names))


def flatten_token_map(prefix: str, value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    primitive = to_primitive(value)
    if isinstance(primitive, dict):
        scalar_keys = {"value", "hex", "rgba", "rgb"}
        if scalar_keys.intersection(primitive.keys()):
            items.append((prefix, primitive))
            return items
        for key, item in primitive.items():
            nested_prefix = f"{prefix}-{slugify(key, 'token')}" if prefix else slugify(key, "token")
            items.extend(flatten_token_map(nested_prefix, item))
        return items
    items.append((prefix, primitive))
    return items


def extract_scalar_token(value: Any) -> str | None:
    primitive = to_primitive(value)
    if primitive is None:
        return None
    if isinstance(primitive, list):
        for item in primitive:
            item_data = as_mapping(item)
            if item_data and item_data.get("visible", True) is False:
                continue
            extracted = extract_scalar_token(item)
            if extracted:
                return extracted
        return None
    if isinstance(primitive, str):
        return primitive
    if isinstance(primitive, (int, float)):
        return str(primitive)
    if isinstance(primitive, dict):
        if "value" in primitive and primitive["value"] not in (None, ""):
            return extract_scalar_token(primitive["value"])
        if "hex" in primitive:
            return ensure_text(primitive["hex"])
        if "rgba" in primitive:
            rgba = as_mapping(primitive["rgba"])
            return rgba_to_css(rgba)
        if "rgb" in primitive:
            rgb = as_mapping(primitive["rgb"])
            return rgba_to_css({**rgb, "a": 1})
        if "color" in primitive:
            return extract_scalar_token(primitive["color"])
        color = rgba_to_css(primitive)
        if color:
            return color
    return None


def rgba_to_css(value: dict[str, Any]) -> str | None:
    if not value:
        return None
    has_rgb = any(channel in value for channel in ("r", "g", "b"))
    if not has_rgb:
        return None
    red = clamp_channel(value.get("r", 0))
    green = clamp_channel(value.get("g", 0))
    blue = clamp_channel(value.get("b", 0))
    alpha = value.get("a", value.get("alpha", 1))
    try:
        alpha_value = float(alpha)
    except (TypeError, ValueError):
        alpha_value = 1.0
    alpha_value = max(0.0, min(alpha_value, 1.0))
    if alpha_value == 1.0:
        return f"rgb({red} {green} {blue})"
    return f"rgb({red} {green} {blue} / {alpha_value:.3f})"


def clamp_channel(value: Any) -> int:
    try:
        channel = float(value)
    except (TypeError, ValueError):
        return 0
    if channel <= 1:
        channel *= 255
    return max(0, min(int(round(channel)), 255))


def normalize_path_fragment(value: str) -> str:
    return ensure_text(value).replace("\\", "/").strip()


def asset_relative_path(candidate: str, fallback_name: str, fallback_format: str) -> str:
    normalized = normalize_path_fragment(candidate)
    if not normalized:
        extension = fallback_format.lstrip(".") or "png"
        return f"images/{slugify(fallback_name, 'asset')}.{extension}"
    parsed = urlparse(normalized)
    if parsed.scheme and parsed.netloc:
        filename = PurePosixPath(parsed.path).name or f"{slugify(fallback_name, 'asset')}.{fallback_format}"
        return f"images/{filename}"
    parts = [part for part in PurePosixPath(normalized).parts if part not in (".", "")]
    if "images" in parts:
        image_index = parts.index("images")
        return "/".join(parts[image_index:])
    if "static" in parts and len(parts) > parts.index("static") + 1 and parts[parts.index("static") + 1] == "images":
        image_index = parts.index("images")
        return "/".join(parts[image_index:])
    return f"images/{PurePosixPath(normalized).name}"


def normalize_public_path(relative_path: str, mode: str) -> str:
    path = normalize_path_fragment(relative_path)
    return path.lstrip("/")


def sanitize_attributes(value: Any) -> dict[str, str]:
    data = as_mapping(value)
    attrs: dict[str, str] = {}
    for key, item in data.items():
        text = ensure_text(item).strip()
        if not text:
            continue
        attribute_name = ensure_text(key).replace("_", "-").strip()
        attrs[attribute_name] = text
    return attrs


def append_attribute(attrs: dict[str, str], key: str, value: Any) -> None:
    text = ensure_text(value).strip()
    if text:
        attrs[key] = text


def normalize_layer_name(value: Any) -> str:
    return slugify(value, default="")


def layer_tokens(value: Any) -> tuple[str, ...]:
    normalized = normalize_layer_name(value)
    if not normalized:
        return ()
    return tuple(token for token in normalized.split("-") if token)


def name_has_prefix(value: Any, prefixes: tuple[str, ...]) -> bool:
    normalized = normalize_layer_name(value)
    return any(normalized == prefix or normalized.startswith(f"{prefix}-") for prefix in prefixes)


def name_has_token(value: Any, tokens: tuple[str, ...]) -> bool:
    node_tokens = set(layer_tokens(value))
    return any(token in node_tokens for token in tokens)


def infer_container_role(name: Any, fallback: str = "container") -> str:
    normalized_fallback = ensure_text(fallback).strip().lower()
    if normalized_fallback and normalized_fallback not in GENERIC_CONTAINER_ROLES:
        return normalized_fallback
    if name_has_prefix(name, ("href-card", "link-card")):
        return "link-card"
    if name_has_prefix(name, ("href-grid", "link-grid")):
        return "link-grid"
    if name_has_prefix(name, ("accordion-item",)):
        return "accordion-item"
    if name_has_prefix(name, ("accordion-trigger",)):
        return "accordion-trigger"
    if name_has_prefix(name, ("accordion-panel",)):
        return "accordion-panel"
    if name_has_prefix(name, ("accordion",)):
        return "accordion"
    if name_has_prefix(name, ("carousel-stage", "carousel-main")):
        return "carousel-stage"
    if name_has_prefix(name, ("carousel-thumbs", "carousel-nav", "carousel-track")):
        return "carousel-nav"
    if name_has_prefix(name, ("carousel-slide",)):
        return "carousel-slide"
    if name_has_prefix(name, ("carousel-thumb",)):
        return "carousel-thumb"
    if name_has_prefix(name, ("carousel",)):
        return "carousel"
    if name_has_prefix(name, ("formulaire", "form")):
        return "form"
    if name_has_prefix(name, ("button", "btn")):
        return "button"
    if name_has_prefix(name, ("input", "champ", "zone", "field")):
        return "field"
    if name_has_prefix(name, ("card-v", "card-h", "card", "article")):
        return "card"
    if name_has_prefix(name, ("nav",)):
        return "nav"
    if name_has_prefix(name, ("footer",)):
        return "footer"
    if name_has_prefix(name, ("header",)):
        return "header"
    if name_has_prefix(name, ("hero", "section")):
        return "section"
    return normalized_fallback or "container"


def semantic_section_tag(role: str, index: int) -> str:
    normalized_role = role.lower()
    if normalized_role in {"header", "hero", "masthead"}:
        return "header" if index == 0 else "section"
    if normalized_role in {"nav", "navigation"}:
        return "nav"
    if normalized_role == "footer":
        return "footer"
    if normalized_role == "article":
        return "article"
    return "section"


def semantic_container_tag(kind: str, role: str) -> str:
    normalized_role = role.lower()
    normalized_kind = kind.lower()
    if normalized_role in {"button", "accordion-trigger", "carousel-thumb"}:
        return "button"
    if normalized_role == "link-card":
        return "article"
    if normalized_role == "form":
        return "form"
    if normalized_role == "nav":
        return "nav"
    if normalized_role == "header":
        return "header"
    if normalized_role == "section":
        return "section"
    if normalized_role == "card":
        return "article"
    if normalized_role == "list":
        return "ul"
    if normalized_role == "list-item":
        return "li"
    if normalized_role == "footer":
        return "footer"
    if normalized_kind == "group":
        return "div"
    return "div"


def guess_text_tag(role: str, section_index: int, text_index: int) -> str:
    normalized_role = role.lower()
    if normalized_role == "label":
        return "label"
    if normalized_role == "link":
        return "a"
    if normalized_role == "button":
        return "a"
    if normalized_role == "quote":
        return "blockquote"
    if normalized_role == "list-item":
        return "li"
    if normalized_role in HEADING_ROLES:
        return "h1" if section_index == 0 and text_index == 0 else "h2"
    return "p"


def accordion_mode(name: Any) -> str:
    if name_has_token(name, ("single", "exclusive")):
        return "single"
    return "multi"


def accordion_item_starts_open(name: Any) -> bool:
    if name_has_token(name, ("closed", "collapse", "collapsed")):
        return False
    if name_has_token(name, ("open", "expanded", "active")):
        return True
    return True


def carousel_item_key(name: Any, prefixes: tuple[str, ...]) -> str:
    tokens = list(layer_tokens(name))
    for prefix in prefixes:
        prefix_tokens = list(layer_tokens(prefix))
        if tokens[: len(prefix_tokens)] != prefix_tokens:
            continue
        suffix_tokens = [
            token
            for token in tokens[len(prefix_tokens) :]
            if token not in {"active", "selected", "default", "current", "open", "closed"}
        ]
        return "-".join(suffix_tokens)
    return normalize_layer_name(name)


def carousel_item_starts_active(name: Any) -> bool:
    return name_has_token(name, ("active", "selected", "default", "current"))


def looks_like_href(value: Any) -> bool:
    text = ensure_text(value).strip().strip("\"'")
    if not text or any(character.isspace() for character in text):
        return False
    if text.startswith(("/", "#", "mailto:", "tel:")):
        return True
    parsed = urlparse(text)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme in {"mailto", "tel"}))


def style_map_to_css(value: Any) -> str:
    data = as_mapping(value)
    if not data:
        return ""
    declarations: list[str] = []
    font_family = coalesce(data, "fontFamily", "font_family")
    if font_family:
        declarations.append(f'font-family: "{ensure_text(font_family)}", sans-serif;')
    font_size = coalesce(data, "fontSize", "font_size")
    if font_size:
        declarations.append(f"font-size: {ensure_unit(font_size)};")
    font_weight = coalesce(data, "fontWeight", "font_weight")
    if font_weight:
        declarations.append(f"font-weight: {ensure_text(font_weight)};")
    font_style = coalesce(data, "fontStyle", "font_style")
    normalized_font_style = normalize_font_style(font_style, italic=data.get("italic"))
    if normalized_font_style:
        declarations.append(f"font-style: {normalized_font_style};")
    line_height = coalesce(data, "lineHeight", "line_height")
    if line_height:
        declarations.append(f"line-height: {ensure_unit(line_height)};")
    letter_spacing = coalesce(data, "letterSpacing", "letter_spacing")
    if letter_spacing not in (None, ""):
        declarations.append(f"letter-spacing: {ensure_unit(letter_spacing)};")
    text_align = normalize_text_align(coalesce(data, "textAlignHorizontal", "text_align_horizontal"))
    if text_align:
        declarations.append(f"text-align: {text_align};")
    text_decoration = coalesce(data, "textDecoration", "text_decoration")
    if text_decoration:
        declarations.append(f"text-decoration: {ensure_text(text_decoration)};")
    text_transform = coalesce(data, "textTransform", "text_transform")
    if text_transform:
        declarations.append(f"text-transform: {ensure_text(text_transform)};")
    color = extract_scalar_token(coalesce(data, "color", "fill", "fills"))
    if color:
        declarations.append(f"color: {color};")
    background = extract_scalar_token(coalesce(data, "background", "backgroundColor"))
    if background:
        declarations.append(f"background: {background};")
    border = coalesce(data, "border")
    if border:
        declarations.append(f"border: {ensure_text(border)};")
    border_radius = coalesce(data, "borderRadius", "border_radius")
    if border_radius not in (None, ""):
        declarations.append(f"border-radius: {ensure_unit(border_radius)};")
    box_shadow = coalesce(data, "boxShadow", "box_shadow")
    if box_shadow:
        declarations.append(f"box-shadow: {ensure_text(box_shadow)};")
    opacity = coalesce(data, "opacity")
    if opacity not in (None, ""):
        declarations.append(f"opacity: {ensure_text(opacity)};")
    return " ".join(declarations)


def normalize_font_style(value: Any, *, italic: Any = None) -> str:
    text = ensure_text(value).strip().lower()
    if "italic" in text:
        return "italic"
    if italic is True:
        return "italic"
    if text:
        return "normal"
    return ""


def normalize_text_align(value: Any) -> str:
    text = ensure_text(value).strip().lower()
    mapping = {
        "left": "left",
        "center": "center",
        "right": "right",
        "justified": "justify",
    }
    return mapping.get(text, "")


def ensure_unit(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value}px"
    text = ensure_text(value)
    if not text:
        return text
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return f"{text}px"
    return text


class CanonicalModelBuilder:
    """Construit un modèle canonique indépendant de la sortie finale.

    Cette étape centralise la normalisation des nœuds et l'interprétation des
    conventions de naming (`accordion-*`, `href-card-*`, `carousel-*`, etc.)
    pour éviter que chaque générateur réimplémente ses propres heuristiques.
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self._warnings: list[str] = []
        self._text_index: dict[str, dict[str, Any]] = {}
        self._asset_index: dict[str, dict[str, Any]] = {}
        self._global_texts: dict[str, Any] = {}
        self._global_assets: dict[str, Any] = {}
        self._class_registry: dict[tuple[str, str], str] = {}
        self._used_class_names: set[str] = set()

    def build(self, model: Any) -> dict[str, Any]:
        source = as_mapping(model)
        self._warnings = []
        self._text_index = {}
        self._asset_index = {}
        self._class_registry = {}
        self._used_class_names = set()
        self._global_texts = self._index_by_identifier(source.get("texts"))
        self._global_assets = self._index_by_identifier(source.get("assets"))
        source_sections = [as_mapping(section) for section in coerce_list(source.get("sections"))]
        source_sections = sort_by_bounds(source_sections)
        sections = [
            self._normalize_section(section, index)
            for index, section in enumerate(source_sections)
        ]
        for key, value in self._global_texts.items():
            if key not in self._text_index:
                self._normalize_text(value, section_id="", section_index=0, text_index=0)
        for key, value in self._global_assets.items():
            if key not in self._asset_index:
                self._normalize_asset(value, section_id="", asset_index=0)
        page = self._normalize_page(source.get("page"))
        warnings = dedupe_strings(coerce_list(source.get("warnings")) + self._warnings)
        return {
            "page": page,
            "sections": sections,
            "texts": self._text_index,
            "assets": list(self._asset_index.values()),
            "tokens": self._normalize_tokens(source.get("tokens")),
            "warnings": warnings,
        }

    def _index_by_identifier(self, value: Any) -> dict[str, Any]:
        indexed: dict[str, Any] = {}
        primitive = to_primitive(value)
        if isinstance(primitive, dict):
            for key, item in primitive.items():
                item_data = as_mapping(item)
                item_id = ensure_text(
                    coalesce(item_data, "id", "nodeId", "node_id", default=key),
                    default=ensure_text(key),
                )
                indexed[item_id] = item_data
            return indexed
        for item in coerce_list(primitive):
            item_data = as_mapping(item)
            item_id = ensure_text(coalesce(item_data, "id", "nodeId", "node_id"))
            if item_id:
                indexed[item_id] = item_data
        return indexed

    def _normalize_page(self, value: Any) -> dict[str, Any]:
        data = as_mapping(value)
        page_name = ensure_text(coalesce(data, "name", "title", default="Page"), default="Page")
        width = float(coalesce(data, "width", default=0) or 0)
        height = float(coalesce(data, "height", default=0) or 0)
        return {
            "id": ensure_text(coalesce(data, "id", "nodeId", "node_id", default="page"), default="page"),
            "name": page_name,
            "title": ensure_text(coalesce(data, "title", "name", default=page_name), default=page_name),
            "slug": slugify(page_name, "page"),
            "width": width,
            "height": height,
            "meta": as_mapping(coalesce(data, "meta", "source_meta", default={})),
        }

    def _normalize_tokens(self, value: Any) -> dict[str, Any]:
        data = as_mapping(value)
        return {
            "colors": as_mapping(data.get("colors")),
            "spacing": as_mapping(data.get("spacing")),
            "typography": as_mapping(data.get("typography")),
            "shadows": as_mapping(data.get("shadows")),
            "radii": as_mapping(data.get("radii", data.get("radius"))),
        }

    def _normalize_section(self, value: Any, index: int) -> dict[str, Any]:
        data = as_mapping(value)
        section_id = ensure_text(
            coalesce(data, "id", "nodeId", "node_id", default=f"section-{index + 1}"),
            default=f"section-{index + 1}",
        )
        section_name = ensure_text(
            coalesce(data, "name", "title", default=f"Section {index + 1}"),
            default=f"Section {index + 1}",
        )
        section_role = ensure_text(coalesce(data, "role", default="section"), default="section").lower()
        section_tag = ensure_text(
            coalesce(data, "tag", default=semantic_section_tag(section_role, index)),
            default="section",
        )
        section_texts = [
            self._normalize_text(
                item,
                section_id=section_id,
                section_index=index,
                text_index=text_index,
            )
            for text_index, item in enumerate(self._resolve_items(data.get("texts"), self._global_texts))
        ]
        section_assets = [
            self._normalize_asset(item, section_id=section_id, asset_index=asset_index)
            for asset_index, item in enumerate(self._resolve_items(data.get("assets"), self._global_assets))
        ]
        decorative_assets = [
            self._normalize_asset(
                item,
                section_id=section_id,
                asset_index=asset_index,
                default_purpose="decorative",
            )
            for asset_index, item in enumerate(
                self._resolve_items(data.get("decorative_assets"), self._global_assets)
            )
        ]
        children = [
            self._normalize_node(
                item,
                section_id=section_id,
                section_index=index,
                node_index=node_index,
                parent_absolute_offset=(0.0, 0.0),
                source_space=SECTION_COORDINATE_SPACE,
            )
            for node_index, item in enumerate(coerce_list(data.get("children")))
        ]
        children = [child for child in children if child]
        if not children:
            children = sort_by_bounds(
                [
                    {
                        "id": f"{text['id']}-node",
                        "dom_id": dom_identifier(f"{text['id']}-node", default=f"{section_id}-text-node-{index + 1}"),
                        "kind": "text",
                        "tag": text["tag"],
                        "role": text["role"],
                        "class_name": class_name("node", text["id"]),
                        "text": text,
                        "bounds": text["bounds"],
                        "children": [],
                        "attributes": {},
                    }
                    for text in section_texts
                ]
                + [
                    {
                        "id": f"{asset['id']}-node",
                        "dom_id": dom_identifier(
                            f"{asset['id']}-node",
                            default=f"{section_id}-asset-node-{index + 1}",
                        ),
                        "kind": "asset",
                        "tag": "figure",
                        "role": asset["purpose"],
                        "class_name": class_name("node", asset["id"]),
                        "asset": asset,
                        "bounds": asset["bounds"],
                        "children": [],
                        "attributes": {},
                    }
                    for asset in section_assets + decorative_assets
                ]
            )
        return {
            "id": section_id,
            "name": section_name,
            "role": section_role,
            "tag": section_tag,
            "anchor": slugify(coalesce(data, "anchor", "slug", default=section_name), default=section_id),
            "class_name": self._unique_class_name("section", section_name, section_id),
            "bounds": normalize_bounds(coalesce(data, "bounds", "absoluteBoundingBox", default={})),
            "metadata": as_mapping(data.get("metadata")),
            "texts": sort_by_bounds(section_texts),
            "assets": sort_by_bounds(section_assets),
            "decorative_assets": sort_by_bounds(decorative_assets),
            "children": children,
        }

    def _normalize_node(
        self,
        value: Any,
        *,
        section_id: str,
        section_index: int,
        node_index: int,
        parent_absolute_offset: tuple[float, float] = (0.0, 0.0),
        source_space: str = PARENT_COORDINATE_SPACE,
    ) -> dict[str, Any]:
        if isinstance(value, str):
            if value in self._global_texts:
                text = self._text_for_context(
                    self._global_texts[value],
                    section_id=section_id,
                    section_index=section_index,
                    text_index=node_index,
                    parent_absolute_offset=parent_absolute_offset,
                    source_space=source_space,
                )
                return self._wrap_text_node(text, node_id=value)
            if value in self._global_assets:
                asset = self._asset_for_context(
                    self._global_assets[value],
                    section_id=section_id,
                    asset_index=node_index,
                    parent_absolute_offset=parent_absolute_offset,
                    source_space=source_space,
                )
                return self._wrap_asset_node(asset, node_id=value)
            return {}
        data = as_mapping(value)
        node_id = ensure_text(
            coalesce(data, "id", "nodeId", "node_id", default=f"{section_id}-node-{node_index + 1}"),
            default=f"{section_id}-node-{node_index + 1}",
        )
        node_name = ensure_text(coalesce(data, "name", default=node_id), default=node_id)
        node_source_space = ensure_text(
            coalesce(data, "coordinateSpace", "coordinate_space", default=source_space),
            default=source_space,
        ).lower()
        kind = ensure_text(
            coalesce(data, "kind", "type", "node_type", default=self._guess_node_kind(data)),
            default="container",
        ).lower()
        role = infer_container_role(
            node_name,
            fallback=ensure_text(coalesce(data, "role", default=kind), default=kind).lower(),
        )
        if kind == "text":
            text_value = (
                data
                if isinstance(value, dict)
                and any(key in data for key in ("bounds", "render_bounds", "renderBounds", "coordinate_space"))
                else coalesce(data, "text", default=data)
            )
            text = self._text_for_context(
                text_value,
                section_id=section_id,
                section_index=section_index,
                text_index=node_index,
                parent_absolute_offset=parent_absolute_offset,
                source_space=node_source_space,
            )
            return self._wrap_text_node(text, node_id=node_id)
        if kind == "asset":
            asset_value = (
                data
                if isinstance(value, dict)
                and any(key in data for key in ("bounds", "coordinate_space"))
                else coalesce(data, "asset", default=data)
            )
            asset = self._asset_for_context(
                asset_value,
                section_id=section_id,
                asset_index=node_index,
                parent_absolute_offset=parent_absolute_offset,
                source_space=node_source_space,
            )
            return self._wrap_asset_node(asset, node_id=node_id)
        attrs = sanitize_attributes(data.get("attributes"))
        append_attribute(attrs, "aria-label", coalesce(data, "ariaLabel", "aria_label"))
        append_attribute(attrs, "href", coalesce(data, "href", "url"))
        bounds, absolute_offset = self._normalize_container_bounds(
            data,
            parent_absolute_offset=parent_absolute_offset,
            source_space=node_source_space,
        )
        child_source_space = ensure_text(
            coalesce(
                data,
                "childrenCoordinateSpace",
                "children_coordinate_space",
                default=PARENT_COORDINATE_SPACE,
            ),
            default=PARENT_COORDINATE_SPACE,
        ).lower()
        children = [
            self._normalize_node(
                child,
                section_id=section_id,
                section_index=section_index,
                node_index=child_index,
                parent_absolute_offset=absolute_offset,
                source_space=child_source_space,
            )
            for child_index, child in enumerate(coerce_list(data.get("children")))
        ]
        children = [child for child in children if child]
        if not children:
            children = sort_by_bounds(
                [
                    self._normalize_node(
                        {"kind": "text", "text": item},
                        section_id=section_id,
                        section_index=section_index,
                        node_index=child_index,
                        parent_absolute_offset=absolute_offset,
                        source_space=child_source_space,
                    )
                    for child_index, item in enumerate(
                        self._resolve_items(data.get("texts"), self._global_texts)
                    )
                ]
                + [
                    self._normalize_node(
                        {"kind": "asset", "asset": item},
                        section_id=section_id,
                        section_index=section_index,
                        node_index=child_index + 1000,
                        parent_absolute_offset=absolute_offset,
                        source_space=child_source_space,
                    )
                    for child_index, item in enumerate(
                        self._resolve_items(data.get("assets"), self._global_assets)
                    )
                ]
            )
        children = self._apply_container_naming_conventions(
            role=role,
            node_name=node_name,
            bounds=bounds,
            children=children,
        )
        tag = ensure_text(coalesce(data, "tag", default=semantic_container_tag(kind, role)), default="div")
        if tag == "button" and "type" not in attrs:
            attrs["type"] = "button"
        tag, attrs, children = self._apply_component_container_conventions(
            role=role,
            node_name=node_name,
            tag=tag,
            attrs=attrs,
            children=children,
        )
        return {
            "id": node_id,
            "name": node_name,
            "dom_id": dom_identifier(node_id, default=f"{section_id}-node-{node_index + 1}"),
            "kind": "container",
            "tag": tag,
            "role": role,
            "class_name": self._unique_class_name(
                "node",
                node_name,
                node_id,
            ),
            "bounds": bounds,
            "attributes": attrs,
            "children": children,
        }

    def _apply_container_naming_conventions(
        self,
        *,
        role: str,
        node_name: str,
        bounds: dict[str, float],
        children: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized_role = ensure_text(role).strip().lower()
        if normalized_role not in {"button", "field", "accordion-trigger", "carousel-thumb"}:
            return children
        effective_role = "button" if normalized_role in {"accordion-trigger", "carousel-thumb"} else normalized_role

        normalized_children: list[dict[str, Any]] = []
        for child in children:
            if child.get("kind") != "asset":
                normalized_children.append(child)
                continue

            asset = as_mapping(child.get("asset"))
            if not asset:
                normalized_children.append(child)
                continue
            if not self._should_promote_container_asset_to_background(
                container_role=effective_role,
                asset=asset,
                container_bounds=bounds,
            ):
                normalized_children.append(child)
                continue

            normalized_children.append(
                {
                    **child,
                    "role": "background",
                    "asset": {
                        **asset,
                        "purpose": "background",
                        "alt": "",
                        "aria_hidden": True,
                    },
                }
            )
        return normalized_children

    def _apply_component_container_conventions(
        self,
        *,
        role: str,
        node_name: str,
        tag: str,
        attrs: dict[str, str],
        children: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        """Applique les conventions métier dans un ordre stable.

        L'ordre reste volontairement explicite pour garder des effets
        prévisibles quand plusieurs conventions peuvent s'empiler.
        """

        conventions = (
            self._apply_link_card_container_conventions,
            self._apply_card_container_conventions,
            self._apply_accordion_container_conventions,
            self._apply_carousel_container_conventions,
        )
        for convention in conventions:
            tag, attrs, children = convention(
                role=role,
                node_name=node_name,
                tag=tag,
                attrs=attrs,
                children=children,
            )
        return tag, attrs, children

    def _apply_link_card_container_conventions(
        self,
        *,
        role: str,
        node_name: str,
        tag: str,
        attrs: dict[str, str],
        children: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        """Transforme une card nommée en lien complet quand une URL existe."""

        normalized_role = ensure_text(role).strip().lower()
        if normalized_role == "link-grid":
            attrs["data-link-grid"] = "true"
            return tag, attrs, children
        if normalized_role != "link-card":
            return tag, attrs, children

        link_attrs = dict(attrs)
        link_attrs["data-link-card"] = "true"
        link_children, extracted_href = self._extract_link_card_href(children)
        href_value = ensure_text(link_attrs.get("href")).strip() or extracted_href

        if not href_value:
            link_attrs.pop("href", None)
            return "article", link_attrs, link_children

        anchor_attrs = {"href": href_value}
        if name_has_token(node_name, ("blank", "newtab", "external")):
            anchor_attrs["target"] = "_blank"
            anchor_attrs["rel"] = "noopener noreferrer"

        link_attrs.update(anchor_attrs)
        return "a", link_attrs, link_children

    def _apply_card_container_conventions(
        self,
        *,
        role: str,
        node_name: str,
        tag: str,
        attrs: dict[str, str],
        children: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        del node_name
        normalized_role = ensure_text(role).strip().lower()
        if normalized_role != "card":
            return tag, attrs, children
        attrs["data-card"] = "true"
        return tag, attrs, children

    def _apply_accordion_container_conventions(
        self,
        *,
        role: str,
        node_name: str,
        tag: str,
        attrs: dict[str, str],
        children: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        """Enrichit les blocs d'accordéon avec les attributs HTML/ARIA attendus."""

        normalized_role = ensure_text(role).strip().lower()
        if normalized_role == "accordion":
            attrs["data-accordion"] = "true"
            attrs["data-accordion-mode"] = accordion_mode(node_name)
            return tag, attrs, children
        if normalized_role == "accordion-trigger":
            attrs["data-accordion-trigger"] = "true"
            attrs.setdefault("aria-expanded", "true")
            attrs.setdefault("type", "button")
            return "button", attrs, children
        if normalized_role == "accordion-panel":
            attrs["data-accordion-panel"] = "true"
            return tag, attrs, children
        if normalized_role != "accordion-item":
            return tag, attrs, children

        attrs["data-accordion-item"] = "true"
        starts_open = accordion_item_starts_open(node_name)
        attrs["data-accordion-open"] = "true" if starts_open else "false"

        trigger = self._first_container_child_by_role(children, "accordion-trigger")
        panel = self._first_container_child_by_role(children, "accordion-panel")

        if trigger:
            trigger_attrs = dict(trigger.get("attributes", {}))
            trigger_attrs["data-accordion-trigger"] = "true"
            trigger_attrs["aria-expanded"] = "true" if starts_open else "false"
            trigger_attrs.setdefault("type", "button")
            if panel and trigger.get("dom_id") and panel.get("dom_id"):
                trigger_attrs["aria-controls"] = ensure_text(panel.get("dom_id"))
            trigger["attributes"] = trigger_attrs
            trigger["tag"] = "button"

        if panel:
            panel_attrs = dict(panel.get("attributes", {}))
            panel_attrs["data-accordion-panel"] = "true"
            panel_attrs["role"] = "region"
            panel_attrs["aria-hidden"] = "false" if starts_open else "true"
            if trigger and trigger.get("dom_id"):
                panel_attrs["aria-labelledby"] = ensure_text(trigger.get("dom_id"))
            if starts_open:
                panel_attrs.pop("hidden", None)
            else:
                panel_attrs["hidden"] = "hidden"
            panel["attributes"] = panel_attrs

        return tag, attrs, children

    def _first_container_child_by_role(
        self,
        children: list[dict[str, Any]],
        role: str,
    ) -> dict[str, Any] | None:
        normalized_role = ensure_text(role).strip().lower()
        return next(
            (
                child
                for child in children
                if child.get("kind") == "container"
                and ensure_text(child.get("role")).strip().lower() == normalized_role
            ),
            None,
        )

    def _apply_carousel_container_conventions(
        self,
        *,
        role: str,
        node_name: str,
        tag: str,
        attrs: dict[str, str],
        children: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str], list[dict[str, Any]]]:
        """Prépare le markup d'un carousel et relie thumbs <-> slides."""

        normalized_role = ensure_text(role).strip().lower()
        updated_attrs = dict(attrs)

        if normalized_role == "carousel-stage":
            updated_attrs["data-carousel-stage"] = "true"
            return tag, updated_attrs, children
        if normalized_role == "carousel-nav":
            updated_attrs["data-carousel-nav"] = "true"
            return tag, updated_attrs, children
        if normalized_role == "carousel-slide":
            updated_attrs["data-carousel-slide"] = carousel_item_key(node_name, ("carousel-slide",))
            if carousel_item_starts_active(node_name):
                updated_attrs["data-carousel-default"] = "true"
            return tag, updated_attrs, children
        if normalized_role == "carousel-thumb":
            updated_attrs["data-carousel-thumb"] = carousel_item_key(node_name, ("carousel-thumb",))
            updated_attrs.setdefault("aria-pressed", "false")
            updated_attrs.setdefault("type", "button")
            if carousel_item_starts_active(node_name):
                updated_attrs["data-carousel-default"] = "true"
            return "button", updated_attrs, children
        if normalized_role != "carousel":
            return tag, updated_attrs, children

        updated_attrs["data-carousel"] = "true"
        slide_nodes = [
            node
            for node in self._iter_container_nodes(children)
            if ensure_text(node.get("role")).strip().lower() == "carousel-slide"
        ]
        thumb_nodes = [
            node
            for node in self._iter_container_nodes(children)
            if ensure_text(node.get("role")).strip().lower() == "carousel-thumb"
        ]

        slide_by_key: dict[str, dict[str, Any]] = {}
        for slide in slide_nodes:
            slide_attrs = dict(slide.get("attributes", {}))
            slide_key = ensure_text(slide_attrs.get("data-carousel-slide")).strip() or carousel_item_key(
                slide.get("class_name") or slide.get("id"),
                ("carousel-slide",),
            )
            slide_attrs["data-carousel-slide"] = slide_key
            if not slide_key:
                slide_attrs["data-carousel-slide"] = ensure_text(slide.get("dom_id") or slide.get("id"))
            slide["attributes"] = slide_attrs
            slide_by_key[ensure_text(slide_attrs.get("data-carousel-slide"))] = slide

        for thumb in thumb_nodes:
            thumb_attrs = dict(thumb.get("attributes", {}))
            thumb_key = ensure_text(thumb_attrs.get("data-carousel-thumb")).strip() or carousel_item_key(
                thumb.get("class_name") or thumb.get("id"),
                ("carousel-thumb",),
            )
            thumb_attrs["data-carousel-thumb"] = thumb_key or ensure_text(thumb.get("dom_id") or thumb.get("id"))
            thumb_attrs.setdefault("aria-pressed", "false")
            thumb_attrs.setdefault("type", "button")
            matching_slide = slide_by_key.get(ensure_text(thumb_attrs.get("data-carousel-thumb")))
            if matching_slide and matching_slide.get("dom_id"):
                thumb_attrs["aria-controls"] = ensure_text(matching_slide.get("dom_id"))
            thumb["attributes"] = thumb_attrs

        return tag, updated_attrs, children

    def _iter_container_nodes(self, children: list[dict[str, Any]]):
        for child in children:
            if child.get("kind") != "container":
                continue
            yield child
            yield from self._iter_container_nodes(child.get("children", []))

    def _extract_link_card_href(self, children: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        href_value = ""

        def walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
            nonlocal href_value
            retained_nodes: list[dict[str, Any]] = []
            for node in nodes:
                if node.get("kind") == "text":
                    text_payload = as_mapping(node.get("text"))
                    text_name = ensure_text(text_payload.get("name") or text_payload.get("id"))
                    text_value = ensure_text(text_payload.get("value")).strip().strip("\"'")
                    if not href_value and name_has_prefix(text_name, ("href", "url")) and looks_like_href(text_value):
                        href_value = text_value
                        continue
                    retained_nodes.append(node)
                    continue
                if node.get("kind") == "container":
                    node["children"] = walk(list(node.get("children", [])))
                retained_nodes.append(node)
            return retained_nodes

        return walk(list(children)), href_value

    def _find_link_card_text_target(self, children: list[dict[str, Any]]) -> dict[str, Any] | None:
        text_nodes = list(self._iter_text_nodes(children))
        if not text_nodes:
            return None
        preferred = next(
            (
                node
                for node in text_nodes
                if name_has_prefix(
                    as_mapping(node.get("text")).get("name") or as_mapping(node.get("text")).get("id"),
                    ("card-link", "link-label", "href-label", "link"),
                )
            ),
            None,
        )
        return preferred or text_nodes[0]

    def _iter_text_nodes(self, children: list[dict[str, Any]]):
        for child in children:
            if child.get("kind") == "text":
                yield child
                continue
            if child.get("kind") == "container":
                yield from self._iter_text_nodes(child.get("children", []))

    def _should_promote_container_asset_to_background(
        self,
        *,
        container_role: str,
        asset: dict[str, Any],
        container_bounds: dict[str, float],
    ) -> bool:
        purpose = ensure_text(asset.get("purpose")).strip().lower()
        if purpose == "background":
            return True
        if purpose not in {"", "content"}:
            return False

        asset_name = ensure_text(asset.get("name") or asset.get("id"))
        if container_role == "button" and name_has_prefix(asset_name, ("button", "btn", "bg", "fond")):
            return True
        if container_role == "field" and name_has_prefix(asset_name, ("zone", "input", "champ", "bg", "fond")):
            return True

        asset_bounds = normalize_bounds(asset.get("bounds"))
        container_width = float(container_bounds.get("width", 0.0) or 0.0)
        container_height = float(container_bounds.get("height", 0.0) or 0.0)
        if container_width <= 0 or container_height <= 0:
            return False

        return (
            abs(float(asset_bounds.get("x", 0.0) or 0.0)) <= 4.0
            and abs(float(asset_bounds.get("y", 0.0) or 0.0)) <= 4.0
            and abs(float(asset_bounds.get("width", 0.0) or 0.0) - container_width) <= 4.0
            and abs(float(asset_bounds.get("height", 0.0) or 0.0) - container_height) <= 4.0
        )

    def _wrap_text_node(self, text: dict[str, Any], *, node_id: str) -> dict[str, Any]:
        return {
            "id": node_id,
            "dom_id": dom_identifier(node_id, default=f"{text['id']}-node"),
            "kind": "text",
            "tag": text["tag"],
            "role": text["role"],
            "class_name": self._unique_class_name("node", text["id"], node_id),
            "bounds": text["bounds"],
            "attributes": {},
            "children": [],
            "text": text,
        }

    def _wrap_asset_node(self, asset: dict[str, Any], *, node_id: str) -> dict[str, Any]:
        return {
            "id": node_id,
            "dom_id": dom_identifier(node_id, default=f"{asset['id']}-node"),
            "kind": "asset",
            "tag": "figure",
            "role": asset["purpose"],
            "class_name": self._unique_class_name("node", asset["id"], node_id),
            "bounds": asset["bounds"],
            "attributes": {},
            "children": [],
            "asset": asset,
        }

    def _normalize_container_bounds(
        self,
        data: dict[str, Any],
        *,
        parent_absolute_offset: tuple[float, float],
        source_space: str,
    ) -> tuple[dict[str, float], tuple[float, float]]:
        raw_bounds = normalize_bounds(coalesce(data, "bounds", "absoluteBoundingBox", default={}))
        if source_space == SECTION_COORDINATE_SPACE:
            return (
                self._rebase_bounds(raw_bounds, parent_absolute_offset),
                (float(raw_bounds.get("x", 0.0) or 0.0), float(raw_bounds.get("y", 0.0) or 0.0)),
            )
        return (
            raw_bounds,
            (
                parent_absolute_offset[0] + float(raw_bounds.get("x", 0.0) or 0.0),
                parent_absolute_offset[1] + float(raw_bounds.get("y", 0.0) or 0.0),
            ),
        )

    def _text_for_context(
        self,
        value: Any,
        *,
        section_id: str,
        section_index: int,
        text_index: int,
        parent_absolute_offset: tuple[float, float],
        source_space: str,
    ) -> dict[str, Any]:
        value = self._resolve_text_reference(value)
        text = self._normalize_text(
            value,
            section_id=section_id,
            section_index=section_index,
            text_index=text_index,
        )
        if source_space != SECTION_COORDINATE_SPACE:
            return text
        if parent_absolute_offset == (0.0, 0.0):
            return text
        return {
            **text,
            "bounds": self._rebase_bounds(text["bounds"], parent_absolute_offset),
            "render_bounds": self._rebase_optional_bounds(text.get("render_bounds"), parent_absolute_offset),
        }

    def _asset_for_context(
        self,
        value: Any,
        *,
        section_id: str,
        asset_index: int,
        parent_absolute_offset: tuple[float, float],
        source_space: str,
    ) -> dict[str, Any]:
        value = self._resolve_asset_reference(value)
        asset = self._normalize_asset(
            value,
            section_id=section_id,
            asset_index=asset_index,
        )
        if source_space != SECTION_COORDINATE_SPACE:
            return asset
        if parent_absolute_offset == (0.0, 0.0):
            return asset
        return {
            **asset,
            "bounds": self._rebase_bounds(asset["bounds"], parent_absolute_offset),
        }

    def _resolve_text_reference(self, value: Any) -> Any:
        if isinstance(value, str):
            return value
        data = as_mapping(value)
        if not data:
            return value
        reference = data.get("text")
        if not isinstance(reference, str) or reference not in self._global_texts:
            return value
        base = as_mapping(self._global_texts[reference])
        if not base:
            return value
        overrides = {key: item for key, item in data.items() if key not in {"kind", "text"}}
        return {**base, **overrides, "_contextual_ref": True}

    def _resolve_asset_reference(self, value: Any) -> Any:
        if isinstance(value, str):
            return value
        data = as_mapping(value)
        if not data:
            return value
        reference = data.get("asset")
        if not isinstance(reference, str) or reference not in self._global_assets:
            return value
        base = as_mapping(self._global_assets[reference])
        if not base:
            return value
        overrides = {key: item for key, item in data.items() if key not in {"kind", "asset"}}
        return {**base, **overrides, "_contextual_ref": True}

    def _rebase_bounds(
        self,
        bounds: dict[str, float],
        parent_absolute_offset: tuple[float, float],
    ) -> dict[str, float]:
        return {
            "x": float(bounds.get("x", 0.0) or 0.0) - parent_absolute_offset[0],
            "y": float(bounds.get("y", 0.0) or 0.0) - parent_absolute_offset[1],
            "width": float(bounds.get("width", 0.0) or 0.0),
            "height": float(bounds.get("height", 0.0) or 0.0),
        }

    def _rebase_optional_bounds(
        self,
        bounds: Any,
        parent_absolute_offset: tuple[float, float],
    ) -> dict[str, float]:
        data = as_mapping(bounds)
        if not data:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        return self._rebase_bounds(normalize_bounds(data), parent_absolute_offset)

    def _normalize_text(
        self,
        value: Any,
        *,
        section_id: str,
        section_index: int,
        text_index: int,
    ) -> dict[str, Any]:
        data = as_mapping(value)
        if isinstance(value, str) and value in self._global_texts:
            data = as_mapping(self._global_texts[value])
        has_contextual_bounds = bool(data and data.get("_contextual_ref"))
        text_id = ensure_text(
            coalesce(data, "id", "nodeId", "node_id", default=f"{section_id or 'page'}-text-{text_index + 1}"),
            default=f"{section_id or 'page'}-text-{text_index + 1}",
        )
        if text_id in self._text_index and not has_contextual_bounds:
            return self._text_index[text_id]
        raw_value = ""
        for key in TEXT_VALUE_KEYS:
            if key in data and data[key] not in (None, ""):
                raw_value = ensure_text(data[key])
                break
        role = ensure_text(coalesce(data, "role", "type", default="body"), default="body").lower()
        tag = ensure_text(coalesce(data, "tag", default=guess_text_tag(role, section_index, text_index)), default="p")
        attrs = sanitize_attributes(data.get("attributes"))
        if tag == "a":
            append_attribute(attrs, "href", coalesce(data, "href", "url"))
        if tag == "label":
            append_attribute(attrs, "for", coalesce(data, "for", "label_for"))
        style_runs = coalesce(data, "styleRuns", "style_runs", default=[])
        display_value, normalized_break_lines = self._normalize_display_text(
            raw_value,
            role=role,
            style_runs=style_runs,
        )
        segments = self._normalize_segments(display_value, style_runs)
        normalized = {
            "id": text_id,
            "dom_id": dom_identifier(text_id, default=f"{section_id or 'page'}-text-{text_index + 1}"),
            "name": ensure_text(coalesce(data, "name", default=text_id), default=text_id),
            "value": display_value,
            "source_value": raw_value,
            "plain_text": " ".join(display_value.split()),
            "html": html_with_line_breaks(display_value),
            "tag": tag,
            "role": role,
            "section_id": section_id,
            "class_name": self._unique_class_name(
                "text",
                ensure_text(coalesce(data, "name", default=text_id), default=text_id),
                text_id,
            ),
            "bounds": normalize_bounds(coalesce(data, "bounds", "absoluteBoundingBox", default={})),
            "render_bounds": normalize_bounds(coalesce(data, "renderBounds", "render_bounds", default={})),
            "attributes": attrs,
            "style": as_mapping(coalesce(data, "style", default={})),
            "style_css": style_map_to_css(coalesce(data, "style", default={})),
            "hard_breaks": self._has_hard_breaks(display_value),
            "nowrap": self._should_nowrap_text(
                display_value,
                normalize_bounds(coalesce(data, "bounds", "absoluteBoundingBox", default={})),
                as_mapping(coalesce(data, "style", default={})),
            ),
            "preserve_spaces": self._should_preserve_spaces(display_value),
            "normalized_break_lines": normalized_break_lines,
            "source_line_count": self._line_count(raw_value),
            "display_line_count": self._line_count(display_value),
            "segments": segments,
        }
        if not has_contextual_bounds:
            self._text_index[text_id] = normalized
        return normalized

    def _normalize_display_text(
        self,
        raw_value: str,
        *,
        role: str,
        style_runs: Any,
    ) -> tuple[str, bool]:
        normalized_value = raw_value.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized_value:
            return normalized_value, False
        if role not in HEADING_ROLES:
            return normalized_value, False
        if coerce_list(style_runs):
            return normalized_value, False
        collapsed_value = self._collapse_isolated_punctuation_breaks(normalized_value)
        return collapsed_value, collapsed_value != normalized_value

    def _collapse_isolated_punctuation_breaks(self, value: str) -> str:
        lines = value.split("\n")
        if len(lines) < 3:
            return value
        collapsed_lines: list[str] = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            if (
                0 < index < len(lines) - 1
                and stripped
                and PUNCTUATION_ONLY_LINE_RE.fullmatch(stripped)
                and collapsed_lines
                and collapsed_lines[-1].strip()
                and lines[index + 1].strip()
            ):
                collapsed_lines[-1] = collapsed_lines[-1].rstrip() + f" {stripped}"
                continue
            collapsed_lines.append(line)
        return "\n".join(collapsed_lines)

    def _line_count(self, value: str) -> int:
        if not value:
            return 0
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        return len(normalized.split("\n"))

    def _normalize_segments(self, text_value: str, value: Any) -> list[dict[str, Any]]:
        runs = coerce_list(value)
        segments: list[dict[str, Any]] = []
        cursor = 0
        used_indexed_ranges = False
        ordered_runs = sorted(
            (as_mapping(run) for run in runs),
            key=lambda run: (
                int(run.get("start", run.get("startIndex", 0)) or 0),
                int(run.get("end", run.get("endIndex", 0)) or 0),
            ),
        )
        for index, data in enumerate(ordered_runs):
            start = data.get("start", data.get("startIndex"))
            end = data.get("end", data.get("endIndex"))
            if isinstance(start, int) and isinstance(end, int):
                used_indexed_ranges = True
                bounded_start = max(0, min(start, len(text_value)))
                bounded_end = max(bounded_start, min(end, len(text_value)))
                if bounded_start > cursor:
                    plain_text = text_value[cursor:bounded_start]
                    if plain_text:
                        segments.append(
                            {
                                "id": f"segment-gap-{len(segments) + 1}",
                                "value": plain_text,
                                "html": html_with_line_breaks(plain_text),
                                "class_name": class_name("segment", f"segment-gap-{len(segments) + 1}"),
                                "style": "",
                            }
                        )
                segment_text = text_value[bounded_start:bounded_end]
                cursor = max(cursor, bounded_end)
            else:
                segment_text = ensure_text(coalesce(data, "text", "value"))

            if not segment_text:
                continue
            segment_name = ensure_text(coalesce(data, "name", default=f"segment-{index + 1}"))
            segments.append(
                {
                    "id": ensure_text(coalesce(data, "id", default=f"segment-{index + 1}")),
                    "value": segment_text,
                    "html": html_with_line_breaks(segment_text),
                    "class_name": class_name("segment", segment_name),
                    "style": style_map_to_css(coalesce(data, "style", default=data)),
                }
            )
        if used_indexed_ranges and cursor < len(text_value):
            trailing_text = text_value[cursor:]
            if trailing_text:
                segments.append(
                    {
                        "id": f"segment-gap-{len(segments) + 1}",
                        "value": trailing_text,
                        "html": html_with_line_breaks(trailing_text),
                        "class_name": class_name("segment", f"segment-gap-{len(segments) + 1}"),
                        "style": "",
                    }
                )
        return segments

    def _normalize_asset(
        self,
        value: Any,
        *,
        section_id: str,
        asset_index: int,
        default_purpose: str = "content",
    ) -> dict[str, Any]:
        data = as_mapping(value)
        if isinstance(value, str) and value in self._global_assets:
            data = as_mapping(self._global_assets[value])
        has_contextual_bounds = bool(data and data.get("_contextual_ref"))
        asset_id = ensure_text(
            coalesce(data, "id", "nodeId", "node_id", default=f"{section_id or 'page'}-asset-{asset_index + 1}"),
            default=f"{section_id or 'page'}-asset-{asset_index + 1}",
        )
        if asset_id in self._asset_index and not has_contextual_bounds:
            return self._asset_index[asset_id]
        asset_name = ensure_text(coalesce(data, "name", default=asset_id), default=asset_id)
        render_mode = ensure_text(coalesce(data, "renderMode", "render_mode", default="image"), default="image")
        asset_format = ensure_text(
            coalesce(data, "format", "extension", default=PurePosixPath(ensure_text(data.get("local_path"))).suffix.lstrip(".")),
            default="png",
        ).lstrip(".")
        if render_mode == "shape" or asset_format == "shape":
            relative_path = ""
        else:
            relative_path = asset_relative_path(
                ensure_text(coalesce(data, "local_path", "localPath", "path", "file", "src", "url")),
                fallback_name=asset_name,
                fallback_format=asset_format or "png",
            )
        purpose = ensure_text(coalesce(data, "purpose", "function", "role", default=default_purpose), default=default_purpose).lower()
        attrs = sanitize_attributes(data.get("attributes"))
        append_attribute(attrs, "loading", coalesce(data, "loading", default="lazy"))
        style = as_mapping(coalesce(data, "style", default={}))
        normalized = {
            "id": asset_id,
            "dom_id": dom_identifier(asset_id, default=f"{section_id or 'page'}-asset-{asset_index + 1}"),
            "node_id": ensure_text(coalesce(data, "nodeId", "node_id", default=asset_id), default=asset_id),
            "name": asset_name,
            "format": asset_format or "png",
            "render_mode": render_mode,
            "source_url": coalesce(data, "url", "source_url"),
            "source_local_path": ensure_text(coalesce(data, "local_path", "localPath", "path", "file", "src")),
            "local_path": relative_path,
            "public_path": normalize_public_path(relative_path, self.mode) if relative_path else "",
            "css_public_path": self._css_public_path(relative_path),
            "purpose": purpose,
            "alt": "" if purpose in DECORATIVE_PURPOSES else ensure_text(coalesce(data, "alt", default=asset_name), default=asset_name),
            "aria_hidden": purpose in DECORATIVE_PURPOSES,
            "render": purpose != "mask",
            "class_name": self._unique_class_name("asset", asset_name, asset_id),
            "bounds": normalize_bounds(coalesce(data, "bounds", "absoluteBoundingBox", default={})),
            "width": int(
                coalesce(
                    data,
                    "width",
                    default=normalize_bounds(
                        coalesce(data, "bounds", "absoluteBoundingBox", default={})
                    ).get("width", 0),
                )
                or 0
            ),
            "height": int(
                coalesce(
                    data,
                    "height",
                    default=normalize_bounds(
                        coalesce(data, "bounds", "absoluteBoundingBox", default={})
                    ).get("height", 0),
                )
                or 0
            ),
            "attributes": attrs,
            "style": style,
            "style_css": style_map_to_css(style),
        }
        if not has_contextual_bounds:
            self._asset_index[asset_id] = normalized
        return normalized

    def _css_public_path(self, relative_path: str) -> str:
        public_path = normalize_public_path(relative_path, self.mode)
        if not public_path:
            return ""
        if self.mode == "hugo":
            return f"/{public_path.lstrip('/')}"
        return public_path

    def _unique_class_name(self, prefix: str, label: str, identifier: str) -> str:
        key = (prefix, identifier)
        existing = self._class_registry.get(key)
        if existing:
            return existing

        base_name = class_name(prefix, label)
        if not base_name:
            base_name = class_name(prefix, identifier)

        candidate = base_name
        if candidate in self._used_class_names:
            identifier_part = css_escape_identifier(identifier, default="item")
            candidate = class_name(base_name, identifier_part)
            suffix = 2
            while candidate in self._used_class_names:
                candidate = class_name(base_name, identifier_part, str(suffix))
                suffix += 1

        self._class_registry[key] = candidate
        self._used_class_names.add(candidate)
        return candidate

    def _resolve_items(self, value: Any, registry: dict[str, Any]) -> list[Any]:
        items: list[Any] = []
        for item in coerce_list(value):
            if isinstance(item, str) and item in registry:
                items.append(registry[item])
            else:
                items.append(item)
        return items

    def _guess_node_kind(self, data: dict[str, Any]) -> str:
        if "text" in data:
            return "text"
        if "asset" in data:
            return "asset"
        if any(key in data for key in TEXT_VALUE_KEYS):
            return "text"
        if any(key in data for key in ("local_path", "localPath", "src", "url", "format")):
            return "asset"
        return "container"

    def _should_nowrap_text(self, raw_value: str, bounds: dict[str, float], style: dict[str, Any]) -> bool:
        if not raw_value or self._has_hard_breaks(raw_value):
            return False
        line_height = coalesce(style, "lineHeight", "line_height")
        if line_height in (None, ""):
            return False
        try:
            line_height_value = float(line_height)
        except (TypeError, ValueError):
            return False
        if line_height_value <= 0:
            return False
        height = float(bounds.get("height", 0) or 0)
        if height <= 0:
            return False
        return height <= line_height_value * 1.35

    def _should_preserve_spaces(self, raw_value: str) -> bool:
        if not raw_value:
            return False
        if "\t" in raw_value:
            return True
        if raw_value != raw_value.strip():
            return True
        return "  " in raw_value

    def _has_hard_breaks(self, raw_value: str) -> bool:
        return any(marker in raw_value for marker in ("\n", "\u2028", "\u2029"))
