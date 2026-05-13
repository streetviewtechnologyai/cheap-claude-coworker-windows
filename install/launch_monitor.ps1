# Wrapper used by the TokenMonitor scheduled task. Launches the monitor and
# captures its stderr to a log file so silent failures at sign-in stay
# debuggable.
#
# Logs:
#   %LOCALAPPDATA%\claude-coworker\monitor.log        — wrapper diagnostics
#   %LOCALAPPDATA%\claude-coworker\monitor.stderr.log — Python tracebacks
#
# We use python.exe (not pythonw) + cmd /c start /b with file redirection,
# because the redirected file handles survive cmd's exit. A pipe owned by
# Start-Process would close when this wrapper exits and kill python on its
# next stderr write. cmd /c start /b also hides the console window cleanly.

$ErrorActionPreference = "Stop"

$VenvPy   = Join-Path $env:LOCALAPPDATA "claude-coworker\venv\Scripts\python.exe"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir   = Join-Path $env:LOCALAPPDATA "claude-coworker"
$LogFile  = Join-Path $LogDir "monitor.log"
$ErrLog   = Join-Path $LogDir "monitor.stderr.log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Log($msg) {
    "$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))  $msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

Log "==== launch ===="
Log "user=$env:USERNAME"
Log "python exists=$(Test-Path $VenvPy)"
Log "repo   exists=$(Test-Path $RepoRoot)"

try {
    Remove-Item $ErrLog -ErrorAction SilentlyContinue
    $cmdLine = "start /b """" """ + $VenvPy + """ -m monitor > """ + $ErrLog + """ 2>&1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c",$cmdLine -WorkingDirectory $RepoRoot -WindowStyle Hidden
    Start-Sleep 5
    $py = Get-Process python -ErrorAction SilentlyContinue
    if ($py) {
        Log "python alive after 5s: pid=$($py.Id -join ',')"
    } else {
        Log "python DEAD after 5s -- see monitor.stderr.log for traceback"
    }
    exit 0
} catch {
    Log "FAILED: $($_.Exception.Message)"
    exit 1
}
