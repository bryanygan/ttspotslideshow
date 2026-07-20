<#
TTSpot Services Watchdog Script
Checks if the TTSpot Dashboard and Ollama APIs are responding.
If either is unresponsive, attempts to restart the corresponding Windows service.

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

# 1. Check Ollama API (Port 11434)
$ollamaOk = $false
try {
    # Call the API with a 5-second timeout
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 -ErrorAction Stop
    if ($response.models -ne $null) {
        $ollamaOk = $true
    } else {
        Log-Message "Ollama API responded but returned no models configuration." -IsError $true
    }
} catch {
    Log-Message "Ollama API check failed: $_" -IsError $true
}

if (-not $ollamaOk) {
    Log-Message "Ollama is unresponsive! Attempting to restart 'ollama' service..."
    try {
        $svc = Get-Service -Name "ollama" -ErrorAction Stop
        if ($svc.Status -eq 'Running') {
            Restart-Service -Name "ollama" -Force -ErrorAction Stop
        } else {
            Start-Service -Name "ollama" -ErrorAction Stop
        }
        Start-Sleep -Seconds 5
        $svc = Get-Service -Name "ollama"
        Log-Message "Ollama service status after restart: $($svc.Status)"
    } catch {
        Log-Message "Failed to restart Ollama service: $_" -IsError $true
    }
} else {
    Log-Message "Ollama service is healthy."
}

# 2. Check Dashboard API (Port 8000)
$dashboardOk = $false
try {
    # Call health check with a 5-second timeout
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5 -ErrorAction Stop
    if ($response.status -eq "ok" -or $response.status -eq "degraded") {
        $dashboardOk = $true
        # If dashboard is ok, verify if it reports Ollama as failed (secondary check)
        if ($response.checks -ne $null -and $response.checks.ollama -ne $null) {
            $dashboardOllamaOk = $response.checks.ollama.ok
            if (-not $dashboardOllamaOk) {
                Log-Message "Dashboard reports Ollama is offline/degraded. Triggering Ollama service restart..."
                Restart-Service -Name "ollama" -Force -ErrorAction SilentlyContinue
            }
        }
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
