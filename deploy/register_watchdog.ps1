<#
  Registers the ttspot-Watchdog scheduled task.
  Runs as NT AUTHORITY\SYSTEM (highest privileges) so it can start/restart Windows services.
  Runs every 10 minutes to verify the health of Ollama and the TTSpot Dashboard.

  Usage: open an ELEVATED (Run as administrator) PowerShell and run:
            powershell -ExecutionPolicy Bypass -File .\deploy\register_watchdog.ps1
#>

$ErrorActionPreference = "Stop"

$Repo       = (Resolve-Path "$PSScriptRoot\..").Path
$ScriptPath = Join-Path $Repo "scripts\watchdog.ps1"
$TaskName   = "ttspot-Watchdog"

if (-not (Test-Path $ScriptPath)) {
    throw "Watchdog script not found at $ScriptPath - create it first."
}

Write-Host "Repo:        $Repo"
Write-Host "Script Path: $ScriptPath`n"

# 1. Define triggers
# Trigger A: Run at boot/startup
$TriggerBoot = New-ScheduledTaskTrigger -AtStartup

# Trigger B: Run every 10 minutes starting now, indefinitely
# Note: Set start time to 1 minute ago to ensure it is immediately active
$startTime = (Get-Date).AddMinutes(-1)
$TriggerRepeat = New-ScheduledTaskTrigger -Once -At $startTime -RepetitionInterval (New-TimeSpan -Minutes 10)

$Triggers = @($TriggerBoot, $TriggerRepeat)

# 2. Define action (run powershell in hidden/non-interactive mode)
$powershell = "powershell.exe"
$arguments  = "-WindowStyle Hidden -NonInteractive -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Action     = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $Repo

# 3. Define Principal (NT AUTHORITY\SYSTEM with highest privileges)
$Principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType Service -RunLevel Highest

# 4. Remove existing task if it exists
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Unregistered existing task '$TaskName'."
}

# 5. Register new task
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers -Principal $Principal | Out-Null
Write-Host "Registered task '$TaskName' under SYSTEM account."

# 6. Start the task immediately
Start-ScheduledTask -TaskName $TaskName
Write-Host "Started task '$TaskName' successfully."
