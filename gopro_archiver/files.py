from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path


def get_file_capture_date(file_path: str | os.PathLike[str]) -> date:
    """Best-effort clip date for archive folders (creation time on Windows, mtime elsewhere)."""
    stat = Path(file_path).stat()
    if sys.platform == "win32":
        timestamp = stat.st_ctime
    else:
        birthtime = getattr(stat, "st_birthtime", None)
        timestamp = stat.st_mtime if birthtime is None else birthtime
    return datetime.fromtimestamp(timestamp).date()
