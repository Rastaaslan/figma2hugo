"""Helpers de configuration partages par la CLI et l'interface desktop."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SUPPORTED_FIGMA_HOSTS = {"figma.com", "www.figma.com"}
_SUPPORTED_FIGMA_PATHS = {"file", "design", "proto"}
_FIGMA_PATH_PATTERN = re.compile(
    r"^/(?P<url_kind>file|design|proto)/(?P<file_key>[^/?#]+)/?(?P<slug>[^?#]*)$"
)
_NODE_ID_PATTERN = re.compile(r"^\d+(?:-\d+)+$")


class FidelityMode(StrEnum):
    EXACT = "exact"
    BALANCED = "balanced"
    SEMANTIC = "semantic"


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class _ConfigModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class FigmaUrl(_ConfigModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str = Field(min_length=1)
    url_kind: str = Field(pattern="^(file|design|proto)$")
    file_key: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    slug: str | None = None

    @field_validator("url_kind")
    @classmethod
    def validate_url_kind(cls, value: str) -> str:
        if value not in _SUPPORTED_FIGMA_PATHS:
            msg = f"Unsupported Figma URL kind: {value}"
            raise ValueError(msg)
        return value

    @classmethod
    def parse(cls, value: str) -> Self:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Figma URL must start with http:// or https://.")
        if parsed.netloc not in _SUPPORTED_FIGMA_HOSTS:
            raise ValueError("Figma URL host must be figma.com or www.figma.com.")

        match = _FIGMA_PATH_PATTERN.match(parsed.path)
        if not match:
            raise ValueError(
                "Figma URL path must look like /file/<file_key>/..., /design/<file_key>/..., or /proto/<file_key>/... ."
            )

        query = parse_qs(parsed.query)
        node_values = query.get("node-id") or query.get("node_id")
        if not node_values or not node_values[0]:
            raise ValueError("Figma URL must include a node-id query parameter.")

        slug = match.group("slug") or None
        return cls(
            source_url=value,
            url_kind=match.group("url_kind"),
            file_key=match.group("file_key"),
            node_id=normalize_node_id(node_values[0]),
            slug=slug,
        )


def normalize_node_id(raw_value: str) -> str:
    normalized = unquote(raw_value).strip()
    if ":" in normalized:
        return normalized
    if _NODE_ID_PATTERN.match(normalized):
        return normalized.replace("-", ":")
    return normalized


def parse_figma_url(value: str) -> FigmaUrl:
    return FigmaUrl.parse(value)
