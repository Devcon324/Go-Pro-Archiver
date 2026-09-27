import json

import gopro_archiver.app_paths as app_paths
import gopro_archiver.settings as settings
from tests.mock_data import MOCK_FAVORITE_PATH_A, MOCK_FAVORITE_PATH_B


def test_save_and_load_favorite_destinations(tmp_path, monkeypatch):
    monkeypatch.setattr(app_paths, "config_dir", lambda: tmp_path)

    settings.save_favorite_destinations([MOCK_FAVORITE_PATH_A, MOCK_FAVORITE_PATH_B])
    loaded = settings.load_favorite_destinations()

    assert loaded == [MOCK_FAVORITE_PATH_A, MOCK_FAVORITE_PATH_B]
    payload = json.loads((tmp_path / app_paths.FAVORITES_FILENAME).read_text(encoding="utf-8"))
    assert payload == [MOCK_FAVORITE_PATH_A, MOCK_FAVORITE_PATH_B]


def test_load_favorite_destinations_deduplicates_on_save(tmp_path, monkeypatch):
    monkeypatch.setattr(app_paths, "config_dir", lambda: tmp_path)

    settings.save_favorite_destinations([MOCK_FAVORITE_PATH_A, MOCK_FAVORITE_PATH_A, "  ", MOCK_FAVORITE_PATH_B])
    loaded = settings.load_favorite_destinations()

    assert loaded == [MOCK_FAVORITE_PATH_A, MOCK_FAVORITE_PATH_B]
