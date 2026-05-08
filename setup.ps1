# Claude Coworker Model - Windows 11 setup
# Creates a venv, installs deps, and drops .cmd shims that invoke the venv Python.
#
# Run from this folder:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "claude-coworker"
$BinDir     = Join-Path $env:USERPROFILE ".local\bin"
$VenvDir    = Join-Path $InstallDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "=== Claude Coworker Model - Windows Setup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Locate Python
Write-Host "[1/5] Locating Python..."
$python = $null
foreach ($cand in @("py -3", "python", "python3")) {
    try {
        $parts = $cand.Split(" ")
        $exe = $parts[0]
        if ($parts.Length -gt 1) {
            $rest = $parts[1..($parts.Length - 1)]
        } else {
            $rest = @()
        }
        $ver = & $exe @rest --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $python = $cand
            Write-Host ("      found: " + $cand + " (" + $ver + ")")
            break
        }
    } catch { }
}
if (-not $python) {
    throw "No Python interpreter found. Install Python 3.10+ from https://python.org and re-run."
}

# 2. Create venv
Write-Host ("[2/5] Creating venv at " + $VenvDir + " ...")
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir | Out-Null }
if (-not (Test-Path $VenvPython)) {
    $pyParts = $python.Split(" ")
    & $pyParts[0] $pyParts[1..($pyParts.Length - 1)] -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
} else {
    Write-Host "      venv already exists, reusing."
}

# 3. Install deps
Write-Host "[3/5] Installing dependencies..."
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $ScriptDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
$monitorReq = Join-Path $ScriptDir "requirements-monitor.txt"
if (Test-Path $monitorReq) {
    Write-Host "      installing token-monitor deps (PySide6, requests)..."
    & $VenvPython -m pip install --quiet -r $monitorReq
    if ($LASTEXITCODE -ne 0) { throw "monitor pip install failed" }
}

# 4. Create .cmd shims
Write-Host ("[4/5] Installing .cmd shims to " + $BinDir + " ...")
if (-not (Test-Path $BinDir)) { New-Item -ItemType Directory -Path $BinDir | Out-Null }

$tools = @("ask", "write", "extract-chat", "coworker-config")
foreach ($tool in $tools) {
    $toolPath = Join-Path $ScriptDir ("tools\" + $tool)
    if (-not (Test-Path $toolPath)) {
        Write-Warning ("  skipping " + $tool + " - not found at " + $toolPath)
        continue
    }
    $shim = Join-Path $BinDir ($tool + ".cmd")
    $body = "@echo off`r`n`"" + $VenvPython + "`" `"" + $toolPath + "`" %*`r`n"
    Set-Content -Path $shim -Value $body -Encoding ASCII -NoNewline
    Write-Host ("      installed " + $tool + ".cmd")
}

# 4b. token-monitor shim (launches the tray app from the venv)
$VenvPyW = Join-Path $VenvDir "Scripts\pythonw.exe"
$monitorShim = Join-Path $BinDir "token-monitor.cmd"
$monitorBody = "@echo off`r`nstart `"`" `"" + $VenvPyW + "`" -m monitor`r`n"
Set-Content -Path $monitorShim -Value $monitorBody -Encoding ASCII -NoNewline
Write-Host "      installed token-monitor.cmd"

# 5. PATH check
Write-Host "[5/5] Checking PATH..."
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike ("*" + $BinDir + "*")) {
    Write-Host ""
    Write-Host ("  " + $BinDir + " is NOT on your User PATH.") -ForegroundColor Yellow
    if ([string]::IsNullOrEmpty($userPath)) {
        $newPath = $BinDir
    } else {
        $newPath = $userPath + ";" + $BinDir
    }
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "  Added. Open a NEW terminal for the change to take effect." -ForegroundColor Yellow
} else {
    Write-Host ("      " + $BinDir + " already on PATH")
}

Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Set your API key, e.g.:"
Write-Host "       setx DEEPSEEK_API_KEY  sk-..."
Write-Host "       setx MOONSHOT_API_KEY  sk-..."
Write-Host "     (Or keep using WORKER_API_KEY as a generic override.)"
Write-Host "  2. Open a new terminal, then try:"
Write-Host "       coworker-config list"
Write-Host "       coworker-config show"
Write-Host "       ask --paths setup.ps1 --question can-you-summarize"
Write-Host ""
Write-Host "Switch providers with:  coworker-config use deepseek-v4-pro"