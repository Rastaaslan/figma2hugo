from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

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


class _FakeRestClient:
    available = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict[str, object]]] = []

    def get_render_urls(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        image_format: str = "png",
        scale: int = 2,
        use_absolute_bounds: bool = True,
        contents_only: bool = False,
    ) -> dict[str, str]:
        self.calls.append(
            (
                file_key,
                list(node_ids),
                {
                    "image_format": image_format,
                    "scale": scale,
                    "use_absolute_bounds": use_absolute_bounds,
                    "contents_only": contents_only,
                },
            )
        )
        return {node_id: f"https://example.test/{node_id}.{image_format}" for node_id in node_ids}


def test_asset_downloader_batches_large_render_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    rest_client = _FakeRestClient()
    downloader = AssetDownloader(rest_client)
    downloader.MAX_RENDER_IDS_PER_REQUEST = 50
    downloaded: list[str] = []
    scratch_root = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "tests"
    scratch_root.mkdir(parents=True, exist_ok=True)

    def fake_download_rendered_assets(
        render_urls: dict[str, str | None],
        asset_map: dict[str, dict[str, object]],
        assets_dir: Path,
        client: object,
    ) -> None:
        for node_id in render_urls:
            downloaded.append(node_id)
            asset_map[node_id]["localPath"] = str(assets_dir / f"{node_id.replace(':', '-')}.svg")

    monkeypatch.setattr(downloader, "_download_rendered_assets", fake_download_rendered_assets)

    assets = [
        {
            "nodeId": f"{index}:1",
            "name": f"Vector {index}",
            "format": "svg",
            "isVector": True,
        }
        for index in range(55)
    ]

    with tempfile.TemporaryDirectory(dir=str(scratch_root)) as temp_dir:
        materialized = downloader.materialize_assets(
            "file-key",
            assets,
            Path(temp_dir),
            asset_mode="svg-first",
        )

    assert [len(call[1]) for call in rest_client.calls] == [50, 5]
    assert downloaded == [asset["nodeId"] for asset in assets]
    assert all(asset.get("localPath") for asset in materialized)


def test_asset_downloader_batches_by_query_length(monkeypatch: pytest.MonkeyPatch) -> None:
    rest_client = _FakeRestClient()
    downloader = AssetDownloader(rest_client)
    downloader.MAX_RENDER_IDS_PER_REQUEST = 99
    downloader.MAX_RENDER_IDS_QUERY_CHARS = 12
    scratch_root = Path(__file__).resolve().parents[1] / ".figma2hugo-scratch" / "tests"
    scratch_root.mkdir(parents=True, exist_ok=True)

    def fake_download_rendered_assets(
        render_urls: dict[str, str | None],
        asset_map: dict[str, dict[str, object]],
        assets_dir: Path,
        client: object,
    ) -> None:
        for node_id in render_urls:
            asset_map[node_id]["localPath"] = str(assets_dir / f"{node_id.replace(':', '-')}.png")

    monkeypatch.setattr(downloader, "_download_rendered_assets", fake_download_rendered_assets)

    assets = [
        {"nodeId": "1234:5678", "name": "A", "format": "png", "isVector": False},
        {"nodeId": "2234:5678", "name": "B", "format": "png", "isVector": False},
        {"nodeId": "3234:5678", "name": "C", "format": "png", "isVector": False},
    ]

    with tempfile.TemporaryDirectory(dir=str(scratch_root)) as temp_dir:
        downloader.materialize_assets("file-key", assets, Path(temp_dir), asset_mode="raster-first")

    assert [call[1] for call in rest_client.calls] == [["1234:5678"], ["2234:5678"], ["3234:5678"]]
