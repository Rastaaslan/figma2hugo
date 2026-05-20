"""Recupere les donnees brutes Figma et analyse les URLs collees par l'utilisateur."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from figma2hugo.local_config import get_local_figma_token

FIGMA_API_BASE_URL = "https://api.figma.com/v1"
SUPPORTED_FIGMA_HOSTS = {"figma.com", "www.figma.com"}
FIGMA_PATH_RE = re.compile(r"^/(?P<kind>file|design|proto)/(?P<file_key>[^/?#]+)")
NODE_ID_DASH_RE = re.compile(r"^\d+(?:-\d+)+$")
MAX_REQUEST_ATTEMPTS = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class FigmaPipelineFetchError(RuntimeError):
    """Raised when the standalone pipeline Figma fetcher cannot retrieve raw data."""


@dataclass(frozen=True, slots=True)
class FigmaPipelineTarget:
    source_url: str
    file_key: str
    node_id: str


def fetch_raw_node_from_figma(
    figma_url: str,
    *,
    token: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 60.0,
    client: httpx.Client | None = None,
    include_image_fills: bool = True,
) -> dict[str, Any]:
    target = parse_figma_pipeline_url(figma_url)
    resolved_base_url = base_url if base_url is not None else os.getenv("FIGMA_API_BASE_URL")
    rest = FigmaPipelineRawClient(
        token=token or resolve_figma_pipeline_token(),
        base_url=resolved_base_url or FIGMA_API_BASE_URL,
        timeout_seconds=timeout_seconds,
        client=client,
    )
    return rest.get_node_document(target, include_image_fills=include_image_fills)


def parse_figma_pipeline_url(value: str) -> FigmaPipelineTarget:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Figma URL must start with http:// or https://.")
    if parsed.netloc not in SUPPORTED_FIGMA_HOSTS:
        raise ValueError("Figma URL host must be figma.com or www.figma.com.")
    path_match = FIGMA_PATH_RE.match(parsed.path)
    if not path_match:
        raise ValueError("Figma URL path must look like /file/<file_key> or /design/<file_key>.")
    query = parse_qs(parsed.query)
    node_values = query.get("node-id") or query.get("node_id")
    if not node_values or not node_values[0]:
        raise ValueError("Figma URL must include a node-id query parameter.")
    return FigmaPipelineTarget(
        source_url=value,
        file_key=path_match.group("file_key"),
        node_id=_normalize_node_id(node_values[0]),
    )


@dataclass(slots=True)
class FigmaPipelineRawClient:
    token: str | None
    base_url: str = FIGMA_API_BASE_URL
    timeout_seconds: float = 60.0
    client: httpx.Client | None = None

    def get_node_document(
        self,
        target: FigmaPipelineTarget,
        *,
        include_image_fills: bool = True,
    ) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"/files/{target.file_key}/nodes",
            params={"ids": target.node_id, "geometry": "paths"},
        )
        nodes = payload.get("nodes")
        if not isinstance(nodes, dict):
            raise FigmaPipelineFetchError("Figma response does not contain a nodes object.")
        node_payload = nodes.get(target.node_id)
        if not isinstance(node_payload, dict):
            raise FigmaPipelineFetchError(f"Figma response does not contain node {target.node_id}.")
        document = node_payload.get("document")
        if not isinstance(document, dict):
            raise FigmaPipelineFetchError(f"Figma node {target.node_id} has no document payload.")
        if include_image_fills:
            image_fills = self.get_image_fills(target.file_key)
            if image_fills:
                document = _with_image_fill_urls(document, image_fills)
            missing_image_node_ids = _image_fill_node_ids_without_url(document)
            if missing_image_node_ids:
                render_urls = self.get_node_render_urls(target.file_key, missing_image_node_ids)
                if render_urls:
                    document = _with_node_render_urls(document, render_urls)
        return document

    def get_image_fills(self, file_key: str) -> dict[str, str]:
        payload = self._request("GET", f"/files/{file_key}/images", params={})
        images = payload.get("images")
        if not isinstance(images, dict):
            return {}
        return {str(key): str(value) for key, value in images.items() if value}

    def get_node_render_urls(self, file_key: str, node_ids: list[str]) -> dict[str, str]:
        urls: dict[str, str] = {}
        for chunk in _chunks(node_ids, size=100):
            payload = self._request(
                "GET",
                f"/images/{file_key}",
                params={"ids": ",".join(chunk), "format": "png", "scale": 1},
            )
            images = payload.get("images")
            if not isinstance(images, dict):
                continue
            urls.update({str(key): str(value) for key, value in images.items() if value})
        return urls

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.token:
            raise FigmaPipelineFetchError(
                "Figma REST token missing. Set FIGMA_ACCESS_TOKEN or FIGMA_TOKEN for pipeline fetch."
            )
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        retry_delay = 1.0
        for attempt in range(MAX_REQUEST_ATTEMPTS):
            try:
                response = self._send(method, url, params=params)
            except httpx.TransportError as exc:
                if attempt < MAX_REQUEST_ATTEMPTS - 1:
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2.0, 8.0)
                    continue
                raise FigmaPipelineFetchError(
                    f"{method} {url} failed after retries: {exc}"
                ) from exc
            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt < MAX_REQUEST_ATTEMPTS - 1
            ):
                delay = _retry_delay(response, fallback=retry_delay)
                time.sleep(delay)
                retry_delay = min(retry_delay * 2.0, 8.0)
                continue
            if response.is_error:
                detail = response.text.strip() or response.reason_phrase
                raise FigmaPipelineFetchError(
                    f"{method} {url} failed with {response.status_code}: {detail}"
                )
            decoded = response.json()
            if not isinstance(decoded, dict):
                raise FigmaPipelineFetchError("Figma response JSON root must be an object.")
            return decoded
        raise FigmaPipelineFetchError(f"{method} {url} failed after retries.")

    def _send(self, method: str, url: str, *, params: dict[str, Any]) -> httpx.Response:
        headers = {"X-Figma-Token": self.token or ""}
        if self.client is not None:
            return self.client.request(method, url, headers=headers, params=params)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.request(method, url, headers=headers, params=params)


def _token_from_env() -> str | None:
    return get_local_figma_token() or os.getenv("FIGMA_ACCESS_TOKEN") or os.getenv("FIGMA_TOKEN")


def resolve_figma_pipeline_token() -> str | None:
    return _token_from_env()


def _normalize_node_id(raw_value: str) -> str:
    normalized = unquote(raw_value).strip()
    if ":" in normalized:
        return normalized
    if NODE_ID_DASH_RE.match(normalized):
        return normalized.replace("-", ":")
    return normalized


def _retry_delay(response: httpx.Response, *, fallback: float) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return fallback
    try:
        return float(retry_after)
    except ValueError:
        return fallback


def _with_image_fill_urls(node: dict[str, Any], image_fills: dict[str, str]) -> dict[str, Any]:
    cloned = dict(node)
    fills = cloned.get("fills")
    if isinstance(fills, list):
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            image_ref = fill.get("imageRef")
            if image_ref and str(image_ref) in image_fills:
                cloned.setdefault("pipelineImageRef", str(image_ref))
                cloned.setdefault("pipelineImageUrl", image_fills[str(image_ref)])
                break
    children = cloned.get("children")
    if isinstance(children, list):
        cloned["children"] = [
            _with_image_fill_urls(child, image_fills) if isinstance(child, dict) else child
            for child in children
        ]
    return cloned


def _image_fill_node_ids_without_url(node: dict[str, Any]) -> list[str]:
    node_ids: list[str] = []
    if _has_image_fill(node) and not node.get("pipelineImageUrl"):
        node_id = node.get("id")
        if node_id:
            node_ids.append(str(node_id))
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                node_ids.extend(_image_fill_node_ids_without_url(child))
    return node_ids


def _has_image_fill(node: dict[str, Any]) -> bool:
    fills = node.get("fills")
    if not isinstance(fills, list):
        return False
    return any(
        isinstance(fill, dict)
        and fill.get("visible") is not False
        and str(fill.get("type", "")).upper() == "IMAGE"
        for fill in fills
    )


def _with_node_render_urls(node: dict[str, Any], render_urls: dict[str, str]) -> dict[str, Any]:
    cloned = dict(node)
    node_id = cloned.get("id")
    if node_id and str(node_id) in render_urls:
        cloned.setdefault("pipelineImageUrl", render_urls[str(node_id)])
    children = cloned.get("children")
    if isinstance(children, list):
        cloned["children"] = [
            _with_node_render_urls(child, render_urls) if isinstance(child, dict) else child
            for child in children
        ]
    return cloned


def _chunks(values: list[str], *, size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
