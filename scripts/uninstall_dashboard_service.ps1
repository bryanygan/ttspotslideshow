<#
Remove the ttspot-dashboard NSSM service and (optionally) re-enable the old
Task Scheduler task. Run from an elevated PowerShell.
#>

$nssm = "C:\tools\nssm\nssm.exe"
$svc  = "ttspot-dashboard"

if (Test-Path $nssm) {
  & $nssm stop $svc | Out-Null
  & $nssm remove $svc confirm | Out-Null
  Write-Host "Removed service '$svc'."
} else {
  Write-Host "NSSM not found; skipping service removal."
}

# Re-enable the legacy scheduled task as a fallback (still fragile — prefer the service).
$old = Get-ScheduledTask -TaskName 'ttspot-Dashboard' -ErrorAction SilentlyContinue
if ($old) {
  Enable-ScheduledTask -TaskName 'ttspot-Dashboard' | Out-Null
  Write-Host "Re-enabled scheduled task 'ttspot-Dashboard'."
}
