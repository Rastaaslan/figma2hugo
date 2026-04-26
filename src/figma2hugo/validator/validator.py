from __future__ import annotations

import contextlib
import functools
import html
import http.server
import json
import math
import re
import threading
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


class SiteValidator:
    def validate(
        self,
        target_dir: Path,
        *,
        mode: str | None = None,
        against_reference: Path | None = None,
    ) -> dict[str, Any]:
        mode = mode or self.detect_mode(target_dir)
        page_model = self._load_page_model(target_dir, mode)
        report = {
            "buildOk": True,
            "visualScore": None,
            "missingAssets": [],
            "missingTexts": [],
            "warnings": list(page_model.get("warnings", [])),
        }

        if mode == "hugo":
            report["buildOk"] = self._validate_hugo_build(target_dir, report["warnings"])

        html_path = self._html_path(target_dir, mode)
        html_content = html_path.read_text(encoding="utf-8")
        report["missingAssets"] = self._missing_assets(target_dir, page_model, mode)
        report["missingTexts"] = self._missing_texts(html_content, page_model)
        report["warnings"].extend(self._validate_page_model(page_model))

        if against_reference and against_reference.exists():
            visual_score = self._visual_compare(target_dir, html_path, against_reference, mode, report["warnings"])
            report["visualScore"] = visual_score

        return report

    def detect_mode(self, target_dir: Path) -> str:
        if (target_dir / "layouts" / "index.html").exists():
            return "hugo"
        return "static"

    def _load_page_model(self, target_dir: Path, mode: str) -> dict[str, Any]:
        if mode == "hugo":
            path = target_dir / "data" / "page.json"
        else:
            path = target_dir / "page.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _html_path(self, target_dir: Path, mode: str) -> Path:
        if mode == "static":
            return target_dir / "index.html"
        public_dir = target_dir / "public"
        if (public_dir / "index.html").exists():
            return public_dir / "index.html"
        return target_dir / "layouts" / "index.html"

    def _missing_assets(self, target_dir: Path, page_model: dict[str, Any], mode: str) -> list[str]:
        missing: list[str] = []
        for asset in page_model.get("assets", []):
            if asset.get("renderMode") == "shape" or asset.get("render_mode") == "shape" or asset.get("format") == "shape":
                continue
            local_path = asset.get("localPath") or asset.get("local_path")
            if not local_path:
                missing.append(asset.get("nodeId") or asset.get("node_id") or asset.get("name") or "unknown-asset")
                continue
            resolved = Path(local_path)
            if not resolved.is_absolute():
                resolved = target_dir / local_path if mode == "static" else target_dir / "static" / local_path
            if not resolved.exists():
                missing.append(asset.get("nodeId") or asset.get("node_id") or asset.get("name") or resolved.as_posix())
        return missing

    def _missing_texts(self, html_content: str, page_model: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        normalized_html = self._normalize_visible_text(html_content)
        for text in page_model.get("texts", {}).values():
            value = (text.get("plain_text") or text.get("value") or "").strip()
            if not value:
                continue
            if self._normalize_text(value) not in normalized_html:
                missing.append(text.get("id") or value[:32])
        return missing

    def _validate_hugo_build(self, target_dir: Path, warnings: list[str]) -> bool:
        source_dir = target_dir.resolve()
        public_dir = (source_dir / "public").resolve()
        command = ["hugo", "--source", str(source_dir), "--destination", str(public_dir)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            warnings.append(result.stderr.strip() or result.stdout.strip() or "Hugo build failed.")
            return False
        return True

    def _validate_page_model(self, page_model: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if not isinstance(page_model.get("page"), dict):
            warnings.append("Generated page model is missing the `page` object.")
        if not isinstance(page_model.get("sections"), list):
            warnings.append("Generated page model is missing the `sections` list.")
        if not isinstance(page_model.get("texts"), dict):
            warnings.append("Generated page model is missing the `texts` map.")
        if not isinstance(page_model.get("assets"), list):
            warnings.append("Generated page model is missing the `assets` list.")
        return warnings

    def _visual_compare(
        self,
        target_dir: Path,
        html_path: Path,
        reference_path: Path,
        mode: str,
        warnings: list[str],
    ) -> float | None:
        screenshot_path = target_dir / ".figma2hugo-validation.png"
        try:
            self._capture_page(html_path, screenshot_path)
        except Exception as exc:  # pragma: no cover - optional dependency path
            warnings.append(f"Playwright screenshot skipped: {exc}")
            return None

        if not screenshot_path.exists():
            warnings.append("Playwright did not produce a validation screenshot.")
            return None

        try:
            with Image.open(reference_path) as reference, Image.open(screenshot_path) as generated:
                reference_image = reference.convert("RGBA")
                generated_image = generated.convert("RGBA")
                reference_image, generated_image = self._align_images(reference_image, generated_image)
                diff = ImageChops.difference(reference_image, generated_image)
                histogram = diff.histogram()
                squares = sum(value * ((idx % 256) ** 2) for idx, value in enumerate(histogram))
                total_pixels = reference_image.size[0] * reference_image.size[1] * 4
                rms = math.sqrt(squares / max(total_pixels, 1))
                return round(max(0.0, 1.0 - (rms / 255.0)), 4)
        except Exception as exc:  # pragma: no cover - pillow edge cases
            warnings.append(f"Visual comparison failed: {exc}")
            return None
        finally:
            if mode == "hugo" and screenshot_path.exists():
                screenshot_path.unlink(missing_ok=True)

    def _capture_page(self, html_path: Path, screenshot_path: Path) -> None:
        with self._served_page_url(html_path) as url:
            self._capture_url(url, screenshot_path)

    def _capture_url(self, url: str, screenshot_path: Path) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("Playwright is not installed in the current environment.") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 2200}, device_scale_factor=1)
            page.goto(url, wait_until="networkidle")
            page.screenshot(path=str(screenshot_path), full_page=True)
            browser.close()

    @contextlib.contextmanager
    def _served_page_url(self, html_path: Path):
        resolved_html_path = html_path.resolve()
        root_dir = resolved_html_path.parent
        relative_path = resolved_html_path.relative_to(root_dir).as_posix()
        with self._serve_directory(root_dir) as base_url:
            yield f"{base_url}/{relative_path}"

    @contextlib.contextmanager
    def _serve_directory(self, directory: Path):
        handler = functools.partial(_QuietSimpleHTTPRequestHandler, directory=str(directory))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

    def _align_images(self, reference: Image.Image, generated: Image.Image) -> tuple[Image.Image, Image.Image]:
        width = max(reference.width, generated.width)
        height = max(reference.height, generated.height)
        background = (255, 255, 255, 0)

        aligned_reference = Image.new("RGBA", (width, height), background)
        aligned_reference.paste(reference, (0, 0))

        aligned_generated = Image.new("RGBA", (width, height), background)
        aligned_generated.paste(generated, (0, 0))
        return aligned_reference, aligned_generated

    def _normalize_text(self, value: str) -> str:
        collapsed = " ".join(value.replace("\n", " ").split())
        collapsed = re.sub(r"\s+([:;,.!?%])", r"\1", collapsed)
        return collapsed.casefold()

    def _normalize_visible_text(self, html_content: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", html_content)
        return self._normalize_text(html.unescape(without_tags))


class _QuietSimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - noise reduction
        return
