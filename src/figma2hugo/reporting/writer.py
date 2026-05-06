from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReportWriter:
    def write(self, target_dir: Path, report: dict[str, Any]) -> Path:
        path = target_dir / "report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        return path

    def write_responsive_audit(self, target_dir: Path, report: dict[str, Any]) -> Path | None:
        responsive = _as_dict(report.get("responsive"))
        families = _as_list(responsive.get("families"))
        if not families:
            return None
        path = target_dir / "responsive-audit.md"
        path.write_text(responsive_audit_markdown(report), encoding="utf-8", newline="\n")
        return path

    def read(self, target_dir: Path) -> dict[str, Any]:
        path = target_dir / "report.json"
        return json.loads(path.read_text(encoding="utf-8"))


def responsive_audit_markdown(report: dict[str, Any]) -> str:
    responsive = _as_dict(report.get("responsive"))
    summary = _as_dict(responsive.get("summary"))
    families = [_as_dict(family) for family in _as_list(responsive.get("families"))]
    strict_blocking = [
        family
        for family in families
        if any(_as_dict(issue).get("severity") == "strict-blocker" for issue in _issues(family))
    ]
    strict_ready = [family for family in families if family.get("strictReady") is True]
    text_review = [
        family
        for family in families
        if any(_as_dict(issue).get("type") == "text-content-change" for issue in _issues(family))
    ]
    repeated_components = [
        family
        for family in families
        if any(_as_dict(issue).get("type") == "repeated-component-token" for issue in _issues(family))
    ]

    lines: list[str] = [
        "# Audit responsive",
        "",
        "## Synthese",
        "",
        f"- Familles responsive: {_summary_value(summary, 'familyCount')}",
        f"- Familles strict-ready: {_summary_value(summary, 'strictReadyFamilyCount')}",
        f"- Familles bloquees en strict: {_summary_value(summary, 'strictBlockingFamilyCount')}",
        f"- Issues strict bloquantes: {_summary_value(summary, 'strictBlockingIssueCount')}",
        f"- Tokens traites comme composants repetitifs: {_summary_value(summary, 'repeatedComponentTokenCount')}",
        f"- Changements de texte a relire: {_summary_value(summary, 'textContentChangeCount')}",
        f"- Board splits informatifs: {_summary_value(summary, 'boardSplitCount')}",
        f"- Overflow horizontal: {_summary_value(summary, 'horizontalOverflowCount')}",
        "",
    ]

    lines.extend(_strict_blocker_section(strict_blocking))
    lines.extend(_repeated_component_section(repeated_components))
    lines.extend(_text_review_section(text_review))
    lines.extend(_strict_ready_section(strict_ready))
    lines.extend(_verification_section())
    return "\n".join(lines).rstrip() + "\n"


def _strict_blocker_section(families: list[dict[str, Any]]) -> list[str]:
    lines = ["## Priorite 1 - Debloquer le mode strict", ""]
    if not families:
        lines.extend(["Aucune famille ne bloque le mode strict.", ""])
        return lines
    for family in families:
        lines.append(f"### {family.get('family') or family.get('page') or 'page'}")
        for grouped_issue in _group_strict_blockers(_issues(family)):
            widths = ", ".join(grouped_issue["widths"])
            token = grouped_issue["token"]
            parent = grouped_issue["parent"]
            lines.append(
                f"- {widths}: renommer ou differencier `{token}` sous `{parent}`."
            )
        lines.append("")
    return lines


def _repeated_component_section(families: list[dict[str, Any]]) -> list[str]:
    lines = ["## Composants repetitifs detectes", ""]
    if not families:
        lines.extend(["Aucun token de sibling traite comme collection repetitive.", ""])
        return lines
    for family in families:
        lines.append(f"### {family.get('family') or family.get('page') or 'page'}")
        for issue in _issues(family):
            if issue.get("type") != "repeated-component-token":
                continue
            width = _issue_width(issue)
            token = issue.get("token") or "token inconnu"
            parent = issue.get("parent") or "parent inconnu"
            count = issue.get("count") or "?"
            lines.append(
                f"- {width}: `{count}` items `{token}` sous `{parent}` traites comme collection."
            )
        lines.append("")
    return lines


def _text_review_section(families: list[dict[str, Any]]) -> list[str]:
    lines = ["## Priorite 2 - Arbitrer les textes par breakpoint", ""]
    if not families:
        lines.extend(["Aucun changement de texte responsive detecte.", ""])
        return lines
    for family in families:
        lines.append(f"### {family.get('family') or family.get('page') or 'page'}")
        for issue in _issues(family):
            if issue.get("type") != "text-content-change":
                continue
            width = _issue_width(issue)
            path = issue.get("path") or "chemin inconnu"
            lines.append(
                f"- {width}: confirmer la variante de texte ou dupliquer le layer: `{path}`."
            )
        lines.append("")
    return lines


def _strict_ready_section(families: list[dict[str, Any]]) -> list[str]:
    lines = ["## Familles deja strict-ready", ""]
    if not families:
        lines.extend(["Aucune famille strict-ready pour le moment.", ""])
        return lines
    for family in families:
        lines.append(f"- {family.get('family') or family.get('page') or 'page'}")
    lines.append("")
    return lines


def _verification_section() -> list[str]:
    return [
        "## Verification apres corrections Figma",
        "",
        "- Relancer le build tolerant pour confirmer le rendu et les interactions.",
        "- Relancer ensuite avec `--strict-responsive-matching`.",
        "- Le flag d'environnement `FIGMA2HUGO_STRICT_RESPONSIVE_MATCHING=1` reste supporte.",
        "- Le strict est pret quand `strictBlockingIssueCount` vaut `0`.",
        "",
    ]


def _group_strict_blockers(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for issue in issues:
        if issue.get("severity") != "strict-blocker":
            continue
        token = str(issue.get("token") or "token inconnu")
        parent = str(issue.get("parent") or "parent inconnu")
        key = (token, parent)
        if key not in grouped:
            grouped[key] = {"token": token, "parent": parent, "width_values": []}
        grouped[key]["width_values"].append(issue.get("width"))

    ordered: list[dict[str, Any]] = []
    for item in grouped.values():
        width_values = sorted(
            {
                int(width)
                for width in item["width_values"]
                if isinstance(width, int) or str(width).isdigit()
            },
            reverse=True,
        )
        widths = [f"{width}px" for width in width_values] or ["breakpoint inconnu"]
        ordered.append(
            {
                "token": item["token"],
                "parent": item["parent"],
                "widths": widths,
            }
        )
    return ordered


def _issues(family: dict[str, Any]) -> list[dict[str, Any]]:
    return [_as_dict(issue) for issue in _as_list(family.get("issues"))]


def _issue_width(issue: dict[str, Any]) -> str:
    width = issue.get("width")
    return f"{width}px" if width not in (None, "") else "breakpoint inconnu"


def _summary_value(summary: dict[str, Any], key: str) -> int:
    try:
        return int(summary.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
