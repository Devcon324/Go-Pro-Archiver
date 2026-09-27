import json
import os
from datetime import date, datetime
from pathlib import Path

import gopro_archiver
from tests.mock_data import (
    MOCK_ARCHIVE_DATETIME,
    MOCK_ARCHIVE_DAY,
    MOCK_ARCHIVE_YEAR,
    MOCK_CAMERA_TYPE,
    MOCK_CAMERA_TYPE_ALT,
    MOCK_CLIP_FILENAME,
    MOCK_CLIP_RENAME,
    MOCK_FIRMWARE,
    MOCK_SERIAL_ALT,
    mock_version_metadata,
)


def stat_with_capture_date(path, capture_dates, original_stat):
    """Return a stat result whose mtime and ctime match a patched capture date."""
    stat_result = original_stat(path)
    capture_date = capture_dates(path) if callable(capture_dates) else capture_dates.get(path)
    if capture_date is None:
        return stat_result

    timestamp = (
        capture_date.timestamp()
        if isinstance(capture_date, datetime)
        else datetime.combine(capture_date, datetime.min.time()).timestamp()
    )
    values = list(stat_result)
    values[8] = timestamp  # st_mtime
    values[9] = timestamp  # st_ctime
    return os.stat_result(values)


def test_parse_version_file(tmp_path):
    version_file = tmp_path / "version.txt"
    version_file.write_text(json.dumps(mock_version_metadata()), encoding="utf-8")

    parsed = gopro_archiver.parse_version_file(version_file)

    assert parsed["firmware version"] == MOCK_FIRMWARE
    assert parsed["camera type"] == MOCK_CAMERA_TYPE


def test_detect_gopro_devices(tmp_path):
    source = tmp_path / "MOCKCARD"
    (source / "DCIM" / "100GOPRO").mkdir(parents=True)
    (source / "MISC").mkdir(parents=True)
    (source / "MISC" / "version.txt").write_text(
        json.dumps(mock_version_metadata(camera_type=MOCK_CAMERA_TYPE_ALT, serial=MOCK_SERIAL_ALT)),
        encoding="utf-8",
    )

    discovered = gopro_archiver.find_gopro_devices([str(source)])

    assert len(discovered) == 1
    assert discovered[0]["drive"] == str(source)
    assert discovered[0]["camera_type"] == MOCK_CAMERA_TYPE_ALT


def test_collect_mp4_files_only(tmp_path):
    base = tmp_path / "clip"
    clips = [
        base / "mock-a.mp4",
        base / "mock-b.MP4",
        base / "thumb.thm",
        base / "preview.lrv",
        base / "nested" / "mock-c.mp4",
    ]

    for item in clips:
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(b"mock-bytes")

    result = gopro_archiver.collect_mp4_files(base)

    normalized = {os.path.normpath(str(path.relative_to(base))) for path in result}

    assert normalized == {
        "mock-a.mp4",
        "mock-b.MP4",
        os.path.normpath("nested/mock-c.mp4"),
    }


def test_collect_mp4_files_date_range_is_inclusive(tmp_path, monkeypatch):
    base = tmp_path / "clip"
    files = [base / "before.mp4", base / "start.mp4", base / "end.mp4", base / "after.mp4"]
    for item in files:
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(b"mock-bytes")

    creation_dates = {
        files[0]: date(2030, 1, 9),
        files[1]: date(2030, 1, 10),
        files[2]: date(2030, 1, 20),
        files[3]: date(2030, 1, 21),
    }
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(path, creation_dates, original_stat),
    )

    result = gopro_archiver.collect_mp4_files(base, date(2030, 1, 10), date(2030, 1, 20))

    assert {path.name for path in result} == {"start.mp4", "end.mp4"}


def test_get_mp4_selection_size_uses_date_range(tmp_path, monkeypatch):
    base = tmp_path / "clip"
    selected = base / "selected.mp4"
    excluded = base / "excluded.mp4"
    selected.parent.mkdir(parents=True)
    selected.write_bytes(b"12345")
    excluded.write_bytes(b"123456789")

    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(
            path,
            lambda item: date(2030, 1, 15) if item == selected else date(2030, 1, 9),
            original_stat,
        ),
    )

    result = gopro_archiver.get_mp4_selection_size(base, date(2030, 1, 10), date(2030, 1, 20))

    assert result == 5


def test_get_archive_target_path_uses_year_and_date(tmp_path, monkeypatch):
    source_file = tmp_path / MOCK_CLIP_FILENAME
    source_file.write_bytes(b"mock-bytes")
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(
            path,
            {source_file: MOCK_ARCHIVE_DATETIME},
            original_stat,
        ),
    )

    result = gopro_archiver.get_archive_target_path(tmp_path / "archive", source_file)

    assert result == tmp_path / "archive" / MOCK_ARCHIVE_YEAR / MOCK_ARCHIVE_DAY / MOCK_CLIP_FILENAME


