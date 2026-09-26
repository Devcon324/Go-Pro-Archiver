"""Standalone uninstall entry (no gopro_archiver package import — keeps Uninstall.exe small)."""

from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# Keep APP_DIR_NAME in sync with gopro_archiver.app_paths
APP_DIR_NAME = "GoProFootageArchiver"


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    config_path = config_dir()
    if not messagebox.askyesno(
        "GoPro Footage Archiver — Uninstall",
        "Remove saved favourites and settings?\n\n"
        f"Folder:\n{config_path}\n\n"
        "Your archived MP4 files are not deleted.",
    ):
        root.destroy()
        return

    if config_path.exists():
        shutil.rmtree(config_path, ignore_errors=True)

    if config_path.exists():
        messagebox.showerror(
            "Uninstall",
            "Could not remove all app data.\nClose GoPro Footage Archiver and try again.",
        )
    else:
        if sys.platform == "win32":
            cleanup = "GoPro-Footage-Archiver.exe and Uninstall.exe"
        else:
            cleanup = "GoPro-Footage-Archiver and Uninstall"
        messagebox.showinfo(
            "Uninstall",
            f"App data removed.\n\nYou can delete {cleanup} from this folder.",
        )
    root.destroy()


if __name__ == "__main__":
    main()
