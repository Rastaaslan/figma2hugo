"""Figma access helpers and extraction services."""

from .url_tools import parse_figma_url

__all__ = ["FigmaExtractionService", "parse_figma_url"]


def __getattr__(name: str):
    if name == "FigmaExtractionService":
        from .service import FigmaExtractionService

        return FigmaExtractionService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
