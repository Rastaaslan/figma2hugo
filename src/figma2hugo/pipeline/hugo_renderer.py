"""Ecrit la structure du site Hugo : contenu, donnees, layouts, assets et scripts."""

from __future__ import annotations

import json
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from figma2hugo.pipeline.export import render_plan_to_dict, responsive_manifest_to_dict
from figma2hugo.pipeline.html_renderer import render_static_css
from figma2hugo.pipeline.hugo_assets import (
    asset_filename as _asset_filename,
)
from figma2hugo.pipeline.hugo_assets import (
    localize_group_assets as _localize_group_assets,
)
from figma2hugo.pipeline.models import RenderPlan
from figma2hugo.pipeline.naming import slugify as _slug
from figma2hugo.pipeline.naming import unique_slug as _unique_slug
from figma2hugo.pipeline.responsive import ResponsiveManifest

_URLLIB_REQUEST_FOR_ASSET_TEST_PATCHING = urllib.request
PIPELINE_MANAGED_MARKER = "figma2hugo:pipeline-managed"
PIPELINE_MANAGED_MANIFEST = ".figma2hugo-pipeline/managed-files.json"
PIPELINE_MANAGED_ZONES = (
    "data/pipeline",
    "assets/css/pipeline",
    "assets/js/pipeline",
    "static/pipeline-assets",
    "layouts/partials/pipeline",
)
__all__ = [
    "PipelineHugoPage",
    "PipelineHugoRenderGroup",
    "write_pipeline_hugo_site",
    "write_pipeline_hugo_site_groups",
    "_asset_filename",
]


@dataclass(frozen=True, slots=True)
class PipelineHugoPage:
    slug: str
    title: str
    content_path: Path
    data_path: Path
    css_path: Path
    responsive: bool = False


@dataclass(frozen=True, slots=True)
class PipelineHugoRenderGroup:
    plans: list[RenderPlan]
    responsive_manifest: ResponsiveManifest | None = None


def write_pipeline_hugo_site(
    plans: list[RenderPlan],
    out_dir: Path,
    *,
    responsive_manifest: ResponsiveManifest | None = None,
    include_debug_pages: bool = True,
) -> dict[str, Any]:
    return write_pipeline_hugo_site_groups(
        [PipelineHugoRenderGroup(plans=plans, responsive_manifest=responsive_manifest)],
        out_dir,
        include_debug_pages=include_debug_pages,
    )


def write_pipeline_hugo_site_groups(
    groups: list[PipelineHugoRenderGroup],
    out_dir: Path,
    *,
    include_debug_pages: bool = True,
) -> dict[str, Any]:
    if not groups:
        raise ValueError("Pipeline Hugo site requires at least one render group.")
    for group in groups:
        if not group.plans:
            raise ValueError("Pipeline Hugo render groups require at least one render plan.")
    # On supprime seulement les fichiers crees par ce generateur. Le contenu Hugo
    # ecrit a la main peut cohabiter avec le genere sans etre efface.
    _clean_pipeline_managed_outputs(out_dir)
    _ensure_hugo_dirs(out_dir)
    groups, localized_assets, asset_cache = _localize_group_assets(groups, out_dir)
    written_files: list[Path] = []
    written_files.extend(_write_hugo_scaffold(out_dir))
    written_files.extend(localized_assets)

    pages: list[PipelineHugoPage] = []
    used_slugs: set[str] = set()
    page_index = 1
    for group in groups:
        responsive_manifest = group.responsive_manifest
        plans = group.plans
        if responsive_manifest is not None and len(plans) > 1:
            # Une page Hugo publique peut contenir plusieurs breakpoints Figma. Le choix
            # du breakpoint se fait ensuite en CSS genere, pas dans la logique Hugo.
            responsive_slug = _unique_slug(
                _slug(responsive_manifest.family) or "responsive", used_slugs
            )
            pages.append(
                _write_responsive_page(
                    out_dir,
                    slug=responsive_slug,
                    plans=plans,
                    manifest=responsive_manifest,
                )
            )

        should_write_plan_pages = (
            include_debug_pages or responsive_manifest is None or len(plans) == 1
        )
        if should_write_plan_pages:
            for plan in plans:
                slug = _unique_slug(_slug(plan.page_name) or f"page-{page_index}", used_slugs)
                pages.append(_write_page(out_dir, slug=slug, plan=plan, responsive=False))
                page_index += 1

    site_data_path = out_dir / "data" / "pipeline" / "site.json"
    site_data_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "path": f"/{page.slug}/",
                        "responsive": page.responsive,
                    }
                    for page in pages
                ]
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    written_files.append(site_data_path)
    for page in pages:
        written_files.extend([page.content_path, page.data_path, page.css_path])
    manifest_path = _write_managed_manifest(out_dir, written_files=written_files, pages=pages)
    written_files.append(manifest_path)

    return {
        "root": str(out_dir),
        "files": [str(path) for path in written_files],
        "pages": [
            {
                "slug": page.slug,
                "title": page.title,
                "content": str(page.content_path),
                "data": str(page.data_path),
                "css": str(page.css_path),
                "responsive": page.responsive,
            }
            for page in pages
        ],
        "assetCache": asset_cache,
    }


