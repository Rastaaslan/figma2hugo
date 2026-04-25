from __future__ import annotations

from enum import StrEnum


class SectionRole(StrEnum):
    HEADER = "header"
    HERO = "hero"
    SECTION = "section"
    ARTICLE = "article"
    NAV = "nav"
    FORM = "form"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class AssetRole(StrEnum):
    CONTENT = "content"
    DECORATIVE = "decorative"
    FOREGROUND = "foreground"
    MASK = "mask"
    BACKGROUND = "background"
    ICON = "icon"
