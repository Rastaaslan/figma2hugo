from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.asset_downloader import AssetDownloader


def test_asset_filename_sanitizes_windows_unsafe_node_ids() -> None:
    filename = AssetDownloader()._asset_filename(
        {
            "name": "Footer BG",
            "nodeId": "3:75",
            "format": "svg",
        }
    )

    assert filename == "Footer-BG-3-75.svg"
    assert ":" not in filename
