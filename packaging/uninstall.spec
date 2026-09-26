# PyInstaller spec — single-file uninstall helper.
# Build: uv run pyinstaller packaging/uninstall.spec

from pathlib import Path

project_root = Path(SPECPATH).resolve().parent

block_cipher = None

a = Analysis(
    [str(project_root / "packaging" / "uninstall_entry.py")],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["tkinter", "tkinter.messagebox"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Uninstall",
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
    icon=None,
)
