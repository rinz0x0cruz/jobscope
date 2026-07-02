#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Retire this machine as the jobscope dashboard publisher: remove the daily
    Scheduled Task and delete the .publish-primary marker.

.DESCRIPTION
    Undoes register-publish-task.ps1. Unregisters the scheduled task (no error if it
    is already absent) and deletes the gitignored .publish-primary marker so this
    machine no longer pushes the redacted dashboard. Run register-publish-task.ps1 on
    whichever machine should take over publishing.

.PARAMETER TaskName
    Scheduled task name to remove. Default "jobscope publish".

.EXAMPLE
    ./scripts/unregister-publish-task.ps1
#>
[CmdletBinding()]
param(
    [string]$TaskName = "jobscope publish"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

# Remove the scheduled task if it exists (don't throw when it's already gone).
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
} else {
    Write-Host "No scheduled task named '$TaskName' found (nothing to remove)."
}

# Remove the designated-publisher marker if present.
$Marker = Join-Path $RepoRoot ".publish-primary"
if (Test-Path $Marker) {
    Remove-Item $Marker -Force
    Write-Host "Removed publisher marker: $Marker"
} else {
    Write-Host "No .publish-primary marker found (this machine was not the designated publisher)."
}

Write-Host "This machine will no longer publish. Run scripts/register-publish-task.ps1 on the machine that should."
