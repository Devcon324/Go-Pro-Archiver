from __future__ import annotations

import shutil
import threading
import time
from datetime import date
from pathlib import Path

from gopro_archiver.archive import (
    build_destination_indexes,
    collect_mp4_files,
    resolve_archive_target_path,
)


def copy_file_with_progress(source_file: Path, destination_file: Path, progress_callback, should_stop) -> bool:
    with source_file.open("rb") as source_handle, destination_file.open("wb") as destination_handle:
        while chunk := source_handle.read(4 * 1024 * 1024):
            destination_handle.write(chunk)
            progress_callback(len(chunk))
            if should_stop():
                destination_handle.close()
                destination_file.unlink(missing_ok=True)
                return False
    shutil.copystat(source_file, destination_file)
    return True


class TransferThread(threading.Thread):
    def __init__(
        self,
        source_dir: str,
        destination_dir: str,
        callback=None,
        start_date: date | None = None,
        end_date: date | None = None,
        selected_files: list[Path] | None = None,
    ):
        super().__init__(daemon=True)
        self.source_dir = source_dir
        self.destination_dir = destination_dir
        self.callback = callback
        self.start_date = start_date
        self.end_date = end_date
        self.selected_files = selected_files
        self._stop = threading.Event()

    def run(self):
        files = self.selected_files if self.selected_files is not None else collect_mp4_files(self.source_dir, self.start_date, self.end_date)
        destination_indexes = build_destination_indexes(self.destination_dir, files)
        total_bytes = sum(file.stat().st_size for file in files)
        copied_bytes = 0
        files_skipped = 0
        files_renamed = 0
        files_copied_count = 0
        processed_bytes = 0
        speed_history: list[float] = []
        cancelled = False
        current_file_name = None
        current_destination_path = None
        current_action = None
        current_file_index = 0

        def report_progress(file_index, current_speed):
            if self.callback:
                completed = (processed_bytes / total_bytes) if total_bytes else 1.0
                eta_seconds = ((total_bytes - processed_bytes) / max(current_speed, 0.001)) if current_speed > 0 else 0
                self.callback(
                    {
                        "completed": completed,
                        "copied_bytes": copied_bytes,
                        "total_bytes": total_bytes,
                        "current_speed": current_speed,
                        "speed_history": speed_history[:],
                        "eta_seconds": eta_seconds,
                        "files_processed": file_index,
                        "files_copied": files_copied_count,
                        "files_skipped": files_skipped,
                        "files_renamed": files_renamed,
                        "total_files": len(files),
                        "current_file": current_file_name,
                        "destination_path": current_destination_path,
                        "current_action": current_action,
                        "current_file_index": current_file_index,
                    }
                )

        report_progress(0, 0.0)

        for idx, file_path in enumerate(files, start=1):
            if self._stop.is_set():
                cancelled = True
                break

            file_size = file_path.stat().st_size
            target_file, action = resolve_archive_target_path(
                self.destination_dir,
                file_path,
                destination_indexes,
            )
            current_file_name = file_path.name
            current_destination_path = str(target_file)
            current_action = action
            current_file_index = idx
            report_progress(idx - 1, speed_history[-1] if speed_history else 0.0)
            if action == "skip":
                files_skipped += 1
            else:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                last_progress_time = time.monotonic()

                def record_chunk(chunk_size):
                    nonlocal copied_bytes, processed_bytes, last_progress_time
                    copied_bytes += chunk_size
                    processed_bytes += chunk_size
                    now = time.monotonic()
                    elapsed = max(now - last_progress_time, 0.01)
                    current_speed = chunk_size / elapsed
                    speed_history.append(current_speed)
                    last_progress_time = now
                    report_progress(idx - 1, current_speed)

                completed_file = copy_file_with_progress(file_path, target_file, record_chunk, self._stop.is_set)
                if not completed_file:
                    cancelled = True
                    break
                if action == "renamed":
                    files_renamed += 1
                files_copied_count += 1
                destination_indexes.setdefault(target_file.parent, {})[target_file.name] = file_size
            if action == "skip":
                processed_bytes += file_size
            current_file_name = None
            current_destination_path = None
            current_action = None
            current_file_index = 0
            report_progress(idx, 0.0 if action == "skip" else speed_history[-1] if speed_history else 0.0)

        if self.callback:
            self.callback({
                "completed": 1.0,
                "copied_bytes": copied_bytes,
                "total_bytes": total_bytes,
                "current_speed": 0.0,
                "speed_history": speed_history,
                "eta_seconds": 0,
                "files_processed": len(files),
                "files_copied": files_copied_count,
                "files_skipped": files_skipped,
                "files_renamed": files_renamed,
                "total_files": len(files),
                "cancelled": cancelled,
                "finished": True,
            })

    def stop(self):
        self._stop.set()
