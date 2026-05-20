"""Clean pipeline primitives.

The pipeline owns its raw snapshot, geometry normalization, responsive
manifest and render-plan contracts. Official entrypoints route through these
modules directly.
"""

from figma2hugo.pipeline.orchestrator import Pipeline

__all__ = ("Pipeline",)
