# Build release EXEs: dist/GoPro-Footage-Archiver.exe and dist/Uninstall.exe
# Requires: uv, Python 3.13+, run from repo root.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Installing dependencies (including PyInstaller)..."
uv sync --group dev

Write-Host "Building GoPro-Footage-Archiver.exe..."
uv run pyinstaller packaging/gopro_archiver.spec --noconfirm --clean

Write-Host "Building Uninstall.exe..."
uv run pyinstaller packaging/uninstall.spec --noconfirm

$appExe = "dist\GoPro-Footage-Archiver.exe"
$uninstallExe = "dist\Uninstall.exe"

if (-not (Test-Path $appExe)) {
    throw "Build failed: $appExe not found"
}
if (-not (Test-Path $uninstallExe)) {
    throw "Build failed: $uninstallExe not found"
}

Write-Host ""
Write-Host "Release files ready in dist\:"
Write-Host "  GoPro-Footage-Archiver.exe"
Write-Host "  Uninstall.exe"
