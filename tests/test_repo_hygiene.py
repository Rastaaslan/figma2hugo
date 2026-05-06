from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "figma2hugo"
TEMPLATES = ROOT / "templates"


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
    inspected_paths = [*SRC.rglob("*.py"), *TEMPLATES.rglob("*")]

    for path in inspected_paths:
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".py", ".html", ".js", ".css", ".toml", ".j2"}:
            continue
        content = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"{token!r} should not be hardcoded in {path}"
