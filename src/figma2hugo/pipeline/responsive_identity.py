"""Compare l'identite des noeuds entre breakpoints sans dependre de noms fragiles."""

from __future__ import annotations

import re

RENDER_WIDTH_SUFFIX_RE = re.compile(r"(?:-w\d{3,4})+$")


def unique_breakpoint_render_name(name: str, *, suffix: str, used_names: set[str]) -> str:
    original_name = str(name or "").strip()
    base_name = RENDER_WIDTH_SUFFIX_RE.sub("", original_name)
    candidate_base = f"{base_name or original_name}-{suffix}"
    candidate = candidate_base
    index = 2
    while candidate in used_names:
        candidate = f"{candidate_base}-{index}"
        index += 1
    used_names.add(candidate)
    return candidate
