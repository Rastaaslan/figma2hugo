from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from figma2hugo.layout_analyzer.analyzer import SectionCandidate


TEXT_TYPES = {"TEXT"}
VECTOR_TYPES = {"VECTOR", "LINE", "STAR", "ELLIPSE", "POLYGON", "BOOLEAN_OPERATION"}
IMAGE_HOST_TYPES = {"RECTANGLE", "FRAME", "INSTANCE", "COMPONENT"}
COMPOSITE_HOST_TYPES = {"FRAME", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET"}
KNOWN_CONTAINER_TYPES = {"DOCUMENT", "CANVAS", "PAGE", "SECTION"}
KNOWN_NODE_TYPES = TEXT_TYPES | VECTOR_TYPES | IMAGE_HOST_TYPES | COMPOSITE_HOST_TYPES | KNOWN_CONTAINER_TYPES
NAME_TOKEN_RE = re.compile(r"[a-z0-9]+")
MASK_NAME_TOKENS = {"mask", "clip", "clippath"}
FOREGROUND_NAME_TOKENS = {"foreground", "fg"}
BACKGROUND_NAME_TOKENS = {"background", "bg", "backdrop"}
ICON_NAME_TOKENS = {"icon", "icone", "glyph", "logo", "pictogram", "symbol"}
DECORATIVE_NAME_TOKENS = {"decor", "decoration", "overlay", "blur", "shadow", "motif", "pattern", "triangle"}


@dataclass(slots=True)
class ExtractionResult:
    texts: dict[str, dict[str, Any]]
    assets: list[dict[str, Any]]
    tokens: dict[str, dict[str, Any]]
    warnings: list[str]


class ContentExtractor:
    def extract(
        self,
        sections: list[SectionCandidate],
        *,
        image_fill_urls: dict[str, str] | None = None,
        token_payload: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        texts: dict[str, dict[str, Any]] = {}
        assets: list[dict[str, Any]] = []
        warnings: list[str] = []
        unsupported_types: set[str] = set()
        image_fill_urls = image_fill_urls or {}

        for section in sections:
            self._walk_section(section, section.node, texts, assets, image_fill_urls, unsupported_types)

        tokens = self._extract_tokens(token_payload or {}, list(texts.values()), assets)
        if not texts:
            warnings.append("No visible text nodes were extracted from the selected Figma node.")
        if unsupported_types:
            warnings.append(
                "Skipped unsupported visible node types: " + ", ".join(sorted(unsupported_types)) + "."
            )
        return ExtractionResult(texts=texts, assets=assets, tokens=tokens, warnings=warnings)

    def _walk_section(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
        texts: dict[str, dict[str, Any]],
        assets: list[dict[str, Any]],
        image_fill_urls: dict[str, str],
        unsupported_types: set[str],
    ) -> None:
        if not node.get("visible", True):
            return

        node_type = node.get("type")
        if node_type in TEXT_TYPES:
            text_payload = self._text_payload(section, node)
            texts[text_payload["id"]] = text_payload
            return

        composite_asset_payload = self._composite_asset_payload(section, node)
        if composite_asset_payload is not None:
            assets.append(composite_asset_payload)
            return

        asset_payload = self._asset_payload(section, node, image_fill_urls)
        if asset_payload is not None:
            assets.append(asset_payload)

        for child in node.get("children", []):
            self._walk_section(section, child, texts, assets, image_fill_urls, unsupported_types)

        if self._should_warn_unsupported_node(node):
            unsupported_types.add(str(node.get("type") or "<unknown>"))

    def _text_payload(self, section: SectionCandidate, node: dict[str, Any]) -> dict[str, Any]:
        text_id = node.get("id", "")
        characters = node.get("characters") or ""
        style = node.get("style") or {}
        bounds = self._relative_bounds(section, node)
        tag = self._guess_text_tag(node)
        return {
            "id": text_id,
            "name": node.get("name") or text_id,
            "value": characters,
            "rawValue": characters,
            "sectionId": section.id,
            "bounds": bounds,
            "styleRuns": self._style_runs(node),
            "tag": tag,
            "role": self._guess_text_role(tag, node),
            "style": {
                "fontFamily": style.get("fontFamily"),
                "fontStyle": style.get("fontStyle"),
                "fontSize": style.get("fontSize"),
                "fontWeight": style.get("fontWeight"),
                "letterSpacing": style.get("letterSpacing"),
                "lineHeight": style.get("lineHeightPx"),
                "textAlignHorizontal": style.get("textAlignHorizontal"),
                "textAlignVertical": style.get("textAlignVertical"),
                "fills": node.get("fills") or [],
            },
        }

    def _asset_payload(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
        image_fill_urls: dict[str, str],
    ) -> dict[str, Any] | None:
        node_type = node.get("type")
        fills = node.get("fills") or []
        strokes = node.get("strokes") or []
        name = node.get("name") or node.get("id", "asset")
        image_ref = self._find_image_ref(node)

        if image_ref:
            return {
                "nodeId": node.get("id"),
                "sectionId": section.id,
                "name": name,
                "format": self._guess_image_format(image_fill_urls.get(image_ref)),
                "sourceUrl": image_fill_urls.get(image_ref),
                "localPath": None,
                "function": self._guess_asset_function(name, node, section),
                "bounds": self._relative_bounds(section, node),
                "isVector": False,
                "imageRef": image_ref,
            }

        if node_type in VECTOR_TYPES:
            return {
                "nodeId": node.get("id"),
                "sectionId": section.id,
                "name": name,
                "format": "svg",
                "sourceUrl": None,
                "localPath": None,
                "function": self._guess_asset_function(name, node, section),
                "bounds": self._relative_bounds(section, node),
                "isVector": True,
                "imageRef": None,
            }

        if node_type in IMAGE_HOST_TYPES and (fills or strokes) and not node.get("children"):
            if self._looks_decorative(name, node):
                return {
                    "nodeId": node.get("id"),
                    "sectionId": section.id,
                    "name": name,
                    "format": "png",
                    "sourceUrl": None,
                    "localPath": None,
                    "function": "decorative",
                    "bounds": self._relative_bounds(section, node),
                    "isVector": False,
                    "imageRef": None,
                }
        return None

    def _composite_asset_payload(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
    ) -> dict[str, Any] | None:
        if node.get("id") == section.id:
            return None
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return None
        if not node.get("children"):
            return None
        if self._subtree_contains_visible_text(node):
            return None
        if not (self._subtree_contains_mask(node) or self._subtree_contains_override_image(node)):
            return None

        name = node.get("name") or node.get("id", "asset")
        return {
            "nodeId": node.get("id"),
            "sectionId": section.id,
            "name": name,
            "format": "png",
            "sourceUrl": None,
            "localPath": None,
            "function": self._guess_asset_function(name, node, section),
            "bounds": self._relative_bounds(section, node),
            "isVector": False,
            "imageRef": None,
            "renderMode": "composite",
        }

    def _extract_tokens(
        self,
        token_payload: dict[str, Any],
        texts: list[dict[str, Any]],
        assets: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        tokens: dict[str, dict[str, Any]] = {
            "colors": {},
            "spacing": {},
            "typography": {},
            "shadows": {},
            "radii": {},
        }

        meta = token_payload.get("meta") or token_payload.get("variables") or {}
        if isinstance(meta, dict):
            for key, value in meta.items():
                lower_key = key.lower()
                if "color" in lower_key:
                    tokens["colors"][key] = value
                elif "space" in lower_key or "gap" in lower_key or "padding" in lower_key:
                    tokens["spacing"][key] = value
                elif "font" in lower_key or "type" in lower_key or "text" in lower_key:
                    tokens["typography"][key] = value

        for text in texts:
            font_size = text.get("style", {}).get("fontSize")
            font_family = text.get("style", {}).get("fontFamily")
            if font_size is not None or font_family:
                token_key = f"{font_family or 'font'}-{font_size or 'default'}"
                tokens["typography"][token_key] = {
                    "fontFamily": font_family,
                    "fontSize": font_size,
                    "lineHeight": text.get("style", {}).get("lineHeight"),
                }

        for asset in assets:
            bounds = asset.get("bounds", {})
            width = bounds.get("width", 0)
            if width:
                tokens["spacing"].setdefault(f"asset-width-{int(width)}", width)

        return tokens

    def _guess_text_tag(self, node: dict[str, Any]) -> str:
        style = node.get("style") or {}
        font_size = float(style.get("fontSize", 0) or 0)
        name = (node.get("name") or "").lower()
        if "label" in name:
            return "label"
        if "button" in name or "cta" in name:
            return "span"
        if font_size >= 44:
            return "h1"
        if font_size >= 30:
            return "h2"
        if font_size >= 24:
            return "h3"
        return "p"

    def _style_runs(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        overrides = node.get("characterStyleOverrides") or []
        override_table = node.get("styleOverrideTable") or {}
        if not overrides or not override_table:
            return []

        runs: list[dict[str, Any]] = []
        last_override = overrides[0]
        start = 0
        for index, override in enumerate(overrides[1:], start=1):
            if override != last_override:
                runs.append(
                    {
                        "start": start,
                        "end": index,
                        **self._normalize_style_run(override_table.get(str(last_override), {})),
                    }
                )
                start = index
                last_override = override
        runs.append(
            {
                "start": start,
                "end": len(overrides),
                **self._normalize_style_run(override_table.get(str(last_override), {})),
            }
        )
        return runs

    def _normalize_style_run(self, style: dict[str, Any]) -> dict[str, Any]:
        return {
            "style": style,
        }

    def _guess_asset_function(self, name: str, node: dict[str, Any], section: SectionCandidate) -> str:
        tokens = self._name_tokens(name)
        if node.get("isMask") is True or tokens & MASK_NAME_TOKENS:
            return "mask"
        if tokens & FOREGROUND_NAME_TOKENS:
            return "foreground"
        if tokens & BACKGROUND_NAME_TOKENS:
            return "background"
        if tokens & ICON_NAME_TOKENS:
            return "icon"
        bounds = self._relative_bounds(section, node)
        if self._looks_like_background(node, bounds, section.bounds):
            return "background"
        if self._looks_like_icon(node, bounds, section.bounds):
            return "icon"
        if self._looks_decorative(name, node):
            return "decorative"
        return "content"

    def _looks_decorative(self, name: str, node: dict[str, Any]) -> bool:
        if self._name_tokens(name) & DECORATIVE_NAME_TOKENS:
            return True
        return node.get("type") in VECTOR_TYPES and not node.get("children")

    def _looks_like_background(
        self,
        node: dict[str, Any],
        bounds: dict[str, float],
        section_bounds: dict[str, float],
    ) -> bool:
        if node.get("type") in VECTOR_TYPES and not node.get("children"):
            return False
        section_width = float(section_bounds.get("width", 0.0) or 0.0)
        section_height = float(section_bounds.get("height", 0.0) or 0.0)
        width = float(bounds.get("width", 0.0) or 0.0)
        height = float(bounds.get("height", 0.0) or 0.0)
        x = float(bounds.get("x", 0.0) or 0.0)
        y = float(bounds.get("y", 0.0) or 0.0)
        if section_width <= 0 or section_height <= 0 or width <= 0 or height <= 0:
            return False
        area_ratio = (width * height) / max(section_width * section_height, 1.0)
        width_ratio = width / section_width
        height_ratio = height / section_height
        near_origin = x <= section_width * 0.05 and y <= section_height * 0.05
        return near_origin and (area_ratio >= 0.35 or (width_ratio >= 0.85 and height_ratio >= 0.3))

    def _looks_like_icon(
        self,
        node: dict[str, Any],
        bounds: dict[str, float],
        section_bounds: dict[str, float],
    ) -> bool:
        if node.get("type") not in VECTOR_TYPES or node.get("children"):
            return False
        section_width = float(section_bounds.get("width", 0.0) or 0.0)
        section_height = float(section_bounds.get("height", 0.0) or 0.0)
        width = float(bounds.get("width", 0.0) or 0.0)
        height = float(bounds.get("height", 0.0) or 0.0)
        if section_width <= 0 or section_height <= 0 or width <= 0 or height <= 0:
            return False
        area_ratio = (width * height) / max(section_width * section_height, 1.0)
        max_dim_ratio = max(width / section_width, height / section_height)
        aspect_ratio = max(width, height) / max(min(width, height), 1.0)
        return area_ratio <= 0.02 and max_dim_ratio <= 0.25 and aspect_ratio <= 4.0

    def _name_tokens(self, name: str) -> set[str]:
        return {token for token in NAME_TOKEN_RE.findall(name.lower()) if token}

    def _find_image_ref(self, node: dict[str, Any]) -> str | None:
        fills = node.get("fills") or []
        for fill in fills:
            if fill.get("type") == "IMAGE" and fill.get("visible", True):
                image_ref = fill.get("imageRef")
                if image_ref:
                    return image_ref
        override_table = node.get("fillOverrideTable") or {}
        for override in override_table.values():
            if not isinstance(override, dict):
                continue
            for fill in override.get("fills") or []:
                if fill.get("type") == "IMAGE" and fill.get("visible", True):
                    image_ref = fill.get("imageRef")
                    if image_ref:
                        return image_ref
        return None

    def _guess_image_format(self, url: str | None) -> str:
        if not url:
            return "png"
        lower_url = url.lower()
        if ".svg" in lower_url:
            return "svg"
        if ".jpg" in lower_url or ".jpeg" in lower_url:
            return "jpg"
        if ".webp" in lower_url:
            return "webp"
        return "png"

    def _relative_bounds(self, section: SectionCandidate, node: dict[str, Any]) -> dict[str, float]:
        box = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        return {
            "x": float(box.get("x", 0.0)) - section.bounds["x"],
            "y": float(box.get("y", 0.0)) - section.bounds["y"],
            "width": float(box.get("width", 0.0)),
            "height": float(box.get("height", 0.0)),
        }

    def _subtree_contains_visible_text(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        if node.get("type") in TEXT_TYPES:
            return True
        return any(self._subtree_contains_visible_text(child) for child in node.get("children", []))

    def _subtree_contains_mask(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        if node.get("isMask") is True:
            return True
        return any(self._subtree_contains_mask(child) for child in node.get("children", []))

    def _subtree_contains_override_image(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        if self._node_contains_override_image(node):
            return True
        return any(self._subtree_contains_override_image(child) for child in node.get("children", []))

    def _node_contains_override_image(self, node: dict[str, Any]) -> bool:
        override_table = node.get("fillOverrideTable") or {}
        for override in override_table.values():
            if not isinstance(override, dict):
                continue
            for fill in override.get("fills") or []:
                if fill.get("type") == "IMAGE" and fill.get("visible", True):
                    return True
        return False

    def _should_warn_unsupported_node(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        node_type = str(node.get("type") or "")
        if node_type in KNOWN_NODE_TYPES:
            return False
        if node.get("children"):
            return False
        return True

    def _guess_text_role(self, tag: str, node: dict[str, Any]) -> str:
        if tag == "label":
            return "label"
        if tag == "h1":
            return "hero-title"
        if tag == "h2":
            return "heading"
        if tag == "h3":
            return "subheading"
        name = (node.get("name") or "").lower()
        if "button" in name or "cta" in name:
            return "cta"
        return "body"
