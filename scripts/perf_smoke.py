"""Smoke tests de performance rapides pour les commandes qui doivent rester reactives."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _timed(label: str, command: list[str]) -> dict[str, object]:
    start = time.perf_counter()
    env = os.environ.copy()
    src_dir = Path(__file__).resolve().parents[1] / "src"
    if src_dir.exists():
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    return {"label": label, "seconds": round(time.perf_counter() - start, 3)}


def _parse_budgets(values: list[str]) -> dict[str, float]:
    budgets: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Budget must use name=seconds: {value}")
        name, raw_seconds = value.split("=", 1)
        budgets[name.strip()] = float(raw_seconds)
    return budgets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight performance smoke checks.")
    parser.add_argument("--skip-hugo", action="store_true")
    parser.add_argument("--include-validate", action="store_true")
    parser.add_argument("--budget", action="append", default=[])
    parser.add_argument("--site", type=Path, default=Path("site"))
    args = parser.parse_args(argv)

    budgets = _parse_budgets(args.budget)
    results = [_timed("cli_help", [sys.executable, "-m", "figma2hugo.cli", "--help"])]
    if not args.skip_hugo and args.site.exists():
        results.append(_timed("hugo_build", ["hugo", "--quiet", "-s", str(args.site)]))
    if args.include_validate:
        results.append(
            _timed(
                "validate_site", [sys.executable, "-m", "figma2hugo.cli", "report", str(args.site)]
            )
        )

    failures = [
        {**result, "budget": budgets[result["label"]]}
        for result in results
        if result["label"] in budgets and float(result["seconds"]) > budgets[result["label"]]
    ]
    print(json.dumps({"results": results, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
