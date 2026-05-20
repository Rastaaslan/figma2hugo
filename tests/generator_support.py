from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile as _stdlib_tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRATCH_TEST_ROOT = ROOT / ".figma2hugo-tmp" / "tests"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

HUGO_BIN = shutil.which("hugo")
__all__ = ("HUGO_BIN", "ROOT", "json", "subprocess", "tempfile", "unittest")


class _ScratchTempfile:
    def TemporaryDirectory(self, *args, **kwargs):
        prefix = str(kwargs.get("prefix", ""))
        target_dir = kwargs.get("dir")
        if target_dir == ROOT or prefix.startswith(".pipeline-"):
            SCRATCH_TEST_ROOT.mkdir(parents=True, exist_ok=True)
            kwargs["dir"] = str(SCRATCH_TEST_ROOT)
            return _ProjectTemporaryDirectory(*args, **kwargs)
        return _stdlib_tempfile.TemporaryDirectory(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(_stdlib_tempfile, name)


class _ProjectTemporaryDirectory:
    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | Path | None = None,
        ignore_cleanup_errors: bool = False,
        *,
        delete: bool = True,
    ) -> None:
        self._ignore_cleanup_errors = ignore_cleanup_errors
        self._delete = delete
        root = Path(dir or SCRATCH_TEST_ROOT)
        root.mkdir(parents=True, exist_ok=True)
        prefix = "tmp" if prefix is None else prefix
        suffix = "" if suffix is None else suffix
        for _ in range(100):
            candidate = root / f"{prefix}{uuid.uuid4().hex[:8]}{suffix}"
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            self.name = str(candidate)
            return
        raise FileExistsError(f"Could not create temporary directory in {root}")

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if not self._delete:
            return
        try:
            shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)
        except OSError:
            shutil.rmtree(self.name, ignore_errors=True)


tempfile = _ScratchTempfile()
