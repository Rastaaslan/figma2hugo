from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def dedupe_warnings(warnings: Iterable[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning is None:
            continue
        normalized = str(warning).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
