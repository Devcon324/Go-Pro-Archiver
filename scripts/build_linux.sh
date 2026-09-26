#!/usr/bin/env bash
# Build release binaries for Linux: dist/GoPro-Footage-Archiver and dist/Uninstall
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Installing dependencies (including PyInstaller)..."
uv sync --group dev

echo "Building GoPro-Footage-Archiver..."
uv run pyinstaller packaging/gopro_archiver_linux.spec --noconfirm --clean

echo "Building Uninstall..."
uv run pyinstaller packaging/uninstall.spec --noconfirm

app_bin="dist/GoPro-Footage-Archiver"
uninstall_bin="dist/Uninstall"

if [[ ! -f "$app_bin" ]]; then
  echo "Build failed: $app_bin not found" >&2
  exit 1
fi
if [[ ! -f "$uninstall_bin" ]]; then
  echo "Build failed: $uninstall_bin not found" >&2
  exit 1
fi

chmod +x "$app_bin" "$uninstall_bin"

echo ""
echo "Release files ready in dist/:"
echo "  GoPro-Footage-Archiver"
echo "  Uninstall"
