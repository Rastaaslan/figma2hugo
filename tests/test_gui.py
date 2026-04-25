from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import figma2hugo.gui as gui_module
import figma2hugo.local_config as local_config


def test_gui_main_launches_app(monkeypatch) -> None:
    launched = {"called": False}

    monkeypatch.setattr(
        gui_module,
        "launch_app",
        lambda: launched.__setitem__("called", True),
    )

    gui_module.main()

    assert launched["called"] is True


def test_has_figma_access_accepts_token_override(monkeypatch) -> None:
    monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_MCP_URL", raising=False)
    monkeypatch.delenv("FIGMA_MCP_COMMAND", raising=False)

    assert gui_module._has_figma_access("secret-token") is True


def test_has_figma_access_detects_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_MCP_URL", raising=False)
    monkeypatch.delenv("FIGMA_MCP_COMMAND", raising=False)
    monkeypatch.setattr(gui_module, "get_local_figma_token", lambda: None)

    assert gui_module._has_figma_access("") is False
    assert "Generation impossible" in gui_module._missing_access_message()


def test_local_config_reads_token_from_project_file(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        config_path = temp_path / "figma2hugo.local.json"
        config_path.write_text('{"figma_access_token":"abc123"}', encoding="utf-8")
        monkeypatch.setenv("FIGMA2HUGO_HOME", str(temp_path))
        monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("FIGMA_TOKEN", raising=False)

        assert local_config.get_local_config_path() == config_path
        assert local_config.get_local_figma_token() == "abc123"
