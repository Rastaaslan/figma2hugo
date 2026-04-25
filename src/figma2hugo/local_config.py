from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def get_app_home() -> Path:
    configured_home = os.getenv("FIGMA2HUGO_HOME")
    if configured_home:
        return Path(configured_home).resolve()

    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "SPEC.md").exists() or (candidate / "lancer-figma2hugo.bat").exists():
            return candidate
    return current


def get_local_config_path() -> Path:
    return get_app_home() / "figma2hugo.local.json"


def load_local_config() -> dict[str, Any]:
    path = get_local_config_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def get_local_figma_token() -> str | None:
    env_token = os.getenv("FIGMA_ACCESS_TOKEN") or os.getenv("FIGMA_TOKEN")
    if env_token:
        return env_token

    config = load_local_config()
    candidates = (
        config.get("figma_access_token"),
        config.get("FIGMA_ACCESS_TOKEN"),
        config.get("figmaToken"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None
