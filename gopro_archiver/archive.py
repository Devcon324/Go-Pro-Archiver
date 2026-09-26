from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

IDENTICAL_SAMPLE_BYTES = 256 * 1024


def collect_mp4_files(
    source_dir: str | os.PathLike[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Path]:
    root = Path(source_dir)
    files: list[Path] = []
    if not root.exists():
        return files

    for item in root.rglob("*"):
        if not item.is_file() or item.suffix.lower() != ".mp4":
            continue
        if start_date is not None or end_date is not None:
            created_date = datetime.fromtimestamp(item.stat().st_ctime).date()
            if start_date is not None and created_date < start_date:
                continue
            if end_date is not None and created_date > end_date:
                continue
        files.append(item)

    return sorted(files)


def get_mp4_selection_size(
    source_dir: str | os.PathLike[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    return sum(file_path.stat().st_size for file_path in collect_mp4_files(source_dir, start_date, end_date))


def get_archive_target_path(destination_dir: str | os.PathLike[str], file_path: str | os.PathLike[str]) -> Path:
    source_file = Path(file_path)
    file_date = datetime.fromtimestamp(source_file.stat().st_ctime).date()
    return Path(destination_dir) / str(file_date.year) / file_date.isoformat() / source_file.name


def files_are_identical(source_file: str | os.PathLike[str], destination_file: str | os.PathLike[str]) -> bool:
    source_path = Path(source_file)
    destination_path = Path(destination_file)
    try:
        source_size = source_path.stat().st_size
        if source_size != destination_path.stat().st_size:
            return False
        if source_size == 0:
            return True

        with source_path.open("rb") as source_handle, destination_path.open("rb") as destination_handle:
            head_size = min(IDENTICAL_SAMPLE_BYTES, source_size)
            if source_handle.read(head_size) != destination_handle.read(head_size):
                return False
            if source_size <= IDENTICAL_SAMPLE_BYTES:
                return True
            tail_size = min(IDENTICAL_SAMPLE_BYTES, source_size - head_size)
            source_handle.seek(source_size - tail_size)
            destination_handle.seek(source_size - tail_size)
            return source_handle.read(tail_size) == destination_handle.read(tail_size)
    except OSError:
        return False


def index_archive_folder(folder: str | os.PathLike[str]) -> dict[str, int]:
    folder_path = Path(folder)
    names_to_sizes: dict[str, int] = {}
    if not folder_path.exists():
        return names_to_sizes

    with os.scandir(folder_path) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.lower().endswith(".mp4"):
                names_to_sizes[entry.name] = entry.stat().st_size
    return names_to_sizes


def build_destination_indexes(
    destination_dir: str | os.PathLike[str],
    files: Iterable[Path],
) -> dict[Path, dict[str, int]]:
    folders = {get_archive_target_path(destination_dir, file_path).parent for file_path in files}
    return {folder: index_archive_folder(folder) for folder in folders}


def resolve_archive_target_path(
    destination_dir: str | os.PathLike[str],
    file_path: str | os.PathLike[str],
    folder_indexes: dict[Path, dict[str, int]] | None = None,
) -> tuple[Path, str]:
    target_path = get_archive_target_path(destination_dir, file_path)
    folder_index = None if folder_indexes is None else folder_indexes.get(target_path.parent)

    def existing_size(candidate: Path) -> int | None:
        if folder_index is not None:
            return folder_index.get(candidate.name)
        try:
            return candidate.stat().st_size
        except OSError:
            return None

    def is_duplicate(candidate: Path, size: int) -> bool:
        source_size = Path(file_path).stat().st_size
        if size != source_size:
            return False
        return files_are_identical(file_path, candidate)

    current_size = existing_size(target_path)
    if current_size is None:
        return target_path, "copy"
    if is_duplicate(target_path, current_size):
        return target_path, "skip"

    counter = 1
    while True:
        conflict_path = target_path.with_name(f"{target_path.stem}_{counter}{target_path.suffix}")
        conflict_size = existing_size(conflict_path)
        if conflict_size is None:
            return conflict_path, "renamed"
        if is_duplicate(conflict_path, conflict_size):
            return conflict_path, "skip"
        counter += 1


def analyze_archive_status(
    destination_dir: str | os.PathLike[str],
    files: Iterable[Path],
) -> list[tuple[Path, Path, str]]:
    file_list = list(files)
    folder_indexes = build_destination_indexes(destination_dir, file_list)
    return [
        (file_path, *resolve_archive_target_path(destination_dir, file_path, folder_indexes))
        for file_path in file_list
    ]
