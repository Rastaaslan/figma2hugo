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
FILE_LIKE_NAME_RE = re.compile(r"\.(?:tif|tiff|png|jpe?g|webp|svg)$", re.IGNORECASE)
UNORDERED_LIST_LINE_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[•◦▪‣●○·\-\*])\s+(?P<content>\S.*)$")
ORDERED_LIST_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<ordinal>\d+|[A-Za-z])(?P<delimiter>[.)])\s+(?P<content>\S.*)$"
)
MASK_NAME_TOKENS = {"mask", "clip", "clippath"}
FOREGROUND_NAME_TOKENS = {"foreground", "fg"}
BACKGROUND_NAME_TOKENS = {"background", "bg", "backdrop"}
ICON_NAME_TOKENS = {"icon", "icone", "glyph", "logo", "pictogram", "symbol"}
DECORATIVE_NAME_TOKENS = {"decor", "decoration", "overlay", "blur", "shadow", "motif", "pattern", "triangle"}
SEMANTIC_WRAPPER_PREFIXES = (
    "accordion",
    "accordion-item",
    "accordion-panel",
    "accordion-trigger",
    "carousel",
    "carousel-stage",
    "carousel-main",
    "carousel-slide",
    "carousel-thumbs",
    "carousel-nav",
    "carousel-track",
    "carousel-thumb",
    "href-card",
    "link-card",
    "href-grid",
    "link-grid",
    "formulaire",
    "form",
    "input",
    "field",
    "button",
    "btn",
)


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
            for extra_node in section.extra_nodes:
                self._walk_section(section, extra_node, texts, assets, image_fill_urls, unsupported_types)

        self._merge_paragraph_line_clusters(texts)
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
        inherited_function: str | None = None,
    ) -> None:
        if not node.get("visible", True):
            return

        node_type = node.get("type")
        if node.get("id") == section.id:
            composite_section_asset = self._section_root_composite_asset_payload(section, node)
            if composite_section_asset is not None:
                assets.append(composite_section_asset)
                return
        if node_type in TEXT_TYPES:
            text_payload = self._text_payload(section, node)
            texts[text_payload["id"]] = text_payload
            return

        composite_asset_payload = self._composite_asset_payload(section, node, inherited_function=inherited_function)
        if composite_asset_payload is not None:
            assets.append(composite_asset_payload)
            return

        asset_payload = self._asset_payload(section, node, image_fill_urls, function_hint=inherited_function)
        if asset_payload is not None:
            assets.append(asset_payload)

        child_function = inherited_function
        if child_function is None and node.get("id") != section.id:
            child_function = self._editable_wrapper_function(node)
        for child in node.get("children", []):
            self._walk_section(
                section,
                child,
                texts,
                assets,
                image_fill_urls,
                unsupported_types,
                inherited_function=child_function,
            )

        if self._should_warn_unsupported_node(node):
            unsupported_types.add(str(node.get("type") or "<unknown>"))

    def _text_payload(self, section: SectionCandidate, node: dict[str, Any]) -> dict[str, Any]:
        text_id = node.get("id", "")
        characters = node.get("characters") or ""
        style = node.get("style") or {}
        bounds = self._relative_bounds(section, node)
        render_bounds = self._relative_render_bounds(section, node)
        tag = self._guess_text_tag(node)
        return {
            "id": text_id,
            "name": node.get("name") or text_id,
            "value": characters,
            "rawValue": characters,
            "sectionId": section.id,
            "bounds": bounds,
            "renderBounds": render_bounds,
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
            "layout": self._layout_metadata(node, fallback_strategy="text"),
        }

    def _asset_payload(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
        image_fill_urls: dict[str, str],
        function_hint: str | None = None,
    ) -> dict[str, Any] | None:
        node_type = node.get("type")
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
                "function": self._effective_asset_function(name, node, section, function_hint),
                "bounds": self._relative_bounds(section, node),
                "isVector": False,
                "imageRef": image_ref,
                "layout": self._layout_metadata(node, fallback_strategy="leaf"),
            }

        if node_type in VECTOR_TYPES:
            return {
                "nodeId": node.get("id"),
                "sectionId": section.id,
                "name": name,
                "format": "svg",
                "sourceUrl": None,
                "localPath": None,
                "function": self._effective_asset_function(name, node, section, function_hint),
                "bounds": self._relative_bounds(section, node),
                "isVector": True,
                "imageRef": None,
                "layout": self._layout_metadata(node, fallback_strategy="leaf"),
            }

        shape_style = self._shape_style(node)
        if node_type in IMAGE_HOST_TYPES and shape_style is not None and not node.get("children"):
            return {
                "nodeId": node.get("id"),
                "sectionId": section.id,
                "name": name,
                "format": "shape",
                "sourceUrl": None,
                "localPath": None,
                "function": self._effective_asset_function(name, node, section, function_hint),
                "bounds": self._relative_bounds(section, node),
                "isVector": False,
                "imageRef": None,
                "renderMode": "shape",
                "style": shape_style,
                "layout": self._layout_metadata(node, fallback_strategy="leaf"),
            }
        return None

    def _composite_asset_payload(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
        inherited_function: str | None = None,
    ) -> dict[str, Any] | None:
        if node.get("id") == section.id:
            return None
        return self._build_composite_asset_payload(section, node, function_hint=inherited_function)

    def _section_root_composite_asset_payload(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
    ) -> dict[str, Any] | None:
        if node.get("id") != section.id:
            return None
        if self._is_semantic_wrapper_container(node):
            return None
        if self._subtree_contains_semantic_wrapper(node, include_self=False):
            return None
        if self._subtree_contains_editable_wrapper(node, include_self=False):
            return None
        if self._has_extractable_composite_children(section, node):
            return None
        if not (
            self._has_direct_composite_children(node)
            or self._is_image_wrapper_group(node)
            or self._is_complex_graphic_subtree(node)
        ):
            return None
        return self._build_composite_asset_payload(section, node)

    def _has_extractable_composite_children(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
    ) -> bool:
        for child in node.get("children", []):
            if not isinstance(child, dict) or not child.get("visible", True):
                continue
            if self._build_composite_asset_payload(section, child) is not None:
                return True
        return False

    def _build_composite_asset_payload(
        self,
        section: SectionCandidate,
        node: dict[str, Any],
        function_hint: str | None = None,
    ) -> dict[str, Any] | None:
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return None
        if not node.get("children"):
            return None
        if self._is_semantic_wrapper_container(node):
            return None
        if self._subtree_contains_semantic_wrapper(node, include_self=False):
            return None
        if self._subtree_contains_visible_text(node):
            return None
        contains_mask = self._subtree_contains_mask(node)
        contains_override_image = self._subtree_contains_override_image(node)
        is_image_wrapper = self._is_image_wrapper_group(node)
        is_complex_graphic = self._is_complex_graphic_subtree(node)
        editable_function = self._editable_wrapper_function(node)
        render_as_svg = self._should_render_composite_as_svg(node)
        editable_group_svg = bool(editable_function and render_as_svg)
        if not (contains_mask or contains_override_image or is_image_wrapper or is_complex_graphic or editable_group_svg):
            return None
        if editable_function and not (contains_mask or contains_override_image or editable_group_svg):
            return None
        if self._subtree_contains_editable_wrapper(node, include_self=False):
            return None

        name = node.get("name") or node.get("id", "asset")
        asset_function_hint = function_hint or editable_function
        return {
            "nodeId": node.get("id"),
            "sectionId": section.id,
            "name": name,
            "format": "svg" if render_as_svg else "png",
            "sourceUrl": None,
            "localPath": None,
            "function": self._effective_asset_function(name, node, section, asset_function_hint),
            "bounds": self._relative_bounds(section, node),
            "isVector": render_as_svg,
            "imageRef": None,
            "renderMode": "composite",
            "layout": self._layout_metadata(node, fallback_strategy="absolute"),
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
        characters = (node.get("characters") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        explicit_heading_tag = self._explicit_heading_tag_from_name(name)
        if self._name_has_prefix(name, ("label", "libelle")):
            return "label"
        if self._name_has_prefix(name, ("texte", "para")):
            return "p"
        if self._name_has_prefix(name, ("titre", "heading")):
            if explicit_heading_tag:
                return explicit_heading_tag
            if font_size >= 44:
                return "h1"
            if font_size >= 30:
                return "h2"
            return "h3"
        if list_tag := self._list_tag_from_text(characters):
            return list_tag
        if self._looks_like_paragraph_text(name, characters, font_size):
            return "p"
        if font_size >= 44:
            return "h1"
        if font_size >= 30:
            return "h2"
        if font_size >= 24:
            return "h3"
        return "p"

    def _explicit_heading_tag_from_name(self, name: str) -> str:
        normalized = "-".join(NAME_TOKEN_RE.findall(name.lower()))
        tokens = {token for token in normalized.split("-") if token}
        for level in range(1, 7):
            token = f"h{level}"
            if token in tokens:
                return token
        return ""

    def _looks_like_paragraph_text(self, name: str, value: str, font_size: float) -> bool:
        if not value:
            return False
        lines = [line.strip() for line in value.split("\n") if line.strip()]
        word_count = len(NAME_TOKEN_RE.findall(value.lower()))
        sentence_like = any(marker in value for marker in (".", ",", ";", ":", "!", "?"))
        if any(token in name for token in ("paragraph", "texte", "text", "copy", "description")):
            return True
        if len(lines) >= 3 and word_count >= 8:
            return True
        if word_count >= 14 and sentence_like:
            return True
        if len(value) >= 90 and font_size < 64:
            return True
        return False

    def _list_tag_from_text(self, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized or "\n" not in normalized:
            return ""
        item_count = 0
        list_tag = ""
        for line in normalized.split("\n"):
            if not line.strip():
                continue
            if UNORDERED_LIST_LINE_RE.fullmatch(line):
                current_tag = "ul"
            elif ORDERED_LIST_LINE_RE.fullmatch(line):
                current_tag = "ol"
            else:
                return ""
            if list_tag and current_tag != list_tag:
                return ""
            list_tag = current_tag
            item_count += 1
        if item_count < 2:
            return ""
        return list_tag

    def _looks_like_list_line(self, value: str) -> bool:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized or "\n" in normalized:
            return False
        return bool(
            UNORDERED_LIST_LINE_RE.fullmatch(normalized)
            or ORDERED_LIST_LINE_RE.fullmatch(normalized)
        )

    def _merge_paragraph_line_clusters(self, texts: dict[str, dict[str, Any]]) -> None:
        texts_by_section: dict[str, list[dict[str, Any]]] = {}
        for text in texts.values():
            section_id = str(text.get("sectionId") or "")
            texts_by_section.setdefault(section_id, []).append(text)

        for section_texts in texts_by_section.values():
            buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
            for text in section_texts:
                if not self._is_paragraph_line_candidate(text):
                    continue
                buckets.setdefault(self._paragraph_line_bucket_key(text), []).append(text)

            for bucket_texts in buckets.values():
                ordered_texts = sorted(
                    bucket_texts,
                    key=lambda text: (
                        float((text.get("bounds") or {}).get("y", 0.0)),
                        float((text.get("bounds") or {}).get("x", 0.0)),
                    ),
                )
                clusters: list[list[dict[str, Any]]] = []
                for text in ordered_texts:
                    matched_cluster: list[dict[str, Any]] | None = None
                    matched_distance: float | None = None
                    for cluster in clusters:
                        if not self._belongs_to_paragraph_line_cluster(cluster[-1], text):
                            continue
                        distance = self._paragraph_line_match_distance(cluster[-1], text)
                        if matched_distance is None or distance < matched_distance:
                            matched_cluster = cluster
                            matched_distance = distance
                    if matched_cluster is None:
                        clusters.append([text])
                        continue
                    matched_cluster.append(text)
                for cluster in clusters:
                    self._apply_paragraph_line_cluster(cluster, texts)

    def _is_paragraph_line_candidate(self, text: dict[str, Any]) -> bool:
        if self._is_utility_link_text(text):
            return False
        if text.get("tag") not in {"h2", "h3", "p"}:
            return False
        style = text.get("style") or {}
        font_size = float(style.get("fontSize", 0) or 0)
        if font_size <= 0 or font_size > 40:
            return False
        value = self._normalized_text_value(text)
        if not value:
            return False
        if self._looks_like_list_line(value):
            return False
        words = NAME_TOKEN_RE.findall(value.lower())
        if len(words) < 4:
            return False
        punctuation_count = sum(value.count(marker) for marker in (".", ",", ";", ":"))
        first_alpha = next((char for char in value if char.isalpha()), "")
        starts_lowercase = bool(first_alpha) and first_alpha.islower()
        ends_like_continuation = value.endswith((",", ";", ":"))
        return punctuation_count > 0 or starts_lowercase or ends_like_continuation

    def _is_utility_link_text(self, text: dict[str, Any]) -> bool:
        name = str(text.get("name") or text.get("id") or "")
        return self._name_has_prefix(name, ("href", "url"))

    def _belongs_to_paragraph_line_cluster(self, previous: dict[str, Any], current: dict[str, Any]) -> bool:
        previous_style = previous.get("style") or {}
        current_style = current.get("style") or {}
        if previous_style.get("fontFamily") != current_style.get("fontFamily"):
            return False
        if int(previous_style.get("fontWeight") or 0) != int(current_style.get("fontWeight") or 0):
            return False
        if abs(float(previous_style.get("fontSize", 0) or 0) - float(current_style.get("fontSize", 0) or 0)) > 1.0:
            return False

        previous_bounds = previous.get("bounds") or {}
        current_bounds = current.get("bounds") or {}
        previous_line_height = float(previous_style.get("lineHeight", 0) or 0)
        current_line_height = float(current_style.get("lineHeight", 0) or 0)
        line_height = max(previous_line_height, current_line_height, 1.0)
        previous_y = float(previous_bounds.get("y", 0.0))
        current_y = float(current_bounds.get("y", 0.0))
        previous_height = float(previous_bounds.get("height", 0.0) or 0.0)
        previous_bottom = previous_y + max(previous_height, line_height)
        vertical_gap = current_y - previous_bottom
        if vertical_gap < -max(line_height * 0.6, 24.0):
            return False
        if vertical_gap > max(line_height * 1.35, 72.0):
            return False

        previous_left = float(previous_bounds.get("x", 0.0))
        current_left = float(current_bounds.get("x", 0.0))
        previous_center = previous_left + (float(previous_bounds.get("width", 0.0)) / 2.0)
        current_center = current_left + (float(current_bounds.get("width", 0.0)) / 2.0)
        previous_right = previous_left + float(previous_bounds.get("width", 0.0))
        current_right = current_left + float(current_bounds.get("width", 0.0))

        return any(
            abs(previous_anchor - current_anchor) <= 48.0
            for previous_anchor, current_anchor in (
                (previous_left, current_left),
                (previous_center, current_center),
                (previous_right, current_right),
            )
        )

    def _paragraph_line_bucket_key(self, text: dict[str, Any]) -> tuple[Any, ...]:
        style = text.get("style") or {}
        align = str(style.get("textAlignHorizontal") or "LEFT").upper()
        return (
            style.get("fontFamily"),
            round(float(style.get("fontSize", 0) or 0), 2),
            int(style.get("fontWeight") or 0),
            round(float(style.get("lineHeight", 0) or 0), 2),
            align,
        )

    def _paragraph_line_anchor(self, text: dict[str, Any], align: str) -> float:
        bounds = text.get("bounds") or {}
        x = float(bounds.get("x", 0.0))
        width = float(bounds.get("width", 0.0))
        if align == "CENTER":
            return x + (width / 2.0)
        if align == "RIGHT":
            return x + width
        return x

    def _paragraph_line_match_distance(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        previous_bounds = previous.get("bounds") or {}
        current_bounds = current.get("bounds") or {}
        previous_style = previous.get("style") or {}
        current_style = current.get("style") or {}
        line_height = max(
            float(previous_style.get("lineHeight", 0) or 0),
            float(current_style.get("lineHeight", 0) or 0),
            1.0,
        )
        previous_bottom = float(previous_bounds.get("y", 0.0)) + max(
            float(previous_bounds.get("height", 0.0) or 0.0),
            line_height,
        )
        current_top = float(current_bounds.get("y", 0.0))
        vertical_gap = max(0.0, current_top - previous_bottom)
        horizontal_gap = min(
            abs(self._paragraph_line_anchor(previous, align) - self._paragraph_line_anchor(current, align))
            for align in ("LEFT", "CENTER", "RIGHT")
        )
        return (vertical_gap * 10.0) + horizontal_gap

    def _apply_paragraph_line_cluster(
        self,
        cluster: list[dict[str, Any]],
        texts: dict[str, dict[str, Any]],
    ) -> None:
        if len(cluster) < 2:
            return
        total_words = sum(len(NAME_TOKEN_RE.findall(self._normalized_text_value(text).lower())) for text in cluster)
        if total_words < 8:
            return
        if len(cluster) < 3:
            non_initial_lowercase_lines = sum(
                1
                for text in cluster[1:]
                if self._starts_with_lowercase(self._normalized_text_value(text))
            )
            if non_initial_lowercase_lines == 0:
                return

        merged_value = "\n".join(self._normalized_text_value(text) for text in cluster if self._normalized_text_value(text))
        if not merged_value:
            return

        primary = cluster[0]
        primary["value"] = merged_value
        primary["rawValue"] = merged_value
        primary["tag"] = "p"
        primary["role"] = "body"
        primary["bounds"] = self._union_bounds(*(text.get("bounds") for text in cluster))
        primary["renderBounds"] = self._union_bounds(
            *(
                text.get("renderBounds") or text.get("bounds")
                for text in cluster
            )
        )
        primary["styleRuns"] = self._merge_style_runs(cluster)

        for text in cluster[1:]:
            text_id = str(text.get("id") or "")
            if text_id:
                texts.pop(text_id, None)

    def _normalized_text_value(self, text: dict[str, Any]) -> str:
        value = str(text.get("value") or text.get("rawValue") or "")
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()

    def _starts_with_lowercase(self, value: str) -> bool:
        first_alpha = next((char for char in value if char.isalpha()), "")
        return bool(first_alpha) and first_alpha.islower()

    def _union_bounds(self, *values: Any) -> dict[str, float]:
        boxes = [self._normalize_local_bounds(value) for value in values]
        boxes = [box for box in boxes if box["width"] > 0 or box["height"] > 0]
        if not boxes:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        left = min(box["x"] for box in boxes)
        top = min(box["y"] for box in boxes)
        right = max(box["x"] + box["width"] for box in boxes)
        bottom = max(box["y"] + box["height"] for box in boxes)
        return {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }

    def _normalize_local_bounds(self, value: Any) -> dict[str, float]:
        data = value if isinstance(value, dict) else {}
        return {
            "x": float(data.get("x", 0.0) or 0.0),
            "y": float(data.get("y", 0.0) or 0.0),
            "width": float(data.get("width", 0.0) or 0.0),
            "height": float(data.get("height", 0.0) or 0.0),
        }

    def _merge_style_runs(self, cluster: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged_runs: list[dict[str, Any]] = []
        offset = 0
        for index, text in enumerate(cluster):
            value = self._normalized_text_value(text)
            raw_runs = text.get("styleRuns") or []
            for run in raw_runs:
                start = int(run.get("start", 0) or 0)
                end = int(run.get("end", 0) or 0)
                if end <= start:
                    continue
                merged_runs.append(
                    {
                        "start": start + offset,
                        "end": end + offset,
                        "style": dict(run.get("style") or {}),
                    }
                )
            offset += len(value)
            if index < len(cluster) - 1:
                offset += 1
        return merged_runs

    def _style_runs(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        overrides = node.get("characterStyleOverrides") or []
        override_table = node.get("styleOverrideTable") or {}
        if not overrides or not override_table:
            return []
        characters = node.get("characters") or ""
        if len(overrides) < len(characters):
            overrides = [*overrides, *([0] * (len(characters) - len(overrides)))]
        elif len(overrides) > len(characters):
            overrides = overrides[: len(characters)]

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
        normalized_style = {
            "fontFamily": style.get("fontFamily"),
            "fontStyle": style.get("fontStyle"),
            "fontSize": style.get("fontSize"),
            "fontWeight": style.get("fontWeight"),
            "letterSpacing": style.get("letterSpacing"),
            "lineHeight": style.get("lineHeightPx"),
            "textAlignHorizontal": style.get("textAlignHorizontal"),
            "textAlignVertical": style.get("textAlignVertical"),
            "fills": style.get("fills") or [],
        }
        cleaned_style = {
            key: value
            for key, value in normalized_style.items()
            if value not in (None, "", [])
        }
        return {
            "style": cleaned_style,
        }

    def _guess_asset_function(self, name: str, node: dict[str, Any], section: SectionCandidate) -> str:
        named_function = self._named_asset_function(name, node)
        if named_function:
            return named_function
        return "content"

    def _effective_asset_function(
        self,
        name: str,
        node: dict[str, Any],
        section: SectionCandidate,
        function_hint: str | None = None,
    ) -> str:
        if function_hint:
            return function_hint
        return self._guess_asset_function(name, node, section)

    def _editable_wrapper_function(self, node: dict[str, Any]) -> str | None:
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return None
        if not node.get("children"):
            return None
        return self._named_wrapper_function(node)

    def _named_asset_function(self, name: str, node: dict[str, Any]) -> str | None:
        normalized_name = str(name or "").strip().lower()
        is_composite_mask_host = bool(node.get("children")) and self._subtree_contains_mask(node)
        if (node.get("isMask") is True or self._name_has_prefix(normalized_name, ("mask", "clip"))) and not is_composite_mask_host:
            return "mask"
        if self._name_has_prefix(normalized_name, ("fg", "foreground")):
            return "foreground"
        if self._name_has_prefix(normalized_name, ("bg", "fond", "background")):
            return "background"
        if self._name_has_prefix(normalized_name, ("icon", "icone", "logo")):
            return "icon"
        if self._name_has_prefix(normalized_name, ("decor", "motif", "forme", "triangle")):
            return "decorative"
        return None

    def _named_wrapper_function(self, node: dict[str, Any]) -> str | None:
        named_function = self._named_asset_function(node.get("name") or node.get("id", ""), node)
        if named_function in {"foreground", "background", "icon", "decorative"}:
            return named_function
        return None

    def _subtree_contains_editable_wrapper(self, node: dict[str, Any], *, include_self: bool = True) -> bool:
        if not node.get("visible", True):
            return False
        if include_self and self._editable_wrapper_function(node):
            return True
        return any(self._subtree_contains_editable_wrapper(child) for child in node.get("children", []))

    def _is_editable_graphic_cluster(self, node: dict[str, Any]) -> bool:
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return False
        visible_children = [
            child
            for child in node.get("children", [])
            if isinstance(child, dict) and child.get("visible", True)
        ]
        if len(visible_children) < 2 or len(visible_children) > 48:
            return False
        if self._subtree_contains_visible_text(node):
            return False
        if self._subtree_contains_mask(node):
            return False
        if self._subtree_contains_override_image(node):
            return False
        if self._is_image_wrapper_group(node):
            return False
        if not all(self._is_simple_graphic_leaf(child) for child in visible_children):
            return False
        coverage_ratio = self._graphic_leaf_coverage_ratio(node, visible_children)
        if coverage_ratio >= 0.12:
            return True
        return len(visible_children) >= 8 and all(child.get("type") in VECTOR_TYPES for child in visible_children)

    def _is_simple_graphic_leaf(self, node: dict[str, Any]) -> bool:
        if node.get("children"):
            return False
        if node.get("type") in VECTOR_TYPES:
            return True
        if self._find_image_ref(node):
            return True
        if node.get("type") in IMAGE_HOST_TYPES and self._shape_style(node) is not None:
            return True
        return False

    def _graphic_leaf_coverage_ratio(
        self,
        node: dict[str, Any],
        visible_children: list[dict[str, Any]],
    ) -> float:
        node_bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        node_width = float(node_bounds.get("width", 0) or 0)
        node_height = float(node_bounds.get("height", 0) or 0)
        node_area = node_width * node_height
        if node_area <= 0:
            return 0.0
        child_area = 0.0
        for child in visible_children:
            child_bounds = child.get("absoluteBoundingBox") or child.get("absoluteRenderBounds") or {}
            child_area += float(child_bounds.get("width", 0) or 0) * float(child_bounds.get("height", 0) or 0)
        return child_area / node_area

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
        image_ref = self._find_image_ref(node)
        if image_ref and width_ratio < 0.7:
            return False
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
        box = self._preferred_box(node)
        return {
            "x": float(box.get("x", 0.0)) - section.bounds["x"],
            "y": float(box.get("y", 0.0)) - section.bounds["y"],
            "width": float(box.get("width", 0.0)),
            "height": float(box.get("height", 0.0)),
        }

    def _relative_render_bounds(self, section: SectionCandidate, node: dict[str, Any]) -> dict[str, float] | None:
        render_box = node.get("absoluteRenderBounds") or {}
        if not self._box_has_area(render_box):
            return None
        return {
            "x": float(render_box.get("x", 0.0)) - section.bounds["x"],
            "y": float(render_box.get("y", 0.0)) - section.bounds["y"],
            "width": float(render_box.get("width", 0.0)),
            "height": float(render_box.get("height", 0.0)),
        }

    def _preferred_box(self, node: dict[str, Any]) -> dict[str, Any]:
        absolute_box = node.get("absoluteBoundingBox") or {}
        render_box = node.get("absoluteRenderBounds") or {}
        if self._box_has_area(render_box) and not self._box_has_area(absolute_box):
            return render_box
        return absolute_box or render_box

    def _layout_metadata(
        self,
        node: dict[str, Any],
        *,
        fallback_strategy: str,
    ) -> dict[str, Any]:
        strategy = self._infer_layout_strategy(node, fallback_strategy=fallback_strategy)
        metadata = {
            "layout_mode": self._string_or_none(node.get("layoutMode")),
            "layout_wrap": self._string_or_none(node.get("layoutWrap")),
            "layout_positioning": self._string_or_none(node.get("layoutPositioning")),
            "layout_sizing_horizontal": self._floatless_string_or_none(node.get("layoutSizingHorizontal")),
            "layout_sizing_vertical": self._floatless_string_or_none(node.get("layoutSizingVertical")),
            "primary_axis_sizing_mode": self._string_or_none(node.get("primaryAxisSizingMode")),
            "counter_axis_sizing_mode": self._string_or_none(node.get("counterAxisSizingMode")),
            "primary_axis_align_items": self._string_or_none(node.get("primaryAxisAlignItems")),
            "counter_axis_align_items": self._string_or_none(node.get("counterAxisAlignItems")),
            "counter_axis_align_content": self._string_or_none(node.get("counterAxisAlignContent")),
            "item_spacing": self._number_or_none(node.get("itemSpacing")),
            "counter_axis_spacing": self._number_or_none(node.get("counterAxisSpacing")),
            "padding_top": self._number_or_none(node.get("paddingTop")),
            "padding_right": self._number_or_none(node.get("paddingRight")),
            "padding_bottom": self._number_or_none(node.get("paddingBottom")),
            "padding_left": self._number_or_none(node.get("paddingLeft")),
            "min_width": self._number_or_none(node.get("minWidth")),
            "max_width": self._number_or_none(node.get("maxWidth")),
            "min_height": self._number_or_none(node.get("minHeight")),
            "max_height": self._number_or_none(node.get("maxHeight")),
            "text_auto_resize": self._string_or_none(node.get("textAutoResize")),
            "clips_content": self._bool_or_none(node, "clipsContent"),
            "constraints": self._constraints_payload(node),
            "inferred_strategy": strategy,
            "inferred_flow": self._bool_or_none(
                {
                    "inferred_flow": self._infer_layout_is_flow(node),
                },
                "inferred_flow",
            ),
        }
        return {
            key: value
            for key, value in metadata.items()
            if value not in (None, "")
            and not (key == "constraints" and not value)
        }

    def _infer_layout_strategy(self, node: dict[str, Any], *, fallback_strategy: str) -> str:
        layout_mode = self._string_or_none(node.get("layoutMode"))
        layout_wrap = self._string_or_none(node.get("layoutWrap"))
        if layout_mode in {"HORIZONTAL", "VERTICAL"}:
            return "flow"
        if layout_wrap and layout_wrap != "NO_WRAP":
            return "flow"
        if node.get("type") in TEXT_TYPES:
            return "text"
        if node.get("children"):
            return "absolute"
        return fallback_strategy

    def _infer_layout_is_flow(self, node: dict[str, Any]) -> bool:
        layout_wrap = self._string_or_none(node.get("layoutWrap"))
        return bool(layout_wrap and layout_wrap != "NO_WRAP")

    def _constraints_payload(self, node: dict[str, Any]) -> dict[str, Any]:
        constraints = node.get("constraints")
        if isinstance(constraints, dict):
            return {
                key: value
                for key, value in constraints.items()
                if value not in (None, "")
            }
        return {}

    def _string_or_none(self, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _floatless_string_or_none(self, value: Any) -> str | None:
        text = self._string_or_none(value)
        return text

    def _number_or_none(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _bool_or_none(self, node: dict[str, Any], key: str) -> bool | None:
        if key not in node:
            return None
        return bool(node.get(key))

    def _box_has_area(self, box: dict[str, Any]) -> bool:
        try:
            width = float(box.get("width", 0.0) or 0.0)
            height = float(box.get("height", 0.0) or 0.0)
        except (AttributeError, TypeError, ValueError):
            return False
        return width > 0 and height > 0

    def _shape_style(self, node: dict[str, Any]) -> dict[str, Any] | None:
        fills = node.get("fills") or []
        strokes = node.get("strokes") or []
        style: dict[str, Any] = {}

        fill_color = self._first_solid_paint_color(fills)
        if fill_color:
            style["background"] = fill_color

        border = self._stroke_css(node)
        if border:
            style["border"] = border

        border_radius = self._border_radius_css(node)
        if border_radius:
            style["borderRadius"] = border_radius

        box_shadow = self._box_shadow_css(node)
        if box_shadow:
            style["boxShadow"] = box_shadow

        opacity = node.get("opacity")
        if opacity not in (None, ""):
            style["opacity"] = opacity

        if not style:
            return None

        if not fill_color and not strokes:
            return None
        return style

    def _first_solid_paint_color(self, paints: list[dict[str, Any]]) -> str | None:
        for paint in paints:
            if not isinstance(paint, dict) or paint.get("visible", True) is False:
                continue
            if paint.get("type") != "SOLID":
                continue
            color = paint.get("color") or {}
            alpha = paint.get("opacity", color.get("a", 1))
            normalized = {
                "r": color.get("r", 0),
                "g": color.get("g", 0),
                "b": color.get("b", 0),
                "a": alpha,
            }
            return self._rgba_to_css(normalized)
        return None

    def _stroke_css(self, node: dict[str, Any]) -> str | None:
        strokes = node.get("strokes") or []
        color = self._first_solid_paint_color(strokes)
        if not color:
            return None
        weight = node.get("strokeWeight") or 1
        return f"{float(weight):.1f}px solid {color}"

    def _border_radius_css(self, node: dict[str, Any]) -> str | None:
        corner_radius = node.get("cornerRadius")
        if corner_radius not in (None, ""):
            return f"{float(corner_radius):.1f}px"
        corners = node.get("rectangleCornerRadii") or []
        if len(corners) == 4:
            return " ".join(f"{float(value):.1f}px" for value in corners)
        return None

    def _box_shadow_css(self, node: dict[str, Any]) -> str | None:
        shadows: list[str] = []
        for effect in node.get("effects") or []:
            if not isinstance(effect, dict) or effect.get("visible", True) is False:
                continue
            if effect.get("type") not in {"DROP_SHADOW", "INNER_SHADOW"}:
                continue
            offset = effect.get("offset") or {}
            radius = float(effect.get("radius", 0) or 0)
            spread = float(effect.get("spread", 0) or 0)
            color = self._rgba_to_css(effect.get("color") or {})
            if not color:
                continue
            inset = " inset" if effect.get("type") == "INNER_SHADOW" else ""
            shadows.append(
                f"{float(offset.get('x', 0) or 0):.1f}px "
                f"{float(offset.get('y', 0) or 0):.1f}px "
                f"{radius:.1f}px "
                f"{spread:.1f}px {color}{inset}"
            )
        return ", ".join(shadows) if shadows else None

    def _rgba_to_css(self, color: dict[str, Any]) -> str | None:
        try:
            red = self._clamp_channel(color.get("r", 0))
            green = self._clamp_channel(color.get("g", 0))
            blue = self._clamp_channel(color.get("b", 0))
            alpha = float(color.get("a", 1) or 1)
        except (AttributeError, TypeError, ValueError):
            return None
        alpha = max(0.0, min(alpha, 1.0))
        if alpha == 1.0:
            return f"rgb({red} {green} {blue})"
        return f"rgb({red} {green} {blue} / {alpha:.3f})"

    def _clamp_channel(self, value: Any) -> int:
        channel = float(value or 0)
        if channel <= 1:
            channel *= 255
        return max(0, min(int(round(channel)), 255))

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

    def _has_direct_composite_children(self, node: dict[str, Any]) -> bool:
        visible_children = [
            child
            for child in node.get("children", [])
            if isinstance(child, dict) and child.get("visible", True)
        ]
        if len(visible_children) < 2:
            return False
        for child in visible_children:
            if not isinstance(child, dict) or not child.get("visible", True):
                continue
            if child.get("isMask") is True:
                return True
            if self._node_contains_override_image(child):
                return True
            if self._find_image_ref(child):
                return True
        return False

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

    def _is_complex_graphic_subtree(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return False
        if self._subtree_contains_visible_text(node):
            return False
        graphic_leaf_count = self._graphic_leaf_count(node)
        if graphic_leaf_count < 6:
            return False
        bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds") or {}
        width = float(bounds.get("width", 0) or 0)
        height = float(bounds.get("height", 0) or 0)
        area = width * height
        return area >= 2500 or max(width, height) >= 96

    def _should_render_composite_as_svg(self, node: dict[str, Any]) -> bool:
        if self._subtree_contains_mask(node):
            return False
        if self._subtree_contains_override_image(node):
            return False
        if self._subtree_contains_image_fill(node):
            return False
        return self._subtree_contains_only_vector_drawables(node)

    def _subtree_contains_image_fill(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return False
        if self._find_image_ref(node):
            return True
        return any(self._subtree_contains_image_fill(child) for child in node.get("children", []))

    def _subtree_contains_only_vector_drawables(self, node: dict[str, Any]) -> bool:
        if not node.get("visible", True):
            return True
        children = [child for child in node.get("children", []) if child.get("visible", True)]
        if children:
            return all(self._subtree_contains_only_vector_drawables(child) for child in children)
        node_type = node.get("type")
        if node_type in VECTOR_TYPES:
            return True
        if node_type in IMAGE_HOST_TYPES and self._shape_style(node) is not None:
            return True
        return False

    def _is_image_wrapper_group(self, node: dict[str, Any]) -> bool:
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return False
        visible_children = [
            child
            for child in node.get("children", [])
            if isinstance(child, dict) and child.get("visible", True)
        ]
        if len(visible_children) != 1:
            return False
        if self._subtree_contains_visible_text(node):
            return False
        child = visible_children[0]
        if not self._find_image_ref(child):
            return False
        parent_name = str(node.get("name") or "")
        child_name = str(child.get("name") or "").strip().lower()
        if FILE_LIKE_NAME_RE.search(parent_name):
            return True
        return child_name in {"layer 0", "layer0", "image", "photo"}

    def _graphic_leaf_count(self, node: dict[str, Any]) -> int:
        if not node.get("visible", True):
            return 0
        node_type = node.get("type")
        children = [child for child in node.get("children", []) if child.get("visible", True)]
        if node_type in VECTOR_TYPES:
            return 1
        if node_type in IMAGE_HOST_TYPES and not children:
            return 1
        return sum(self._graphic_leaf_count(child) for child in children)

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
        name = (node.get("name") or "").lower()
        if tag in {"ul", "ol"}:
            return "list"
        if tag == "li":
            return "list-item"
        if self._name_has_prefix(name, ("label", "libelle")):
            return "label"
        if self._name_has_prefix(name, ("button", "btn")):
            return "button"
        if tag == "h1":
            return "hero-title"
        if tag in {"h2", "h4", "h5", "h6"}:
            return "heading"
        if tag == "h3":
            return "subheading"
        return "body"

    def _name_has_prefix(self, name: str, prefixes: tuple[str, ...]) -> bool:
        normalized = "-".join(NAME_TOKEN_RE.findall(name.lower()))
        return any(normalized == prefix or normalized.startswith(f"{prefix}-") for prefix in prefixes)

    def _is_semantic_wrapper_container(self, node: dict[str, Any]) -> bool:
        if node.get("type") not in COMPOSITE_HOST_TYPES:
            return False
        name = str(node.get("name") or node.get("id") or "")
        return self._name_has_prefix(name, SEMANTIC_WRAPPER_PREFIXES)

    def _subtree_contains_semantic_wrapper(self, node: dict[str, Any], *, include_self: bool = True) -> bool:
        if not node.get("visible", True):
            return False
        if include_self and self._is_semantic_wrapper_container(node):
            return True
        return any(
            self._subtree_contains_semantic_wrapper(child, include_self=True)
            for child in node.get("children", [])
            if isinstance(child, dict)
        )
