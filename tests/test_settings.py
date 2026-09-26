import json

import gopro_archiver.app_paths as app_paths
import gopro_archiver.settings as settings


def test_save_and_load_favorite_destinations(tmp_path, monkeypatch):
    monkeypatch.setattr(app_paths, "config_dir", lambda: tmp_path)

    settings.save_favorite_destinations([r"D:\Archive", r"E:\GoPro"])
    loaded = settings.load_favorite_destinations()

    assert loaded == [r"D:\Archive", r"E:\GoPro"]
    payload = json.loads((tmp_path / app_paths.FAVORITES_FILENAME).read_text(encoding="utf-8"))
    assert payload == [r"D:\Archive", r"E:\GoPro"]


def test_load_favorite_destinations_deduplicates_on_save(tmp_path, monkeypatch):
    monkeypatch.setattr(app_paths, "config_dir", lambda: tmp_path)

    settings.save_favorite_destinations([r"D:\Archive", r"D:\Archive", "  ", r"E:\GoPro"])
    loaded = settings.load_favorite_destinations()

    assert loaded == [r"D:\Archive", r"E:\GoPro"]