def test_resolve_archive_target_skips_identical_file(tmp_path, monkeypatch):
    source_file = tmp_path / MOCK_CLIP_FILENAME
    source_file.write_bytes(b"mock-identical-payload")
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(
            path,
            {source_file: MOCK_ARCHIVE_DATETIME},
            original_stat,
        ),
    )
    destination_file = gopro_archiver.get_archive_target_path(tmp_path / "archive", source_file)
    destination_file.parent.mkdir(parents=True)
    destination_file.write_bytes(source_file.read_bytes())

    target, action = gopro_archiver.resolve_archive_target_path(tmp_path / "archive", source_file)

    assert target == destination_file
    assert action == "skip"


def test_resolve_archive_target_renames_different_collision(tmp_path, monkeypatch):
    source_file = tmp_path / MOCK_CLIP_FILENAME
    source_file.write_bytes(b"mock-new-payload")
    destination_file = tmp_path / "archive" / MOCK_ARCHIVE_YEAR / MOCK_ARCHIVE_DAY / source_file.name
    destination_file.parent.mkdir(parents=True)
    destination_file.write_bytes(b"mock-old-payload")
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(
            path,
            {source_file: MOCK_ARCHIVE_DATETIME},
            original_stat,
        ),
    )

    target, action = gopro_archiver.resolve_archive_target_path(tmp_path / "archive", source_file)

    assert target == destination_file.with_name(MOCK_CLIP_RENAME)
    assert action == "renamed"


def test_files_are_identical_uses_size_and_samples(tmp_path):
    source_file = tmp_path / "mock-source.MP4"
    matching = tmp_path / "mock-matching.MP4"
    different_size = tmp_path / "mock-different-size.MP4"
    different_content = tmp_path / "mock-different-content.MP4"
    payload = b"mock-head" + (b"x" * 1024) + b"mock-tail"
    source_file.write_bytes(payload)
    matching.write_bytes(payload)
    different_size.write_bytes(payload + b"extra")
    different_content.write_bytes(b"MOCK-HEAD" + (b"x" * 1024) + b"MOCK-TAIL")

    assert gopro_archiver.files_are_identical(source_file, matching)
    assert not gopro_archiver.files_are_identical(source_file, different_size)
    assert not gopro_archiver.files_are_identical(source_file, different_content)


def test_resolve_archive_target_skips_identical_renamed_collision(tmp_path, monkeypatch):
    source_file = tmp_path / MOCK_CLIP_FILENAME
    source_file.write_bytes(b"mock-identical-payload")
    destination_file = tmp_path / "archive" / MOCK_ARCHIVE_YEAR / MOCK_ARCHIVE_DAY / source_file.name
    renamed_file = destination_file.with_name(MOCK_CLIP_RENAME)
    destination_file.parent.mkdir(parents=True)
    destination_file.write_bytes(b"mock-conflict")
    renamed_file.write_bytes(b"mock-identical-payload")
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(
            path,
            {source_file: MOCK_ARCHIVE_DATETIME},
            original_stat,
        ),
    )

    folder_indexes = gopro_archiver.build_destination_indexes(tmp_path / "archive", [source_file])
    target, action = gopro_archiver.resolve_archive_target_path(
        tmp_path / "archive",
        source_file,
        folder_indexes,
    )

    assert target == renamed_file
    assert action == "skip"


def test_analyze_archive_status_marks_missing_and_archived(tmp_path, monkeypatch):
    source_dir = tmp_path / "mock-card"
    source_dir.mkdir()
    archived = source_dir / "mock-archived.MP4"
    missing = source_dir / "mock-missing.MP4"
    archived.write_bytes(b"mock-archived-payload")
    missing.write_bytes(b"mock-missing-payload")
    original_stat = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda path, *args, **kwargs: stat_with_capture_date(
            path,
            {archived: MOCK_ARCHIVE_DATETIME, missing: MOCK_ARCHIVE_DATETIME},
            original_stat,
        ),
    )

    destination_file = gopro_archiver.get_archive_target_path(tmp_path / "archive", archived)
    destination_file.parent.mkdir(parents=True)
    destination_file.write_bytes(archived.read_bytes())

    results = {
        file_path.name: action
        for file_path, _target, action in gopro_archiver.analyze_archive_status(
            tmp_path / "archive",
            [archived, missing],
        )
    }

    assert results["mock-archived.MP4"] == "skip"
    assert results["mock-missing.MP4"] == "copy"


def test_copy_file_with_progress_removes_partial_file_on_cancel(tmp_path):
    source_file = tmp_path / "mock-source.MP4"
    destination_file = tmp_path / "mock-destination.MP4"
    source_file.write_bytes(b"x" * (5 * 1024 * 1024))
    callback_calls = 0

    def record_chunk(_chunk_size):
        nonlocal callback_calls
        callback_calls += 1

    completed = gopro_archiver.copy_file_with_progress(
        source_file,
        destination_file,
        record_chunk,
        lambda: callback_calls >= 1,
    )

    assert completed is False
    assert not destination_file.exists()


def test_get_storage_usage(tmp_path):
    stats = gopro_archiver.get_storage_usage(str(tmp_path))

    assert stats["total_bytes"] > 0
    assert stats["free_bytes"] >= 0
    assert 0 <= stats["used_percent"] <= 100
