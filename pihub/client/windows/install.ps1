# pihub-client installer for Windows.
# Run in PowerShell from the pihub\client\windows folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Device win-pc -Token <PIHUB_TOKEN>
# Needs Python 3 (https://www.python.org/downloads/ , tick "Add python.exe to PATH").
param(
  [string]$Device = "win-pc",
  [Parameter(Mandatory = $true)][string]$Token,
  [string]$Hub = "http://192.168.1.13:8899"
)
$ErrorActionPreference = "Stop"

$py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "pythonw.exe not found. Install Python 3 and tick 'Add python.exe to PATH'." }

$app = Join-Path $env:LOCALAPPDATA "pihub"
$cfgDir = Join-Path $env:APPDATA "pihub"
New-Item -ItemType Directory -Force -Path $app, $cfgDir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "..\pihub_client.py"), (Join-Path $PSScriptRoot "..\pihub_mcp.py"), (Join-Path $PSScriptRoot "..\report_event.py") $app

$cfgFile = Join-Path $cfgDir "client.json"
if (-not (Test-Path $cfgFile)) {
  $cfg = [ordered]@{
    device = $Device; hub_url = $Hub; token = $Token
    allowed_roots = @("~/Documents", "~/Desktop", "~/Downloads", "~/Pictures", "~/Music", "~/Videos")
    deny = @(".ssh", ".gnupg", ".env", "API Keys.md", "id_rsa", "id_ed25519", "Cookies")
    poll_seconds = 10
    syncthing = [ordered]@{ url = "http://127.0.0.1:8384"; api_key = ""; pi_device_id = "" }
  }
  $cfg | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $cfgFile
  Write-Host "Wrote $cfgFile"
} else {
  Write-Host "Keeping existing $cfgFile"
}

$client = Join-Path $app "pihub_client.py"
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -Force -TaskName "pihub-client" -Trigger $logon -Settings $settings `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "`"$client`"") | Out-Null

$every4 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(3) -RepetitionInterval (New-TimeSpan -Days 4)
$fallback = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries
Register-ScheduledTask -Force -TaskName "pihub-sync-fallback" -Trigger $every4 -Settings $fallback `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "`"$client`" --sync-now") | Out-Null

Start-ScheduledTask -TaskName "pihub-client"
Write-Host "pihub-client is running and will start at every logon."
Write-Host "Next: install Syncthing (https://syncthing.net/downloads/), start it once, then run:"
Write-Host "  py ..\..\setup\pair_syncthing.py"
