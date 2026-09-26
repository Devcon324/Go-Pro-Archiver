# Build after dist/GoPro-Footage-Archiver exists:
# uv run pyinstaller packaging/install.spec --noconfirm --clean

from pathlib import Path

packaging_dir = Path(SPECPATH).resolve()
project_root = packaging_dir.parent
app_source = project_root / "dist" / "GoPro-Footage-Archiver"

if not (app_source / "GoPro-Footage-Archiver.exe").exists():
    raise SystemExit("Run scripts/build_windows.ps1 -SkipInstaller first.")

a = Analysis(
    [str(packaging_dir / "install_launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(app_source), "app")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="GoPro-Footage-Archiver-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
