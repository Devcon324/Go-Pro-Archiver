# GoPro Footage Archiver

**Plug in your GoPro. Pick your archive. Copy only what’s missing.**

A fast, friendly desktop app for Windows (and other platforms with Python) that pulls `.MP4` clips off your GoPro SD card, sorts them by date, and skips footage you’ve already archived — without re-reading gigabytes of video every time.

<p align="center">
  <img src="https://github.com/user-attachments/assets/3da7915c-fd01-46ee-82f0-fecf54948fea" alt="GoPro Footage Archiver screenshot" width="900" />
</p>

---

## Why this exists

GoPro cards fill up fast. Copying everything by hand is slow, and re-copying the same clips wastes hours. This tool:

- **Detects** connected GoPro drives automatically (`MISC/version.txt` + `DCIM/100GOPRO`)
- **Previews** every clip with resolution, FPS, size, and date
- **Archives** to `Year/YYYY-MM-DD/filename.MP4`
- **Skips duplicates** using size + quick head/tail checks (not full-file hashing)
- **Analyzes** the destination and auto-unchecks clips already in your library
- **Shows live progress** — current file, destination path, speed, ETA, and a speed graph

---

## Quick start

### Requirements

- **Python 3.13+**
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install & run

```bash
git clone https://github.com/YOUR_USERNAME/gopro-footage-archiver.git
cd gopro-footage-archiver
uv sync
uv run gopro-archiver
```

Or without installing the console script:

```bash
uv run python -m gopro_archiver
```

### Development

```bash
uv sync --group dev
uv run pytest
```

---

## How to use

1. **Connect** your GoPro (USB / card reader) and select the device in the left panel.
2. **Choose** a destination archive folder (save favourites for next time).
3. Optional: filter by **date range**, sort the file list, and uncheck clips you don’t want.
4. Click **Analyze** to compare against the archive — already-archived files are unchecked automatically.
5. Click **Copy MP4 files** and watch progress; cancel safely if needed.

---

## Project layout

```
gopro-footage-archiver/
├── gopro_archiver/          # Application package
│   ├── __main__.py          # Entry point: python -m gopro_archiver
│   ├── devices.py           # GoPro detection & version.txt parsing
│   ├── archive.py           # Paths, dedup, analyze, file collection
│   ├── transfer.py          # Background copy thread & progress
│   ├── metadata.py          # Video probe (PyAV) & disk usage
│   ├── formatters.py        # Human-readable sizes, speed, ETA
│   └── ui/
│       └── app.py           # CustomTkinter desktop UI
├── tests/
│   └── test_archiver.py     # Core logic tests (no GUI required)
├── pyproject.toml
└── README.md
```

Core logic lives outside the UI so behaviour stays testable and easy to extend.

---

## Archive layout

Each clip lands under the date taken (from file creation time):

```
YourArchive/
└── 2026/
    └── 2026-09-22/
        ├── GX010034.MP4
        └── GX010035.MP4
```

If the same filename exists with **different** content, the new file is saved as `GX010034_1.MP4`, and so on. Identical files are **skipped**.

---

## Tech stack

| Piece | Role |
|--------|------|
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | Modern dark UI |
| [PyAV](https://pyav.org/) | Resolution & FPS without ffprobe |
| [psutil](https://github.com/giampaolo/psutil) | Drive detection & storage stats |
| [tkcalendar](https://github.com/j4321/tkcalendar) | Date range picker |

---

## License

MIT — use it, fork it, improve it. Pull requests welcome.

---

<p align="center">
  <sub>Built for creators who’d rather be editing than babysitting file copies.</sub>
</p>
