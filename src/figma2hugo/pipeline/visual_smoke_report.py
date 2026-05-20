"""Transforme les resultats de smoke visuel en rapport HTML compact."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def render_review_html(report: dict[str, Any]) -> str:
    visual_review = report.get("visualReview", {})
    browser = report.get("browser", {})
    items = visual_review.get("items", []) if isinstance(visual_review, dict) else []
    cards = "\n".join(_render_review_card(item) for item in items if isinstance(item, dict))
    contact_sheet = (
        visual_review.get("contactSheet")
        if isinstance(visual_review, dict) and visual_review.get("contactSheet")
        else None
    )
    contact_sheet_html = (
        f'<p><a href="{html.escape(str(contact_sheet))}">Open contact sheet</a></p>'
        if contact_sheet
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>figma2hugo pipeline visual review</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f6f7fb; color: #101828; }}
    header {{ padding: 24px 32px; background: #06245c; color: white; }}
    main {{ padding: 24px 32px; display: grid; gap: 20px; }}
    article {{ background: white; border: 1px solid #d0d5dd; border-radius: 8px; padding: 16px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .meta {{ color: #475467; font-size: 13px; margin-bottom: 12px; }}
    .status {{ font-weight: 700; }}
    .images {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    figure {{ margin: 0; }}
    figcaption {{ font-size: 12px; color: #475467; margin-bottom: 6px; }}
    img {{ max-width: 100%; border: 1px solid #eaecf0; background: white; }}
  </style>
</head>
<body>
  <header>
    <h1>figma2hugo pipeline visual review</h1>
    <p>{html.escape(str(report.get("pageCount", 0)))} pages, {html.escape(str(report.get("viewportCount", 0)))} viewport probes</p>
    {_render_browser_status(browser if isinstance(browser, dict) else {})}
    {contact_sheet_html}
  </header>
  <main>
    {cards or "<p>No screenshots captured.</p>"}
  </main>
</body>
</html>
"""


def _render_browser_status(browser: dict[str, Any]) -> str:
    if not browser:
        return ""
    status = str(browser.get("status") or "")
    engine = str(browser.get("engine") or "")
    checks = str(browser.get("checks") or "")
    reason = str(browser.get("reason") or "")
    reason_html = f"<br>Reason: {html.escape(reason)}" if reason else ""
    return (
        "<p>"
        f"Browser engine: {html.escape(engine)} "
        f"({html.escape(status)}, {html.escape(checks)})"
        f"{reason_html}"
        "</p>"
    )


def _render_review_card(item: dict[str, Any]) -> str:
    title = f"{item.get('slug', '')} - {item.get('viewport', '')}px"
    ratio = item.get("pixelDiffRatio")
    ratio_text = "n/a" if ratio is None else f"{float(ratio) * 100:.3f}%"
    reference_label = (
        "Figma reference" if item.get("referenceKind") == "figma-reference" else "Baseline"
    )
    figures = [_render_review_figure("Current", item.get("screenshot"))]
    figures.append(_render_review_figure(reference_label, item.get("baseline")))
    figures.append(_render_review_figure("Diff", item.get("diff")))
    return f"""<article>
  <h2>{html.escape(title)}</h2>
  <div class="meta">Status: <span class="status">{html.escape(str(item.get("status", "")))}</span> | Pixel diff: {html.escape(ratio_text)}</div>
  <div class="images">
    {"".join(figures)}
  </div>
</article>"""


def _render_review_figure(label: str, path: object) -> str:
    if not path:
        return f"<figure><figcaption>{html.escape(label)}</figcaption><p>Not available</p></figure>"
    source = html.escape(str(path))
    return (
        f"<figure><figcaption>{html.escape(label)}</figcaption>"
        f'<img src="{source}" alt="{html.escape(label)}"></figure>'
    )


def write_contact_sheet(screenshots: list[dict[str, Any]], *, out_dir: Path) -> Path | None:
    if not screenshots:
        return None
    pages = _ordered_values(screenshots, "slug")
    widths = _ordered_values(screenshots, "viewport")
    records_by_key = {
        (str(item.get("slug") or ""), int(item.get("viewport") or 0)): item
        for item in screenshots
        if item.get("slug") and item.get("viewport")
    }

    thumb_width = 260
    max_thumb_height = 680
    row_label_width = 190
    label_height = 28
    header_height = 40
    gutter = 12
    font = ImageFont.load_default()
    thumbnails: dict[tuple[str, int], Image.Image] = {}
    row_heights: list[int] = []
    for page in pages:
        max_height = 0
        for width_value in widths:
            width = int(width_value)
            item = records_by_key.get((page, width))
            if not item:
                continue
            path = out_dir / str(item.get("path") or "")
            if not path.exists():
                continue
            with Image.open(path) as image:
                source = image.convert("RGB")
                ratio = thumb_width / max(1, source.width)
                thumb_height = min(max_thumb_height, max(1, int(source.height * ratio)))
                thumbnail = source.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
                thumbnails[(page, width)] = thumbnail
                max_height = max(max_height, thumb_height)
        row_heights.append(max_height + label_height)
    if not thumbnails:
        return None

    sheet_width = row_label_width + len(widths) * (thumb_width + gutter) + gutter
    sheet_height = header_height + sum(row_heights) + (len(pages) + 1) * gutter
    sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
    draw = ImageDraw.Draw(sheet)

    x = row_label_width + gutter
    for width_value in widths:
        draw.text((x, 12), str(width_value), fill=(20, 20, 20), font=font)
        x += thumb_width + gutter

    y = header_height + gutter
    for index, page in enumerate(pages):
        draw.text((12, y + label_height), page, fill=(20, 20, 20), font=font)
        x = row_label_width + gutter
        for width_value in widths:
            width = int(width_value)
            current_thumbnail = thumbnails.get((page, width))
            item = records_by_key.get((page, width))
            status = _visual_status(item)
            draw.text((x, y), status, fill=_status_color(status), font=font)
            if current_thumbnail is not None:
                draw.rectangle(
                    (
                        x - 1,
                        y + label_height - 1,
                        x + thumb_width,
                        y + label_height + current_thumbnail.height,
                    ),
                    outline=(210, 210, 210),
                )
                sheet.paste(current_thumbnail, (x, y + label_height))
            else:
                draw.rectangle(
                    (x - 1, y + label_height - 1, x + thumb_width, y + label_height + 120),
                    outline=(210, 210, 210),
                )
                draw.text((x + 10, y + label_height + 12), "missing", fill=(120, 0, 0), font=font)
            x += thumb_width + gutter
        y += row_heights[index] + gutter

    contact_sheet_path = out_dir / "contact-sheet.png"
    sheet.save(contact_sheet_path)
    return contact_sheet_path


def _ordered_values(items: list[dict[str, Any]], key: str) -> list[Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for item in items:
        value = item.get(key)
        marker = str(value)
        if value is None or marker in seen:
            continue
        seen.add(marker)
        values.append(value)
    return values


def _visual_status(item: dict[str, Any] | None) -> str:
    if not item:
        return "missing"
    review = item.get("visualReview")
    if not isinstance(review, dict):
        return "capture-only"
    return str(review.get("status") or "capture-only")


def _status_color(status: str) -> tuple[int, int, int]:
    if status == "pass":
        return (15, 118, 65)
    if status in {"review", "capture-only"}:
        return (181, 71, 8)
    if status in {"fail", "missing-baseline", "missing-figma-reference", "missing"}:
        return (180, 35, 24)
    return (71, 84, 103)
