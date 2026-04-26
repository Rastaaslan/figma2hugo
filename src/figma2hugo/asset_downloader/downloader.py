from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from figma2hugo.figma_reader.rest_client import FigmaRestClient


SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class AssetDownloader:
    MAX_RENDER_IDS_PER_REQUEST = 200
    MAX_RENDER_IDS_QUERY_CHARS = 6000

    def __init__(self, rest_client: FigmaRestClient | None = None) -> None:
        self.rest_client = rest_client or FigmaRestClient.from_env()

    def materialize_assets(
        self,
        file_key: str,
        assets: list[dict[str, Any]],
        assets_dir: Path,
        *,
        asset_mode: str = "mixed",
    ) -> list[dict[str, Any]]:
        assets_dir.mkdir(parents=True, exist_ok=True)

        render_queue_svg: list[str] = []
        render_queue_png: list[str] = []
        asset_map = {asset["nodeId"]: asset for asset in assets if asset.get("nodeId")}

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            for asset in assets:
                if asset.get("renderMode") == "shape" or asset.get("format") == "shape":
                    continue
                source_url = asset.get("sourceUrl")
                if source_url:
                    asset["localPath"] = self._download_url(
                        source_url,
                        assets_dir / self._asset_filename(asset),
                        client,
                    )
                    continue

                if not self.rest_client.available or not asset.get("nodeId"):
                    continue

                if asset_mode == "svg-first" and asset.get("isVector"):
                    render_queue_svg.append(asset["nodeId"])
                elif asset_mode == "raster-first":
                    render_queue_png.append(asset["nodeId"])
                elif asset.get("isVector"):
                    render_queue_svg.append(asset["nodeId"])
                else:
                    render_queue_png.append(asset["nodeId"])

            if self.rest_client.available and render_queue_svg:
                render_urls = self._collect_render_urls(
                    file_key,
                    render_queue_svg,
                    image_format="svg",
                    scale=1,
                    use_absolute_bounds=False,
                    contents_only=True,
                )
                self._download_rendered_assets(render_urls, asset_map, assets_dir, client)

            if self.rest_client.available and render_queue_png:
                render_urls = self._collect_render_urls(
                    file_key,
                    render_queue_png,
                    image_format="png",
                    scale=2,
                    use_absolute_bounds=False,
                    contents_only=True,
                )
                self._download_rendered_assets(render_urls, asset_map, assets_dir, client)

        return assets

    def _download_rendered_assets(
        self,
        render_urls: dict[str, str | None],
        asset_map: dict[str, dict[str, Any]],
        assets_dir: Path,
        client: httpx.Client,
    ) -> None:
        for node_id, url in render_urls.items():
            if not url or node_id not in asset_map:
                continue
            asset = asset_map[node_id]
            target = assets_dir / self._asset_filename(asset)
            asset["localPath"] = self._download_url(url, target, client)

    def _collect_render_urls(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        image_format: str,
        scale: int,
        use_absolute_bounds: bool,
        contents_only: bool,
    ) -> dict[str, str | None]:
        render_urls: dict[str, str | None] = {}
        for batch in self._iter_render_batches(node_ids):
            batch_urls = self.rest_client.get_render_urls(
                file_key,
                batch,
                image_format=image_format,
                scale=scale,
                use_absolute_bounds=use_absolute_bounds,
                contents_only=contents_only,
            )
            render_urls.update(batch_urls)
        return render_urls

    def _iter_render_batches(self, node_ids: list[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_chars = 0

        for node_id in node_ids:
            added_chars = len(node_id) + (1 if current_batch else 0)
            would_exceed_count = len(current_batch) >= self.MAX_RENDER_IDS_PER_REQUEST
            would_exceed_chars = (current_chars + added_chars) > self.MAX_RENDER_IDS_QUERY_CHARS
            if current_batch and (would_exceed_count or would_exceed_chars):
                batches.append(current_batch)
                current_batch = [node_id]
                current_chars = len(node_id)
                continue

            current_batch.append(node_id)
            current_chars += added_chars

        if current_batch:
            batches.append(current_batch)
        return batches

    def _download_url(self, url: str, target: Path, client: httpx.Client) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            return target.as_posix()
        response = client.get(url)
        response.raise_for_status()
        target.write_bytes(response.content)
        return target.as_posix()

    def _asset_filename(self, asset: dict[str, Any]) -> str:
        base_name = SAFE_NAME_RE.sub("-", asset.get("name") or asset.get("nodeId") or "asset").strip("-")
        node_id = SAFE_NAME_RE.sub("-", asset.get("nodeId") or "node").strip("-")
        suffix = SAFE_NAME_RE.sub("", (asset.get("format") or "png").lower()).strip(".") or "png"
        return f"{base_name or 'asset'}-{node_id or 'node'}.{suffix}"
