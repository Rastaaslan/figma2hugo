from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from figma2hugo.config import normalize_node_id


@dataclass(slots=True)
class ParsedFigmaUrl:
    figma_url: str
    file_key: str
    node_id: str | None
    page_hint: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "figma_url": self.figma_url,
            "file_key": self.file_key,
            "node_id": self.node_id,
            "page_hint": self.page_hint,
        }


def parse_figma_url(figma_url: str) -> ParsedFigmaUrl:
    parsed = urlparse(figma_url)
    if parsed.netloc not in {"www.figma.com", "figma.com"}:
        raise ValueError(f"Unsupported Figma host: {parsed.netloc or '<empty>'}")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("The provided Figma URL does not contain a file key.")

    if parts[0] not in {"file", "design", "proto"}:
        raise ValueError(f"Unsupported Figma URL type: {parts[0]}")

    file_key = parts[1]
    page_hint = unquote(parts[2]) if len(parts) >= 3 else None
    query = parse_qs(parsed.query)
    node_id = query.get("node-id", query.get("node_id", [None]))[0]
    node_id = normalize_node_id(node_id) if node_id else None
    return ParsedFigmaUrl(
        figma_url=figma_url,
        file_key=file_key,
        node_id=node_id,
        page_hint=page_hint,
    )