def _write_page(
    out_dir: Path, *, slug: str, plan: RenderPlan, responsive: bool
) -> PipelineHugoPage:
    content_path = out_dir / "content" / slug / "index.md"
    data_path = out_dir / "data" / "pipeline" / "pages" / f"{slug}.json"
    css_path = out_dir / "assets" / "css" / "pipeline" / f"{slug}.css"
    content_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(
        _front_matter(
            {
                "title": plan.page_name,
                "pipelinePageKey": slug,
                "pipelineStylesheet": f"css/pipeline/{slug}.css",
            }
        ),
        encoding="utf-8",
    )
    data_path.write_text(
        json.dumps(render_plan_to_dict(plan), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    css_path.write_text(render_static_css(plan) + "\n", encoding="utf-8")
    return PipelineHugoPage(
        slug=slug,
        title=plan.page_name,
        content_path=content_path,
        data_path=data_path,
        css_path=css_path,
        responsive=responsive,
    )


def _write_responsive_page(
    out_dir: Path,
    *,
    slug: str,
    plans: list[RenderPlan],
    manifest: ResponsiveManifest,
) -> PipelineHugoPage:
    sorted_plans = sorted(plans, key=lambda plan: plan.width, reverse=True)
    content_path = out_dir / "content" / slug / "index.md"
    data_path = out_dir / "data" / "pipeline" / "responsive" / f"{slug}.json"
    css_path = out_dir / "assets" / "css" / "pipeline" / f"{slug}.responsive.css"
    content_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    css_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_text(
        _front_matter(
            {
                "title": f"{manifest.family} responsive",
                "pipelineResponsiveKey": slug,
                "pipelineStylesheet": f"css/pipeline/{slug}.responsive.css",
            }
        ),
        encoding="utf-8",
    )
    data_path.write_text(
        json.dumps(
            {
                "manifest": responsive_manifest_to_dict(manifest),
                "variants": [
                    {
                        "width": plan.width,
                        "page": render_plan_to_dict(plan),
                    }
                    for plan in sorted_plans
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    css_path.write_text(_responsive_css(sorted_plans) + "\n", encoding="utf-8")
    return PipelineHugoPage(
        slug=slug,
        title=f"{manifest.family} responsive",
        content_path=content_path,
        data_path=data_path,
        css_path=css_path,
        responsive=True,
    )


def _ensure_hugo_dirs(out_dir: Path) -> None:
    for relative in (
        "content",
        "data/pipeline/pages",
        "data/pipeline/responsive",
        "layouts/_default",
        "layouts/partials/pipeline",
        "assets/css/pipeline",
        "assets/js/pipeline",
    ):
        (out_dir / relative).mkdir(parents=True, exist_ok=True)


def _clean_pipeline_managed_outputs(out_dir: Path) -> None:
    _remove_previous_managed_files(out_dir)
    for relative in PIPELINE_MANAGED_ZONES:
        target = out_dir / relative
        if target.exists():
            _remove_tree_best_effort(target)
    content_dir = out_dir / "content"
    if content_dir.exists():
        for index_path in content_dir.glob("*/index.md"):
            try:
                content = index_path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "pipelinePageKey" in content or "pipelineResponsiveKey" in content:
                _remove_tree_best_effort(index_path.parent)
    index_path = content_dir / "_index.md"
    if index_path.exists():
        try:
            content = index_path.read_text(encoding="utf-8")
        except OSError:
            return
        if 'title = "Pipeline"' in content:
            _unlink_best_effort(index_path)


def _remove_previous_managed_files(out_dir: Path) -> None:
    for relative in _read_managed_manifest_files(out_dir):
        path = (out_dir / relative).resolve()
        if not _is_relative_to(path, out_dir.resolve()):
            continue
        if path.is_file():
            if _unlink_best_effort(path):
                _remove_empty_parents(path.parent, stop_at=out_dir.resolve())


def _unlink_best_effort(path: Path) -> bool:
    try:
        path.unlink()
    except PermissionError:
        return False
    except FileNotFoundError:
        return True
    return True


def _remove_tree_best_effort(path: Path) -> bool:
    try:
        shutil.rmtree(path)
    except PermissionError:
        return False
    except FileNotFoundError:
        return True
    return True


def _read_managed_manifest_files(out_dir: Path) -> list[Path]:
    manifest_path = out_dir / PIPELINE_MANAGED_MANIFEST
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    if payload.get("pipeline") != "pipeline":
        return []
    files = payload.get("files")
    if not isinstance(files, list):
        return []
    return [Path(str(path)) for path in files if str(path).strip()]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _remove_empty_parents(path: Path, *, stop_at: Path) -> None:
    current = path.resolve()
    while _is_relative_to(current, stop_at) and current != stop_at:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _write_hugo_scaffold(out_dir: Path) -> list[Path]:
    files = {
        out_dir / "hugo.toml": HUGO_TOML,
        out_dir / "content" / "_index.md": _front_matter({"title": "Pipeline"}),
        out_dir / "layouts" / "_default" / "baseof.html": BASEOF_TEMPLATE,
        out_dir / "layouts" / "_default" / "single.html": SINGLE_TEMPLATE,
        out_dir / "layouts" / "index.html": INDEX_TEMPLATE,
        out_dir / "layouts" / "partials" / "pipeline" / "page.html": PAGE_PARTIAL,
        out_dir
        / "layouts"
        / "partials"
        / "pipeline"
        / "responsive-page.html": RESPONSIVE_PAGE_PARTIAL,
        out_dir / "layouts" / "partials" / "pipeline" / "section.html": SECTION_PARTIAL,
        out_dir / "layouts" / "partials" / "pipeline" / "node.html": NODE_PARTIAL,
        out_dir / "assets" / "js" / "pipeline" / "runtime.js": PIPELINE_RUNTIME_JS,
    }
    _assert_pipeline_scaffold_writable(files.keys())
    written: list[Path] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_pipeline_managed_text(path, content.rstrip() + "\n")
        written.append(path)
    return written


def _write_managed_manifest(
    out_dir: Path,
    *,
    written_files: list[Path],
    pages: list[PipelineHugoPage],
) -> Path:
    manifest_path = out_dir / PIPELINE_MANAGED_MANIFEST
    files = [*written_files, manifest_path]
    payload = {
        "schemaVersion": 1,
        "pipeline": "pipeline",
        "managedMarker": PIPELINE_MANAGED_MARKER,
        "managedZones": list(PIPELINE_MANAGED_ZONES),
        "files": sorted({_site_relative_path(path, out_dir) for path in files}),
        "pages": [
            {
                "slug": page.slug,
                "content": _site_relative_path(page.content_path, out_dir),
                "data": _site_relative_path(page.data_path, out_dir),
                "css": _site_relative_path(page.css_path, out_dir),
                "responsive": page.responsive,
            }
            for page in pages
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _site_relative_path(path: Path, out_dir: Path) -> str:
    try:
        relative = path.resolve().relative_to(out_dir.resolve())
    except ValueError:
        relative = path
    return relative.as_posix()


def _assert_pipeline_scaffold_writable(paths: Any) -> None:
    protected_paths: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        current = path.read_text(encoding="utf-8")
        if not _is_pipeline_managed_scaffold(current):
            protected_paths.append(path)
    if protected_paths:
        formatted_paths = ", ".join(str(path) for path in protected_paths)
        raise ValueError(
            f"Pipeline refuses to overwrite non-pipeline Hugo scaffold files: {formatted_paths}"
        )


def _write_pipeline_managed_text(path: Path, content: str) -> None:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if not _is_pipeline_managed_scaffold(current):
            raise ValueError(
                f"Pipeline refuses to overwrite a non-pipeline Hugo scaffold file: {path}"
            )
    path.write_text(content, encoding="utf-8")


def _is_pipeline_managed_scaffold(content: str) -> bool:
    previous_pipeline_markers = (
        'title = "Pipeline"',
        ".Params.pipelineStylesheet",
        ".Params.pipelineResponsiveKey",
        "hugo.Data.pipeline.site.pages",
    )
    return PIPELINE_MANAGED_MARKER in content or any(
        marker in content for marker in previous_pipeline_markers
    )


def _front_matter(values: dict[str, str]) -> str:
    lines = ["+++"]
    for key, value in values.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key} = "{escaped}"')
    lines.extend(["+++", ""])
    return "\n".join(lines)


def _responsive_css(plans: list[RenderPlan]) -> str:
    sorted_plans = sorted(plans, key=lambda plan: plan.width)
    largest = sorted_plans[-1]
    lines = [
        _base_responsive_css(sorted_plans),
        ".pipeline-responsive-variant { display: none; }",
        f".pipeline-responsive-variant-{largest.width} {{ display: block; }}",
    ]
    for index in range(len(sorted_plans) - 2, -1, -1):
        plan = sorted_plans[index]
        next_width = sorted_plans[index + 1].width
        boundary = int((plan.width + next_width) / 2)
        lines.extend(
            [
                f"@media (max-width: {boundary}px) {{",
                "  .pipeline-responsive-variant { display: none; }",
                f"  .pipeline-responsive-variant-{plan.width} {{ display: block; }}",
                "}",
            ]
        )
    return "\n".join(lines)


def _base_responsive_css(plans: list[RenderPlan]) -> str:
    largest = max(plans, key=lambda plan: plan.width)
    sorted_plans = sorted(plans, key=lambda plan: plan.width)
    page_rules = []
    scale_rules = []
    for plan in sorted_plans:
        height = _plan_visual_height(plan)
        page_rules.append(
            f".pipeline-responsive-variant-{plan.width} {{ width: {plan.width}px; "
            f"height: {height}px; max-width: 100%; }}"
        )
        page_rules.append(
            f".pipeline-responsive-variant-{plan.width} .pipeline-page {{ width: {plan.width}px; "
            f"min-height: {height}px; }}"
        )

    for index in range(len(sorted_plans) - 1, -1, -1):
        plan = sorted_plans[index]
        height = _plan_visual_height(plan)
        ratio_vw = (height / plan.width) * 100
        upper_scale_width = (
            int((plan.width + sorted_plans[index + 1].width) / 2)
            if index < len(sorted_plans) - 1
            else plan.width
        )
        scale_rules.extend(
            [
                f"@media (max-width: {upper_scale_width}px) {{",
                f"  .pipeline-responsive-variant-{plan.width} {{ width: 100vw; "
                f"height: {ratio_vw:.6f}vw; max-width: none; }}",
                "  .pipeline-responsive-variant-"
                f"{plan.width} .pipeline-page {{ transform: scale(calc(100vw / {plan.width}px)); }}",
                "}",
            ]
        )
    return "\n".join(
        [
            render_static_css(largest),
            ".pipeline-responsive-variant { display: none; overflow: hidden; margin: 0 auto; max-width: 100%; }",
            ".pipeline-responsive-variant .pipeline-page { margin: 0; overflow: visible; transform-origin: top left; }",
            *page_rules,
            *scale_rules,
        ]
    )


def _plan_visual_height(plan: RenderPlan) -> int:
    bottom = int(round(max((section.bounds.bottom for section in plan.sections), default=0)))
    return max(plan.height, bottom)


HUGO_COMMENT = "{{/* " + PIPELINE_MANAGED_MARKER + " */}}\n"

HUGO_TOML = f"""
# {PIPELINE_MANAGED_MARKER}
baseURL = "/"
languageCode = "fr-fr"
title = "Pipeline"
disableKinds = ["taxonomy", "term", "RSS", "sitemap", "robotsTXT"]
"""

BASEOF_TEMPLATE = (
    HUGO_COMMENT
    + """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ .Title }}</title>
  {{ with .Params.pipelineStylesheet }}
    {{ with resources.Get . }}
      <link rel="stylesheet" href="{{ .RelPermalink }}">
    {{ end }}
  {{ end }}
  {{ with resources.Get "js/pipeline/runtime.js" }}
    <script src="{{ .RelPermalink }}" defer></script>
  {{ end }}
</head>
<body>
  {{ block "main" . }}{{ end }}
</body>
</html>
"""
)

PIPELINE_RUNTIME_JS = (
    "/* "
    + PIPELINE_MANAGED_MARKER
    + """ */
(function () {
  "use strict";

  var EPSILON = 0.5;

  function numberFromStyle(element, propertyName, fallback) {
    var raw = element.style.getPropertyValue(propertyName) || window.getComputedStyle(element).getPropertyValue(propertyName);
    var parsed = Number.parseFloat(String(raw || "").replace("px", ""));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function originalTop(element) {
    if (!element.dataset.pipelineOriginalTop) {
      element.dataset.pipelineOriginalTop = String(numberFromStyle(element, "top", element.offsetTop || 0));
    }
    return Number.parseFloat(element.dataset.pipelineOriginalTop || "0") || 0;
  }

  function originalHeight(element) {
    if (!element.dataset.pipelineOriginalHeight) {
      element.dataset.pipelineOriginalHeight = String(numberFromStyle(element, "min-height", element.offsetHeight || 0));
    }
    return Number.parseFloat(element.dataset.pipelineOriginalHeight || "0") || 0;
  }

  function currentHeight(element) {
    var stored = Number.parseFloat(element.dataset.pipelineCurrentHeight || "");
    var baseline = Number.isFinite(stored) && stored > 0 ? stored : originalHeight(element);
    if (!usesAccordionLayoutHeight(element)) {
      return baseline;
    }
    if (Number.isFinite(stored) && stored > 0 && usesAccordionLayoutHeight(element)) {
      return stored;
    }
    return Math.max(baseline, naturalHeight(element));
  }

  function usesAccordionLayoutHeight(element) {
    var component = element.getAttribute("data-component");
    return component === "accordion" || component === "accordion-item";
  }

  function isRendered(element) {
    return !element.hidden && window.getComputedStyle(element).display !== "none";
  }

  function contributesToLayout(element) {
    if (
      element.classList.contains("pipeline-layer-background") ||
      element.classList.contains("pipeline-layer-decorative")
    ) {
      return false;
    }
    if (
      element.classList.contains("pipeline-layer-asset") &&
      !element.classList.contains("pipeline-text") &&
      !element.matches("[data-component]") &&
      !element.querySelector(".pipeline-layer-content, .pipeline-layer-foreground, [data-component]")
    ) {
      return false;
    }
    return true;
  }

  function ownNaturalHeight(element) {
    return originalHeight(element);
  }

  function naturalHeight(element) {
    if (!isRendered(element)) {
      return 0;
    }
    var height = ownNaturalHeight(element);
    element.querySelectorAll(":scope > .pipeline-node").forEach(function (child) {
      if (!isRendered(child) || !contributesToLayout(child)) {
        return;
      }
      height = Math.max(height, originalTop(child) + currentHeight(child));
    });
    return height;
  }

  function setBox(element, top, height) {
    if (Number.isFinite(top)) {
      element.style.top = Math.max(0, top) + "px";
    }
    if (Number.isFinite(height)) {
      var normalizedHeight = Math.max(1, height);
      element.dataset.pipelineCurrentHeight = String(normalizedHeight);
      element.style.minHeight = normalizedHeight + "px";
    }
  }

  function sortedByOriginalTop(elements) {
    return elements.sort(function (left, right) {
      var delta = originalTop(left) - originalTop(right);
      if (Math.abs(delta) > EPSILON) {
        return delta;
      }
      return left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });
  }

  function childBottom(parent) {
    var bottom = originalHeight(parent);
    parent.querySelectorAll(":scope > .pipeline-node").forEach(function (child) {
      if (!isRendered(child) || !contributesToLayout(child)) {
        return;
      }
      bottom = Math.max(bottom, originalTop(child) + currentHeight(child));
    });
    return bottom;
  }

  function accordionItemHeight(item) {
    var summary = item.querySelector(':scope > summary[data-component="accordion-trigger"]');
    var panel = item.querySelector(':scope > [data-component="accordion-panel"]');
    if (!summary) {
      return originalHeight(item);
    }
    var closedHeight = Math.max(originalHeight(summary), originalTop(summary) + originalHeight(summary));
    if (!item.open) {
      return closedHeight;
    }
    var openHeight = originalHeight(item);
    openHeight = Math.max(openHeight, originalTop(summary) + originalHeight(summary));
    if (panel) {
      openHeight = Math.max(openHeight, originalTop(panel) + originalHeight(panel));
    }
    return openHeight;
  }

  function accordionSingleMode(root) {
    var name = String(root.getAttribute("data-node-name") || "").toLowerCase();
    var tokens = name.split(/[^a-z0-9]+/).filter(Boolean);
    return tokens.indexOf("multi") === -1;
  }

  function layoutAccordion(root) {
    var items = sortedByOriginalTop(Array.from(root.querySelectorAll(':scope > details[data-component="accordion-item"]')));
    if (!items.length) {
      return originalHeight(root);
    }
    var cursor = originalTop(items[0]);
    var previousOriginalBottom = cursor;
    items.forEach(function (item, index) {
      var gap = index === 0 ? 0 : Math.max(0, originalTop(item) - previousOriginalBottom);
      cursor += gap;
      var height = accordionItemHeight(item);
      setBox(item, cursor, height);
      cursor += height;
      previousOriginalBottom = originalTop(item) + originalHeight(item);
    });
    var nextHeight = Math.max(1, cursor);
    setBox(root, Number.NaN, nextHeight);
    return nextHeight;
  }

  function layoutSection(section) {
    var nodes = sortedByOriginalTop(Array.from(section.querySelectorAll(":scope > .pipeline-node")));
    var previous = [];
    var shrink = sectionAllowsDynamicShrink(section);
    var bottomPadding = shrink ? originalBottomPadding(section, nodes) : 0;
    var contentBottom = 0;
    nodes.forEach(function (node) {
      var originalNodeTop = originalTop(node);
      var nextTop = originalNodeTop;
      previous.forEach(function (candidate) {
        if (originalNodeTop + EPSILON >= candidate.originalBottom) {
          nextTop += candidate.delta;
        }
      });
      if (node.getAttribute("data-component") === "accordion") {
        layoutAccordion(node);
      }
      var height = currentHeight(node);
      if (Math.abs(nextTop - originalNodeTop) > EPSILON) {
        setBox(node, nextTop, height);
      }
      if (!contributesToLayout(node)) {
        return;
      }
      contentBottom = Math.max(contentBottom, nextTop + height);
      previous.push({
        originalBottom: originalNodeTop + originalHeight(node),
        delta: height - originalHeight(node),
      });
    });
    var nextHeight = shrink
      ? Math.max(1, contentBottom + bottomPadding)
      : Math.max(originalHeight(section), contentBottom);
    setBox(section, Number.NaN, nextHeight);
    return nextHeight;
  }

  function sectionAllowsDynamicShrink(section) {
    return Boolean(section.querySelector('[data-component="accordion"]'));
  }

  function originalBottomPadding(section, nodes) {
    var bottom = 0;
    nodes.forEach(function (node) {
      if (!isRendered(node) || !contributesToLayout(node)) {
        return;
      }
      bottom = Math.max(bottom, originalTop(node) + originalHeight(node));
    });
    return Math.max(0, originalHeight(section) - bottom);
  }

  function stretchSectionBackground(section) {
    var height = currentHeight(section);
    Array.from(section.querySelectorAll(":scope > .pipeline-layer-background")).forEach(function (node) {
      var nodeTop = originalTop(node);
      var nodeWidth = numberFromStyle(node, "width", node.offsetWidth || 0);
      var sectionWidth = numberFromStyle(section, "width", section.offsetWidth || 0);
      if (sectionWidth > 0 && nodeWidth < sectionWidth * 0.66) {
        return;
      }
      setBox(node, nodeTop, Math.max(originalHeight(node), height - nodeTop));
    });
  }

  function layoutPage(page) {
    var sections = sortedByOriginalTop(Array.from(page.querySelectorAll(":scope > .pipeline-section")));
    var pageBottom = 0;
    var previous = [];
    sections.forEach(function (section) {
      var originalSectionTop = originalTop(section);
      var nextTop = originalSectionTop;
      previous.forEach(function (candidate) {
        if (originalSectionTop + EPSILON >= candidate.originalBottom) {
          nextTop += candidate.delta;
        }
      });
      var height = layoutSection(section);
      setBox(section, nextTop, height);
      stretchSectionBackground(section);
      pageBottom = Math.max(pageBottom, nextTop + height);
      previous.push({
        originalBottom: originalSectionTop + originalHeight(section),
        delta: height - originalHeight(section),
      });
    });
    page.style.minHeight = pageBottom + "px";
    page.style.height = pageBottom + "px";
    var wrapper = page.closest(".pipeline-responsive-variant");
    if (wrapper) {
      var pageWidth = Number.parseFloat(page.getAttribute("data-page-width") || "0") || page.offsetWidth || 1;
      var scale = page.getBoundingClientRect().width / pageWidth;
      wrapper.style.height = pageBottom * scale + "px";
    }
  }

  function carouselActiveKey(root, slides, thumbs) {
    var defaultSlide = slides.find(function (slide) {
      return slide.getAttribute("data-carousel-default") === "true";
    });
    if (defaultSlide) {
      return defaultSlide.getAttribute("data-carousel-slide") || "";
    }
    var defaultThumb = thumbs.find(function (thumb) {
      return thumb.getAttribute("data-carousel-default") === "true";
    });
    if (defaultThumb) {
      return defaultThumb.getAttribute("data-carousel-thumb") || "";
    }
    return slides.length ? slides[0].getAttribute("data-carousel-slide") || "" : "";
  }

  function setCarouselState(root, activeKey) {
    if (!activeKey) {
      return;
    }
    root.dataset.carouselActive = activeKey;
    Array.from(root.querySelectorAll("[data-carousel-slide]")).forEach(function (slide) {
      var isActive = slide.getAttribute("data-carousel-slide") === activeKey;
      slide.hidden = !isActive;
      slide.setAttribute("aria-hidden", isActive ? "false" : "true");
      slide.style.visibility = isActive ? "visible" : "hidden";
      slide.style.opacity = isActive ? "1" : "0";
      slide.style.pointerEvents = isActive ? "" : "none";
    });
    Array.from(root.querySelectorAll("[data-carousel-thumb]")).forEach(function (thumb) {
      var isActive = thumb.getAttribute("data-carousel-thumb") === activeKey;
      thumb.dataset.carouselActive = isActive ? "true" : "false";
      thumb.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function initializeCarouselRoot(root) {
    if (root.dataset.carouselReady === "true") {
      return;
    }
    var slides = Array.from(root.querySelectorAll("[data-carousel-slide]"));
    var thumbs = Array.from(root.querySelectorAll("[data-carousel-thumb]"));
    if (!slides.length) {
      root.dataset.carouselReady = "true";
      return;
    }
    var slideKeys = slides.map(function (slide) {
      return slide.getAttribute("data-carousel-slide") || "";
    });
    thumbs.forEach(function (thumb, index) {
      var key = thumb.getAttribute("data-carousel-thumb") || "";
      if (slideKeys.indexOf(key) === -1 && slideKeys[index]) {
        thumb.setAttribute("data-carousel-thumb", slideKeys[index]);
      }
      thumb.addEventListener("click", function () {
        setCarouselState(root, thumb.getAttribute("data-carousel-thumb") || "");
        schedule(root.closest(".pipeline-page"));
      });
    });
    setCarouselState(root, carouselActiveKey(root, slides, thumbs));
    root.dataset.carouselReady = "true";
  }

  function closeSiblingAccordions(item) {
    var root = item.closest('[data-component="accordion"]');
    if (!root || !accordionSingleMode(root)) {
      return;
    }
    root.querySelectorAll(':scope > details[data-component="accordion-item"][open]').forEach(function (candidate) {
      if (candidate !== item) {
        candidate.open = false;
      }
    });
  }

  function normalizeInitialAccordionState(root) {
    if (!accordionSingleMode(root)) {
      return;
    }
    var opened = sortedByOriginalTop(Array.from(root.querySelectorAll(':scope > details[data-component="accordion-item"][open]')));
    opened.slice(1).forEach(function (item) {
      item.open = false;
    });
  }

  function schedule(page) {
    if (!page || page.dataset.pipelineRuntimeScheduled === "true") {
      return;
    }
    page.dataset.pipelineRuntimeScheduled = "true";
    window.requestAnimationFrame(function () {
      delete page.dataset.pipelineRuntimeScheduled;
      layoutPage(page);
    });
  }

  function init() {
    document.querySelectorAll(".pipeline-page").forEach(function (page) {
      page.querySelectorAll("[data-carousel='true']").forEach(initializeCarouselRoot);
      page.querySelectorAll("[data-component='accordion']").forEach(normalizeInitialAccordionState);
      page.querySelectorAll("[data-component='accordion'] > details[data-component='accordion-item']").forEach(function (item) {
        item.addEventListener("toggle", function () {
          if (item.open) {
            closeSiblingAccordions(item);
          }
          schedule(page);
        });
      });
      schedule(page);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
  window.addEventListener("resize", function () {
    document.querySelectorAll(".pipeline-page").forEach(schedule);
  }, { passive: true });
})();
"""
)

SINGLE_TEMPLATE = (
    HUGO_COMMENT
    + """
{{ define "main" }}
  {{ with .Params.pipelineResponsiveKey }}
    {{ $page := index hugo.Data.pipeline.responsive . }}
    {{ partial "pipeline/responsive-page.html" $page }}
  {{ else }}
    {{ $pageKey := .Params.pipelinePageKey }}
    {{ $page := index hugo.Data.pipeline.pages $pageKey }}
    {{ partial "pipeline/page.html" $page }}
  {{ end }}
{{ end }}
"""
)

INDEX_TEMPLATE = (
    HUGO_COMMENT
    + """
{{ define "main" }}
  <main style="margin:40px;font-family:Arial,sans-serif">
    <h1>{{ .Title }}</h1>
    <ul>
      {{ range hugo.Data.pipeline.site.pages }}
        <li><a href="{{ .path }}">{{ .title }}</a>{{ if .responsive }} <strong>responsive</strong>{{ end }}</li>
      {{ end }}
    </ul>
  </main>
{{ end }}
"""
)

PAGE_PARTIAL = (
    HUGO_COMMENT
    + """
{{ $page := .page }}
<main class="pipeline-page" data-page-id="{{ $page.id }}" data-page-width="{{ $page.width }}">
  {{ range .sections }}
    {{ partial "pipeline/section.html" . }}
  {{ end }}
</main>
"""
)

RESPONSIVE_PAGE_PARTIAL = (
    HUGO_COMMENT
    + """
{{ range .variants }}
  <div class="pipeline-responsive-variant pipeline-responsive-variant-{{ .width }}" data-pipeline-width="{{ .width }}">
    {{ partial "pipeline/page.html" .page }}
  </div>
{{ end }}
"""
)

SECTION_PARTIAL = (
    HUGO_COMMENT
    + """
{{ $b := .bounds }}
<section class="pipeline-section pipeline-section-{{ .layoutMode }}" data-section-id="{{ .id }}" data-section-name="{{ .name }}" style="left:{{ $b.x }}px;top:{{ $b.y }}px;width:{{ $b.width }}px;min-height:{{ $b.height }}px;{{ range $name, $value := .style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
  {{ range .nodes }}
    {{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
  {{ end }}
</section>
"""
)

NODE_PARTIAL = (
    HUGO_COMMENT
    + """
{{ $node := .node }}
{{ $b := $node.bounds }}
{{ $attrs := $node.attributes | default (dict) }}
{{ $component := $node.component | default "" }}
{{ $class := printf "pipeline-node pipeline-layer-%s" $node.layer }}
{{ if eq $node.kind "text" }}{{ $class = printf "%s pipeline-text" $class }}{{ end }}
{{ if or (eq $component "field") (eq $component "textarea") }}{{ $class = printf "%s pipeline-form-control" $class }}{{ end }}
{{ if eq $component "select" }}{{ $class = printf "%s pipeline-select-wrapper" $class }}{{ end }}
{{ if eq $component "submit" }}{{ $class = printf "%s pipeline-button" $class }}{{ end }}
{{ if eq $component "link-card" }}{{ $class = printf "%s pipeline-link-card" $class }}{{ end }}
{{ if eq $component "carousel" }}{{ $class = printf "%s pipeline-carousel" $class }}{{ end }}
{{ if eq $component "carousel-stage" }}{{ $class = printf "%s pipeline-carousel-stage" $class }}{{ end }}
{{ if eq $component "carousel-nav" }}{{ $class = printf "%s pipeline-carousel-nav" $class }}{{ end }}
{{ if eq $component "carousel-slide" }}{{ $class = printf "%s pipeline-carousel-slide" $class }}{{ end }}
{{ if eq $component "carousel-thumb" }}{{ $class = printf "%s pipeline-carousel-thumb" $class }}{{ end }}
{{ if eq $component "accordion-item" }}{{ $class = printf "%s pipeline-accordion-item" $class }}{{ end }}
{{ if eq $component "accordion-trigger" }}{{ $class = printf "%s pipeline-accordion-trigger" $class }}{{ end }}
{{ if eq $component "accordion-panel" }}{{ $class = printf "%s pipeline-accordion-panel" $class }}{{ end }}
{{ $style := printf "left:%gpx;top:%gpx;width:%gpx;min-height:%gpx;" (sub $b.x .originX) (sub $b.y .originY) $b.width $b.height }}
{{ if or $node.assetUrl (eq $node.kind "asset") }}{{ $style = printf "%sheight:%gpx;" $style $b.height }}{{ end }}
{{ if eq $node.kind "text" }}{{ $style = printf "%sheight:%gpx;" $style $b.height }}{{ end }}
{{ if eq $component "form" }}
<form class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" method="{{ default "post" (index $attrs "method") }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</form>
{{ else if eq $component "field" }}
<input class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}" type="{{ default "text" (index $attrs "type") }}"{{ with index $attrs "name" }} name="{{ . }}"{{ end }}{{ with index $attrs "placeholder" }} placeholder="{{ . }}"{{ end }}{{ with index $attrs "required" }} required{{ end }}>
{{ else if eq $component "textarea" }}
<textarea class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}"{{ with index $attrs "name" }} name="{{ . }}"{{ end }}{{ with index $attrs "placeholder" }} placeholder="{{ . }}"{{ end }}{{ with index $attrs "required" }} required{{ end }}></textarea>
{{ else if eq $component "select" }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
<select class="pipeline-form-control pipeline-select-control" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}"{{ with index $attrs "name" }} name="{{ . }}"{{ end }}{{ with index $attrs "placeholder" }} aria-label="{{ . }}"{{ end }}{{ with index $attrs "required" }} required{{ end }}>
  <option value="" style="color:#111;background-color:#fff;">{{ default "" (index $attrs "placeholder") }}</option>
  {{ range (index $attrs "options") }}
    <option value="{{ default "" (index . "value") }}" style="color:#111;background-color:#fff;">{{ default (index . "value") (index . "label") }}</option>
  {{ end }}
</select>
<span class="pipeline-select-arrow" aria-hidden="true"></span>
</div>
{{ else if eq $component "submit" }}
{{ $label := default $node.name (index $attrs "label") }}{{ if $node.text }}{{ $label = $node.text }}{{ end }}
<button class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}" type="{{ default "submit" (index $attrs "type") }}">{{ $label }}</button>
{{ else if eq $component "link-card" }}
<a class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}" href="{{ default "#" (index $attrs "href") }}"{{ with index $attrs "target" }} target="{{ . }}"{{ end }}{{ with index $attrs "rel" }} rel="{{ . }}"{{ end }}{{ with index $attrs "label" }} aria-label="{{ . }}"{{ end }}>
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</a>
{{ else if eq $component "carousel" }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" data-carousel="true" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</div>
{{ else if eq $component "carousel-stage" }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" data-carousel-stage="true" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</div>
{{ else if eq $component "carousel-nav" }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" data-carousel-nav="true" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</div>
{{ else if eq $component "carousel-slide" }}
{{ $key := default $node.id (index $attrs "key") }}
{{ $isDefault := eq (default "" (index $attrs "default")) "true" }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" data-carousel-slide="{{ $key }}"{{ if $isDefault }} data-carousel-default="true" aria-hidden="false"{{ else }} hidden aria-hidden="true"{{ end }} style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</div>
{{ else if eq $component "carousel-thumb" }}
{{ $key := default $node.id (index $attrs "key") }}
{{ $isDefault := eq (default "" (index $attrs "default")) "true" }}
<button class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" type="button" data-carousel-thumb="{{ $key }}"{{ if $isDefault }} data-carousel-default="true" aria-pressed="true"{{ else }} aria-pressed="false"{{ end }} style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</button>
{{ else if eq $component "accordion-item" }}
<details class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}"{{ with index $attrs "open" }} open{{ end }}>
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</details>
{{ else if eq $component "accordion-trigger" }}
<summary class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</summary>
{{ else if eq $component "accordion-panel" }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}" data-component="{{ $component }}" style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end }}
</div>
{{ else }}
<div class="{{ $class }}" data-node-id="{{ $node.id }}" data-node-name="{{ $node.name }}" data-kind="{{ $node.kind }}"{{ if $component }} data-component="{{ $component }}"{{ end }} style="{{ $style | safeCSS }}{{ range $name, $value := $node.style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}">
{{- if $node.assetUrl -}}
<img class="pipeline-img" src="{{ $node.assetUrl }}" alt="{{ $node.name }}">
{{- else if index $attrs "textLines" -}}
<span class="pipeline-text-content pipeline-list-text">{{- range (index $attrs "textLines") -}}<span class="pipeline-list-line" data-list-type="{{ default "none" .type }}" style="--pipeline-list-level:{{ default 0 .indent }};">{{ default "" .text }}</span>{{- end -}}</span>
{{- else if $node.textRuns -}}
<span class="pipeline-text-content">{{- range $node.textRuns -}}<span{{ if .style }} style="{{ range $name, $value := .style }}{{ $name }}:{{ $value | safeCSS }};{{ end }}"{{ end }}>{{ .text }}</span>{{- end -}}</span>
{{- else if $node.text -}}
{{- $node.text -}}
{{- else -}}
{{- range $node.children }}
{{ partial "pipeline/node.html" (dict "node" . "originX" $b.x "originY" $b.y) }}
{{- end -}}
{{- end -}}
</div>
{{ end }}
"""
)
