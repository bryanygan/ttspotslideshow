<#
  Registers the ttspotslideshow scheduled tasks on this mini PC.

  Usage:  open an ELEVATED (Run as administrator) PowerShell and run:
            powershell -ExecutionPolicy Bypass -File .\deploy\register_tasks.ps1

  Paths auto-detect from this script's location, so no editing is needed as long
  as the repo lives anywhere and the venv is at <repo>\.venv. Re-running replaces
  tasks of the same name. Review before running.

  Creates:
    ttspot-Slideshow     run_bidaily.py             every 2 days, 9:00 AM
    ttspot-Logger        logger.py                  every 3 hours
    ttspot-GenreRefresh  -m ingest.enrich_cli --refresh   weekly, Sun 4:00 AM
    ttspot-Dashboard     dashboard_server.py        at startup (for remote use)
#>

$ErrorActionPreference = "Stop"

$Repo   = (Resolve-Path "$PSScriptRoot\..").Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "venv python not found at $Python — create the venv first (see deploy\DEPLOY.md)."
}
Write-Host "Repo:   $Repo"
Write-Host "Python: $Python`n"

# Run whether the user is logged on or not, without storing a password (S4U).
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

function Register-Job($Name, $Arguments, $Trigger) {
    $action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $Repo
    if (Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Principal $Principal | Out-Null
    Write-Host "Registered: $Name"
}

# A) Bi-daily slideshow
Register-Job "ttspot-Slideshow" "run_bidaily.py" `
    (New-ScheduledTaskTrigger -Daily -DaysInterval 2 -At 9:00AM)

# B) Spotify logger every 3 hours (so nothing slips past the last-50 buffer)
Register-Job "ttspot-Logger" "logger.py" `
    (New-ScheduledTaskTrigger -Once -At 12:00AM -RepetitionInterval (New-TimeSpan -Hours 3))

# C) Weekly Spotify genre upgrade
Register-Job "ttspot-GenreRefresh" "-m ingest.enrich_cli --refresh" `
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 4:00AM)

# D) Dashboard backend on boot (required for the remote dashboard to reach the PC)
Register-Job "ttspot-Dashboard" "dashboard_server.py" `
    (New-ScheduledTaskTrigger -AtStartup)

Write-Host "`nDone. Manage these in Task Scheduler (names start with 'ttspot-')."
Write-Host "Start the dashboard now without rebooting:  Start-ScheduledTask -TaskName ttspot-Dashboard"
