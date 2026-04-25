from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.config import GenerateConfig, OutputMode, parse_figma_url


def test_parse_figma_url_normalizes_node_id() -> None:
    parsed = parse_figma_url("https://www.figma.com/design/FILE123/Page?node-id=42-7")

    assert parsed.file_key == "FILE123"
    assert parsed.node_id == "42:7"
    assert parsed.url_kind == "design"


def test_parse_figma_url_accepts_encoded_node_id() -> None:
    parsed = parse_figma_url("https://www.figma.com/file/FILE123/Page?node-id=42%3A7")

    assert parsed.file_key == "FILE123"
    assert parsed.node_id == "42:7"
    assert parsed.url_kind == "file"


def test_parse_figma_url_rejects_missing_node_id() -> None:
    with pytest.raises(ValueError, match="node-id"):
        parse_figma_url("https://www.figma.com/design/FILE123/Page")


def test_generate_config_keeps_mode_and_target_dir() -> None:
    figma = parse_figma_url("https://www.figma.com/design/FILE123/Page?node-id=1-2")
    config = GenerateConfig(figma=figma, target_dir="dist", output_mode=OutputMode.STATIC)

    assert config.output_mode is OutputMode.STATIC
    assert config.target_dir == Path("dist")
