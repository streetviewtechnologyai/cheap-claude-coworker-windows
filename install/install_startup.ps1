# Add Token Monitor to the Windows Startup folder so it launches at sign-in.
# Run from this folder:
#   powershell -ExecutionPolicy Bypass -File .\install\install_startup.ps1

$ErrorActionPreference = "Stop"

$RepoRoot   = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvDir    = Join-Path $env:LOCALAPPDATA "claude-coworker\venv"
$VenvPyW    = Join-Path $VenvDir "Scripts\pythonw.exe"
$StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$LinkPath   = Join-Path $StartupDir "TokenMonitor.lnk"

if (-not (Test-Path $VenvPyW)) {
    throw "Coworker venv not found at $VenvDir. Run setup.ps1 first."
}
if (-not (Test-Path $StartupDir)) {
    New-Item -ItemType Directory -Path $StartupDir | Out-Null
}

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($LinkPath)
$shortcut.TargetPath       = $VenvPyW
$shortcut.Arguments        = "-m monitor"
$shortcut.WorkingDirectory = $RepoRoot
$shortcut.WindowStyle      = 7   # minimized
$shortcut.Description      = "Token Monitor (Claude Code + Coworker)"
$shortcut.Save()

Write-Host "Installed startup shortcut: $LinkPath"
Write-Host "It will launch on next sign-in. To start now, run:"
Write-Host "  & '$VenvPyW' -m monitor"
