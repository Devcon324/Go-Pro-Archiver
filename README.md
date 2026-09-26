# GoPro Footage Archiver

**Plug in your GoPro. Pick your archive. Copy only what’s missing.**

A fast, friendly desktop app for **Windows and Linux** that pulls `.MP4` clips off your GoPro SD card, sorts them by date, and skips footage you’ve already archived — without re-reading gigabytes of video every time.

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

## Download

No Python required. Open **[Releases](https://github.com/devcon324/gopro-footage-archiver/releases)** and pick your platform. Each release ships **two programs** (app + uninstall).

### Windows

Download **`GoPro-Footage-Archiver-x.x.x-windows-x64.zip`**.

| File | What it does |
|------|----------------|
| **`GoPro-Footage-Archiver.exe`** | The app |
| **`Uninstall.exe`** | Removes saved favourites/settings |

Extract both to a folder and run **`GoPro-Footage-Archiver.exe`**.

Windows may show SmartScreen the first time — choose **More info → Run anyway** if you trust the release.

Settings: `%APPDATA%\GoProFootageArchiver`

### Linux

Download **`GoPro-Footage-Archiver-x.x.x-linux-x64.tar.gz`**.

```bash
tar xzf GoPro-Footage-Archiver-x.x.x-linux-x64.tar.gz
chmod +x GoPro-Footage-Archiver Uninstall
./GoPro-Footage-Archiver
```

| File | What it does |
|------|----------------|
| **`GoPro-Footage-Archiver`** | The app |
| **`Uninstall`** | Removes saved favourites/settings |

You may need desktop libraries for Tk (Ubuntu/Debian example):

```bash
sudo apt install libgl1 libglib2.0-0 libxrender1 libxext6
```

Settings: `~/.config/GoProFootageArchiver/`

### Uninstall (both platforms)

1. Run **`Uninstall`** / **`Uninstall.exe`** next to the app.
2. Delete the app files when you are done.

Your archived MP4 folders are never deleted by the uninstaller.

---

## Build from source (developers)

Run from source on **Windows or Linux** with Python 3.13+. Release binaries are built on GitHub Actions for both platforms.

### 1. Prerequisites

| Tool | Notes |
|------|--------|
| **Windows 10/11** or **Linux** | Match the OS you want to build a release for |
| **Python 3.13+** | Matches `.python-version` in the repo |
| **[uv](https://docs.astral.sh/uv/getting-started/installation/)** | Installs Python and dependencies |

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) for your OS, then verify:

```bash
uv --version
```

**Linux — Tk / GUI libraries** (required to run or build the UI):

```bash
sudo apt install python3-tk tk-dev libgl1 libglib2.0-0 libxrender1 libxext6
```

### 2. Clone the repository

```bash
git clone https://github.com/devcon324/gopro-footage-archiver.git
cd gopro-footage-archiver
```

### 3. Install dependencies

Runtime + dev tools (pytest, PyInstaller):

```bash
uv sync --group dev
```

`uv` creates a virtual environment in `.venv` and installs everything from `pyproject.toml` / `uv.lock`.

### 4. Run the app (without building an `.exe`)

```bash
uv run gopro-archiver
```

Or:

```bash
uv run python -m gopro_archiver
```

### 5. Run tests

```bash
uv run pytest
```

All tests are headless (no GUI window required).

### 6. Build release binaries

Build on the **same OS** you are targeting (Windows → `.exe`, Linux → standalone binaries).

**Linux:**

```bash
./scripts/build_linux.sh
```

Output: `dist/GoPro-Footage-Archiver` and `dist/Uninstall`

**Windows:**

**Git Bash / WSL / any shell:**

```bash
./scripts/build_windows.sh
```

**PowerShell:**

```powershell
.\scripts\build_windows.ps1
```

Both scripts do the same thing. There are two only because Windows developers often use either shell; pick whichever you use day to day.

That script:

1. Runs `uv sync --group dev`
2. Builds `GoPro-Footage-Archiver.exe` via `packaging/gopro_archiver.spec`
3. Builds `Uninstall.exe` via `packaging/uninstall.spec`

**Output** (same folder):

```
dist/
├── GoPro-Footage-Archiver.exe
└── Uninstall.exe
```

**Manual build** (equivalent to the script):

```powershell
uv sync --group dev
uv run pyinstaller packaging/gopro_archiver.spec --noconfirm --clean
uv run pyinstaller packaging/uninstall.spec --noconfirm
```

Test the build locally: run both EXEs from `dist\`. The first launch of the main app may take a few seconds while Windows extracts the bundled runtime.

**Optional — ZIP like GitHub Releases:**

```powershell
$version = "0.1.0"   # match pyproject.toml
Compress-Archive -Path dist/GoPro-Footage-Archiver.exe, dist/Uninstall.exe `
  -DestinationPath "dist/GoPro-Footage-Archiver-${version}-windows-x64.zip" -Force
```

### 7. Publish a GitHub Release (CI)

Releases are built automatically when you push a **version tag**. Workflow: [`.github/workflows/release.yml`](.github/workflows/release.yml).

1. **Bump the version** in `pyproject.toml` (`[project] version = "0.1.0"`).
2. **Commit** your changes on `master` (or your default branch).
3. **Create and push a tag** (must start with `v`, tag name without `v` becomes the ZIP version):

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. Open **Actions** on GitHub and wait for the **Release** workflow to finish.
5. Open **Releases** — the workflow uploads the Windows ZIP and Linux `.tar.gz`.

If the workflow fails, check the PyInstaller step logs on the `windows-latest` runner.

### Build troubleshooting

- **`uv` not found** — install uv (step 1) and reopen the terminal.
- **PyInstaller errors** — run `uv sync --group dev` again; delete `build/` and `dist/`, then rebuild.
- **SmartScreen on your own build** — expected without a code-signing certificate; same as end-user downloads.

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
│   ├── app_paths.py         # AppData paths (favourites file)
│   ├── settings.py          # Load/save favourites
│   ├── devices.py           # GoPro detection & mount points (incl. /media on Linux)
│   ├── files.py             # Cross-platform clip date for archive paths
│   ├── archive.py           # Paths, dedup, analyze, file collection
│   ├── transfer.py          # Background copy thread & progress
│   ├── metadata.py          # Video probe (PyAV) & disk usage
│   ├── formatters.py        # Human-readable sizes, speed, ETA
│   └── ui/
│       └── app.py           # CustomTkinter desktop UI
├── packaging/
│   ├── gopro_archiver.spec  # PyInstaller spec — main app
│   ├── uninstall.spec       # PyInstaller spec — Uninstall.exe
│   └── uninstall_entry.py   # Standalone uninstall script
├── scripts/
│   ├── build_linux.sh       # Linux release build
│   ├── build_windows.sh     # Windows release build (bash)
│   └── build_windows.ps1    # Windows release build (PowerShell)
├── .github/workflows/
│   └── release.yml          # Tag → build ZIP → GitHub Release
├── tests/
├── pyproject.toml
└── README.md
```

Core logic lives outside the UI so behaviour stays testable and easy to extend.

---

## Archive layout

Each clip lands under the date taken (creation time on Windows; modification time on Linux when birth time is unavailable):

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
