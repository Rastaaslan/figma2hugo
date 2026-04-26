from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "figma2hugo"


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
