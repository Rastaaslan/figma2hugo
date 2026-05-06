from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from figma2hugo.config import OutputMode
from figma2hugo.progress import stage_status_label, translate_generation_stage


@dataclass(frozen=True, slots=True)
class GuiControlStates:
    default: str
    static_button: str
    progress_running: bool


def has_figma_access(
    token_override: str | None = None,
    *,
    local_token: str | None = None,
    mcp_url: str | None = None,
    mcp_command: str | None = None,
) -> bool:
    if token_override and token_override.strip():
        return True
    if local_token:
        return True
    if mcp_url or mcp_command:
        return True
    return False


def missing_access_message(local_config_name: str) -> str:
    return (
        "Generation impossible: aucun acces Figma n'est configure.\n\n"
        "Solutions:\n"
        '1. colle un personal access token dans le champ "Token Figma"\n'
        f"2. ou ajoute-le dans {local_config_name}\n"
        "3. ou definis FIGMA_ACCESS_TOKEN dans l'environnement\n"
        "4. ou configure FIGMA_MCP_URL / FIGMA_MCP_COMMAND pour un bridge MCP\n\n"
        "Le token REST Figma peut etre genere depuis les reglages de securite Figma."
    )


def clean_figma_urls(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        candidate = value.get() if hasattr(value, "get") else value
        text = str(candidate or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def supports_static_mode(figma_urls: list[str]) -> bool:
    return len(figma_urls) <= 1


def control_states(figma_urls: list[str], *, running: bool) -> GuiControlStates:
    default_state = "disabled" if running else "normal"
    static_button_state = (
        "normal" if not running and supports_static_mode(figma_urls) else "disabled"
    )
    return GuiControlStates(
        default=default_state,
        static_button=static_button_state,
        progress_running=running,
    )


def figma_access_source(
    token_override: str | None = None,
    *,
    local_token: str | None = None,
    local_config_name: str,
    env_token: str | None = None,
    env_token_alt: str | None = None,
    mcp_url: str | None = None,
    mcp_command: str | None = None,
) -> str:
    if token_override and token_override.strip():
        return "token saisi dans l'UI"
    if local_token:
        return f"config locale ({local_config_name})"
    if env_token or env_token_alt:
        return "variable d'environnement"
    if mcp_url or mcp_command:
        return "bridge MCP"
    return "configuration non detectee"


def selection_hint_message(figma_urls: list[str]) -> str:
    if not figma_urls:
        return (
            "Ajoute une URL Figma individuelle ou l'URL d'un parent contenant plusieurs "
            "frames top-level `page-<slug>-<width>` pour le responsive."
        )
    if len(figma_urls) == 1:
        return (
            "Une URL detectee. Le mode Hugo est recommande et accepte aussi un board "
            "unique contenant plusieurs frames top-level `page-<slug>-<width>`. "
            "Le mode Statique reste disponible pour une seule page."
        )
    return (
        f"{len(figma_urls)} URLs detectees. Le mode Hugo fusionnera les pages ou "
        "variantes ensemble. Le mode Statique est desactive pour plusieurs URLs."
    )


def generation_launch_summary(mode: OutputMode, figma_url_count: int) -> str:
    page_label = "page" if figma_url_count == 1 else "pages"
    return f"Lancement du mode {mode.value} pour {figma_url_count} {page_label}..."


def format_generation_start(
    figma_urls: list[str],
    destination: Path,
    mode: OutputMode,
    *,
    access_source: str,
) -> str:
    lines = [
        "Preparation de la generation.",
        "",
        f"Mode: {mode.value}",
        f"URLs detectees: {len(figma_urls)}",
        f"Dossier cible: {destination}",
        f"Acces Figma: {access_source}",
    ]
    if len(figma_urls) == 1:
        lines.append(
            "Entree: une URL unique. En mode Hugo, un board top-level "
            "`page-<slug>-<width>` peut etre splitte automatiquement."
        )
    else:
        lines.append(
            "Entree: plusieurs URLs. Le mode Hugo traitera l'ensemble comme une "
            "generation multi-pages ou multi-variantes."
        )
    if mode is OutputMode.STATIC:
        lines.append("Sortie attendue: export statique d'une seule page.")
    else:
        lines.append("Sortie attendue: site Hugo avec validation et rapport.")
    return "\n".join(lines)


def format_generation_success(result: dict[str, Any]) -> str:
    output_dir = Path(str(result.get("outDir") or "."))
    written_files = [str(path) for path in result.get("writtenFiles", [])]
    report_path = str(result.get("report") or "")
    lines = [
        "Generation terminee.",
        "",
        f"Mode: {result.get('mode', 'unknown')}",
        f"Dossier: {output_dir}",
        f"Build valide: {'oui' if bool(result.get('buildOk')) else 'non'}",
    ]
    if report_path:
        lines.append(f"Rapport: {report_path}")
    lines.extend(["", f"Fichiers ecrits: {len(written_files)}", ""])
    lines.extend(f"- {path}" for path in written_files[:20])
    if len(written_files) > 20:
        lines.append(f"- ... {len(written_files) - 20} autres fichiers")
    return "\n".join(lines)


def format_generation_error(message: str, *, access_message: str) -> str:
    if "Unable to extract Figma data" in message or "FIGMA_ACCESS_TOKEN" in message:
        return access_message + "\n\nDetail technique:\n" + message
    return message


def describe_generation_error(message: str, *, access_message: str) -> dict[str, str]:
    raw_message = str(message or "").strip() or "La generation a echoue."
    details = format_generation_error(raw_message, access_message=access_message)
    stage, cause, debug_path = split_generation_error(raw_message)
    normalized = cause.lower()

    if looks_like_invalid_figma_url(normalized):
        return {
            "status": "URL invalide",
            "summary": "Au moins une URL Figma est invalide. Verifie le format et le node-id.",
            "details": details,
        }

    if (
        "unable to extract figma data" in normalized
        or "rest token missing" in normalized
        or "figma_access_token" in normalized
    ):
        return {
            "status": "Acces Figma manquant",
            "summary": "Impossible d'acceder a Figma avec la configuration actuelle.",
            "details": details,
        }

    if (
        "multi-page generation is only supported in hugo mode" in normalized
        or "does not support multi-page generation" in normalized
    ):
        return {
            "status": "Mode incompatible",
            "summary": "Le multi-pages n'est disponible qu'en mode Hugo.",
            "details": details,
        }

    if "invalid intermediate model" in normalized:
        return {
            "status": "Modele invalide",
            "summary": "Le modele intermediaire genere n'est pas valide.",
            "details": details,
        }

    if (
        "too flat for structured extraction" in normalized
        or "grouping frames or sections" in normalized
    ):
        return {
            "status": "Structure Figma invalide",
            "summary": "Le noeud choisi est trop plat pour une extraction structuree.",
            "details": details,
        }

    if "playwright is not installed" in normalized:
        return {
            "status": "Validation indisponible",
            "summary": "La validation visuelle n'est pas disponible dans cet environnement.",
            "details": details,
        }

    if stage:
        translated_stage = translate_generation_stage(stage)
        summary = f"La generation a echoue pendant {translated_stage}."
        if debug_path:
            summary += " Les fichiers de debug ont ete conserves."
        return {
            "status": stage_status_label(stage),
            "summary": summary,
            "details": details,
        }

    return {
        "status": "Erreur",
        "summary": "La generation a echoue.",
        "details": details,
    }


def split_generation_error(message: str) -> tuple[str | None, str, str | None]:
    match = re.match(
        (
            r"Generation failed during (?P<stage>.+?): (?P<cause>.+?)"
            r"(?:\nDebug files written to: (?P<debug>.+))?$"
        ),
        message,
        re.S,
    )
    if not match:
        return None, message.strip(), None
    return (
        str(match.group("stage") or "").strip() or None,
        str(match.group("cause") or "").strip() or message.strip(),
        str(match.group("debug") or "").strip() or None,
    )


def looks_like_invalid_figma_url(normalized_message: str) -> bool:
    return any(
        token in normalized_message
        for token in (
            "figma url must start with http:// or https://",
            "figma url host must be figma.com or www.figma.com",
            "figma url path must look like",
            "figma url must include a node-id query parameter",
            "unsupported figma host",
            "the provided figma url does not contain a file key",
            "unsupported figma url type",
            "unsupported figma url kind",
        )
    )
