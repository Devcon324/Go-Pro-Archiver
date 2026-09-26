from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import customtkinter as ctk
import av
import psutil
from tkcalendar import Calendar


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


def find_gopro_devices(paths: Iterable[str] | None = None) -> list[dict]:
    if paths is None:
        paths = [part.mountpoint for part in psutil.disk_partitions(all=False)]

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


IDENTICAL_SAMPLE_BYTES = 256 * 1024


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


def get_video_metadata(file_path: str | os.PathLike[str]) -> dict[str, str]:
    try:
        with av.open(str(file_path)) as container:
            video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
            if video_stream is None:
                return {"resolution": "--", "fps": "--"}

            frame_rate = video_stream.average_rate
            fps = f"{float(frame_rate):.2f}" if frame_rate else "--"
            return {
                "resolution": f"{video_stream.width}x{video_stream.height}",
                "fps": fps,
            }
    except (OSError, av.error.FFmpegError, StopIteration):
        return {"resolution": "--", "fps": "--"}


def get_storage_usage(path: str | os.PathLike[str]) -> dict:
    target = str(path)
    if not target or not os.path.exists(target):
        return {
            "path": target,
            "total_bytes": 0,
            "used_bytes": 0,
            "free_bytes": 0,
            "used_percent": 0.0,
        }

    total, used, free = shutil.disk_usage(target)
    total_bytes = float(total)
    used_bytes = float(used)
    free_bytes = float(free)
    used_percent = (used_bytes / total_bytes * 100.0) if total_bytes else 0.0

    return {
        "path": target,
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "used_percent": used_percent,
    }


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
        start_time = time.monotonic()
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


class GoProArchiverApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GoPro Footage Archiver")
        self.geometry("1500x980")
        self.minsize(1300, 980)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        forest_theme = ctk.ThemeManager.theme
        forest_theme["CTk"]["fg_color"] = ["#dce7df", "#09120d"]
        forest_theme["CTkToplevel"]["fg_color"] = ["#dce7df", "#09120d"]
        forest_theme["CTkFrame"]["fg_color"] = ["#cbd9ce", "#101d15"]
        forest_theme["CTkFrame"]["top_fg_color"] = ["#b9cdbd", "#17291e"]
        forest_theme["CTkButton"]["fg_color"] = ["#2ea043", "#238636"]
        forest_theme["CTkButton"]["hover_color"] = ["#238636", "#196c2e"]
        # forest_theme["CTkProgressBar"]["progress_color"] = ["#2ea043", "#238636"]
        forest_theme["CTkProgressBar"]["progress_color"] = ["#2ed44c", "#18D53E"]
        forest_theme["CTkOptionMenu"]["fg_color"] = ["#2ea043", "#238636"]
        forest_theme["CTkOptionMenu"]["button_color"] = ["#238636", "#196c2e"]
        forest_theme["CTkOptionMenu"]["button_hover_color"] = ["#1f883d", "#145c27"]

        self.favorites = []
        self.detected_devices = []
        self.selected_device = None
        self.transfer_thread = None
        self.analyzing = False
        self.analyze_generation = 0
        self.start_date_var = ctk.StringVar(value="")
        self.end_date_var = ctk.StringVar(value="")
        self.file_sort_key = "title"
        self.file_sort_reverse = False
        self.video_metadata_cache = {}
        self.preview_generation = 0
        self.preview_metadata_labels = {}
        self.file_selection_vars = {}
        self.select_all_var = ctk.BooleanVar(value=False)
        self.transfer_updates = queue.Queue()
        self.transfer_update_poll = None
        self.transfer_finished_received = False
        self.eta_display_value = 0
        self.last_eta_display_update = 0.0

        self._build_ui()
        self.refresh_devices()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        main = ctk.CTkFrame(self, corner_radius=18)
        main.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        main.grid_columnconfigure(0, weight=60)
        main.grid_columnconfigure(1, weight=60)
        main.grid_columnconfigure(2, weight=17)
        main.grid_rowconfigure(0, weight=1)

        left_panel = ctk.CTkFrame(main, corner_radius=16, fg_color="transparent")
        left_panel.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="nsew")
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(1, weight=1)

        preview_panel = ctk.CTkFrame(main, corner_radius=16, fg_color="transparent")
        preview_panel.grid(row=0, column=1, padx=10, pady=20, sticky="nsew")
        preview_panel.grid_columnconfigure(0, weight=1)
        preview_panel.grid_rowconfigure(1, weight=1)

        preview_title_row = ctk.CTkFrame(preview_panel, fg_color="transparent")
        preview_title_row.grid(row=0, column=0, pady=(10, 8), sticky="ew")
        preview_title_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(preview_title_row, text="Files to copy", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.file_preview_summary = ctk.CTkLabel(preview_title_row, text="Select a GoPro to preview files", text_color="#cbd5e1", anchor="e")
        self.file_preview_summary.grid(row=0, column=1, sticky="e")

        file_preview = ctk.CTkFrame(preview_panel, corner_radius=14)
        file_preview.grid(row=1, column=0, sticky="nsew")
        file_preview.grid_columnconfigure(0, weight=1)
        file_preview.grid_rowconfigure(1, weight=1)

        file_header = ctk.CTkFrame(file_preview, fg_color="transparent")
        file_header.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        file_header.grid_columnconfigure(0, weight=0, minsize=28)
        file_header.grid_columnconfigure(1, weight=0, minsize=112)
        file_header.grid_columnconfigure(2, weight=2, minsize=105)
        file_header.grid_columnconfigure(3, weight=0, minsize=92)
        file_header.grid_columnconfigure(4, weight=0, minsize=52)
        file_header.grid_columnconfigure(5, weight=0, minsize=92)
        self.file_sort_buttons = {}
        ctk.CTkCheckBox(
            file_header,
            text="",
            width=20,
            checkbox_width=15,
            checkbox_height=15,
            variable=self.select_all_var,
            command=self.toggle_all_visible_files,
        ).grid(row=0, column=0, padx=5, sticky="ew")
        header_specs = (
            ("title", "Title", 112),
            ("date", "Date", 105),
            (None, "Resolution", 92),
            (None, "FPS", 52),
            ("size", "Size", 92),
        )
        for column, (key, label, header_width) in enumerate(header_specs, start=1):
            if key is None:
                ctk.CTkLabel(file_header, text=label, text_color="#94a3b8", anchor="w").grid(
                    row=0, column=column, padx=2, sticky="ew"
                )
                continue
            button = ctk.CTkButton(
                file_header,
                text=label,
                anchor="e" if key == "size" else "w",
                fg_color="transparent",
                hover_color="#244235",
                text_color="#94a3b8",
                height=24,
                width=header_width,
                command=lambda sort_key=key: self.sort_file_preview(sort_key),
            )
            button.grid(row=0, column=column, padx=2, sticky="ew")
            self.file_sort_buttons[key] = button
        self.update_file_sort_headers()

        self.file_preview_list = ctk.CTkScrollableFrame(file_preview, corner_radius=10)
        self.file_preview_list.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        for column, weight, minsize in ((0, 0, 28), (1, 0, 112), (2, 2, 105), (3, 0, 92), (4, 0, 52), (5, 0, 92)):
            self.file_preview_list.grid_columnconfigure(column, weight=weight, minsize=minsize)

        right_panel = ctk.CTkFrame(main, corner_radius=16, fg_color="transparent")
        right_panel.grid(row=0, column=2, padx=(10, 20), pady=20, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left_panel, text="Detected GoPro devices", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, pady=(10, 10), sticky="w")

        self.device_list = ctk.CTkScrollableFrame(left_panel, corner_radius=14)
        self.device_list.grid(row=1, column=0, sticky="nsew")
        self.device_list.grid_columnconfigure(0, weight=1)

        self.source_var = ctk.StringVar(value="")
        self.destination_var = ctk.StringVar(value="")

        form = ctk.CTkFrame(right_panel, corner_radius=16)
        form.grid(row=0, column=0, sticky="nsew")
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="Source", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        self.source_entry = ctk.CTkEntry(form, textvariable=self.source_var, state="readonly")
        self.source_entry.grid(row=1, column=0, padx=20, sticky="ew")

        destination_title_row = ctk.CTkFrame(form, corner_radius=10, fg_color="transparent")
        destination_title_row.grid(row=2, column=0, padx=20, pady=(18, 10), sticky="ew")
        destination_title_row.grid_columnconfigure(0, weight=1)
        destination_title_row.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(destination_title_row, text="Destination archive", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        self.favorite_menu = ctk.CTkOptionMenu(destination_title_row, values=["Favourite Destination Paths"], command=self.select_favorite_destination, width=190)
        self.favorite_menu.grid(row=0, column=1, sticky="e")
        self.favorite_menu.set("Favourite Destination Paths")

        destination_row = ctk.CTkFrame(form, corner_radius=10)
        destination_row.grid(row=3, column=0, padx=20, sticky="ew")
        destination_row.grid_columnconfigure(0, weight=1)
        destination_row.grid_columnconfigure(1, weight=0)

        self.destination_entry = ctk.CTkEntry(destination_row, textvariable=self.destination_var, state="readonly")
        self.destination_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.save_favorite_button = ctk.CTkButton(destination_row, text="Save", command=self.save_favorite_destination, width=80)
        self.save_favorite_button.grid(row=0, column=1, sticky="e")

        row = 4
        self.choose_destination_button = ctk.CTkButton(form, text="Choose destination folder", command=self.choose_destination)
        self.choose_destination_button.grid(row=row, column=0, padx=20, pady=(12, 8), sticky="ew")
        row += 1

        self.remove_favorite_button = ctk.CTkButton(form, text="Remove selected favourite", command=self.remove_favorite_destination)
        self.remove_favorite_button.grid(row=row, column=0, padx=20, pady=(8, 6), sticky="ew")
        row += 1

        date_range = ctk.CTkFrame(form, corner_radius=14)
        date_range.grid(row=row, column=0, padx=20, pady=(12, 8), sticky="ew")
        date_range.grid_columnconfigure(0, weight=1)
        date_range.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(date_range, text="Date range (optional)", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(12, 8), sticky="w"
        )
        ctk.CTkLabel(date_range, text="From (YYYY-MM-DD)").grid(row=1, column=0, padx=(14, 6), sticky="w")
        ctk.CTkLabel(date_range, text="To (YYYY-MM-DD)").grid(row=1, column=1, padx=(6, 14), sticky="w")
        start_date_row = ctk.CTkFrame(date_range, fg_color="transparent")
        start_date_row.grid(row=2, column=0, padx=(14, 6), pady=(4, 14), sticky="ew")
        start_date_row.grid_columnconfigure(0, weight=1)
        self.start_date_entry = ctk.CTkEntry(start_date_row, textvariable=self.start_date_var, placeholder_text="All earlier files")
        self.start_date_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(start_date_row, text="Calendar", width=86, command=lambda: self.open_date_picker(self.start_date_var, "Select start date")).grid(row=0, column=1, sticky="e")

        end_date_row = ctk.CTkFrame(date_range, fg_color="transparent")
        end_date_row.grid(row=2, column=1, padx=(6, 14), pady=(4, 14), sticky="ew")
        end_date_row.grid_columnconfigure(0, weight=1)
        self.end_date_entry = ctk.CTkEntry(end_date_row, textvariable=self.end_date_var, placeholder_text="All later files")
        self.end_date_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(end_date_row, text="Calendar", width=86, command=lambda: self.open_date_picker(self.end_date_var, "Select end date")).grid(row=0, column=1, sticky="e")
        row += 1

        self.storage_panel = ctk.CTkFrame(form, corner_radius=14)
        self.storage_panel.grid(row=row, column=0, padx=20, pady=(18, 8), sticky="ew")
        self.storage_panel.grid_columnconfigure(0, weight=1)

        self.source_storage_label = ctk.CTkLabel(self.storage_panel, text="Size of Selected Files: --", anchor="w")
        self.source_storage_label.grid(row=0, column=0, padx=14, pady=(14, 4), sticky="ew")
        self.source_storage_bar = ctk.CTkProgressBar(self.storage_panel, height=12)
        self.source_storage_bar.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        self.set_storage_bar(self.source_storage_bar, 0)

        self.destination_storage_label = ctk.CTkLabel(self.storage_panel, text="Destination storage: --", anchor="w")
        self.destination_storage_label.grid(row=2, column=0, padx=14, pady=(10, 4), sticky="ew")
        self.destination_storage_bar = ctk.CTkCanvas(self.storage_panel, height=16, bg="#101d15", highlightthickness=0)
        self.destination_storage_bar.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")
        self.destination_storage_bar.bind("<Configure>", lambda _event: self.draw_destination_projection())
        self.destination_storage_projection = (0.0, 0.0, 0.0)
        self.destination_storage_warning = ctk.CTkLabel(
            self.storage_panel,
            text="Not enough storage space",
            text_color="#f06a6a",
            anchor="w",
        )
        self.destination_storage_warning.grid(row=4, column=0, padx=14, pady=(0, 10), sticky="ew")
        self.destination_storage_warning.grid_remove()

        action_row = ctk.CTkFrame(form, fg_color="transparent")
        action_row.grid(row=row + 1, column=0, padx=20, pady=(12, 8), sticky="ew")
        action_row.grid_columnconfigure(0, weight=0)
        action_row.grid_columnconfigure(1, weight=1)
        action_row.grid_columnconfigure(2, weight=0)
        self.analyze_button = ctk.CTkButton(action_row, text="Analyze", width=90, command=self.start_analyze)
        self.analyze_button.grid(row=0, column=0, padx=(0, 8), sticky="w")
        self.copy_button = ctk.CTkButton(action_row, text="Copy MP4 files", fg_color="#238636", hover_color="#196c2e", command=self.start_copy)
        self.copy_button.grid(row=0, column=1, padx=(0, 8), sticky="ew")
        self.cancel_button = ctk.CTkButton(action_row, text="Cancel", width=90, command=self.cancel_copy, state="disabled")
        self.cancel_button.grid(row=0, column=2, sticky="e")

        self.progress_var = ctk.DoubleVar(value=0)
        self.progress = ctk.CTkProgressBar(form, variable=self.progress_var, height=18)
        self.progress.grid(row=row + 2, column=0, padx=20, pady=(12, 5), sticky="ew")
        self.progress.set(0)

        status = ctk.CTkFrame(form, corner_radius=14)
        status.grid(row=row + 3, column=0, padx=20, pady=(12, 20), sticky="nsew")
        status.grid_columnconfigure(0, weight=1)
        status.grid_rowconfigure(2, weight=1)
        form.grid_rowconfigure(row + 3, weight=1)

        self.status_label = ctk.CTkLabel(
            status,
            text="Ready",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            justify="left",
        )
        self.status_label.grid(row=0, column=0, padx=16, pady=(14, 6), sticky="ew")

        self.meta_label = ctk.CTkLabel(status, text="Transfer speed: --\nETA: --\nFiles: --", justify="left", anchor="w")
        self.meta_label.grid(row=1, column=0, padx=16, pady=(6, 14), sticky="ew")
        status.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(event.width - 32, 120)))

        self.graph_canvas = ctk.CTkCanvas(status, width=320, height=100, bg="#1d1e2a", highlightthickness=0)
        self.graph_canvas.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")

        self.refresh_favorites()
        self.start_date_var.trace_add("write", lambda *_: self.on_date_range_changed())
        self.end_date_var.trace_add("write", lambda *_: self.on_date_range_changed())

    def refresh_devices(self):
        self.detected_devices = find_gopro_devices()
        for child in self.device_list.winfo_children():
            child.destroy()

        if not self.detected_devices:
            empty = ctk.CTkLabel(self.device_list, text="No GoPro SD card detected", text_color="#cbd5e1")
            empty.grid(row=0, column=0, padx=16, pady=20, sticky="w")
            return

        for index, device in enumerate(self.detected_devices):
            is_selected = self.selected_device is not None and self.selected_device.get("drive") == device.get("drive")
            card = ctk.CTkFrame(self.device_list, corner_radius=14, fg_color="#1b3625" if is_selected else "#101812")
            card.grid(row=index, column=0, padx=12, pady=8, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            card._device = device

            if is_selected:
                card.configure(border_width=2, border_color="#3fb950")
            else:
                card.configure(border_width=0, border_color="#3fb950")

            header_row = ctk.CTkFrame(card, corner_radius=8, fg_color="transparent")
            header_row.grid(row=0, column=0, padx=14, pady=(14, 6), sticky="ew")
            header_row.grid_columnconfigure(0, weight=1)
            header_row.grid_columnconfigure(1, weight=0)
            header_row.grid_columnconfigure(2, weight=0)

            name = device.get("camera_type") or "GoPro"
            serial = device.get("serial_number") or "Unknown"
            firmware = device.get("firmware_version") or "Unknown"

            title = ctk.CTkLabel(header_row, text=f"{name}", font=ctk.CTkFont(size=18, weight="bold"))
            title.grid(row=0, column=0, padx=(0, 8), sticky="w")

            selected_label = ctk.CTkLabel(header_row, text="Selected", text_color="#9ae6b4", font=ctk.CTkFont(size=11, weight="bold"))
            selected_label.grid(row=0, column=1, padx=(0, 8), sticky="w")
            if not is_selected:
                selected_label.grid_remove()
            card._selected_label = selected_label

            dot_canvas = ctk.CTkCanvas(header_row, width=16, height=16, bg="#1b3625" if is_selected else "#101812", highlightthickness=0)
            dot_canvas.grid(row=0, column=2, sticky="e")
            card._dot_canvas = dot_canvas
            dot_canvas.delete("all")
            if is_selected:
                dot_canvas.create_oval(1, 1, 15, 15, outline="#a8c9ad", width=2, fill="#1b3625")
                dot_canvas.create_oval(4, 4, 12, 12, fill="#3fb950", outline="")
                dot_canvas.create_oval(6, 6, 10, 10, fill="#b7f0bd", outline="")
            else:
                dot_canvas.create_oval(2, 2, 14, 14, fill="#64748b", outline="")

            mcu = device.get("mcu_version") or "Unknown"
            wifi = device.get("wifi_mac") or "Unknown"

            serial_label = ctk.CTkTextbox(card, height=22, wrap="word", state="disabled", activate_scrollbars=False)
            serial_label.grid(row=1, column=0, padx=14, sticky="ew")
            serial_label.configure(state="normal")
            serial_label.insert("end", f"Serial: {serial}")
            serial_label.configure(state="disabled")

            firmware_label = ctk.CTkTextbox(card, height=22, wrap="word", state="disabled", activate_scrollbars=False)
            firmware_label.grid(row=2, column=0, padx=14, sticky="ew")
            firmware_label.configure(state="normal")
            firmware_label.insert("end", f"Firmware: {firmware}")
            firmware_label.configure(state="disabled")

            mcu_label = ctk.CTkTextbox(card, height=22, wrap="word", state="disabled", activate_scrollbars=False)
            mcu_label.grid(row=3, column=0, padx=14, sticky="ew")
            mcu_label.configure(state="normal")
            mcu_label.insert("end", f"MCU: {mcu}")
            mcu_label.configure(state="disabled")

            wifi_label = ctk.CTkTextbox(card, height=22, wrap="word", state="disabled", activate_scrollbars=False)
            wifi_label.grid(row=4, column=0, padx=14, pady=(0, 12), sticky="ew")
            wifi_label.configure(state="normal")
            wifi_label.insert("end", f"Wi‑Fi MAC: {wifi}")
            wifi_label.configure(state="disabled")

            copy_button = ctk.CTkButton(card, text="Copy details", width=120, command=lambda d=device: self.copy_device_details(d))
            copy_button.grid(row=5, column=0, padx=14, pady=(0, 12), sticky="w")

            storage_usage = get_storage_usage(device["drive"])
            storage_label = ctk.CTkLabel(
                card,
                text=f"GoPro storage:\n{format_bytes(storage_usage['free_bytes'])} free / {format_bytes(storage_usage['total_bytes'])} total",
                anchor="w",
                justify="left",
            )
            storage_label.grid(row=6, column=0, padx=14, pady=(0, 4), sticky="ew")
            storage_bar = ctk.CTkProgressBar(card, height=10)
            storage_bar.grid(row=7, column=0, padx=14, pady=(0, 14), sticky="ew")
            self.set_storage_bar(storage_bar, storage_usage["used_percent"] / 100.0)

            card.bind("<Button-1>", lambda event, d=device: self.select_device(d))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda event, d=device: self.select_device(d))

    def select_device(self, device):
        self.selected_device = device
        self.file_sort_key = "date"
        self.file_sort_reverse = True
        self.update_file_sort_headers()
        self.source_var.set(device["drive"])
        self.status_label.configure(text=f"Selected: {device['camera_type']}")
        self.refresh_file_preview()
        self.update_storage_display()

        for child in self.device_list.winfo_children():
            if not hasattr(child, "_device"):
                continue
            is_selected = child._device.get("drive") == device.get("drive")
            child.configure(fg_color="#1b3625" if is_selected else "#101812")
            child.configure(border_width=2 if is_selected else 0, border_color="#3fb950")

            if hasattr(child, "_selected_label"):
                if is_selected:
                    child._selected_label.grid()
                else:
                    child._selected_label.grid_remove()

            if hasattr(child, "_dot_canvas"):
                dot = child._dot_canvas
                dot.delete("all")
                if is_selected:
                    dot.create_oval(1, 1, 15, 15, outline="#a8c9ad", width=2, fill="#1b3625")
                    dot.create_oval(4, 4, 12, 12, fill="#3fb950", outline="")
                    dot.create_oval(6, 6, 10, 10, fill="#b7f0bd", outline="")
                else:
                    dot.create_oval(2, 2, 14, 14, fill="#64748b", outline="")

        self.meta_label.configure(text="Transfer speed: --\nETA: --\nFiles: --")

    def on_date_range_changed(self):
        self.refresh_file_preview()
        self.update_storage_display()

    def sort_file_preview(self, sort_key):
        if self.file_sort_key == sort_key:
            self.file_sort_reverse = not self.file_sort_reverse
        else:
            self.file_sort_key = sort_key
            self.file_sort_reverse = False
        self.update_file_sort_headers()
        self.refresh_file_preview()

    def update_file_sort_headers(self):
        for key, button in self.file_sort_buttons.items():
            arrow = "  ↓" if self.file_sort_reverse else "  ↑"
            button.configure(text=f"{button.cget('text').split('  ')[0]}{arrow}" if key == self.file_sort_key else button.cget("text").split("  ")[0])

    def refresh_file_preview(self):
        self.preview_generation += 1
        self.analyze_generation += 1
        generation = self.preview_generation
        self.preview_metadata_labels = {}
        previous_selection = {
            file_path: variable.get()
            for file_path, variable in self.file_selection_vars.items()
        }
        self.file_selection_vars = {}
        self.select_all_var.set(False)
        for child in self.file_preview_list.winfo_children():
            child.destroy()

        source_path = self.source_var.get().strip()
        if not source_path or not os.path.exists(source_path):
            self.file_preview_summary.configure(text="Select a GoPro to preview files")
            ctk.CTkLabel(self.file_preview_list, text="No GoPro source selected", text_color="#cbd5e1").grid(
                row=0, column=0, columnspan=6, padx=12, pady=20, sticky="w"
            )
            return

        start_text = self.start_date_var.get().strip()
        end_text = self.end_date_var.get().strip()
        try:
            start_date = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else None
            end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
        except ValueError:
            self.file_preview_summary.configure(text="Enter valid dates to preview files")
            return

        if start_date and end_date and start_date > end_date:
            self.file_preview_summary.configure(text="The selected date range is reversed")
            return

        files = collect_mp4_files(source_path, start_date, end_date)
        file_rows = [
            (
                file_path,
                datetime.fromtimestamp(file_path.stat().st_ctime).date(),
                file_path.stat().st_size,
            )
            for file_path in files
        ]
        sort_values = {
            "title": lambda row: row[0].name.lower(),
            "date": lambda row: row[1],
            "size": lambda row: row[2],
        }
        file_rows.sort(key=sort_values[self.file_sort_key], reverse=self.file_sort_reverse)
        total_bytes = sum(row[2] for row in file_rows)
        self.file_preview_summary.configure(text=f"{len(files)} files  |  {format_bytes(total_bytes)}")

        if not files:
            ctk.CTkLabel(self.file_preview_list, text="No MP4 files match the selected range", text_color="#cbd5e1").grid(
                row=0, column=0, columnspan=6, padx=12, pady=20, sticky="w"
            )
            return

        uncached_files = []
        for index, (file_path, file_date, file_size) in enumerate(file_rows):
            row = ctk.CTkFrame(self.file_preview_list, corner_radius=3, fg_color="#15231a" if index % 2 == 0 else "transparent")
            row.grid(row=index, column=0, columnspan=6, padx=1, pady=1, sticky="ew")
            for column, weight, minsize in ((0, 0, 28), (1, 0, 112), (2, 2, 105), (3, 0, 92), (4, 0, 52), (5, 0, 92)):
                row.grid_columnconfigure(column, weight=weight, minsize=minsize)
            selection_var = ctk.BooleanVar(value=previous_selection.get(str(file_path), True))
            self.file_selection_vars[str(file_path)] = selection_var
            ctk.CTkCheckBox(
                row,
                text="",
                width=20,
                checkbox_width=15,
                checkbox_height=15,
                variable=selection_var,
                command=self.on_file_selection_changed,
            ).grid(row=0, column=0, padx=5, pady=1)
            cached_metadata = self.video_metadata_cache.get(str(file_path), {"resolution": "...", "fps": "..."})
            if str(file_path) not in self.video_metadata_cache:
                uncached_files.append(file_path)
            values = (file_path.name, file_date.strftime("%Y-%m-%d"), cached_metadata["resolution"], cached_metadata["fps"], format_bytes(file_size))
            metadata_labels = []
            for column, value in enumerate(values):
                anchor = "e" if column == 4 else "center" if column in (1, 2, 3) else "w"
                cell_padx = (2, 4) if column in (2, 3, 4) else (6, 10)
                label = ctk.CTkLabel(row, text=value, anchor=anchor, height=20)
                label.grid(row=0, column=column + 1, padx=cell_padx, pady=1, sticky="ew")
                if column in (2, 3):
                    metadata_labels.append(label)
            self.preview_metadata_labels[str(file_path)] = metadata_labels

        selected_files = self.get_selected_preview_files()
        selected_bytes = self.get_selected_preview_size()
        self.update_select_all_state()
        self.file_preview_summary.configure(text=f"{len(selected_files)} files  |  {format_bytes(selected_bytes)} selected")

        if uncached_files:
            threading.Thread(
                target=self.load_preview_metadata,
                args=(uncached_files, generation),
                daemon=True,
            ).start()

    def get_selected_preview_files(self):
        return [Path(file_path) for file_path, variable in self.file_selection_vars.items() if variable.get()]

    def get_selected_preview_size(self):
        return sum(file_path.stat().st_size for file_path in self.get_selected_preview_files())

    def update_select_all_state(self):
        all_selected = bool(self.file_selection_vars) and all(variable.get() for variable in self.file_selection_vars.values())
        self.select_all_var.set(all_selected)

    def toggle_all_visible_files(self):
        selected = self.select_all_var.get()
        for variable in self.file_selection_vars.values():
            variable.set(selected)
        self.on_file_selection_changed()

    def on_file_selection_changed(self):
        self.update_select_all_state()
        selected_files = self.get_selected_preview_files()
        selected_bytes = self.get_selected_preview_size()
        self.file_preview_summary.configure(text=f"{len(selected_files)} files  |  {format_bytes(selected_bytes)} selected")
        self.update_storage_display()

    def load_preview_metadata(self, file_paths, generation):
        metadata_updates = {}
        for file_path in file_paths:
            metadata = get_video_metadata(file_path)
            self.video_metadata_cache[str(file_path)] = metadata
            metadata_updates[str(file_path)] = metadata
        self.after(0, lambda: self.apply_preview_metadata(metadata_updates, generation))

    def apply_preview_metadata(self, metadata_updates, generation):
        if generation != self.preview_generation:
            return
        for file_path, metadata in metadata_updates.items():
            labels = self.preview_metadata_labels.get(file_path)
            if labels:
                labels[0].configure(text=metadata["resolution"])
                labels[1].configure(text=metadata["fps"])

    def copy_device_details(self, device):
        payload = [
            f"Serial: {device.get('serial_number') or 'Unknown'}",
            f"Firmware: {device.get('firmware_version') or 'Unknown'}",
            f"MCU: {device.get('mcu_version') or 'Unknown'}",
            f"Wi‑Fi MAC: {device.get('wifi_mac') or 'Unknown'}",
        ]
        details = "\n".join(payload)
        self.clipboard_clear()
        self.clipboard_append(details)
        self.update()
        self.status_label.configure(text=f"Copied {device.get('camera_type') or 'GoPro'} details")

    def choose_source(self):
        if self.selected_device:
            self.source_var.set(self.selected_device["drive"])
        else:
            self.source_var.set("")
        self.update_storage_display()

    def choose_destination(self):
        from tkinter import filedialog

        folder = filedialog.askdirectory(title="Choose destination folder")
        if folder:
            self.destination_var.set(folder)
            self.update_storage_display()

    def update_storage_display(self):
        source_path = self.source_var.get().strip()
        source_usage = get_storage_usage(source_path)
        if source_path and os.path.exists(source_path):
            source_available = source_usage["total_bytes"]
        else:
            self.source_storage_label.configure(text="Size of Selected Files: no source selected")
            self.set_storage_bar(self.source_storage_bar, 0)
            source_available = 0

        destination_path = self.destination_var.get().strip()
        destination_usage = get_storage_usage(destination_path)
        if destination_path and os.path.exists(destination_path):
            self.destination_storage_label.configure(
                text=f"Destination storage: {format_bytes(destination_usage['free_bytes'])} free / {format_bytes(destination_usage['total_bytes'])} total"
            )
        else:
            self.destination_storage_label.configure(text="Destination storage: no destination selected")
        self.destination_storage_projection = (
            destination_usage["used_bytes"],
            destination_usage["total_bytes"],
            0.0,
        )
        self.draw_destination_projection()

        if not source_path or not os.path.exists(source_path):
            return

        start_text = self.start_date_var.get().strip()
        end_text = self.end_date_var.get().strip()
        try:
            start_date = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else None
            end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
        except ValueError:
            self.source_storage_label.configure(text="Size of Selected Files: enter valid dates")
            self.set_storage_bar(self.source_storage_bar, 0)
            return

        if start_date and end_date and start_date > end_date:
            self.source_storage_label.configure(text="Size of Selected Files: date range is reversed")
            self.set_storage_bar(self.source_storage_bar, 0)
            return

        selected_files = self.get_selected_preview_files()
        selected_bytes = self.get_selected_preview_size()
        self.source_storage_label.configure(text=f"Size of Selected Files: {format_bytes(selected_bytes)}")
        self.set_storage_bar(self.source_storage_bar, selected_bytes / source_available if source_available else 0)
        self.destination_storage_projection = (
            destination_usage["used_bytes"],
            destination_usage["total_bytes"],
            selected_bytes,
        )
        self.draw_destination_projection()

    def set_storage_bar(self, progress_bar, value):
        normalized_value = min(1.0, max(0.0, value))
        progress_bar.set(normalized_value)
        progress_bar.configure(progress_color="#c94b4b" if normalized_value > 0.8 else "#238636")

    def draw_destination_projection(self):
        canvas = self.destination_storage_bar
        canvas.delete("all")
        used_bytes, total_bytes, selected_bytes = self.destination_storage_projection
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 16)
        bar_top = 1
        bar_bottom = height - 1
        radius = min(6, (bar_bottom - bar_top) // 2)
        self.draw_rounded_bar_segment(canvas, 0, width, bar_top, bar_bottom, radius, "#4a4d50")
        if total_bytes <= 0:
            self.destination_storage_warning.grid_remove()
            self.update_copy_button_state()
            return

        used_ratio = min(1.0, max(0.0, used_bytes / total_bytes))
        projected_ratio = (used_bytes + selected_bytes) / total_bytes
        used_width = width * used_ratio
        projected_width = min(width, max(used_width, width * projected_ratio))

        overflow = projected_ratio > 1.0
        projection_color = "#c94b4b" if overflow else "#3fb950"
        self.draw_rounded_bar_segment(canvas, 0, projected_width, bar_top, bar_bottom, radius, projection_color)
        self.draw_rounded_bar_segment(canvas, 0, used_width, bar_top, bar_bottom, radius, "#238636")
        hatch_inset = 2
        hatch_top = bar_top + hatch_inset
        hatch_bottom = bar_bottom - hatch_inset
        hatch_height = max(hatch_bottom - hatch_top, 1)
        for start_x in range(int(used_width) - hatch_height, int(projected_width) + hatch_height, 8):
            line_start = max(0.0, (used_width - start_x) / hatch_height)
            line_end = min(1.0, (projected_width - start_x) / hatch_height)
            if line_start < line_end:
                self.destination_storage_bar.create_line(
                    start_x + line_start * hatch_height,
                    hatch_bottom - line_start * hatch_height,
                    start_x + line_end * hatch_height,
                    hatch_bottom - line_end * hatch_height,
                    fill="#d8f3dc" if not overflow else "#ffd0d0",
                    width=1,
                )

        if overflow:
            self.destination_storage_warning.grid()
        else:
            self.destination_storage_warning.grid_remove()
        self.update_copy_button_state()

    def update_copy_button_state(self):
        if not hasattr(self, "copy_button"):
            return
        transferring = bool(self.transfer_thread and self.transfer_thread.is_alive())
        analyzing = self.analyzing
        if hasattr(self, "analyze_button"):
            self.analyze_button.configure(state="disabled" if transferring or analyzing else "normal")
        if transferring or analyzing:
            self.copy_button.configure(state="disabled")
            return
        used_bytes, total_bytes, selected_bytes = self.destination_storage_projection
        overflow = total_bytes > 0 and used_bytes + selected_bytes > total_bytes
        self.copy_button.configure(state="disabled" if overflow else "normal")

    def draw_rounded_bar_segment(self, canvas, left, right, top, bottom, radius, color):
        if right <= left:
            return
        if right - left <= radius * 2:
            canvas.create_rectangle(left, top, right, bottom, fill=color, outline="")
            return
        canvas.create_rectangle(left + radius, top, right - radius, bottom, fill=color, outline="")
        canvas.create_rectangle(left, top + radius, right, bottom - radius, fill=color, outline="")
        canvas.create_arc(left, top, left + radius * 2, bottom, start=90, extent=180, fill=color, outline="")
        canvas.create_arc(right - radius * 2, top, right, bottom, start=-90, extent=180, fill=color, outline="")

    def save_favorite_destination(self):
        if not self.destination_var.get():
            return
        if self.destination_var.get() not in self.favorites:
            self.favorites.append(self.destination_var.get())
        self.refresh_favorites()
        self.update_storage_display()

    def refresh_favorites(self):
        options = self.favorites[:]
        if not options:
            self.favorite_menu.configure(values=["Favourite Destination Paths"])
            self.favorite_menu.set("Favourite Destination Paths")
            return

        self.favorite_menu.configure(values=options)
        if self.destination_var.get() in options:
            self.favorite_menu.set(self.destination_var.get())
        else:
            self.favorite_menu.set(options[0])

    def select_favorite_destination(self, value):
        if value == "Favourite Destination Paths":
            return
        self.destination_var.set(value)
        self.update_storage_display()

    def remove_favorite_destination(self):
        current_value = self.favorite_menu.get()
        if current_value in self.favorites:
            self.favorites.remove(current_value)
            self.destination_var.set("")
            self.refresh_favorites()
            self.update_storage_display()

    def get_selected_date_range(self) -> tuple[date | None, date | None] | None:
        start_text = self.start_date_var.get().strip()
        end_text = self.end_date_var.get().strip()
        try:
            start_date = datetime.strptime(start_text, "%Y-%m-%d").date() if start_text else None
            end_date = datetime.strptime(end_text, "%Y-%m-%d").date() if end_text else None
        except ValueError:
            self.status_label.configure(text="Dates must use YYYY-MM-DD format.")
            return None

        if start_date and end_date and start_date > end_date:
            self.status_label.configure(text="The start date must be before the end date.")
            return None
        return start_date, end_date

    def open_date_picker(self, target_var: ctk.StringVar, title: str):
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("330x330")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        initial_date = date.today()
        current_value = target_var.get().strip()
        if current_value:
            try:
                initial_date = datetime.strptime(current_value, "%Y-%m-%d").date()
            except ValueError:
                pass

        calendar = Calendar(
            popup,
            selectmode="day",
            year=initial_date.year,
            month=initial_date.month,
            day=initial_date.day,
            date_pattern="yyyy-mm-dd",
        )
        calendar.pack(padx=14, pady=(14, 8), fill="both", expand=True)

        def apply_date():
            target_var.set(calendar.get_date())
            popup.grab_release()
            popup.destroy()

        ctk.CTkButton(popup, text="Use selected date", command=apply_date).pack(padx=14, pady=(0, 14), fill="x")

    def get_preview_files(self):
        return [Path(file_path) for file_path in self.file_selection_vars]

    def start_analyze(self):
        destination = self.destination_var.get().strip()
        if not destination or not os.path.exists(destination):
            self.status_label.configure(text="Choose a destination archive to analyze.")
            return
        if self.transfer_thread and self.transfer_thread.is_alive():
            return
        files = self.get_preview_files()
        if not files:
            self.status_label.configure(text="No files to analyze. Select a GoPro first.")
            return

        self.analyze_generation += 1
        generation = self.analyze_generation
        self.analyzing = True
        self.update_copy_button_state()
        self.status_label.configure(text="Analyzing archive...")
        self.meta_label.configure(text="Checking which files are already in the destination...")

        def worker():
            try:
                results = analyze_archive_status(destination, files)
            except OSError:
                results = None
            self.after(0, lambda: self.apply_analyze_results(results, generation))

        threading.Thread(target=worker, daemon=True).start()

    def apply_analyze_results(self, results, generation):
        self.analyzing = False
        self.update_copy_button_state()
        if generation != self.analyze_generation:
            return
        if results is None:
            self.status_label.configure(text="Analyze failed. Check the destination folder.")
            return

        missing_paths = {str(file_path) for file_path, _target, action in results if action != "skip"}
        archived_count = sum(1 for _file_path, _target, action in results if action == "skip")
        for file_path, variable in self.file_selection_vars.items():
            variable.set(file_path in missing_paths)
        self.on_file_selection_changed()
        missing_count = len(missing_paths)
        self.status_label.configure(
            text=f"Analyze complete: {archived_count} already archived, {missing_count} not present"
        )
        self.meta_label.configure(
            text=(
                f"Checked files now include only clips missing from the archive.\n"
                f"Already archived: {archived_count}  |  Need copy: {missing_count}"
            )
        )

    def start_copy(self):
        source = self.source_var.get().strip()
        destination = self.destination_var.get().strip()
        if not source or not destination:
            self.status_label.configure(text="Select both a GoPro source and a destination.")
            return
        used_bytes, total_bytes, selected_bytes = self.destination_storage_projection
        if total_bytes > 0 and used_bytes + selected_bytes > total_bytes:
            self.status_label.configure(text="Not enough storage space for the selected files.")
            self.update_copy_button_state()
            return
        date_range = self.get_selected_date_range()
        if date_range is None:
            return
        start_date, end_date = date_range
        selected_files = self.get_selected_preview_files()
        if not selected_files:
            self.status_label.configure(text="Select at least one file to copy.")
            return

        self.copy_button.configure(state="disabled")
        if hasattr(self, "analyze_button"):
            self.analyze_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.set(0)
        self.status_label.configure(text="Copying MP4 files...")
        self.meta_label.configure(text="Preparing transfer...")
        self.eta_display_value = 0
        self.last_eta_display_update = 0.0
        self.transfer_finished_received = False

        self.transfer_thread = TransferThread(
            source,
            destination,
            self.queue_transfer_update,
            start_date=start_date,
            end_date=end_date,
            selected_files=selected_files,
        )
        self.transfer_thread.start()
        self.transfer_update_poll = self.after(50, self.process_transfer_updates)

    def cancel_copy(self):
        if self.transfer_thread and self.transfer_thread.is_alive():
            self.transfer_thread.stop()
            self.cancel_button.configure(state="disabled")
            self.status_label.configure(text="Stopping safely...")
            self.meta_label.configure(text="Finishing the current chunk and removing any partial file...")

    def queue_transfer_update(self, payload):
        self.transfer_updates.put(payload)

    def process_transfer_updates(self):
        latest_payload = None
        while True:
            try:
                latest_payload = self.transfer_updates.get_nowait()
            except queue.Empty:
                break

        if latest_payload is not None:
            self.update_transfer_progress(latest_payload)

        if (
            self.transfer_thread
            and self.transfer_thread.is_alive()
            or not self.transfer_finished_received
            or not self.transfer_updates.empty()
        ):
            self.transfer_update_poll = self.after(50, self.process_transfer_updates)
        else:
            self.transfer_update_poll = None
            self.update_copy_button_state()

    def update_transfer_progress(self, payload):
        if payload.get("finished"):
            self.transfer_finished_received = True
            self.copy_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            if payload.get("cancelled"):
                self.status_label.configure(text="Copy canceled safely")
                self.meta_label.configure(
                    text=(
                        f"Copied: {payload['files_copied']}  |  Skipped: {payload['files_skipped']}  |  "
                        f"Renamed: {payload['files_renamed']}\n"
                        f"Transferred: {format_bytes(payload['copied_bytes'])}"
                    )
                )
                return
            self.progress.set(1.0)
            self.status_label.configure(text="Copy complete")
            self.meta_label.configure(
                text=(
                    f"Copied: {payload['files_copied']}  |  Skipped: {payload['files_skipped']}  |  "
                    f"Renamed: {payload['files_renamed']}\n"
                    f"Transferred: {format_bytes(payload['copied_bytes'])}"
                )
            )
            self.show_success_dialog(payload)
            return

        completed = payload.get("completed", 0.0)
        current_speed = payload.get("current_speed", 0.0)
        eta_seconds = payload.get("eta_seconds", 0)
        files_processed = payload.get("files_processed", 0)
        total_files = payload.get("total_files", 0)
        current_file = payload.get("current_file")
        destination_path = payload.get("destination_path")
        current_action = payload.get("current_action")
        current_file_index = payload.get("current_file_index") or min(files_processed + 1, total_files)

        self.progress.set(completed)
        if current_file and destination_path:
            action_label = "Skipping" if current_action == "skip" else "Copying"
            self.status_label.configure(
                text=f"{action_label} {current_file} ({current_file_index}/{total_files})\nto {destination_path}"
            )
        else:
            self.status_label.configure(text=f"Processing {files_processed}/{total_files} files")
        now = time.monotonic()
        if now - self.last_eta_display_update >= 0.1:
            self.eta_display_value = eta_seconds
            self.last_eta_display_update = now
        self.meta_label.configure(
            text=(
                f"Transfer speed: {format_speed(current_speed)}\n"
                f"ETA: {format_duration(self.eta_display_value)}\n"
                f"Files processed: {files_processed}/{total_files}"
            )
        )
        self._draw_speed_graph(payload.get("speed_history", []))

    def _draw_speed_graph(self, history):
        self.graph_canvas.delete("all")
        width = max(self.graph_canvas.winfo_width(), 320)
        height = max(self.graph_canvas.winfo_height(), 100)
        left_pad = 34
        right_pad = 10
        top_pad = 10
        bottom_pad = 24

        x_axis_y = height - bottom_pad
        y_axis_x = left_pad
        self.graph_canvas.create_line(y_axis_x, top_pad, y_axis_x, x_axis_y, fill="#94a3b8", width=1)
        self.graph_canvas.create_line(y_axis_x, x_axis_y, width - right_pad, x_axis_y, fill="#94a3b8", width=1)
        self.graph_canvas.create_text(
            10,
            (top_pad + x_axis_y) / 2,
            text="Speed (MB/s)",
            fill="#94a3b8",
            angle=90,
            anchor="center",
        )
        self.graph_canvas.create_text(width - right_pad, height - 4, text="Time", fill="#94a3b8", anchor="se")

        for x in range(y_axis_x + 12, width - right_pad, 14):
            self.graph_canvas.create_line(x, top_pad, x, x_axis_y, fill="#2d3748", width=1)

        if not history:
            return

        max_speed = max(history) if max(history) > 0 else 1

        point_count = min(len(history), max(1, width - left_pad - right_pad))
        bucket_size = max(1, (len(history) + point_count - 1) // point_count)
        sampled_history = [
            max(history[index:index + bucket_size])
            for index in range(0, len(history), bucket_size)
        ]
        points = []
        for idx, speed in enumerate(sampled_history):
            x = y_axis_x + (idx / max(1, len(sampled_history) - 1)) * (width - right_pad - y_axis_x)
            y = x_axis_y - (speed / max_speed) * (x_axis_y - top_pad)
            points.append((x, y))

        if len(points) > 1:
            for i in range(1, len(points)):
                self.graph_canvas.create_line(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1], fill="#3fb950", width=2)

    def show_success_dialog(self, payload):
        from tkinter import messagebox

        messagebox.showinfo(
            "Copy complete",
            (
                "Archive update complete.\n\n"
                f"Copied: {payload['files_copied']}\n"
                f"Skipped (already identical): {payload['files_skipped']}\n"
                f"Conflict-renamed: {payload['files_renamed']}"
            ),
        )


def format_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"


def format_speed(value: float) -> str:
    return f"{value / (1024 * 1024):.2f} MB/s" if value > 0 else "--"


def format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def main():
    app = GoProArchiverApp()
    app.mainloop()


if __name__ == "__main__":
    main()
