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
    assert gui_module._figma_access_source("secret-token") == "token saisi dans l'UI"


def test_has_figma_access_detects_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_MCP_URL", raising=False)
    monkeypatch.delenv("FIGMA_MCP_COMMAND", raising=False)
    monkeypatch.setattr(gui_module, "get_local_figma_token", lambda: None)

    assert gui_module._has_figma_access("") is False
    assert gui_module._figma_access_source("") == "configuration non detectee"
    assert "Generation impossible" in gui_module._missing_access_message()


def test_clean_figma_urls_keeps_only_filled_entries() -> None:
    values = [
        " https://www.figma.com/design/FILE/About?node-id=1-1 ",
        "",
        "   ",
        "https://www.figma.com/design/FILE/Contact?node-id=1-2",
    ]

    assert gui_module._clean_figma_urls(values) == [
        "https://www.figma.com/design/FILE/About?node-id=1-1",
        "https://www.figma.com/design/FILE/Contact?node-id=1-2",
    ]


def test_clean_figma_urls_accepts_stringvar_like_objects() -> None:
    class DummyVar:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self) -> str:
            return self._value

    values = [DummyVar(" https://www.figma.com/design/FILE/About?node-id=1-1 "), DummyVar("")]

    assert gui_module._clean_figma_urls(values) == [
        "https://www.figma.com/design/FILE/About?node-id=1-1"
    ]


def test_selection_hint_message_mentions_responsive_board_for_single_url() -> None:
    message = gui_module._selection_hint_message(
        ["https://www.figma.com/design/FILE/Mentions?node-id=200-1"]
    )

    assert "board unique" in message.lower()
    assert "page-<slug>-<width>" in message
    assert (
        gui_module._supports_static_mode(
            ["https://www.figma.com/design/FILE/Mentions?node-id=200-1"]
        )
        is False
    )


def test_selection_hint_message_disables_static_for_multiple_urls() -> None:
    message = gui_module._selection_hint_message(
        [
            "https://www.figma.com/design/FILE/About?node-id=1-1",
            "https://www.figma.com/design/FILE/Contact?node-id=1-2",
        ]
    )

    assert "statique" not in message.lower()
    assert (
        gui_module._supports_static_mode(
            [
                "https://www.figma.com/design/FILE/About?node-id=1-1",
                "https://www.figma.com/design/FILE/Contact?node-id=1-2",
            ]
        )
        is False
    )


def test_control_states_disable_static_for_multiple_urls_and_running_state() -> None:
    single_url_states = gui_module._control_states(
        ["https://www.figma.com/design/FILE/About?node-id=1-1"],
        running=False,
    )
    multi_url_states = gui_module._control_states(
        [
            "https://www.figma.com/design/FILE/About?node-id=1-1",
            "https://www.figma.com/design/FILE/Contact?node-id=1-2",
        ],
        running=False,
    )
    running_states = gui_module._control_states(
        ["https://www.figma.com/design/FILE/About?node-id=1-1"],
        running=True,
    )

    assert single_url_states.default == "normal"
    assert single_url_states.static_button == "disabled"
    assert single_url_states.progress_running is False
    assert multi_url_states.default == "normal"
    assert multi_url_states.static_button == "disabled"
    assert running_states.default == "disabled"
    assert running_states.static_button == "disabled"
    assert running_states.progress_running is True


def test_generation_launch_summary_pluralizes_page_count() -> None:
    assert gui_module._generation_launch_summary(1) == "Lancement du mode hugo pour 1 page..."
    assert gui_module._generation_launch_summary(3) == "Lancement du mode hugo pour 3 pages..."


