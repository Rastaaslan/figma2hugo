"""Conversion des objets internes du pipeline en rapports JSON stables."""

from __future__ import annotations

from typing import Any

from figma2hugo.pipeline.models import RenderNodePlan, RenderPlan, RenderSectionPlan
from figma2hugo.pipeline.responsive import (
    ResponsiveIssue,
    ResponsiveManifest,
    ResponsiveNodeFamily,
)


def render_plan_to_dict(plan: RenderPlan) -> dict[str, Any]:
    return {
        "page": {
            "id": plan.page_id,
            "name": plan.page_name,
            "width": plan.width,
            "height": plan.height,
        },
        "sections": [_section_to_dict(section) for section in plan.sections],
        "diagnostics": [issue.to_dict() for issue in plan.diagnostics],
    }


def responsive_manifest_to_dict(manifest: ResponsiveManifest) -> dict[str, Any]:
    return {
        "family": manifest.family,
        "baseWidth": manifest.base_width,
        "breakpoints": list(manifest.breakpoints),
        "nodeFamilies": [
            _node_family_to_dict(node_family) for node_family in manifest.node_families
        ],
        "issues": [_responsive_issue_to_dict(issue) for issue in manifest.issues],
    }


def _responsive_issue_to_dict(issue: ResponsiveIssue) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": issue.code,
        "severity": issue.severity.value,
        "message": issue.message,
        "family": issue.family,
        "key": issue.key,
        "width": issue.width,
    }
    if issue.present_widths:
        payload["presentWidths"] = list(issue.present_widths)
    if issue.missing_widths:
        payload["missingWidths"] = list(issue.missing_widths)
    if issue.signature_count:
        payload["signatureCount"] = issue.signature_count
    if issue.difference_kind:
        payload["differenceKind"] = issue.difference_kind
    if issue.node_role:
        payload["nodeRole"] = issue.node_role
    if issue.contract_rule:
        payload["contractRule"] = issue.contract_rule
    if issue.contract_action:
        payload["contractAction"] = issue.contract_action
    if issue.contract_risk:
        payload["contractRisk"] = issue.contract_risk
    return payload


def _section_to_dict(section: RenderSectionPlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": section.section_id,
        "name": section.name,
        "bounds": section.bounds.to_dict(),
        "layoutMode": section.layout_mode,
        "nodes": [_node_to_dict(node) for node in section.nodes],
    }
    if section.style:
        payload["style"] = dict(section.style)
    return payload


def _node_to_dict(node: RenderNodePlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node.node_id,
        "name": node.name,
        "kind": node.kind.value,
        "bounds": node.bounds.to_dict(),
        "layer": node.layer,
        "children": [_node_to_dict(child) for child in node.children],
    }
    if node.text:
        payload["text"] = node.text
    if node.text_runs:
        payload["textRuns"] = [
            {"text": run.text, "style": dict(run.style)} if run.style else {"text": run.text}
            for run in node.text_runs
        ]
    if node.asset_url:
        payload["assetUrl"] = node.asset_url
    if node.style:
        payload["style"] = dict(node.style)
    if node.component:
        payload["component"] = node.component
    if node.attributes:
        payload["attributes"] = dict(node.attributes)
    return payload


def _node_family_to_dict(node_family: ResponsiveNodeFamily) -> dict[str, Any]:
    return {
        "key": node_family.key,
        "decision": node_family.decision.value,
        "widths": list(node_family.widths),
        "contentSignatures": {
            str(width): signature
            for width, signature in sorted(node_family.content_signatures.items())
        },
    }
