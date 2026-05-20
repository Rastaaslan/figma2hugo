from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import figma2hugo.cli as cli_module
import figma2hugo.pipeline.runner as pipeline_runner
import figma2hugo.pipeline.visual_smoke as pipeline_visual_smoke
from figma2hugo.cli import app
from figma2hugo.pipeline.options import PipelineRenderMode

FIGMA_URL = "https://www.figma.com/design/AbCdEf1234567890/Test-Page?node-id=3-964"


def _raw_page(name: str = "page-pipeline-402", node_id: str = "3:964") -> dict[str, object]:
    return {
        "id": node_id,
        "name": name,
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
        "children": [
            {
                "id": f"{node_id}-hero",
                "name": "section-hero",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 200},
            }
        ],
    }


def test_cli_help_exposes_pipeline_as_official_surface() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "official generation pipeline is enabled" in result.output
    assert "build-raw" in result.output
    assert "build-figma" in result.output
    assert "build-site" in result.output
    assert "visual-smoke" in result.output
    assert "promote-visual-baseline" in result.output
    assert "promote-review-baseline" in result.output
    assert "generate" not in result.output
    assert "extract" not in result.output
    assert "inspect" not in result.output


def test_report_can_print_pipeline_report() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        site_dir = Path("site-pipeline")
        site_dir.mkdir()
        (site_dir / "report.json").write_text(
            json.dumps({"pipeline": "pipeline", "buildOk": True, "pageCount": 2}),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["report", "site-pipeline"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["pageCount"] == 2


def test_report_rejects_removed_artifact_flags() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("site").mkdir()

        result = runner.invoke(
            app,
            ["report", "site", "--readiness"],
        )

        assert result.exit_code != 0
        assert "No such option" in result.output


def test_build_generates_pipeline_hugo_site_with_url_and_destination_only(monkeypatch) -> None:
    runner = CliRunner()

    def fail_generation(*_args, **_kwargs):
        raise AssertionError("build default must route to pipeline.")

    def fake_fetch(figma_url: str, *, token: str | None = None):
        assert figma_url == FIGMA_URL
        assert token is None
        return _raw_page()

    monkeypatch.setattr(cli_module, "run_generation", fail_generation, raising=False)
    monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["build", FIGMA_URL, "site"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["command"] == "build-site"
        assert Path("site/hugo.toml").exists()
        assert Path("site/content/page-pipeline-402/index.md").exists()
        assert Path("site/data/pipeline/pages/page-pipeline-402.json").exists()
        assert Path("site/report.json").exists()


def test_build_site_default_generates_multi_page_pipeline_hugo_output(monkeypatch) -> None:
    runner = CliRunner()

    def fail_generation(*_args, **_kwargs):
        raise AssertionError("build-site default must route to pipeline.")

    def fake_fetch(figma_url: str, *, token: str | None = None):
        assert token == "token-pipeline"
        page_name = "page-contact-402" if "Contact" in figma_url else "page-about-402"
        node_id = "1:2" if "Contact" in figma_url else "1:1"
        return _raw_page(page_name, node_id)

    monkeypatch.setattr(cli_module, "run_generation", fail_generation, raising=False)
    monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)

    with runner.isolated_filesystem():
        Path("pages.txt").write_text(
            "https://www.figma.com/design/AbCdEf1234567890/About?node-id=1-1\n"
            "https://www.figma.com/design/AbCdEf1234567890/Contact?node-id=1-2\n",
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "build-site",
                "site-pipeline",
                "--page-file",
                "pages.txt",
                "--token",
                "token-pipeline",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["command"] == "build-site"
        assert [page["slug"] for page in payload["hugo"]["pages"]] == [
            "page-about-402",
            "page-contact-402",
        ]
        assert Path("site-pipeline/hugo.toml").exists()
        assert Path("site-pipeline/content/page-about-402/index.md").exists()
        assert Path("site-pipeline/content/page-contact-402/index.md").exists()
        assert Path("site-pipeline/report.json").exists()
        assert not Path("site-pipeline/hugo").exists()


def test_build_site_rejects_removed_pipeline_option() -> None:
    result = CliRunner().invoke(
        app,
        ["build-site", "site-pipeline", "--pipeline", "pipeline", "--page", FIGMA_URL],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_build_site_fidelity_exact_selects_strict_pipeline_render_mode(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []

    def fake_run_build_site_command(
        figma_urls: list[str],
        out: Path,
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append({"figmaUrls": figma_urls, "out": out, **kwargs})
        render_mode = kwargs["render_mode"]
        assert isinstance(render_mode, PipelineRenderMode)
        return {
            "pipeline": "pipeline",
            "command": "build-site",
            "renderMode": render_mode.value,
        }

    monkeypatch.setattr(cli_module, "_run_build_site_command", fake_run_build_site_command)

    exact_result = runner.invoke(
        app,
        ["build-site", "site-pipeline", "--page", FIGMA_URL, "--fidelity-mode", "exact"],
    )
    override_result = runner.invoke(
        app,
        [
            "build-site",
            "site-pipeline",
            "--page",
            FIGMA_URL,
            "--fidelity-mode",
            "exact",
            "--render-mode",
            "usable",
        ],
    )

    assert exact_result.exit_code == 0
    assert override_result.exit_code == 0
    assert calls[0]["render_mode"] is PipelineRenderMode.STRICT
    assert calls[1]["render_mode"] is PipelineRenderMode.USABLE
    assert json.loads(exact_result.stdout)["renderMode"] == "strict"
    assert json.loads(override_result.stdout)["renderMode"] == "usable"


def test_build_site_pipeline_expands_parent_page_variants(monkeypatch) -> None:
    runner = CliRunner()

    def fake_fetch(figma_url: str, *, token: str | None = None):
        assert "About" in figma_url
        assert token == "token-pipeline"
        return {
            "id": "parent",
            "name": "page-about",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 2000, "height": 1000},
            "children": [
                {
                    "id": "about-1920",
                    "name": "page-about-1920",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 600},
                    "children": [
                        {
                            "id": "hero-1920",
                            "name": "section-hero",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 1920,
                                "height": 300,
                            },
                        }
                    ],
                },
                {
                    "id": "about-402",
                    "name": "page-about-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 800},
                    "children": [
                        {
                            "id": "hero-402",
                            "name": "section-hero",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 400,
                            },
                        }
                    ],
                },
            ],
        }

    monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            [
                "build-site",
                "site-pipeline",
                "--page",
                "https://www.figma.com/design/AbCdEf1234567890/About?node-id=1-0",
                "--token",
                "token-pipeline",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert [page["slug"] for page in payload["hugo"]["pages"]] == ["page-about"]
        assert Path("site-pipeline/content/page-about/index.md").exists()
        assert Path("site-pipeline/data/pipeline/responsive/page-about.json").exists()
        assert not Path("site-pipeline/content/page-about-1920/index.md").exists()
        report = json.loads(Path("site-pipeline/report.json").read_text(encoding="utf-8"))
        figma_reference = report["figmaReference"]
        assert figma_reference["enabled"] is True
        assert figma_reference["source"] == "figma-render"
        assert {item["fileName"] for item in figma_reference["items"]} >= {
            "page-about-1920.png",
            "page-about-402.png",
        }
        assert {item["nodeId"] for item in figma_reference["items"]} == {
            "about-1920",
            "about-402",
        }


def test_build_rejects_removed_pipeline_option() -> None:
    result = CliRunner().invoke(
        app,
        ["build", FIGMA_URL, "site-pipeline", "--pipeline", "pipeline"],
    )

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_build_raw_reads_raw_json() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        Path("raw.json").write_text(json.dumps(_raw_page()), encoding="utf-8")

        result = runner.invoke(
            app,
            ["build-raw", "raw.json", "--out", "pipeline", "--render-mode", "strict"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["renderMode"] == "strict"
        assert Path("pipeline/page-pipeline-402.render-plan.json").exists()
        assert Path("pipeline/page-pipeline-402.html").exists()
        assert Path("pipeline/diagnostics.json").exists()
        assert Path("pipeline/site/index.html").exists()
        assert Path("pipeline/site/pages/page-pipeline-402/index.html").exists()
        assert Path("pipeline/hugo/hugo.toml").exists()
        assert Path("pipeline/hugo/content/page-pipeline-402/index.md").exists()
        assert Path("pipeline/hugo/data/pipeline/pages/page-pipeline-402.json").exists()


def test_build_figma_fetches_raw(monkeypatch) -> None:
    runner = CliRunner()

    def fake_fetch(figma_url: str, *, token: str | None = None):
        assert figma_url == FIGMA_URL
        assert token == "token-pipeline"
        return _raw_page()

    monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["build-figma", FIGMA_URL, "--out", "pipeline", "--token", "token-pipeline"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["command"] == "build-figma"
        assert Path("pipeline/raw/abcdef1234567890-3-964.raw.json").exists()
        assert Path("pipeline/page-pipeline-402.render-plan.json").exists()
        assert Path("pipeline/site/pages/page-pipeline-402/index.html").exists()
        assert Path("pipeline/hugo/hugo.toml").exists()
        assert Path("pipeline/hugo/content/page-pipeline-402/index.md").exists()


def test_build_site_writes_final_hugo_site_from_raw() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        Path("raw.json").write_text(json.dumps(_raw_page()), encoding="utf-8")

        result = runner.invoke(
            app,
            ["build-site", "site-pipeline", "--raw", "raw.json", "--render-mode", "strict"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["command"] == "build-site"
        assert payload["renderMode"] == "strict"
        assert Path("site-pipeline/hugo.toml").exists()
        assert Path("site-pipeline/content/page-pipeline-402/index.md").exists()
        assert Path("site-pipeline/data/pipeline/pages/page-pipeline-402.json").exists()
        assert Path("site-pipeline/.figma2hugo-pipeline-debug/diagnostics.json").exists()
        assert not Path("site-pipeline/hugo").exists()
        report = json.loads(Path("site-pipeline/report.json").read_text(encoding="utf-8"))
        assert report["renderMode"] == "strict"


def test_build_site_fetches_figma(monkeypatch) -> None:
    runner = CliRunner()

    def fake_fetch(figma_url: str, *, token: str | None = None):
        assert figma_url == FIGMA_URL
        assert token == "token-pipeline"
        return _raw_page()

    monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["build-site", "site-pipeline", "--page", FIGMA_URL, "--token", "token-pipeline"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["pipeline"] == "pipeline"
        assert payload["command"] == "build-site"
        assert Path("site-pipeline/raw").exists() is False
        assert Path(
            "site-pipeline/.figma2hugo-pipeline-debug/raw/abcdef1234567890-3-964.raw.json"
        ).exists()
        assert Path("site-pipeline/hugo.toml").exists()
        assert Path("site-pipeline/content/page-pipeline-402/index.md").exists()


def test_visual_smoke_command_delegates_to_pipeline_smoke_runner(monkeypatch) -> None:
    runner = CliRunner()
    calls: list[dict[str, object]] = []

    def fake_run_pipeline_visual_smoke(
        source_dir: Path,
        out_dir: Path,
        *,
        public_dir: Path | None = None,
        widths: tuple[int, ...] = (),
        screenshot_widths: tuple[int, ...] = (),
        baseline_dir: Path | None = None,
        baseline_root: Path | None = None,
        baseline_mode: str | None = None,
        baseline_id: str | None = None,
        diff_review_threshold: float = 0.005,
        diff_fail_threshold: float = 0.05,
        hugo_bin: str = "hugo",
        token: str | None = None,
        browser_engine: str = "auto",
    ) -> dict[str, object]:
        calls.append(
            {
                "sourceDir": source_dir,
                "outDir": out_dir,
                "publicDir": public_dir,
                "widths": widths,
                "screenshotWidths": screenshot_widths,
                "baselineDir": baseline_dir,
                "baselineRoot": baseline_root,
                "baselineMode": baseline_mode,
                "baselineId": baseline_id,
                "diffReviewThreshold": diff_review_threshold,
                "diffFailThreshold": diff_fail_threshold,
                "hugoBin": hugo_bin,
                "token": token,
                "browserEngine": browser_engine,
            }
        )
        return {"pipeline": "pipeline", "command": "visual-smoke", "issueCount": 0}

    monkeypatch.setattr(
        pipeline_visual_smoke,
        "run_pipeline_visual_smoke",
        fake_run_pipeline_visual_smoke,
    )

    result = runner.invoke(
        app,
        [
            "visual-smoke",
            "site-pipeline",
            "--out",
            "smoke",
            "--public-dir",
            "public",
            "--widths",
            "1920,402",
            "--screenshot-widths",
            "402",
            "--baseline-dir",
            "baseline",
            "--baseline-root",
            "baseline-root",
            "--baseline-mode",
            "auto",
            "--baseline-id",
            "current",
            "--diff-review-threshold",
            "0.02",
            "--diff-fail-threshold",
            "0.08",
            "--hugo-bin",
            "hugo-test",
            "--token",
            "token-pipeline",
            "--browser-engine",
            "static",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["pipeline"] == "pipeline"
    assert calls == [
        {
            "sourceDir": Path("site-pipeline"),
            "outDir": Path("smoke"),
            "publicDir": Path("public"),
            "widths": (1920, 402),
            "screenshotWidths": (402,),
            "baselineDir": Path("baseline"),
            "baselineRoot": Path("baseline-root"),
            "baselineMode": "auto",
            "baselineId": "current",
            "diffReviewThreshold": 0.02,
            "diffFailThreshold": 0.08,
            "hugoBin": "hugo-test",
            "token": "token-pipeline",
            "browserEngine": "static",
        }
    ]


def test_promote_review_baseline_command_writes_project_contract() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        site = Path("site")
        site.mkdir()
        (site / "report.json").write_text(
            json.dumps(
                {
                    "pipeline": "pipeline",
                    "sourceIdentity": {"projectId": "figma-example", "sourceHash": "abcdef"},
                    "review": {
                        "items": [
                            {
                                "classification": "actionable-review",
                                "source": "responsive",
                                "code": "content-conflict",
                                "priority": "P3",
                                "action": "inspect-responsive-contract",
                                "owner": "figma-contract",
                                "family": "page-example",
                                "key": "section:footer",
                                "differenceKind": "content-delta",
                                "contractRule": "stable-responsive-content",
                                "presentWidths": [402, 1920],
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "promote-review-baseline",
                "site",
                "--baseline-root",
                "baselines",
                "--baseline-id",
                "accepted",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["command"] == "promote-review-baseline"
        assert payload["responsiveContractCount"] == 1
        assert Path("baselines/figma-example/accepted.json").exists()


def test_ui_command_launches_desktop_app(monkeypatch) -> None:
    runner = CliRunner()
    launched = {"called": False}

    monkeypatch.setattr(cli_module, "_launch_ui", lambda: launched.__setitem__("called", True))

    result = runner.invoke(app, ["ui"])

    assert result.exit_code == 0
    assert launched["called"] is True
