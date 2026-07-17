#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pace individually approved Jobscope campaign emails from this computer.

.DESCRIPTION
    Registers an hourly Windows Scheduled Task that runs `jobscope campaign
    tick`. Each invocation incrementally checks configured inboxes for replies,
    then sends at most one due, individually approved draft. Jobscope rechecks
    the local time window, daily limit, spacing,
    application history, cooldown, do-not-contact list, recipient domain,
    attachment, and SMTP gates immediately before sending.

    Registration first runs `jobscope campaign ready`. SMTP passwords are resolved
    from the OS keychain or configured environment variable and are never written
    into the task definition.

.PARAMETER IntervalMinutes
    Scheduler frequency. Default 60; minimum 15. This is only a wake-up cadence,
    not a send rate: Jobscope's stricter campaign pacing remains authoritative.

.PARAMETER Config
    Optional path to a non-default Jobscope config file.

.PARAMETER TaskName
    Scheduled task name. Default "jobscope outreach".
#>
[CmdletBinding()]
param(
    [ValidateRange(15, 1440)]
    [int]$IntervalMinutes = 60,
    [string]$Config = "",
    [string]$TaskName = "jobscope outreach"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) { throw "No Python found (.venv missing and 'python' not on PATH)." }
    $Py = $pyCmd.Source
}

$ResolvedConfig = ""
if ($Config) {
    $ResolvedConfig = (Resolve-Path $Config).Path
}

$ReadyArgs = @("-m", "jobscope")
if ($ResolvedConfig) { $ReadyArgs += @("--config", $ResolvedConfig) }
$ReadyArgs += @("campaign", "ready")
Push-Location $RepoRoot
try {
    & $Py @ReadyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Campaign sending is not configured. Fix the readiness messages above before registering the task."
    }
} finally {
    Pop-Location
}

$ConfigArg = if ($ResolvedConfig) { "--config `"$ResolvedConfig`" " } else { "" }
$CommandArgs = "-m jobscope ${ConfigArg}campaign tick"
$action = New-ScheduledTaskAction -Execute $Py -Argument $CommandArgs -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName'."
Write-Host "  cadence: every $IntervalMinutes minute(s); one approved email maximum per run"
Write-Host "  command: $Py $CommandArgs"
Write-Host "  pacing: campaign daily limit, spacing, timezone, and send window remain authoritative"
Write-Host ""
Write-Host "Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove:   ./scripts/unregister-outreach-task.ps1 -TaskName '$TaskName'"