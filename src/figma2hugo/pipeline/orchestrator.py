"""Facade legere qui relie normalisation, planification, rendu et analyse responsive."""

from __future__ import annotations

from typing import Any

from figma2hugo.pipeline.export import render_plan_to_dict, responsive_manifest_to_dict
from figma2hugo.pipeline.html_renderer import render_static_document
from figma2hugo.pipeline.models import IntermediatePipelineDocument, RenderPlan
from figma2hugo.pipeline.normalizer import normalize_document
from figma2hugo.pipeline.options import PipelineRenderMode, normalize_render_mode
from figma2hugo.pipeline.render_plan import build_render_plan
from figma2hugo.pipeline.responsive import ResponsiveManifest, build_responsive_manifest


class Pipeline:
    """Clean pipeline entrypoint.

    This class intentionally starts from raw Figma-like node payloads and keeps
    normalization, responsive decisions and rendering in the pipeline contract.
    """

    def __init__(
        self, *, render_mode: PipelineRenderMode | str = PipelineRenderMode.USABLE
    ) -> None:
        self.render_mode = normalize_render_mode(render_mode)

    def normalize(self, root_payload: dict[str, Any]) -> IntermediatePipelineDocument:
        return normalize_document(root_payload)

    def render_plan(self, root_payload: dict[str, Any]) -> RenderPlan:
        return build_render_plan(self.normalize(root_payload), render_mode=self.render_mode)

    def render_plan_payload(self, root_payload: dict[str, Any]) -> dict[str, Any]:
        return render_plan_to_dict(self.render_plan(root_payload))

    def render_static_html(self, root_payload: dict[str, Any]) -> str:
        return render_static_document(self.render_plan(root_payload))

    def responsive_manifest(self, root_payloads: list[dict[str, Any]]) -> ResponsiveManifest:
        documents = [self.normalize(root_payload) for root_payload in root_payloads]
        return build_responsive_manifest(documents)

    def responsive_manifest_payload(self, root_payloads: list[dict[str, Any]]) -> dict[str, Any]:
        return responsive_manifest_to_dict(self.responsive_manifest(root_payloads))
