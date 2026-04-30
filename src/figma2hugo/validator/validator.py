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
    RESPONSIVE_VIEWPORTS: tuple[dict[str, int | str], ...] = (
        {"label": "desktop-xl", "width": 1440, "height": 2200},
        {"label": "desktop", "width": 1280, "height": 2200},
        {"label": "tablet-landscape", "width": 1024, "height": 1600},
        {"label": "tablet", "width": 768, "height": 1600},
        {"label": "mobile", "width": 390, "height": 1200},
    )
    INTERACTION_VIEWPORTS: tuple[dict[str, int | str], ...] = (
        {"label": "desktop", "width": 1280, "height": 1800},
        {"label": "mobile", "width": 390, "height": 1200},
    )

    def validate(
        self,
        target_dir: Path,
        *,
        mode: str | None = None,
        against_reference: Path | None = None,
    ) -> dict[str, Any]:
        mode = mode or self.detect_mode(target_dir)
        report_warnings: list[str] = []
        site_manifest = self._load_site_manifest(target_dir, mode, report_warnings)
        page_models = self._load_page_models(target_dir, mode, site_manifest, report_warnings)
        report_warnings.extend(self._collect_page_warnings(page_models))
        report = {
            "buildOk": True,
            "visualScore": None,
            "missingAssets": [],
            "missingTexts": [],
            "warnings": report_warnings,
            "supportedScope": self._supported_scope_payload(),
            "responsive": {
                "checked": False,
                "available": False,
                "viewports": [],
                "summary": {},
                "warnings": [],
            },
            "interactions": {
                "checked": False,
                "available": False,
                "pages": [],
                "summary": {},
                "warnings": [],
            },
        }

        if mode == "hugo":
            report["buildOk"] = self._validate_hugo_build(target_dir, report["warnings"])

        if not page_models:
            report["warnings"].append("No generated page model is available for validation.")
        elif len(page_models) == 1:
            html_path = self._html_path(target_dir, mode)
            report["missingAssets"] = self._missing_assets(target_dir, page_models[0], mode)
            if html_path.exists():
                html_content = html_path.read_text(encoding="utf-8")
                report["missingTexts"] = self._missing_texts(html_content, page_models[0])
            else:
                report["missingTexts"] = ["html-missing"]
                report["warnings"].append(f"Generated HTML file is missing: {html_path}")
            report["warnings"].extend(self._validate_page_model(page_models[0]))
        else:
            report["missingAssets"] = self._missing_site_assets(target_dir, page_models, mode)
            report["missingTexts"] = self._missing_site_texts(target_dir, page_models, mode, site_manifest or {})
            for page_model in page_models:
                report["warnings"].extend(self._validate_page_model(page_model))

        page_targets = self._page_html_targets(target_dir, mode, page_models, site_manifest)
        report["responsive"] = self._responsive_report(page_targets)
        report["interactions"] = self._interaction_report(page_targets)
        report["warnings"].extend(report["responsive"].get("warnings", []))
        report["warnings"].extend(report["interactions"].get("warnings", []))

        if len(page_models) > 1 and against_reference and against_reference.exists():
            report["warnings"].append("Visual validation is skipped for multi-page sites.")
        elif against_reference and against_reference.exists():
            html_path = self._html_path(target_dir, mode)
            if html_path.exists():
                visual_score = self._visual_compare(target_dir, html_path, against_reference, mode, report["warnings"])
                report["visualScore"] = visual_score
            else:
                report["warnings"].append(f"Visual validation skipped: generated HTML file is missing: {html_path}")

        report["warnings"] = self._dedupe_warnings(report["warnings"])
        report["responsive"]["warnings"] = self._dedupe_warnings(report["responsive"].get("warnings", []))
        report["interactions"]["warnings"] = self._dedupe_warnings(report["interactions"].get("warnings", []))
        return report

    def detect_mode(self, target_dir: Path) -> str:
        if (target_dir / "layouts" / "index.html").exists():
            return "hugo"
        return "static"

    def _supported_scope_payload(self) -> dict[str, Any]:
        return {
            "strategy": "desktop-first-with-flow-components",
            "stableDesktopShell": [
                "desktop fixed-canvas pages remain the default rendering strategy",
                "page shell stays faithful to Figma when no flow shell opt-in is present",
            ],
            "responsiveOptInComponents": [
                "accordion",
                "link-grid",
                "link-card",
                "carousel",
                "form fields",
                "section-block",
            ],
            "guarantees": [
                "generated HTML, CSS and Hugo build are validated",
                "missing texts and missing assets are reported",
                "responsive probes run on multiple viewport widths when Playwright is available",
                "interactive probes cover accordion, cards, carousel and forms when present",
            ],
            "notGuaranteedYet": [
                "fully fluid page shells for every Figma page",
                "automatic responsive inference for arbitrary absolute layouts",
                "breakpoint merging from multiple Figma page variants",
            ],
        }

    def _load_page_model(self, target_dir: Path, mode: str, warnings: list[str]) -> dict[str, Any] | None:
        if mode == "hugo":
            path = target_dir / "data" / "page.json"
        else:
            path = target_dir / "page.json"
        return self._load_json_payload(path, warnings, context="generated page model")

    def _load_site_manifest(self, target_dir: Path, mode: str, warnings: list[str]) -> dict[str, Any] | None:
        if mode != "hugo":
            return None
        path = target_dir / "data" / "site.json"
        if not path.exists():
            return None
        payload = self._load_json_payload(path, warnings, context="site manifest")
        return payload if isinstance(payload, dict) else None

    def _load_page_models(
        self,
        target_dir: Path,
        mode: str,
        site_manifest: dict[str, Any] | None,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        if mode != "hugo" or not site_manifest:
            page_model = self._load_page_model(target_dir, mode, warnings)
            return [page_model] if isinstance(page_model, dict) else []
        pages_dir = target_dir / "data" / "pages"
        page_models: list[dict[str, Any]] = []
        for page in site_manifest.get("pages", []):
            page_key = str(page.get("page_key") or page.get("slug") or "").strip()
            if not page_key:
                continue
            path = pages_dir / f"{page_key}.json"
            payload = self._load_json_payload(path, warnings, context=f"page model `{page_key}`")
            if isinstance(payload, dict):
                page_models.append(payload)
        if site_manifest.get("pages") and not page_models:
            warnings.append("Site manifest was found but no page model could be loaded.")
        return page_models

    def _load_json_payload(
        self,
        path: Path,
        warnings: list[str],
        *,
        context: str,
    ) -> dict[str, Any] | None:
        if not path.exists():
            warnings.append(f"Missing {context}: {path}")
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            warnings.append(f"Failed to read {context}: {path} ({exc})")
            return None
        except ValueError as exc:
            warnings.append(f"Invalid JSON in {context}: {path} ({exc})")
            return None
        if not isinstance(payload, dict):
            warnings.append(f"Invalid {context}: expected an object in {path}")
            return None
        return payload

    def _html_path(self, target_dir: Path, mode: str) -> Path:
        if mode == "static":
            return target_dir / "index.html"
        public_dir = target_dir / "public"
        if (public_dir / "index.html").exists():
            return public_dir / "index.html"
        return target_dir / "layouts" / "index.html"

    def _page_html_targets(
        self,
        target_dir: Path,
        mode: str,
        page_models: list[dict[str, Any]],
        site_manifest: dict[str, Any] | None,
    ) -> list[tuple[str, Path]]:
        if mode != "hugo":
            page_model = page_models[0] if page_models else {}
            page = page_model.get("page") or {}
            page_key = str(page.get("slug") or page.get("id") or "page")
            return [(page_key, target_dir / "index.html")]

        public_dir = target_dir / "public"
        if site_manifest and len(page_models) > 1:
            targets: list[tuple[str, Path]] = []
            seen_paths: set[Path] = set()
            for page in site_manifest.get("pages", []):
                page_key = str(page.get("page_key") or page.get("slug") or "page").strip()
                relative_path = str(page.get("output_path") or f"{page_key}/index.html")
                html_path = (public_dir / relative_path).resolve()
                if html_path in seen_paths:
                    continue
                seen_paths.add(html_path)
                targets.append((page_key or "page", html_path))
            return targets

        page_model = page_models[0] if page_models else {}
        page = page_model.get("page") or {}
        page_key = str(page.get("slug") or page.get("id") or "page")
        return [(page_key, self._html_path(target_dir, mode))]

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

    def _missing_site_assets(self, target_dir: Path, page_models: list[dict[str, Any]], mode: str) -> list[str]:
        missing: list[str] = []
        for page_model in page_models:
            page_slug = str((page_model.get("page") or {}).get("slug") or (page_model.get("page") or {}).get("id") or "page")
            missing.extend(f"{page_slug}:{item}" for item in self._missing_assets(target_dir, page_model, mode))
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

    def _missing_site_texts(
        self,
        target_dir: Path,
        page_models: list[dict[str, Any]],
        mode: str,
        site_manifest: dict[str, Any],
    ) -> list[str]:
        del mode
        missing: list[str] = []
        page_entries = {
            str(page.get("page_key") or page.get("slug") or ""): page
            for page in site_manifest.get("pages", [])
        }
        public_dir = target_dir / "public"
        for page_model in page_models:
            page = page_model.get("page") or {}
            page_key = str(page.get("slug") or page.get("id") or "")
            page_entry = page_entries.get(page_key, {})
            relative_path = str(page_entry.get("output_path") or f"{page_key}/index.html")
            html_path = public_dir / relative_path
            if not html_path.exists():
                missing.append(f"{page_key}:html-missing")
                continue
            html_content = html_path.read_text(encoding="utf-8")
            missing.extend(f"{page_key}:{item}" for item in self._missing_texts(html_content, page_model))
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

    def _collect_page_warnings(self, page_models: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        for page_model in page_models:
            warnings.extend(list(page_model.get("warnings", [])))
        return warnings

    def _responsive_report(self, page_targets: list[tuple[str, Path]]) -> dict[str, Any]:
        report = {
            "checked": False,
            "available": False,
            "viewports": [],
            "summary": {},
            "warnings": [],
        }
        if not page_targets:
            report["warnings"].append("Responsive validation skipped: no generated HTML target was found.")
            report["summary"] = self._responsive_summary([])
            return report
        playwright_available = self._playwright_is_available()
        report["available"] = playwright_available
        if not playwright_available:
            report["warnings"].append(
                "Responsive validation skipped: Playwright is not installed in the current environment."
            )
            report["summary"] = self._responsive_summary([])
            return report

        checked_any = False
        for page_key, html_path in page_targets:
            if not html_path.exists():
                report["warnings"].append(f"Responsive validation skipped for {page_key}: missing HTML file.")
                continue
            for viewport in self.RESPONSIVE_VIEWPORTS:
                try:
                    probe = self._probe_responsive_page(html_path, viewport)
                except Exception as exc:  # pragma: no cover - browser/runtime dependent
                    report["warnings"].append(
                        f"Responsive validation failed for {page_key} at {viewport['width']}px: {exc}"
                    )
                    continue
                checked_any = True
                issues: list[str] = []
                if bool(probe.get("horizontalOverflow")):
                    issues.append("horizontal-overflow")
                if int(probe.get("brokenImages", 0) or 0) > 0:
                    issues.append("broken-images")
                report["viewports"].append(
                    {
                        "page": page_key,
                        "label": viewport["label"],
                        "width": int(viewport["width"]),
                        "height": int(viewport["height"]),
                        "pageShell": probe.get("pageShell") or "",
                        "pageFlow": probe.get("pageFlow") or "false",
                        "scrollWidth": int(probe.get("scrollWidth", 0) or 0),
                        "clientWidth": int(probe.get("clientWidth", 0) or 0),
                        "brokenImages": int(probe.get("brokenImages", 0) or 0),
                        "issues": issues,
                    }
                )
        report["checked"] = checked_any
        report["summary"] = self._responsive_summary(report["viewports"])
        return report

    def _interaction_report(self, page_targets: list[tuple[str, Path]]) -> dict[str, Any]:
        report = {
            "checked": False,
            "available": False,
            "pages": [],
            "summary": {},
            "warnings": [],
        }
        if not page_targets:
            report["warnings"].append("Interaction validation skipped: no generated HTML target was found.")
            report["summary"] = self._interaction_summary([])
            return report
        playwright_available = self._playwright_is_available()
        report["available"] = playwright_available
        if not playwright_available:
            report["warnings"].append(
                "Interaction validation skipped: Playwright is not installed in the current environment."
            )
            report["summary"] = self._interaction_summary([])
            return report

        checked_any = False
        for page_key, html_path in page_targets:
            if not html_path.exists():
                report["warnings"].append(f"Interaction validation skipped for {page_key}: missing HTML file.")
                continue
            page_result = {
                "page": page_key,
                "viewports": [],
            }
            for viewport in self.INTERACTION_VIEWPORTS:
                try:
                    probe = self._probe_interactions_page(html_path, viewport)
                except Exception as exc:  # pragma: no cover - browser/runtime dependent
                    report["warnings"].append(
                        f"Interaction validation failed for {page_key} at {viewport['width']}px: {exc}"
                    )
                    continue
                checked_any = True
                page_result["viewports"].append(
                    {
                        "label": viewport["label"],
                        "width": int(viewport["width"]),
                        "height": int(viewport["height"]),
                        "checks": probe.get("checks", []),
                    }
                )
            report["pages"].append(page_result)
        report["checked"] = checked_any
        report["summary"] = self._interaction_summary(report["pages"])
        return report

    def _responsive_summary(self, viewport_rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "totalViewports": len(viewport_rows),
            "viewportsWithIssues": sum(1 for row in viewport_rows if row.get("issues")),
            "horizontalOverflowCount": sum(
                1 for row in viewport_rows if "horizontal-overflow" in set(row.get("issues", []))
            ),
            "brokenImageCount": sum(
                1 for row in viewport_rows if "broken-images" in set(row.get("issues", []))
            ),
        }

    def _interaction_summary(self, pages: list[dict[str, Any]]) -> dict[str, int]:
        checks = [
            check
            for page in pages
            for viewport in page.get("viewports", [])
            for check in viewport.get("checks", [])
        ]
        return {
            "totalPages": len(pages),
            "totalChecks": len(checks),
            "passedChecks": sum(1 for check in checks if check.get("status") == "pass"),
            "failedChecks": sum(1 for check in checks if check.get("status") == "fail"),
            "skippedChecks": sum(1 for check in checks if check.get("status") == "skipped"),
        }

    def _dedupe_warnings(self, warnings: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for warning in warnings:
            normalized = str(warning).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def _playwright_is_available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return False
        return True

    def _probe_responsive_page(self, html_path: Path, viewport: dict[str, int | str]) -> dict[str, Any]:
        with self._served_page_url(html_path) as url:
            return self._probe_responsive_url(url, viewport)

    def _probe_responsive_url(self, url: str, viewport: dict[str, int | str]) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("Playwright is not installed in the current environment.") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                viewport={"width": int(viewport["width"]), "height": int(viewport["height"])},
                device_scale_factor=1,
            )
            page.goto(url, wait_until="networkidle")
            metrics = page.evaluate(
                """
                () => {
                  const doc = document.documentElement;
                  const body = document.body;
                  const pageRoot = document.querySelector('.page');
                  const scrollWidth = Math.max(
                    doc ? doc.scrollWidth : 0,
                    body ? body.scrollWidth : 0,
                    pageRoot ? pageRoot.scrollWidth : 0,
                  );
                  const clientWidth = doc ? doc.clientWidth : window.innerWidth;
                  const horizontalOverflow = scrollWidth > clientWidth + 1;
                  const brokenImages = Array.from(document.images).filter((img) => !img.complete || img.naturalWidth === 0).length;
                  return {
                    scrollWidth,
                    clientWidth,
                    horizontalOverflow,
                    brokenImages,
                    pageShell: pageRoot?.dataset.pageShell || "",
                    pageFlow: pageRoot?.dataset.pageFlow || "false",
                  };
                }
                """
            )
            browser.close()
        return metrics

    def _probe_interactions_page(self, html_path: Path, viewport: dict[str, int | str]) -> dict[str, Any]:
        with self._served_page_url(html_path) as url:
            return self._probe_interactions_url(url, viewport)

    def _probe_interactions_url(self, url: str, viewport: dict[str, int | str]) -> dict[str, Any]:
        try:
            from playwright.sync_api import Page, sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("Playwright is not installed in the current environment.") from exc

        def accordion_check(page: Page) -> dict[str, Any]:
            triggers = page.locator('[data-accordion-trigger="true"]')
            if triggers.count() == 0:
                return {"component": "accordion", "status": "skipped", "issues": ["not-present"]}
            trigger = triggers.nth(0)
            panel_id = trigger.get_attribute("aria-controls") or ""
            if not panel_id:
                return {"component": "accordion", "status": "fail", "issues": ["missing-aria-controls"]}
            panel = page.locator(f"#{panel_id}")
            before_expanded = trigger.get_attribute("aria-expanded") or ""
            before_hidden = panel.get_attribute("hidden") or ""
            trigger.click()
            page.wait_for_timeout(75)
            after_expanded = trigger.get_attribute("aria-expanded") or ""
            after_hidden = panel.get_attribute("hidden") or ""
            success = before_expanded != after_expanded or before_hidden != after_hidden
            return {
                "component": "accordion",
                "status": "pass" if success else "fail",
                "issues": [] if success else ["state-did-not-change"],
            }

        def link_card_check(page: Page) -> dict[str, Any]:
            cards = page.locator('a[data-link-card="true"]')
            if cards.count() == 0:
                return {"component": "link-card", "status": "skipped", "issues": ["not-present"]}
            card = cards.nth(0)
            href = (card.get_attribute("href") or "").strip()
            visible = card.is_visible()
            valid_href = bool(href and not href.lower().startswith("javascript:"))
            success = visible and valid_href
            issues: list[str] = []
            if not visible:
                issues.append("not-visible")
            if not valid_href:
                issues.append("invalid-href")
            return {
                "component": "link-card",
                "status": "pass" if success else "fail",
                "issues": issues,
            }

        def carousel_check(page: Page) -> dict[str, Any]:
            roots = page.locator('[data-carousel="true"]')
            if roots.count() == 0:
                return {"component": "carousel", "status": "skipped", "issues": ["not-present"]}
            root = roots.nth(0)
            thumbs = root.locator("[data-carousel-thumb]")
            if thumbs.count() < 2:
                return {"component": "carousel", "status": "skipped", "issues": ["not-enough-thumbs"]}
            before_active = root.get_attribute("data-carousel-active") or ""
            thumb = thumbs.nth(1)
            expected_active = thumb.get_attribute("data-carousel-thumb") or ""
            thumb.click()
            page.wait_for_timeout(75)
            after_active = root.get_attribute("data-carousel-active") or ""
            success = bool(expected_active) and after_active == expected_active and after_active != before_active
            return {
                "component": "carousel",
                "status": "pass" if success else "fail",
                "issues": [] if success else ["active-slide-did-not-change"],
            }

        def form_check(page: Page) -> dict[str, Any]:
            controls = page.locator(".content-form-control")
            if controls.count() == 0:
                return {"component": "form", "status": "skipped", "issues": ["not-present"]}
            control = controls.nth(0)
            visible = control.is_visible()
            disabled = control.get_attribute("disabled") is not None
            success = visible and not disabled
            issues: list[str] = []
            if not visible:
                issues.append("not-visible")
            if disabled:
                issues.append("disabled")
            return {
                "component": "form",
                "status": "pass" if success else "fail",
                "issues": issues,
            }

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                viewport={"width": int(viewport["width"]), "height": int(viewport["height"])},
                device_scale_factor=1,
            )
            page.goto(url, wait_until="networkidle")
            checks = [
                accordion_check(page),
                link_card_check(page),
                carousel_check(page),
                form_check(page),
            ]
            browser.close()
        return {"checks": checks}

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
        root_dir = self._served_root_dir(resolved_html_path)
        relative_path = resolved_html_path.relative_to(root_dir).as_posix()
        with self._serve_directory(root_dir) as base_url:
            yield f"{base_url}/{relative_path}"

    def _served_root_dir(self, html_path: Path) -> Path:
        for ancestor in html_path.parents:
            if ancestor.name.lower() == "public":
                return ancestor
        return html_path.parent

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
