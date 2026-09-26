from __future__ import annotations

import os
import shutil

import av


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
