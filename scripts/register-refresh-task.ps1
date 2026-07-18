#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run the jobscope "Refresh & Publish" pipeline on a nightly schedule -- the
    same path as the dashboard's Refresh button, hands-free.

.DESCRIPTION
    Registers a Windows Scheduled Task that runs `python -m jobscope refresh
    --force` daily. That syncs your Gmail inbox (last `serve.inbox_days` days,
    append-only), rescores matches, rebuilds the dashboard, and publishes the
    redacted (and, when a passphrase is stored, encrypted) site. It stamps
    `refresh:last_date`, so the dashboard's Refresh button knows the day is
    already done and won't repeat the work.

    By default it does NOT re-scrape job boards (that path is rate-limit prone);
    pass -FullScan to include a board scan. The publish step reads your
    passphrase from the OS keychain -- no prompt.

    ONE-TIME SETUP (do this first): store your passphrase in the OS keychain
        python -m jobscope secrets set JOBSCOPE_APPS_PASSPHRASE
    Without it, the task still refreshes + publishes the redacted dashboard, but
    skips the encrypted applications page.

.PARAMETER Time
    Daily start time, HH:mm (24-hour). Default "07:30".

.PARAMETER TaskName
    Scheduled task name. Default "jobscope refresh".

.PARAMETER FullScan
    Also re-scrape job boards before matching (slower, may hit rate limits).

.EXAMPLE
    python -m jobscope secrets set JOBSCOPE_APPS_PASSPHRASE   # once
    ./scripts/register-refresh-task.ps1

.EXAMPLE
    ./scripts/register-refresh-task.ps1 -Time 06:45 -FullScan
#>
[CmdletBinding()]
param(
    [string]$Time = "07:30",
    [string]$TaskName = "jobscope refresh",
    [switch]$FullScan
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = (Get-Command python).Source }

# The publish step runs publish.ps1 -Encrypted, which needs the passphrase
# unattended. Warn (don't block) if it's missing: the refresh still publishes the
# redacted dashboard, just without the encrypted applications page.
$have = -not [string]::IsNullOrEmpty($env:JOBSCOPE_APPS_PASSPHRASE)
if (-not $have) {
    Push-Location $RepoRoot
    $env:PYTHONPATH = "."
    $kc = (& $Py -c "import keyring,sys;from jobscope.core.config import KEYRING_SERVICE as s;v=keyring.get_password(s,'JOBSCOPE_APPS_PASSPHRASE');sys.stdout.write('1' if v else '')" 2>$null)
    Pop-Location
    $have = ($kc -eq '1')
}
if (-not $have) {
    Write-Warning "No stored passphrase found -- the task will refresh + publish the redacted dashboard, but skip the encrypted applications page."
    Write-Host    "To include it, store the passphrase once (hidden input) and re-run this script:"
    Write-Host    "    $Py -m jobscope secrets set JOBSCOPE_APPS_PASSPHRASE"
}

# python -m jobscope refresh --force: full Gmail-sync -> match -> encrypted
# publish. --force so the nightly run always executes (the schedule is the
# once-a-day guard); it stamps refresh:last_date for the dashboard button.
$refreshArgs = "-m jobscope refresh --force"
if ($FullScan) { $refreshArgs += " --full-scan" }

$action = New-ScheduledTaskAction -Execute $Py -Argument $refreshArgs -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName':"
Write-Host "  runs 'jobscope refresh --force' daily at $Time (Gmail sync -> match -> encrypted publish)."
Write-Host "  stamps refresh:last_date so the dashboard button won't repeat the same day."
Write-Host ""
Write-Host "Run it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove it:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