def test_gui_hugo_generation_routes_to_pipeline(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_hugo_pipeline(
        figma_urls: list[str], destination: Path, token: str
    ) -> dict[str, object]:
        captured["figma_urls"] = figma_urls
        captured["destination"] = destination
        captured["token"] = token
        return {
            "mode": "hugo",
            "pipeline": "pipeline",
            "outDir": str(destination),
            "writtenFiles": [],
            "report": str(destination / "report.json"),
            "buildOk": True,
        }

    def fail_generation(*_args, **_kwargs):
        raise AssertionError("Hugo UI generation must use pipeline")

    monkeypatch.setattr(gui_module, "_run_hugo_pipeline_generation", fake_hugo_pipeline)
    monkeypatch.setattr(gui_module, "run_generation", fail_generation, raising=False)

    result = gui_module._run_generation_for_gui(
        ["https://www.figma.com/design/FILE/Page?node-id=1-1"],
        tmp_path,
        "secret-token",
    )

    assert result["pipeline"] == "pipeline"
    assert captured == {
        "figma_urls": ["https://www.figma.com/design/FILE/Page?node-id=1-1"],
        "destination": tmp_path,
        "token": "secret-token",
    }


def test_gui_hugo_generation_refreshes_figma_raw_cache(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_build_pipeline_hugo_site_from_figma_urls(
        figma_urls,
        destination,
        *,
        token=None,
        refresh_cache=False,
        **_kwargs,
    ):
        captured["figma_urls"] = figma_urls
        captured["destination"] = destination
        captured["token"] = token
        captured["refresh_cache"] = refresh_cache
        captured["responsive_contract_root"] = _kwargs.get("responsive_contract_root")
        return {
            "mode": "hugo",
            "pipeline": "pipeline",
            "outDir": str(destination),
            "writtenFiles": [],
            "report": str(destination / "report.json"),
            "buildOk": True,
        }

    monkeypatch.setattr(
        gui_module,
        "build_pipeline_hugo_site_from_figma_urls",
        fake_build_pipeline_hugo_site_from_figma_urls,
        raising=False,
    )
    monkeypatch.setattr(
        "figma2hugo.pipeline.runner.build_pipeline_hugo_site_from_figma_urls",
        fake_build_pipeline_hugo_site_from_figma_urls,
    )
    monkeypatch.setattr(
        gui_module,
        "_run_visual_smoke_for_gui",
        lambda destination, **_kwargs: {
            "outDir": str(destination.parent / f"{destination.name}-smoke"),
            "baselineRoot": str(tmp_path / "baselines"),
            "issueCount": 0,
            "errorCount": 0,
            "warnCount": 0,
            "visualReview": {
                "bootstrapRequired": True,
                "baselineRoot": str(tmp_path / "baselines"),
                "byStatus": {"capture-only": 1},
            },
        },
    )

    result = gui_module._run_hugo_pipeline_generation(
        ["https://www.figma.com/design/FILE/Page?node-id=1-1"],
        tmp_path,
        "secret-token",
    )

    assert result["pipeline"] == "pipeline"
    assert captured == {
        "figma_urls": ["https://www.figma.com/design/FILE/Page?node-id=1-1"],
        "destination": tmp_path,
        "token": "secret-token",
        "refresh_cache": True,
        "responsive_contract_root": Path.cwd() / "baselines" / "review" / "pipeline" / "projects",
    }
    assert result["visualSmoke"]["visualReview"]["bootstrapRequired"] is True


def test_gui_hugo_generation_keeps_success_when_visual_smoke_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    def fake_build_pipeline_hugo_site_from_figma_urls(*_args, **_kwargs):
        return {
            "mode": "hugo",
            "pipeline": "pipeline",
            "outDir": str(tmp_path),
            "writtenFiles": [],
            "report": str(tmp_path / "report.json"),
            "buildOk": True,
        }

    monkeypatch.setattr(
        "figma2hugo.pipeline.runner.build_pipeline_hugo_site_from_figma_urls",
        fake_build_pipeline_hugo_site_from_figma_urls,
    )
    monkeypatch.setattr(
        gui_module,
        "_run_visual_smoke_for_gui",
        lambda _destination, **_kwargs: (_ for _ in ()).throw(RuntimeError("hugo missing")),
    )

    result = gui_module._run_hugo_pipeline_generation(
        ["https://www.figma.com/design/FILE/Page?node-id=1-1"],
        tmp_path,
        "secret-token",
    )

    assert result["pipeline"] == "pipeline"
    assert result["visualSmoke"]["error"] == "hugo missing"


def test_format_generation_success_returns_readable_summary() -> None:
    output = gui_module._format_generation_success(
        {
            "mode": "hugo",
            "outDir": "C:/tmp/site",
            "writtenFiles": ["C:/tmp/site/index.html", "C:/tmp/site/report.json"],
            "report": "C:/tmp/site/report.json",
            "buildOk": True,
        }
    )

    assert "Generation terminee." in output
    assert "Mode: hugo" in output
    assert "Build valide: oui" in output
    assert "- C:/tmp/site/index.html" in output


def test_format_generation_success_mentions_visual_baseline_bootstrap() -> None:
    output = gui_module._format_generation_success(
        {
            "mode": "hugo",
            "pipeline": "pipeline",
            "outDir": "C:/tmp/site",
            "writtenFiles": [],
            "report": "C:/tmp/site/report.json",
            "buildOk": True,
            "visualSmokeReport": "C:/tmp/site-smoke/report.json",
            "visualSmoke": {
                "issueCount": 0,
                "errorCount": 0,
                "warnCount": 0,
                "visualReview": {
                    "bootstrapRequired": True,
                    "byStatus": {"capture-only": 1},
                },
            },
        }
    )

    assert "Smoke visuel: issues=0, erreurs=0, warnings=0" in output
    assert "Baseline: capture-only=1" in output
    assert "Action: baseline projet a valider." in output


def test_baseline_promotion_helpers_read_visual_smoke_result(tmp_path) -> None:
    result = {
        "visualSmoke": {
            "outDir": str(tmp_path / "smoke"),
            "visualReview": {
                "bootstrapRequired": True,
                "baselineRoot": str(tmp_path / "baselines"),
            },
        }
    }

    assert gui_module._result_needs_baseline_promotion(result) is True
    assert gui_module._baseline_smoke_out_from_result(result) == tmp_path / "smoke"
    assert gui_module._baseline_root_from_result(result) == tmp_path / "baselines"


def test_format_generation_start_returns_contextual_log(monkeypatch) -> None:
    monkeypatch.setattr(gui_module, "get_local_figma_token", lambda: None)
    output = gui_module._format_generation_start(
        ["https://www.figma.com/design/FILE/Mentions?node-id=200-1"],
        Path("C:/tmp/site"),
        "secret-token",
    )

    assert "Preparation de la generation." in output
    assert "Mode: hugo" in output
    assert "URLs detectees: 1" in output
    assert "Acces Figma: token saisi dans l'UI" in output
    assert "Cache Figma: rafraichissement force" in output
    assert "board top-level `page-<slug>-<width>`" in output


def test_format_progress_event_returns_readable_live_log() -> None:
    output = gui_module._format_progress_event(
        {
            "stage": "extracting Figma data for page 1/3",
            "message": "Extraction Figma de la page 1/3.",
            "input_index": 1,
            "input_total": 3,
            "source_label": "Mentions-legales (node 200:1)",
            "document_name": "page-mentions-legales-834",
            "breakpoint_width": 834,
            "document_names": [
                "page-mentions-legales-1920",
                "page-mentions-legales-834",
                "page-mentions-legales-402",
                "page-mentions-legales-alt",
            ],
        }
    )

    assert output.startswith("[Extraction]")
    assert "Extraction Figma de la page 1/3." in output
    assert "entree 1/3" in output
    assert "source Mentions-legales (node 200:1)" in output
    assert "document page-mentions-legales-834" in output
    assert "largeur 834px" in output
    expected_documents = (
        "documents page-mentions-legales-1920, page-mentions-legales-834, "
        "page-mentions-legales-402, +1 autre(s)"
    )
    assert expected_documents in output


def test_describe_generation_error_detects_invalid_figma_url() -> None:
    described = gui_module._describe_generation_error(
        "Generation failed during initialization: Figma URL must start with http:// or https://.\n"
        "Debug files written to: C:/tmp/debug"
    )

    assert described["status"] == "URL invalide"
    assert "URL Figma est invalide" in described["summary"]
    assert "Figma URL must start with http:// or https://" in described["details"]


def test_describe_generation_error_detects_missing_figma_access() -> None:
    described = gui_module._describe_generation_error(
        "Generation failed during extracting Figma data: "
        "Unable to extract Figma data. Configure FIGMA_ACCESS_TOKEN or a FIGMA_MCP_* bridge."
    )

    assert described["status"] == "Acces Figma manquant"
    assert "Impossible d'acceder a Figma" in described["summary"]
    assert "Generation impossible" in described["details"]


def test_describe_generation_error_uses_stage_specific_label_for_generic_failures() -> None:
    described = gui_module._describe_generation_error(
        "Generation failed during generating the output site: template rendering failed\n"
        "Debug files written to: C:/tmp/debug"
    )

    assert described["status"] == "Echec generation"
    assert "la generation du site" in described["summary"]
    assert "debug" in described["summary"].lower()


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
