# Register a Task Scheduler entry that launches Token Monitor at user sign-in
# with a 30-second delay (so the shell tray is fully ready before we register
# the icon). More reliable than the Startup folder .lnk on Windows 11.
#
# Run from this folder:
#   powershell -ExecutionPolicy Bypass -File .\install\install_scheduled_task.ps1
#
# Uninstall:
#   Unregister-ScheduledTask -TaskName "TokenMonitor" -Confirm:$false

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPyW  = Join-Path $env:LOCALAPPDATA "claude-coworker\venv\Scripts\pythonw.exe"
$TaskName = "TokenMonitor"

if (-not (Test-Path $VenvPyW)) {
    throw "Coworker venv not found at $VenvPyW. Run setup.ps1 first."
}

# Remove the legacy Startup folder shortcut so the monitor doesn't get
# launched twice (once by the .lnk without delay, once by the task with delay).
$StartupLnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\TokenMonitor.lnk"
if (Test-Path $StartupLnk) {
    Remove-Item $StartupLnk -Force
    Write-Host "Removed legacy startup shortcut: $StartupLnk"
}

# Drop any prior version of the task
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$LauncherPs1 = Join-Path $RepoRoot "install\launch_monitor.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File `"$LauncherPs1`"" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT30S"   # 30s after sign-in — lets the shell tray settle

# Run only when interactive (otherwise QSystemTrayIcon can't attach to a
# session); no idle requirements; runs on battery too.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 2 `
    -RestartInterval ([TimeSpan]::FromMinutes(1))

# Run as the current user, with their normal token (no elevation — tray
# icons from an elevated process won't talk to the unelevated shell).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Launches Token Monitor (Claude Code + Coworker) 30s after sign-in." | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "  Trigger: at logon of $env:USERNAME, delayed 30s"
Write-Host "  Action:  $VenvPyW -m monitor"
Write-Host "  Workdir: $RepoRoot"
Write-Host ""
Write-Host "Test now without rebooting:"
Write-Host "  Start-ScheduledTask -TaskName $TaskName"
Write-Host "Uninstall:"
Write-Host "  Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
