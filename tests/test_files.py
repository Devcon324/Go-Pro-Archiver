import os
import sys
from datetime import date, datetime
from pathlib import Path

import gopro_archiver.files as files


def test_get_file_capture_date_uses_ctime_on_windows(tmp_path, monkeypatch):
    sample = tmp_path / "clip.MP4"
    sample.write_bytes(b"x")

    original_stat = Path.stat

    def stat_with_times(path, *args, **kwargs):
        stat_result = original_stat(path, *args, **kwargs)
        values = list(stat_result)
        values[8] = datetime(2026, 1, 1).timestamp()  # st_mtime
        values[9] = datetime(2026, 6, 15).timestamp()  # st_ctime
        return os.stat_result(values)

    monkeypatch.setattr(Path, "stat", stat_with_times)
    monkeypatch.setattr(sys, "platform", "win32")

    assert files.get_file_capture_date(sample) == date(2026, 6, 15)


def test_get_file_capture_date_uses_mtime_on_linux(tmp_path, monkeypatch):
    sample = tmp_path / "clip.MP4"
    sample.write_bytes(b"x")

    original_stat = Path.stat

    def stat_with_times(path, *args, **kwargs):
        stat_result = original_stat(path, *args, **kwargs)
        values = list(stat_result)
        values[8] = datetime(2026, 3, 20).timestamp()
        values[9] = datetime(2026, 6, 15).timestamp()
        return os.stat_result(values)

    monkeypatch.setattr(Path, "stat", stat_with_times)
    monkeypatch.setattr(sys, "platform", "linux")

    assert files.get_file_capture_date(sample) == date(2026, 3, 20)
