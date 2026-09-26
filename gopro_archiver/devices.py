from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterable

import psutil


def parse_version_file(path: str | os.PathLike[str]) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return {}

    try:
        raw = file_path.read_text(encoding="utf-8")
        payload = json.loads(raw.replace("\n", "").replace("\r", ""))
        if isinstance(payload, dict):
            return payload
    except (json.JSONDecodeError, OSError, ValueError):
        return {}

    return {}


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _add_removable_media_paths(add) -> None:
    """Scan /media and /run/media (user + volume). Skip /mnt — psutil already lists those mounts."""
    for base in (Path("/media"), Path("/run/media")):
        if not _safe_is_dir(base):
            continue
        for entry in _safe_iterdir(base):
            if not _safe_is_dir(entry):
                continue
            add(str(entry))
            for nested in _safe_iterdir(entry):
                if _safe_is_dir(nested):
                    add(str(nested))


def collect_mount_points() -> list[str]:
    mount_points: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        normalized = os.path.normpath(candidate)
        if normalized in seen:
            return
        seen.add(normalized)
        mount_points.append(normalized)

    for part in psutil.disk_partitions(all=True):
        add(part.mountpoint)

    if sys.platform != "win32":
        _add_removable_media_paths(add)

    return mount_points


def find_gopro_devices(paths: Iterable[str] | None = None) -> list[dict]:
    if paths is None:
        paths = collect_mount_points()

    devices: list[dict] = []
    for root in paths:
        drive = Path(root)
        try:
            if not drive.exists():
                continue
        except OSError:
            continue

        version_file = drive / "MISC" / "version.txt"
        dcim_dir = drive / "DCIM" / "100GOPRO"
        try:
            if not version_file.exists() or not dcim_dir.exists():
                continue
        except OSError:
            continue

        metadata = parse_version_file(version_file)
        if not metadata:
            continue

        devices.append(
            {
                "drive": str(drive),
                "camera_type": metadata.get("camera type") or metadata.get("camera_type") or "GoPro",
                "serial_number": metadata.get("camera serial number") or metadata.get("camera_serial_number") or "Unknown",
                "firmware_version": metadata.get("firmware version") or metadata.get("firmware_version") or "Unknown",
                "mcu_version": metadata.get("mcu version") or metadata.get("mcu_version") or "Unknown",
                "wifi_mac": metadata.get("wifi mac") or metadata.get("wifi_mac") or "Unknown",
                "metadata": metadata,
            }
        )

    return devices
