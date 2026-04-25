from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReportWriter:
    def write(self, target_dir: Path, report: dict[str, Any]) -> Path:
        path = target_dir / "report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        return path

    def read(self, target_dir: Path) -> dict[str, Any]:
        path = target_dir / "report.json"
        return json.loads(path.read_text(encoding="utf-8"))
