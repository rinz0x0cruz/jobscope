#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Remove the local Jobscope outreach scheduler task.
#>
[CmdletBinding()]
param(
    [string]$TaskName = "jobscope outreach"
)

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Scheduled task '$TaskName' is not registered."
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Removed scheduled task '$TaskName'."