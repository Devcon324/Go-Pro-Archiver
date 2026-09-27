import json
from pathlib import Path

import gopro_archiver.devices as devices
from tests.mock_data import MOCK_CARD_LABEL, MOCK_LINUX_USER, MOCK_SERIAL_ALT, mock_version_metadata


def test_find_gopro_devices_under_linux_media_layout(tmp_path, monkeypatch):
    card = tmp_path / "media" / MOCK_LINUX_USER / MOCK_CARD_LABEL
    (card / "DCIM" / "100GOPRO").mkdir(parents=True)
    (card / "MISC").mkdir(parents=True)
    (card / "MISC" / "version.txt").write_text(
        json.dumps(mock_version_metadata(serial=MOCK_SERIAL_ALT)),
        encoding="utf-8",
    )

    monkeypatch.setattr(devices, "collect_mount_points", lambda: [str(card)])

    discovered = devices.find_gopro_devices()

    assert len(discovered) == 1
    assert discovered[0]["drive"] == str(card)


def test_collect_mount_points_ignores_permission_errors(tmp_path, monkeypatch):
    media = tmp_path / "media"
    user = media / MOCK_LINUX_USER
    card = user / MOCK_CARD_LABEL
    card.mkdir(parents=True)

    blocked = user / "mock-blocked-entry.sys"
    blocked.write_text("mock")

    original_is_dir = Path.is_dir

    def is_dir(self, follow_symlinks=True):
        if self == blocked:
            raise PermissionError(13, "Permission denied")
        return original_is_dir(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(devices, "collect_mount_points", devices.collect_mount_points)
    monkeypatch.setattr(devices.psutil, "disk_partitions", lambda all=False: [])
    monkeypatch.setattr(devices.sys, "platform", "linux")
    monkeypatch.setattr(Path, "is_dir", is_dir)

    def fake_media_paths(add):
        base = media
        for entry in base.iterdir():
            if devices._safe_is_dir(entry):
                add(str(entry))
                for nested in entry.iterdir():
                    if devices._safe_is_dir(nested):
                        add(str(nested))

    monkeypatch.setattr(devices, "_add_removable_media_paths", lambda add: fake_media_paths(add))

    mount_points = devices.collect_mount_points()

    assert str(user) in mount_points
    assert str(card) in mount_points
