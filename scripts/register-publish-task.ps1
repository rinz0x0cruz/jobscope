#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Register a Windows Scheduled Task that auto-publishes the redacted jobscope
    dashboard to GitHub Pages on a daily schedule.

.DESCRIPTION
    Creates (or updates) a task that runs scripts/publish.ps1 once a day. Uses
    -StartWhenAvailable so a run missed while the machine was off fires as soon as
    possible, and runs only while you are logged on so cached git credentials
    (Git Credential Manager) are available for the push.

.PARAMETER Time
    Daily start time, HH:mm (24-hour). Default "08:00".

.PARAMETER TaskName
    Scheduled task name. Default "jobscope publish".

.EXAMPLE
    ./scripts/register-publish-task.ps1 -Time 07:30
#>
[CmdletBinding()]
param(
    [string]$Time = "08:00",
    [string]$TaskName = "jobscope publish"
)

$ErrorActionPreference = "Stop"

$RepoRoot   = Split-Path -Parent $PSScriptRoot
$PublishPs1 = Join-Path $RepoRoot "scripts\publish.ps1"
if (-not (Test-Path $PublishPs1)) { throw "publish.ps1 not found at $PublishPs1" }

# Prefer PowerShell 7 (pwsh); fall back to Windows PowerShell.
$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCmd) { $Shell = $pwshCmd.Source } else { $Shell = (Get-Command powershell).Source }

$action = New-ScheduledTaskAction -Execute $Shell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PublishPs1`"" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Run in the current interactive user's context so cached git credentials are usable.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' -> daily at $Time."
Write-Host "Runs: $PublishPs1"
Write-Host "Run it now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove it with:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
