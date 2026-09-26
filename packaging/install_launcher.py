"""One-file installer: copies bundled app to LocalAppData and creates shortcuts."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "GoPro Footage Archiver"
EXE_NAME = "GoPro-Footage-Archiver.exe"


def install_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP_NAME


def bundled_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app"
    return Path(__file__).resolve().parent.parent / "dist" / "GoPro-Footage-Archiver"


def create_shortcut(link_path: Path, target: Path, working_dir: Path, description: str) -> None:
    script = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{link_path}')
$shortcut.TargetPath = '{target}'
$shortcut.WorkingDirectory = '{working_dir}'
$shortcut.Description = '{description}'
$shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def main() -> int:
    if sys.platform != "win32":
        return 1

    source = bundled_app_dir()
    if not (source / EXE_NAME).exists():
        return 1

    destination = install_dir()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    start_menu = (
        Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
    )
    start_menu.mkdir(parents=True, exist_ok=True)
    app_exe = destination / EXE_NAME
    create_shortcut(start_menu / f"{APP_NAME}.lnk", app_exe, destination, APP_NAME)
    create_shortcut(start_menu / f"Uninstall {APP_NAME}.lnk", destination / "Uninstall.exe", destination, f"Uninstall {APP_NAME}")

    desktop = Path(os.environ["USERPROFILE"]) / "Desktop" / f"{APP_NAME}.lnk"
    create_shortcut(desktop, app_exe, destination, APP_NAME)

    subprocess.Popen([str(app_exe)], cwd=str(destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
