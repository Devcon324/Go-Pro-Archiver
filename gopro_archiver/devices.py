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
        for base in (Path("/media"), Path("/run/media"), Path("/mnt")):
            if not base.is_dir():
                continue
            for entry in base.iterdir():
                if entry.is_dir():
                    add(str(entry))
                    for nested in entry.iterdir():
                        if nested.is_dir():
                            add(str(nested))

    return mount_points


def find_gopro_devices(paths: Iterable[str] | None = None) -> list[dict]:
    if paths is None:
        paths = collect_mount_points()

    devices: list[dict] = []
    for root in paths:
        drive = Path(root)
        if not drive.exists():
            continue

        version_file = drive / "MISC" / "version.txt"
        dcim_dir = drive / "DCIM" / "100GOPRO"
        if not version_file.exists() or not dcim_dir.exists():
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
