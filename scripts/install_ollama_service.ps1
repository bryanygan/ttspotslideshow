<#
Install Ollama as an auto-restarting Windows service via NSSM.
This ensures Ollama runs at system boot (before user login) and automatically
restarts if it crashes. It also disables the startup shortcut in the user's
Startup folder to prevent port conflicts.

Run from an elevated PowerShell:
  powershell -ExecutionPolicy Bypass -File scripts\install_ollama_service.ps1
#>

$ErrorActionPreference = "Stop"

$nssm       = "C:\tools\nssm\nssm.exe"
$svc        = "ollama"
$repo       = "C:\Users\Admin\Documents\ttspotslideshow"
$ollamaExe  = "C:\Users\Admin\AppData\Local\Programs\Ollama\ollama.exe"
$logDir     = Join-Path $repo "data\logs"
$startupLnk = "C:\Users\Admin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk"

if (-not (Test-Path $nssm))      { throw "NSSM not found at $nssm" }
if (-not (Test-Path $ollamaExe)) { throw "Ollama executable not found at $ollamaExe" }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# 1. Stop any currently running Ollama processes to free port 11434.
Write-Host "Stopping any running Ollama processes..."
$processes = Get-Process -Name "ollama*", "ollama app*" -ErrorAction SilentlyContinue
if ($processes) {
    foreach ($p in $processes) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped process $($p.ProcessName) (PID $($p.Id))."
    }
    Start-Sleep -Seconds 2
}

# 2. Disable user-session startup shortcut to prevent conflicts on login.
if (Test-Path $startupLnk) {
    $disabledLnk = $startupLnk + ".disabled"
    if (Test-Path $disabledLnk) {
        Remove-Item -Path $disabledLnk -Force -ErrorAction SilentlyContinue
    }
    Rename-Item -Path $startupLnk -NewName (Split-Path $disabledLnk -Leaf)
    Write-Host "Disabled user-session startup shortcut (renamed Ollama.lnk to Ollama.lnk.disabled)."
} else {
    Write-Host "No user-session startup shortcut found in Startup folder."
}

# 3. Remove any prior install of this service (idempotent re-install).
& $nssm stop $svc | Out-Null
& $nssm remove $svc confirm | Out-Null
Start-Sleep -Seconds 1

# 4. Install and configure Ollama service.
Write-Host "Installing Ollama as service '$svc'..."
& $nssm install $svc $ollamaExe "serve"
& $nssm set $svc AppDirectory (Split-Path $ollamaExe)
& $nssm set $svc DisplayName "Ollama Service"
& $nssm set $svc Description "Ollama local LLM server (auto-restarting, managed by TTSpot/NSSM)."
& $nssm set $svc Start SERVICE_AUTO_START

# Configure Environment variables (crucial for model folder location and host binding)
$envList = @(
    "OLLAMA_MODELS=C:\Users\Admin\.ollama\models",
    "OLLAMA_HOST=127.0.0.1:11434"
)
& $nssm set $svc AppEnvironmentExtra $envList

# Restart on exit settings
& $nssm set $svc AppExit Default Restart
& $nssm set $svc AppRestartDelay 5000
& $nssm set $svc AppThrottle 10000

# Logging
& $nssm set $svc AppStdout (Join-Path $logDir "ollama_service.log")
& $nssm set $svc AppStderr (Join-Path $logDir "ollama_service.log")
& $nssm set $svc AppRotateFiles 1
& $nssm set $svc AppRotateBytes 5000000

# 5. Start the service.
Write-Host "Starting Ollama service..."
& $nssm start $svc
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Service '$svc' status:"
& $nssm status $svc
