"""Ecrit un site statique de revue depuis les plans de rendu, hors runtime Hugo."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from figma2hugo.pipeline.html_renderer import (
    render_static_body,
    render_static_css,
    render_static_document,
)
from figma2hugo.pipeline.models import RenderPlan
from figma2hugo.pipeline.naming import slugify as _slug
from figma2hugo.pipeline.naming import unique_slug as _unique_slug
from figma2hugo.pipeline.responsive import ResponsiveManifest


@dataclass(frozen=True, slots=True)
class PipelineSitePage:
    slug: str
    title: str
    html_path: Path
    css_path: Path


@dataclass(frozen=True, slots=True)
class PipelineResponsivePage:
    slug: str
    title: str
    html_path: Path
    css_path: Path


def write_pipeline_static_site(
    plans: list[RenderPlan],
    out_dir: Path,
    *,
    responsive_manifest: ResponsiveManifest | None = None,
) -> dict[str, Any]:
    if not plans:
        raise ValueError("Pipeline static site requires at least one render plan.")
    pages_dir = out_dir / "pages"
    assets_dir = out_dir / "assets"
    pages_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    pages: list[PipelineSitePage] = []
    used_slugs: set[str] = set()
    for index, plan in enumerate(plans, start=1):
        slug = _unique_slug(_slug(plan.page_name) or f"page-{index}", used_slugs)
        page_dir = pages_dir / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        css_path = assets_dir / f"{slug}.css"
        html_path = page_dir / "index.html"
        css_path.write_text(render_static_css(plan) + "\n", encoding="utf-8")
        html_path.write_text(
            render_static_document(plan, stylesheet_href=f"../../assets/{slug}.css") + "\n",
            encoding="utf-8",
        )
        pages.append(
            PipelineSitePage(
                slug=slug, title=plan.page_name, html_path=html_path, css_path=css_path
            )
        )

    responsive_page = (
        _write_responsive_page(
            plans=plans,
            manifest=responsive_manifest,
            pages_dir=pages_dir,
            assets_dir=assets_dir,
        )
        if responsive_manifest is not None and len(plans) > 1
        else None
    )
    index_path = out_dir / "index.html"
    index_path.write_text(
        _render_index(pages, responsive_page=responsive_page) + "\n", encoding="utf-8"
    )
    payload: dict[str, Any] = {
        "index": str(index_path),
        "pages": [
            {
                "slug": page.slug,
                "title": page.title,
                "html": str(page.html_path),
                "css": str(page.css_path),
            }
            for page in pages
        ],
    }
    if responsive_page is not None:
        payload["responsivePage"] = {
            "slug": responsive_page.slug,
            "title": responsive_page.title,
            "html": str(responsive_page.html_path),
            "css": str(responsive_page.css_path),
        }
    return payload


def _write_responsive_page(
    *,
    plans: list[RenderPlan],
    manifest: ResponsiveManifest,
    pages_dir: Path,
    assets_dir: Path,
) -> PipelineResponsivePage:
    sorted_plans = sorted(plans, key=lambda plan: plan.width, reverse=True)
    slug = _slug(manifest.family) or "responsive"
    page_dir = pages_dir / slug
    page_dir.mkdir(parents=True, exist_ok=True)
    css_path = assets_dir / f"{slug}.responsive.css"
    html_path = page_dir / "index.html"
    css_path.write_text(_render_responsive_css(sorted_plans) + "\n", encoding="utf-8")
    html_path.write_text(
        _render_responsive_document(
            plans=sorted_plans,
            title=manifest.family,
            stylesheet_href=f"../../assets/{slug}.responsive.css",
        )
        + "\n",
        encoding="utf-8",
    )
    return PipelineResponsivePage(
        slug=slug,
        title=f"{manifest.family} responsive",
        html_path=html_path,
        css_path=css_path,
    )


def _render_index(
    pages: list[PipelineSitePage],
    *,
    responsive_page: PipelineResponsivePage | None,
) -> str:
    responsive_link = (
        f'<li><a href="pages/{escape(responsive_page.slug)}/">{escape(responsive_page.title)}</a></li>'
        if responsive_page is not None
        else ""
    )
    debug_links = "\n".join(
        f'<li><a href="pages/{escape(page.slug)}/">{escape(page.title)}</a></li>' for page in pages
    )
    links = "\n".join(part for part in (responsive_link, debug_links) if part)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="fr">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Pipeline</title>",
            "<style>",
            "body{margin:40px;font-family:Arial,sans-serif;background:#f4f6f8;color:#061d4f}",
            "a{color:#061d4f;font-weight:700}",
            "li{margin:12px 0}",
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            "<h1>Pipeline</h1>",
            "<p>Responsive pipeline et pages de debug par largeur.</p>",
            "<ul>",
            links,
            "</ul>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def _render_responsive_document(
    *,
    plans: list[RenderPlan],
    title: str,
    stylesheet_href: str,
) -> str:
    variants = "\n".join(
        (
            f'<div class="pipeline-responsive-variant pipeline-responsive-variant-{plan.width}" '
            f'data-pipeline-width="{plan.width}">\n{render_static_body(plan)}\n</div>'
        )
        for plan in plans
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="fr">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(title)}</title>",
            f'<link rel="stylesheet" href="{escape(stylesheet_href)}">',
            "</head>",
            "<body>",
            variants,
            "</body>",
            "</html>",
        ]
    )


def _render_responsive_css(plans: list[RenderPlan]) -> str:
    sorted_plans = sorted(plans, key=lambda plan: plan.width)
    largest = sorted_plans[-1]
    lines = [
        _base_responsive_css(plans),
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
    base = render_static_css(plans[0])
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
            base,
            ".pipeline-responsive-variant { display: none; overflow: hidden; margin: 0 auto; max-width: 100%; }",
            ".pipeline-responsive-variant .pipeline-page { margin: 0; overflow: visible; transform-origin: top left; }",
            *page_rules,
            *scale_rules,
        ]
    )


def _plan_visual_height(plan: RenderPlan) -> int:
    bottom = int(round(max((section.bounds.bottom for section in plan.sections), default=0)))
    return max(plan.height, bottom)
