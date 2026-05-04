from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from figma2hugo.figma_reader.rest_client import FigmaRestClient, FigmaRestError


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
                    local_path = self._download_url(
                        source_url,
                        assets_dir / self._asset_filename(asset),
                        client,
                    )
                    self._optimize_lightweight_raster(local_path, asset)
                    asset["localPath"] = local_path
                    continue

                if not self.rest_client.available or not asset.get("nodeId"):
                    continue

                if asset.get("isVector"):
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
                    scale=1,
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
            batch_urls = self._collect_render_urls_for_batch(
                file_key,
                batch,
                image_format=image_format,
                scale=scale,
                use_absolute_bounds=use_absolute_bounds,
                contents_only=contents_only,
            )
            render_urls.update(batch_urls)
        return render_urls

    def _collect_render_urls_for_batch(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        image_format: str,
        scale: int,
        use_absolute_bounds: bool,
        contents_only: bool,
    ) -> dict[str, str | None]:
        try:
            return self.rest_client.get_render_urls(
                file_key,
                node_ids,
                image_format=image_format,
                scale=scale,
                use_absolute_bounds=use_absolute_bounds,
                contents_only=contents_only,
            )
        except FigmaRestError as exc:
            if not self._is_render_timeout_error(exc) or len(node_ids) <= 1:
                raise

            midpoint = max(1, len(node_ids) // 2)
            left_batch = node_ids[:midpoint]
            right_batch = node_ids[midpoint:]
            render_urls: dict[str, str | None] = {}
            render_urls.update(
                self._collect_render_urls_for_batch(
                    file_key,
                    left_batch,
                    image_format=image_format,
                    scale=scale,
                    use_absolute_bounds=use_absolute_bounds,
                    contents_only=contents_only,
                )
            )
            render_urls.update(
                self._collect_render_urls_for_batch(
                    file_key,
                    right_batch,
                    image_format=image_format,
                    scale=scale,
                    use_absolute_bounds=use_absolute_bounds,
                    contents_only=contents_only,
                )
            )
            return render_urls

    def _is_render_timeout_error(self, exc: FigmaRestError) -> bool:
        return "render timeout" in str(exc).strip().lower()

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

    def _optimize_lightweight_raster(self, local_path: str, asset: dict[str, Any]) -> None:
        target_path = Path(local_path)
        if target_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            return

        target_width, target_height = self._lightweight_target_dimensions(asset)
        if target_width <= 0 or target_height <= 0:
            return

        try:
            with Image.open(target_path) as image:
                working = ImageOps.exif_transpose(image)
                if working.width <= target_width and working.height <= target_height:
                    return

                resized = working.copy()
                resized.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
                save_kwargs: dict[str, Any] = {}
                format_name = (image.format or "").upper()

                if format_name in {"JPEG", "JPG"}:
                    if resized.mode not in {"RGB", "L"}:
                        resized = resized.convert("RGB")
                    save_kwargs.update({"format": "JPEG", "quality": 82, "optimize": True, "progressive": True})
                elif format_name == "WEBP":
                    save_kwargs.update({"format": "WEBP", "quality": 80, "method": 6})
                else:
                    save_kwargs.update({"format": "PNG", "optimize": True})

                temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
                resized.save(temp_path, **save_kwargs)
                temp_path.replace(target_path)
        except (OSError, UnidentifiedImageError):  # pragma: no cover - file format edge cases
            return

    def _lightweight_target_dimensions(self, asset: dict[str, Any]) -> tuple[int, int]:
        bounds = asset.get("bounds", {}) or {}
        width = int(round(float(asset.get("width") or bounds.get("width") or 0) or 0))
        height = int(round(float(asset.get("height") or bounds.get("height") or 0) or 0))
        return max(width, 0), max(height, 0)
