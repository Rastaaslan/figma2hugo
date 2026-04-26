from __future__ import annotations

import html
from pathlib import Path
from typing import Any

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    Environment = None
    FileSystemLoader = None
    select_autoescape = None

from .._shared import (
    CanonicalModelBuilder,
    GenerationArtifacts,
    copy_assets,
    ensure_directory,
    locate_templates_root,
    write_json_file,
    write_text_file,
)
from ..css import CssGenerator


class StaticGenerator:
    def __init__(self) -> None:
        self._builder = CanonicalModelBuilder(mode="static")
        self._css_generator = CssGenerator()

    def generate(self, model: Any, output_dir: str | Path, report: dict[str, Any] | None = None) -> GenerationArtifacts:
        output_path = Path(output_dir)
        ensure_directory(output_path)
        page_data = self._builder.build(model)
        context = {
            "page": page_data["page"],
            "sections": page_data["sections"],
            "header_sections": [section for section in page_data["sections"] if section["tag"] in {"header", "nav"}],
            "body_sections": [
                section for section in page_data["sections"] if section["tag"] not in {"header", "nav", "footer"}
            ],
            "footer_sections": [section for section in page_data["sections"] if section["tag"] == "footer"],
            "warnings": page_data["warnings"],
        }
        environment = self._environment()
        html_output = (
            environment.get_template("index.html.j2").render(**context)
            if environment is not None
            else self._render_without_jinja(context)
        )
        css_output = self._css_generator.generate(page_data)
        written_files = [
            write_text_file(output_path / "index.html", html_output),
            write_text_file(output_path / "styles.css", css_output),
            write_json_file(output_path / "page.json", page_data),
        ]
        written_files.extend(copy_assets(page_data, output_path, mode="static"))
        if report is not None:
            written_files.append(write_json_file(output_path / "report.json", report))
        if page_data["assets"]:
            ensure_directory(output_path / "images")
        return GenerationArtifacts(output_dir=output_path, written_files=tuple(written_files), page_data=page_data)

    def _environment(self) -> Environment | None:
        if Environment is None or FileSystemLoader is None or select_autoescape is None:
            return None
        templates_dir = locate_templates_root() / "static"
        return Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(enabled_extensions=("html", "htm", "xml", "j2"), default=True),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _render_without_jinja(self, context: dict[str, Any]) -> str:
        lines = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"    <title>{html.escape(context['page']['title'])}</title>",
            '    <link rel="stylesheet" href="styles.css">',
            "  </head>",
            f'  <body class="page page--{html.escape(context["page"]["slug"])}">',
        ]
        for section in context["header_sections"]:
            lines.extend(self._render_section(section, indent="    "))
        lines.append('    <main class="page-main">')
        for section in context["body_sections"]:
            lines.extend(self._render_section(section, indent="      "))
        lines.append("    </main>")
        for section in context["footer_sections"]:
            lines.extend(self._render_section(section, indent="    "))
        lines.extend(["  </body>", "</html>"])
        return "\n".join(lines) + "\n"

    def _render_section(self, section: dict[str, Any], *, indent: str) -> list[str]:
        lines = [
            f'{indent}<{section["tag"]} id="{html.escape(section["anchor"])}" class="page-section {html.escape(section["class_name"])}">',
            f'{indent}  <div class="page-section__inner">',
        ]
        for node in section["children"]:
            lines.extend(self._render_node(node, indent=f"{indent}    "))
        lines.extend([f"{indent}  </div>", f"{indent}</{section['tag']}>"])
        return lines

    def _render_node(self, node: dict[str, Any], *, indent: str) -> list[str]:
        kind = node.get("kind")
        if kind == "text":
            return self._render_text(node["text"], indent=indent)
        if kind == "asset":
            return self._render_asset(node["asset"], indent=indent)
        attrs = self._render_attributes(node.get("attributes", {}))
        lines = [
            f'{indent}<{node["tag"]} id="{html.escape(node["id"])}" class="content-node {html.escape(node["class_name"])}"{attrs}>'
        ]
        for child in node.get("children", []):
            lines.extend(self._render_node(child, indent=f"{indent}  "))
        lines.append(f"{indent}</{node['tag']}>")
        return lines

    def _render_text(self, text_item: dict[str, Any], *, indent: str) -> list[str]:
        attrs = self._render_attributes(text_item.get("attributes", {}))
        if text_item.get("segments"):
            segments = []
            for segment in text_item["segments"]:
                style_attr = (
                    f' style="{html.escape(segment["style"], quote=True)}"'
                    if segment.get("style")
                    else ""
                )
                segments.append(
                    f'<span class="{html.escape(segment["class_name"])}"{style_attr}>{segment["html"]}</span>'
                )
            content = "".join(segments)
        else:
            content = text_item["html"]
        return [
            f'{indent}<{text_item["tag"]} id="{html.escape(text_item["id"])}" class="content-text {html.escape(text_item["class_name"])}"{attrs}>{content}</{text_item["tag"]}>'
        ]

    def _render_asset(self, asset: dict[str, Any], *, indent: str) -> list[str]:
        if asset.get("render") is False:
            return []
        figure_class = f'content-asset {asset["class_name"]}'
        if asset.get("aria_hidden"):
            figure_class += " is-decorative"
        if asset.get("render_mode") == "shape" or asset.get("format") == "shape":
            return [f'{indent}<figure class="{html.escape(figure_class)}"></figure>']
        img_attributes = {
            "src": asset["public_path"],
            "alt": asset["alt"],
            **asset.get("attributes", {}),
        }
        if asset.get("aria_hidden"):
            img_attributes["aria-hidden"] = "true"
        if asset.get("width"):
            img_attributes["width"] = str(asset["width"])
        if asset.get("height"):
            img_attributes["height"] = str(asset["height"])
        return [
            f'{indent}<figure class="{html.escape(figure_class)}">',
            f'{indent}  <img{self._render_attributes(img_attributes)}>',
            f"{indent}</figure>",
        ]

    def _render_attributes(self, attributes: dict[str, Any]) -> str:
        rendered = []
        for name, value in attributes.items():
            if value in (None, ""):
                continue
            rendered.append(f' {html.escape(str(name))}="{html.escape(str(value), quote=True)}"')
        return "".join(rendered)
