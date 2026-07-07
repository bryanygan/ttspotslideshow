<#
Install the Weekly Recap dashboard backend as an auto-restarting Windows service
via NSSM. This replaces the old Task Scheduler "ttspot-Dashboard" task, which was
fragile: a 72h execution limit killed the long-running server and a boot-only
trigger never restarted it (an ~11-day outage on 2026-06/07).

A Windows service is the reliable way to keep this up: NSSM auto-restarts the
process on any exit, starts it at boot before login, and runs it under
LocalSystem (git is on the machine PATH, so auto-git-pull still works; Ollama on
127.0.0.1 is reachable).

Run from an elevated PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\install_dashboard_service.ps1
#>

$nssm   = "C:\tools\nssm\nssm.exe"
$svc    = "ttspot-dashboard"
$repo   = "C:\Users\Admin\Documents\ttspotslideshow"
$python = Join-Path $repo ".venv\Scripts\python.exe"
$logDir = Join-Path $repo "data\logs"

if (-not (Test-Path $nssm))   { throw "NSSM not found at $nssm" }
if (-not (Test-Path $python)) { throw "Python venv not found at $python" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 1. Retire the old scheduled task so it can't compete for port 8000 at boot.
$old = Get-ScheduledTask -TaskName 'ttspot-Dashboard' -ErrorAction SilentlyContinue
if ($old) {
  try { Stop-ScheduledTask -TaskName 'ttspot-Dashboard' -ErrorAction SilentlyContinue } catch {}
  Disable-ScheduledTask -TaskName 'ttspot-Dashboard' | Out-Null
  Write-Host "Disabled old scheduled task 'ttspot-Dashboard'."
}

# 2. Free port 8000 from any running dashboard_server instance.
$owner = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess
if ($owner) {
  Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2
  Write-Host "Stopped process on port 8000 (PID $owner)."
}

# 3. Remove any prior install of this service (idempotent re-install).
& $nssm stop $svc | Out-Null
& $nssm remove $svc confirm | Out-Null
Start-Sleep -Seconds 1

# 4. Install + configure.
& $nssm install $svc $python "dashboard_server.py"
& $nssm set $svc AppDirectory $repo
& $nssm set $svc DisplayName "TTSpot Dashboard"
& $nssm set $svc Description "Weekly Recap dashboard backend (auto-restart on failure)."
& $nssm set $svc Start SERVICE_AUTO_START
# Restart on any exit; wait 5s; if it dies within 10s treat as a crash loop and throttle.
& $nssm set $svc AppExit Default Restart
& $nssm set $svc AppRestartDelay 5000
& $nssm set $svc AppThrottle 10000
# Capture early/crash output (the app also tees to dashboard.log once it starts).
& $nssm set $svc AppStdout (Join-Path $logDir "service.log")
& $nssm set $svc AppStderr (Join-Path $logDir "service.log")
& $nssm set $svc AppRotateFiles 1
& $nssm set $svc AppRotateBytes 5000000

# 5. Start.
& $nssm start $svc
Start-Sleep -Seconds 3
Write-Host ""
Write-Host "Service '$svc' status:"
& $nssm status $svc
