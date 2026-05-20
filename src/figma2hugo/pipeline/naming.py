"""Nettoyage des noms et generation de slugs pour pages, noeuds, fichiers et classes CSS."""

from __future__ import annotations

import re
import unicodedata

NON_NAME_RE = re.compile(r"[^a-z0-9]+")
BACKGROUND_PREFIXES = ("bg-", "background-", "fond-", "bandeau-full-")
BACKGROUND_SUFFIXES = ("-bg", "-background", "-fond")
FOREGROUND_PREFIXES = ("fg-", "foreground-", "avant-plan-", "premier-plan-")
FOREGROUND_SUFFIXES = ("-fg", "-foreground", "-avant-plan", "-premier-plan")


def name_key(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", str(name).strip().lower())
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return NON_NAME_RE.sub("-", ascii_name).strip("-")


def slugify(value: object) -> str:
    return name_key(str(value or ""))


def unique_slug(slug: str, used_slugs: set[str]) -> str:
    candidate = slug
    index = 2
    while candidate in used_slugs:
        candidate = f"{slug}-{index}"
        index += 1
    used_slugs.add(candidate)
    return candidate


def is_background_name(name: str) -> bool:
    key = name_key(name)
    return key.startswith(BACKGROUND_PREFIXES) or key.endswith(BACKGROUND_SUFFIXES)


def is_foreground_name(name: str) -> bool:
    key = name_key(name)
    return key.startswith(FOREGROUND_PREFIXES) or key.endswith(FOREGROUND_SUFFIXES)
