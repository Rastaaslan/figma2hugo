from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from figma2hugo.local_config import get_local_figma_token


class FigmaRestError(RuntimeError):
    """Raised when the Figma REST API is unavailable or rejects a request."""


@dataclass(slots=True)
class FigmaRestClient:
    token: str | None
    base_url: str = "https://api.figma.com/v1"
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "FigmaRestClient":
        token = get_local_figma_token()
        base_url = os.getenv("FIGMA_API_BASE_URL", "https://api.figma.com/v1")
        return cls(token=token, base_url=base_url)

    @property
    def available(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise FigmaRestError(
                "Figma REST token missing. Set FIGMA_ACCESS_TOKEN to enable structured extraction."
            )
        return {"X-Figma-Token": self.token}

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        retry_delay = 1.0
        for attempt in range(4):
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, headers=self._headers(), params=params)
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else retry_delay
                except ValueError:
                    delay = retry_delay
                time.sleep(delay)
                retry_delay = min(retry_delay * 2.0, 8.0)
                continue
            if response.is_error:
                detail = response.text.strip() or response.reason_phrase
                raise FigmaRestError(f"{method} {url} failed with {response.status_code}: {detail}")
            return response.json()
        raise FigmaRestError(f"{method} {url} failed after retries.")

    def get_file_nodes(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        depth: int | None = None,
        geometry_paths: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ids": ",".join(node_ids)}
        if depth is not None:
            params["depth"] = depth
        if geometry_paths:
            params["geometry"] = "paths"
        return self._request("GET", f"/files/{file_key}/nodes", params=params)

    def get_file(
        self,
        file_key: str,
        *,
        depth: int | None = None,
        geometry_paths: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if depth is not None:
            params["depth"] = depth
        if geometry_paths:
            params["geometry"] = "paths"
        return self._request("GET", f"/files/{file_key}", params=params)

    def get_render_urls(
        self,
        file_key: str,
        node_ids: list[str],
        *,
        image_format: str = "png",
        scale: int = 2,
        use_absolute_bounds: bool = True,
        contents_only: bool = False,
    ) -> dict[str, str | None]:
        params: dict[str, Any] = {
            "ids": ",".join(node_ids),
            "format": image_format,
            "scale": scale,
            "use_absolute_bounds": str(use_absolute_bounds).lower(),
            "contents_only": str(contents_only).lower(),
        }
        response = self._request("GET", f"/images/{file_key}", params=params)
        return response.get("images", {})

    def get_image_fills(self, file_key: str) -> dict[str, str]:
        response = self._request("GET", f"/files/{file_key}/images")
        return response.get("images", {})

    def get_local_variables(self, file_key: str) -> dict[str, Any]:
        try:
            return self._request("GET", f"/files/{file_key}/variables/local")
        except FigmaRestError:
            return {}
