#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Reconcile Jobscope campaign replies from this computer.

.DESCRIPTION
    Registers an hourly Windows Scheduled Task that runs `jobscope campaign
    tick`. Each invocation incrementally checks configured inboxes, reconciles
    replies, opt-outs, bounces, and complaints, and reports due approved work.
    It never calls SMTP; delivery remains a separate explicit action.

.PARAMETER IntervalMinutes
    Reconciliation frequency. Default 60; minimum 15.

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
Write-Host "  cadence: every $IntervalMinutes minute(s); reconciliation only"
Write-Host "  command: $Py $CommandArgs"
Write-Host "  delivery: separate manual action; this task never calls SMTP"
Write-Host ""
Write-Host "Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove:   ./scripts/unregister-outreach-task.ps1 -TaskName '$TaskName'"