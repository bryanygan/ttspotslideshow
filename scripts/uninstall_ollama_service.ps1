<#
Remove the ollama NSSM service and re-enable the user startup shortcut.
Run from an elevated PowerShell.
#>

$nssm       = "C:\tools\nssm\nssm.exe"
$svc        = "ollama"
$startupLnk = "C:\Users\Admin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk"

if (Test-Path $nssm) {
  & $nssm stop $svc | Out-Null
  & $nssm remove $svc confirm | Out-Null
  Write-Host "Removed service '$svc'."
} else {
  Write-Host "NSSM not found; skipping service removal."
}

# Re-enable the user startup shortcut if it was disabled.
$disabledLnk = $startupLnk + ".disabled"
if (Test-Path $disabledLnk) {
  Rename-Item -Path $disabledLnk -NewName (Split-Path $startupLnk -Leaf)
  Write-Host "Re-enabled user-session startup shortcut (renamed Ollama.lnk.disabled back to Ollama.lnk)."
} else {
  Write-Host "No disabled startup shortcut found."
}
