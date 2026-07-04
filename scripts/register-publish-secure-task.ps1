#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Auto-publish the encrypted applications page (+ redacted dashboard) on a
    schedule, so you never have to double-click the secure publish again.

.DESCRIPTION
    Registers a Windows Scheduled Task that runs `publish.ps1 -Encrypted -Force`
    daily and at logon. It makes NO scan / match / inbox calls (so nothing can
    429), and reads your passphrase from the OS keychain -- no prompt, no manual
    step. It only pushes when your data actually changed.

    ONE-TIME SETUP (do this first): store your passphrase in the OS keychain
        python -m jobscope secrets set JOBSCOPE_APPS_PASSPHRASE
    The keychain is per-user and OS-protected; your local DB is already
    un-encrypted on this machine, so this adds no exposure beyond it. To refresh
    the underlying job/application DATA, run `jobscope inbox` / `scan` yourself
    (those hit the rate-limited AI/boards); the next auto-publish ships it.

.PARAMETER Time
    Daily start time, HH:mm (24-hour). Default "08:15".

.PARAMETER TaskName
    Scheduled task name. Default "jobscope publish-secure".

.EXAMPLE
    python -m jobscope secrets set JOBSCOPE_APPS_PASSPHRASE   # once
    ./scripts/register-publish-secure-task.ps1
#>
[CmdletBinding()]
param(
    [string]$Time = "08:15",
    [string]$TaskName = "jobscope publish-secure"
)

$ErrorActionPreference = "Stop"

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PublishPs1 = Join-Path $RepoRoot "scripts\publish.ps1"
if (-not (Test-Path $PublishPs1)) { throw "publish.ps1 not found at $PublishPs1" }

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = (Get-Command python).Source }

# Refuse to register a task that would stall on a hidden prompt: verify the
# passphrase is retrievable unattended (env var or keychain).
$have = -not [string]::IsNullOrEmpty($env:JOBSCOPE_APPS_PASSPHRASE)
if (-not $have) {
    Push-Location $RepoRoot
    $env:PYTHONPATH = "."
    $kc = (& $Py -c "import keyring,sys;from jobscope.core.config import KEYRING_SERVICE as s;v=keyring.get_password(s,'JOBSCOPE_APPS_PASSPHRASE');sys.stdout.write('1' if v else '')" 2>$null)
    Pop-Location
    $have = ($kc -eq '1')
}
if (-not $have) {
    Write-Warning "No stored passphrase found -- an unattended publish would stall on the prompt."
    Write-Host    "Store it once (hidden input), then re-run this script:"
    Write-Host    "    $Py -m jobscope secrets set JOBSCOPE_APPS_PASSPHRASE"
    return
}

$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
$Shell = if ($pwshCmd) { $pwshCmd.Source } else { (Get-Command powershell).Source }

# -Encrypted -Force: publish the redacted dashboard AND the encrypted apps page
# from the CURRENT DB. No -Refresh => no scan/inbox/AI => nothing to rate-limit.
$action = New-ScheduledTaskAction -Execute $Shell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PublishPs1`" -Encrypted -Force" `
    -WorkingDirectory $RepoRoot

# Daily catch-all + at logon, so your phone view refreshes hands-free.
$trigger = @(
    (New-ScheduledTaskTrigger -Daily -At $Time),
    (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME")
)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName':"
Write-Host "  publishes the encrypted apps page (+ redacted dashboard) daily at $Time and at logon."
Write-Host "  reads the passphrase from the keychain -- no prompt, no double-click."
Write-Host ""
Write-Host "Run it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove it:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
