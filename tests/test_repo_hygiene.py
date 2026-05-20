import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "figma2hugo"
PYPROJECT = ROOT / "pyproject.toml"
QUALITY_GRID = ROOT / "docs" / "project-quality-grid.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CLEAN_GENERATED_ARTIFACTS = ROOT / "scripts" / "clean_generated_artifacts.ps1"


def test_source_code_does_not_hardcode_manual_regression_examples() -> None:
    forbidden_tokens = (
        "tmp-community-",
        "tmp-complex-",
        "tmp-cornelia-",
        "QGdcSH.tif",
        "ncQz6Sp6cov083ktZ1qOTT",
        "bqHx68V3xjy7kLT9yaRyxA",
        "npNuKRtBJ5Iz78PeC65sN8",
    )

    for path in SRC.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"{token!r} should not be hardcoded in source file {path}"


def test_generator_source_and_templates_do_not_hardcode_current_figma_project() -> None:
    forbidden_tokens = (
        "page-accueil",
        "Le Labo",
        "Bastien Blochet",
        "Embedded In Mind",
        "node-button-labo",
        "bandeau-droite-accompagnement",
        "4042:",
        "2070:",
        "4050:",
    )
    inspected_paths = [*SRC.rglob("*.py")]

    for path in inspected_paths:
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".py", ".html", ".js", ".css", ".toml", ".j2"}:
            continue
        content = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"{token!r} should not be hardcoded in {path}"


def test_wheel_packages_only_runtime_python_package() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/figma2hugo"]
    assert "force-include" not in pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]


def test_quality_grid_scores_only_supported_scope() -> None:
    content = QUALITY_GRID.read_text(encoding="utf-8")

    assert "supported scope" in content
    assert "100%" in content
    assert "Out Of Contract" in content
    assert "design-to-code conversion" in content


def test_ci_workflow_runs_complete_quality_gate() -> None:
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    expected_commands = (
        "python -m ruff check src tests scripts",
        "python -m ruff format --check src tests scripts",
        "python -m mypy src/figma2hugo",
        "python -m pytest -p no:cacheprovider",
        "python scripts/perf_smoke.py --skip-hugo --budget cli_help=3",
        "python -m pip wheel . --no-deps -w .figma2hugo-scratch/ci-wheel",
    )
    for command in expected_commands:
        assert command in content


def test_markdown_docs_do_not_contain_common_mojibake_markers() -> None:
    forbidden_markers = ("Ãƒ", "Ã‚", "Ã¢â‚¬â„¢", "Ã¢â‚¬Å“", "Ã¢â‚¬", "\ufffd")
    inspected_paths = [
        ROOT / "README.md",
        ROOT / "SPEC.md",
        *[
            path
            for path in sorted((ROOT / "docs").glob("*.md"))
            if not path.name.startswith("transcript-")
        ],
    ]

    for path in inspected_paths:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in content, f"{marker!r} should not appear in {path}"


def test_pipeline_does_not_import_removed_pipeline_modules() -> None:
    forbidden_prefixes = (
        "figma2hugo.workflow",
        "figma2hugo.generators",
        "figma2hugo.figma_reader",
        "figma2hugo.content_extractor",
        "figma2hugo.layout_analyzer",
        "figma2hugo.asset_downloader",
        "figma2hugo.model",
        "figma2hugo.reporting",
        "figma2hugo.validator",
        "figma2hugo.readiness",
    )

    for path in (SRC / "pipeline").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(forbidden_prefixes), (
                    f"{path} must not import removed module {module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), (
                        f"{path} must not import removed module {alias.name}"
                    )


def test_official_entrypoints_do_not_import_removed_pipeline_modules() -> None:
    entrypoints = [
        SRC / "cli.py",
        SRC / "gui.py",
    ]
    forbidden_modules = (
        "figma2hugo.workflow",
        "figma2hugo.asset_downloader",
        "figma2hugo.content_extractor",
        "figma2hugo.figma_reader",
        "figma2hugo.generators",
        "figma2hugo.layout_analyzer",
        "figma2hugo.model",
        "figma2hugo.reporting",
        "figma2hugo.validator",
        "figma2hugo.readiness",
    )

    for path in entrypoints:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(forbidden_modules), (
                    f"{path} must not import removed pipeline module {module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_modules), (
                        f"{path} must not import removed pipeline module {alias.name}"
                    )


