"""GoPro Footage Archiver — copy and organize MP4 clips from GoPro SD cards."""

from gopro_archiver.archive import (
    analyze_archive_status,
    build_destination_indexes,
    collect_mp4_files,
    files_are_identical,
    get_archive_target_path,
    get_mp4_selection_size,
    resolve_archive_target_path,
)
from gopro_archiver.devices import find_gopro_devices, parse_version_file
from gopro_archiver.metadata import get_storage_usage, get_video_metadata
from gopro_archiver.transfer import TransferThread, copy_file_with_progress

__all__ = [
    "analyze_archive_status",
    "build_destination_indexes",
    "collect_mp4_files",
    "copy_file_with_progress",
    "files_are_identical",
    "find_gopro_devices",
    "get_archive_target_path",
    "get_mp4_selection_size",
    "get_storage_usage",
    "get_video_metadata",
    "parse_version_file",
    "resolve_archive_target_path",
    "TransferThread",
]

__version__ = "0.1.0"
