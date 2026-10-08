<#
TTSpot Services Watchdog Script
Checks if the TTSpot Dashboard API is responding.
If it is unresponsive, attempts to restart the ttspot-dashboard Windows service.

Designed to be run periodically (e.g. every 5-10 minutes) via Windows Task Scheduler.
Requires administrator privileges to restart services (run task as SYSTEM).
#>

$ErrorActionPreference = "Stop"

$repo = "C:\Users\Admin\Documents\ttspotslideshow"
$logDir = Join-Path $repo "data\logs"
$watchdogLog = Join-Path $logDir "watchdog.log"

# Ensure logs directory exists
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

# Rotate watchdog log if it exceeds 1MB
if (Test-Path $watchdogLog) {
    $file = Get-Item $watchdogLog
    if ($file.Length -gt 1MB) {
        Remove-Item $watchdogLog -Force -ErrorAction SilentlyContinue
    }
}

function Log-Message($Message, $IsError = $false) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $prefix = if ($IsError) { "ERROR" } else { "INFO" }
    $line = "[$timestamp] [$prefix] $Message"
    Write-Output $line
    Add-Content -Path $watchdogLog -Value $line
}

Log-Message "Running services check..."

# Check Dashboard API (Port 8000)
$dashboardOk = $false
try {
    # Call health check with a 5-second timeout
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5 -ErrorAction Stop
    if ($response.status -eq "ok" -or $response.status -eq "degraded") {
        $dashboardOk = $true
    } else {
        Log-Message "Dashboard health check returned unexpected status: $($response.status)" -IsError $true
    }
} catch {
    Log-Message "Dashboard API check failed: $_" -IsError $true
}

if (-not $dashboardOk) {
    Log-Message "Dashboard is unresponsive! Attempting to restart 'ttspot-dashboard' service..."
    try {
        $svc = Get-Service -Name "ttspot-dashboard" -ErrorAction Stop
        if ($svc.Status -eq 'Running') {
            Restart-Service -Name "ttspot-dashboard" -Force -ErrorAction Stop
        } else {
            Start-Service -Name "ttspot-dashboard" -ErrorAction Stop
        }
        Start-Sleep -Seconds 5
        $svc = Get-Service -Name "ttspot-dashboard"
        Log-Message "Dashboard service status after restart: $($svc.Status)"
    } catch {
        Log-Message "Failed to restart dashboard service: $_" -IsError $true
    }
} else {
    Log-Message "Dashboard service is healthy."
}

Log-Message "Services check completed."
