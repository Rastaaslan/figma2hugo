"""Modes de rendu supportes et normalisation des options du pipeline officiel."""

from __future__ import annotations

from enum import StrEnum


class PipelineRenderMode(StrEnum):
    USABLE = "usable"
    STRICT = "strict"


def normalize_render_mode(value: PipelineRenderMode | str | None) -> PipelineRenderMode:
    if value is None:
        return PipelineRenderMode.USABLE
    if isinstance(value, PipelineRenderMode):
        return value
    normalized = str(value).strip().lower()
    try:
        return PipelineRenderMode(normalized)
    except ValueError as exc:
        raise ValueError("Pipeline render mode must be 'usable' or 'strict'.") from exc
