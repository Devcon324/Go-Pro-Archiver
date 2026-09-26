from __future__ import annotations

import json

from gopro_archiver.app_paths import favorites_path

FAVORITES_FILENAME = "favorites.json"


def load_favorite_destinations() -> list[str]:
    path = favorites_path()
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, str) and item.strip()]
    if isinstance(payload, dict):
        favorites = payload.get("favorites")
        if isinstance(favorites, list):
            return [item for item in favorites if isinstance(item, str) and item.strip()]
    return []


def save_favorite_destinations(paths: list[str]) -> None:
    normalized = list(dict.fromkeys(path.strip() for path in paths if path.strip()))
    path = favorites_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
