from __future__ import annotations

from pathlib import Path
from typing import Any

from .._shared import (
    CanonicalModelBuilder,
    GenerationArtifacts,
    copy_assets,
    copy_tree,
    ensure_directory,
    locate_templates_root,
    write_json_file,
    write_text_file,
)
from ..css import CssGenerator


class HugoGenerator:
    def __init__(self) -> None:
        self._builder = CanonicalModelBuilder(mode="hugo")
        self._css_generator = CssGenerator()

    def generate(self, model: Any, output_dir: str | Path, report: dict[str, Any] | None = None) -> GenerationArtifacts:
        output_path = Path(output_dir)
        ensure_directory(output_path)
        page_data = self._builder.build(model)
        templates_root = locate_templates_root() / "hugo"
        written_files = copy_tree(templates_root, output_path)
        written_files.append(write_text_file(output_path / "assets" / "css" / "main.css", self._css_generator.generate(page_data)))
        written_files.append(write_json_file(output_path / "data" / "page.json", page_data))
        written_files.extend(copy_assets(page_data, output_path, mode="hugo"))
        if report is not None:
            written_files.append(write_json_file(output_path / "report.json", report))
        if page_data["assets"]:
            ensure_directory(output_path / "static" / "images")
        return GenerationArtifacts(output_dir=output_path, written_files=tuple(written_files), page_data=page_data)
