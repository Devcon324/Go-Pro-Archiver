from pathlib import Path

import gopro_archiver.devices as devices


def test_find_gopro_devices_under_linux_media_layout(tmp_path, monkeypatch):
    card = tmp_path / "media" / "user" / "GOPRO"
    (card / "DCIM" / "100GOPRO").mkdir(parents=True)
    (card / "MISC").mkdir(parents=True)
    (card / "MISC" / "version.txt").write_text(
        '{"camera type": "HERO", "camera serial number": "ABC123"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(devices, "collect_mount_points", lambda: [str(card)])

    discovered = devices.find_gopro_devices()

    assert len(discovered) == 1
    assert discovered[0]["drive"] == str(card)
