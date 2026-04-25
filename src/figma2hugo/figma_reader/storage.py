from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RunDirectories:
    root: Path
    raw_dir: Path
    sections_dir: Path
    assets_dir: Path
    reports_dir: Path
    reference_dir: Path

    @classmethod
    def create(cls, root: Path) -> "RunDirectories":
        raw_dir = root / "raw"
        sections_dir = raw_dir / "sections"
        assets_dir = root / "assets"
        reports_dir = root / "reports"
        reference_dir = root / "reference"

        for directory in (root, raw_dir, sections_dir, assets_dir, reports_dir, reference_dir):
            directory.mkdir(parents=True, exist_ok=True)

        return cls(
            root=root,
            raw_dir=raw_dir,
            sections_dir=sections_dir,
            assets_dir=assets_dir,
            reports_dir=reports_dir,
            reference_dir=reference_dir,
        )


class ExtractionStore:
    def __init__(self, root: Path) -> None:
        self.dirs = RunDirectories.create(root)

    def path(self, *parts: str) -> Path:
        return self.dirs.root.joinpath(*parts)

    def exists(self, *parts: str) -> bool:
        return self.path(*parts).exists()

    def write_json(self, relative_path: str | Path, payload: Any) -> Path:
        path = self.dirs.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return path

    def read_json(self, relative_path: str | Path) -> Any:
        return json.loads((self.dirs.root / relative_path).read_text(encoding="utf-8"))

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        path = self.dirs.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_text(self, relative_path: str | Path) -> str:
        return (self.dirs.root / relative_path).read_text(encoding="utf-8")

    def write_bytes(self, relative_path: str | Path, content: bytes) -> Path:
        path = self.dirs.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def read_bytes(self, relative_path: str | Path) -> bytes:
        return (self.dirs.root / relative_path).read_bytes()
