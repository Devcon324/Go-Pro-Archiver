#!/usr/bin/env bash
# Build release EXEs: dist/GoPro-Footage-Archiver.exe and dist/Uninstall.exe
# Requires: uv, Python 3.13+, run from repo root (Git Bash, WSL, or Linux cross-build not supported for .exe).

set -euo pipefail
cd "$(dirname "$0")/.."

echo "Installing dependencies (including PyInstaller)..."
uv sync --group dev

echo "Building GoPro-Footage-Archiver.exe..."
uv run pyinstaller packaging/gopro_archiver.spec --noconfirm --clean

echo "Building Uninstall.exe..."
uv run pyinstaller packaging/uninstall.spec --noconfirm

app_exe="dist/GoPro-Footage-Archiver.exe"
uninstall_exe="dist/Uninstall.exe"

if [[ ! -f "$app_exe" ]]; then
  echo "Build failed: $app_exe not found" >&2
  exit 1
fi
if [[ ! -f "$uninstall_exe" ]]; then
  echo "Build failed: $uninstall_exe not found" >&2
  exit 1
fi

echo ""
echo "Release files ready in dist/:"
echo "  GoPro-Footage-Archiver.exe"
echo "  Uninstall.exe"
