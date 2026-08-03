#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Reconcile Jobscope campaign replies from this computer.

.DESCRIPTION
    Registers an hourly Windows Scheduled Task that runs `jobscope campaign
    tick`. Each invocation incrementally checks configured inboxes, reconciles
    replies, opt-outs, bounces, and complaints, and reports due approved work.
    Reconciliation never calls SMTP. Pass -Deliver to also send approved work
    that is already due; without it, delivery remains a separate manual action.

.PARAMETER IntervalMinutes
    Reconciliation frequency. Default 60; minimum 15.

.PARAMETER Deliver
    Also run `campaign send-approved` after each reconciliation, sending at most
    one already-approved, already-due message per run inside the campaign's send
    window. Off by default.

.PARAMETER Config
    Optional path to a non-default Jobscope config file.

.PARAMETER TaskName
    Scheduled task name. Default "jobscope outreach".
#>
[CmdletBinding()]
param(
    [ValidateRange(15, 1440)]
    [int]$IntervalMinutes = 60,
    [switch]$Deliver,
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

# An hourly task fails silently, and the fallback above is a system Python that
# usually lacks this project's dependencies.
& $Py -m jobscope --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "$Py cannot run jobscope (exit $LASTEXITCODE). Run .\setup.ps1 to create .venv, then re-run this script."
}

$ResolvedConfig = ""
if ($Config) {
    $ResolvedConfig = (Resolve-Path $Config).Path
}

$ConfigArg = if ($ResolvedConfig) { "--config `"$ResolvedConfig`" " } else { "" }
$CommandArgs = "-m jobscope ${ConfigArg}campaign tick"
$actions = @(
    New-ScheduledTaskAction -Execute $Py -Argument $CommandArgs -WorkingDirectory $RepoRoot
)
$SendArgs = ""
if ($Deliver) {
    # Ordered after reconciliation so a reply, opt-out, or bounce lands first.
    $SendArgs = "-m jobscope ${ConfigArg}campaign send-approved"
    $actions += New-ScheduledTaskAction -Execute $Py -Argument $SendArgs -WorkingDirectory $RepoRoot
}
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $actions -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName'."
Write-Host "  cadence: every $IntervalMinutes minute(s)"
Write-Host "  command: $Py $CommandArgs"
if ($Deliver) {
    Write-Host "  command: $Py $SendArgs"
    Write-Host "  delivery: enabled; at most one due message per run, inside the send window"
} else {
    Write-Host "  delivery: separate manual action; this task never calls SMTP"
}
Write-Host ""
Write-Host "Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove:   ./scripts/unregister-outreach-task.ps1 -TaskName '$TaskName'"