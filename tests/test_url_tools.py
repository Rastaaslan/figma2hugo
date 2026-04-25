from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.figma_reader.url_tools import parse_figma_url


def test_reader_parse_figma_url_normalizes_node_id() -> None:
    parsed = parse_figma_url("https://www.figma.com/design/FILE123/Page?node-id=42-7")

    assert parsed.file_key == "FILE123"
    assert parsed.node_id == "42:7"


def test_reader_parse_figma_url_accepts_encoded_node_id() -> None:
    parsed = parse_figma_url("https://www.figma.com/file/FILE123/Page?node-id=42%3A7")

    assert parsed.file_key == "FILE123"
    assert parsed.node_id == "42:7"