def test_removed_historical_packages_are_absent() -> None:
    removed_paths = (
        SRC / "workflow.py",
        SRC / "asset_downloader",
        SRC / "content_extractor",
        SRC / "figma_reader",
        SRC / "generators",
        SRC / "layout_analyzer",
        SRC / "model",
        SRC / "reporting",
        SRC / "validator",
        SRC / "readiness",
        SRC / "responsive_sections.py",
        SRC / "_lazy.py",
        ROOT / "templates",
    )

    assert [str(path) for path in removed_paths if path.exists()] == []


def test_repo_root_does_not_keep_manual_tmp_artifacts() -> None:
    forbidden_prefixes = ("tmp-", "repro")
    offenders = [
        path.name
        for path in ROOT.iterdir()
        if any(path.name.startswith(prefix) for prefix in forbidden_prefixes)
    ]

    assert offenders == []


def test_generated_pipeline_artifact_roots_are_ignored() -> None:
    ignore_patterns = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    expected_patterns = {
        ".pipeline-*/",
        ".css-pass-*/",
        ".figma2hugo-tmp/",
        "/site-check-*/",
        "/site-smoke/",
        "/css-pass-site/",
    }
    assert expected_patterns <= ignore_patterns


def test_public_repository_names_do_not_expose_historical_pipeline_versions() -> None:
    version_token = "v" + "2"
    previous_token = "v" + "1"
    forbidden_patterns = (
        re.compile(rf"\bpipeline_{version_token}\b", re.IGNORECASE),
        re.compile(rf"\bpipeline-{version_token}\b", re.IGNORECASE),
        re.compile(rf"\bpipeline_{previous_token}\b", re.IGNORECASE),
        re.compile(rf"\bpipeline-{previous_token}\b", re.IGNORECASE),
    )
    inspected_roots = (
        ROOT / "README.md",
        ROOT / "SPEC.md",
        ROOT / "pyproject.toml",
        ROOT / ".github",
        ROOT / "docs",
        ROOT / "scripts",
        SRC,
        ROOT / "tests",
    )

    inspected_files: list[Path] = []
    for root in inspected_roots:
        if root.is_file():
            inspected_files.append(root)
        elif root.exists():
            inspected_files.extend(path for path in root.rglob("*") if path.is_file())

    for path in inspected_files:
        if "__pycache__" in path.parts or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        content = path.read_text(encoding="utf-8")
        haystacks = (path.as_posix(), content)
        for pattern in forbidden_patterns:
            for haystack in haystacks:
                assert not pattern.search(haystack), (
                    f"{pattern.pattern!r} should not appear in {path}"
                )


def test_pipeline_semantic_limits_are_all_used() -> None:
    limits_path = SRC / "pipeline" / "semantic_limits.py"
    tree = ast.parse(limits_path.read_text(encoding="utf-8"))
    constants: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    constants.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                constants.append(node.target.id)

    pipeline_files = [
        path for path in (SRC / "pipeline").rglob("*.py") if path.name != "semantic_limits.py"
    ]
    unused = [
        constant
        for constant in constants
        if not any(constant in path.read_text(encoding="utf-8") for path in pipeline_files)
    ]

    assert unused == []


def test_pipeline_private_helpers_are_referenced() -> None:
    dead_helpers: list[str] = []
    for path in (SRC / "pipeline").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("_") or node.name.startswith("__"):
                continue
            if content.count(node.name) <= 1:
                dead_helpers.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}")

    assert dead_helpers == []


def test_cleanup_script_removes_generated_visual_compare_dirs() -> None:
    if not CLEAN_GENERATED_ARTIFACTS.exists():
        return
    script = CLEAN_GENERATED_ARTIFACTS.read_text(encoding="utf-8")

    assert "site\\public" in script
    assert "compare-*" in script
    assert "compare-probe" in script
