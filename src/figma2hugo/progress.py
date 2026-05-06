from __future__ import annotations

from pathlib import Path
from typing import Any


def format_progress_event(progress: dict[str, Any]) -> str:
    stage = str(progress.get("stage", "")).strip()
    message = str(progress.get("message", "Generation en cours.")).strip()
    label = progress_status_label(stage)
    details: list[str] = []
    if progress.get("input_index") and progress.get("input_total"):
        details.append(f"entree {progress['input_index']}/{progress['input_total']}")
    if progress.get("variant_index") and progress.get("variant_total"):
        details.append(f"variante {progress['variant_index']}/{progress['variant_total']}")
    if progress.get("source_label"):
        details.append(f"source {progress['source_label']}")
    if progress.get("document_name"):
        details.append(f"document {progress['document_name']}")
    if progress.get("breakpoint_width"):
        details.append(f"largeur {progress['breakpoint_width']}px")
    if progress.get("document_total"):
        details.append(f"{progress['document_total']} document(s)")
    if progress.get("document_names"):
        details.append(format_document_names(progress["document_names"]))
    if progress.get("written_file_count"):
        details.append(f"{progress['written_file_count']} fichier(s) ecrits")
    if progress.get("warning_count") is not None:
        details.append(f"{progress['warning_count']} warning(s)")
    if progress.get("report_path"):
        details.append(f"rapport {Path(str(progress['report_path'])).name}")
    elif progress.get("output_dir"):
        output_dir = str(progress["output_dir"])
        details.append(f"dossier {Path(output_dir).name or output_dir}")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"[{label}] {message}{suffix}"


def format_document_names(raw_names: Any) -> str:
    if not isinstance(raw_names, list):
        return str(raw_names)
    names = [str(name).strip() for name in raw_names if str(name).strip()]
    if not names:
        return "documents non nommes"
    preview = ", ".join(names[:3])
    if len(names) > 3:
        preview += f", +{len(names) - 3} autre(s)"
    return f"documents {preview}"


def translate_generation_stage(stage: str) -> str:
    normalized = stage.strip().lower()
    translations = {
        "initialization": "l'initialisation",
        "extracting figma data": "l'extraction Figma",
        "generating the output site": "la generation du site",
        "validating the generated site": "la validation du site genere",
        "validating the intermediate model": "la validation du modele intermediaire",
    }
    if normalized in translations:
        return translations[normalized]
    if normalized.startswith("extracting figma data for page "):
        return "l'extraction Figma"
    if normalized.startswith("validating the intermediate model for page "):
        return "la validation du modele intermediaire"
    return stage


def stage_status_label(stage: str) -> str:
    normalized = stage.strip().lower()
    if normalized == "initialization":
        return "Initialisation"
    if normalized.startswith("extracting figma data"):
        return "Echec extraction"
    if normalized.startswith("validating the intermediate model"):
        return "Modele invalide"
    if normalized == "generating the output site":
        return "Echec generation"
    if normalized == "validating the generated site":
        return "Echec validation"
    return "Erreur"


def progress_status_label(stage: str) -> str:
    normalized = stage.strip().lower()
    if normalized == "initialization":
        return "Initialisation"
    if normalized.startswith("extracting figma data"):
        return "Extraction"
    if normalized.startswith("validating the intermediate model"):
        return "Validation modele"
    if normalized == "generating the output site":
        return "Generation"
    if normalized == "validating the generated site":
        return "Validation site"
    if normalized == "writing generation report":
        return "Rapport"
    return "Generation en cours"
