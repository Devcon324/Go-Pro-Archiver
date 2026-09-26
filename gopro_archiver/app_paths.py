"""App data paths — stdlib only (safe for minimal Uninstall.exe builds)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "GoProFootageArchiver"
FAVORITES_FILENAME = "favorites.json"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    directory = base / APP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def favorites_path() -> Path:
    return config_dir() / FAVORITES_FILENAME
