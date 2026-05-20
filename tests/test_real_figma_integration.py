from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from figma2hugo.local_config import get_local_figma_token
from figma2hugo.pipeline.runner import build_pipeline_hugo_site_from_figma_urls

ROOT = Path(__file__).resolve().parents[1]
REAL_FIGMA_URLS_ENV = "FIGMA2HUGO_REAL_FIGMA_URLS"
REAL_FIGMA_OUT_ENV = "FIGMA2HUGO_REAL_FIGMA_OUT"


def test_configured_real_figma_urls_accept_common_separators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        REAL_FIGMA_URLS_ENV,
        " https://www.figma.com/design/FILE/A?node-id=1-1\n"
        "https://www.figma.com/design/FILE/B?node-id=2-2; "
        "https://www.figma.com/design/FILE/C?node-id=3-3",
    )

    assert _configured_real_figma_urls() == (
        "https://www.figma.com/design/FILE/A?node-id=1-1",
        "https://www.figma.com/design/FILE/B?node-id=2-2",
        "https://www.figma.com/design/FILE/C?node-id=3-3",
    )


def test_real_figma_urls_generate_valid_hugo_site() -> None:
    figma_urls = _configured_real_figma_urls()
    if not figma_urls:
        pytest.skip(f"Set {REAL_FIGMA_URLS_ENV} to run real Figma validation.")
    if not _has_figma_access():
        pytest.skip("Configure FIGMA_ACCESS_TOKEN, FIGMA_TOKEN or FIGMA_MCP_* to access Figma.")

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = _configured_output_dir(Path(temp_dir))
        result = build_pipeline_hugo_site_from_figma_urls(list(figma_urls), output_dir)

        report_path = output_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))

        assert result["pipeline"] == "pipeline"
        assert report["buildOk"] is True
        assert _generated_page_count(output_dir) >= 1
        if report.get("responsive", {}).get("checked"):
            responsive_summary = report["responsive"].get("summary", {})
            assert responsive_summary.get("horizontalOverflowCount", 0) == 0


def _configured_real_figma_urls() -> tuple[str, ...]:
    raw_value = os.getenv(REAL_FIGMA_URLS_ENV, "")
    return tuple(url.strip() for url in re.split(r"[\n;,]+", raw_value) if url.strip())


def _has_figma_access() -> bool:
    return any(
        [
            os.getenv("FIGMA_ACCESS_TOKEN"),
            os.getenv("FIGMA_TOKEN"),
            os.getenv("FIGMA_MCP_URL"),
            os.getenv("FIGMA_MCP_COMMAND"),
            get_local_figma_token(),
        ]
    )


def _configured_output_dir(tmp_path: Path) -> Path:
    configured = os.getenv(REAL_FIGMA_OUT_ENV, "").strip()
    if configured:
        return Path(configured)
    return tmp_path / "real-figma-site"


def _generated_page_count(output_dir: Path) -> int:
    pipeline_pages_dir = output_dir / "data" / "pipeline" / "pages"
    if pipeline_pages_dir.exists():
        return len(list(pipeline_pages_dir.glob("*.json")))
    site_manifest = output_dir / "data" / "site.json"
    if site_manifest.exists():
        payload = json.loads(site_manifest.read_text(encoding="utf-8"))
        pages = payload.get("pages", [])
        return len(pages) if isinstance(pages, list) else 0
    return int((output_dir / "data" / "page.json").exists())
