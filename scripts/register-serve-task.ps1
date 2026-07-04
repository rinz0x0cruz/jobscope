#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Keep the LOCAL jobscope dashboard (full -- includes your Applications board)
    running whenever you are logged on, at http://127.0.0.1:<port>/.

.DESCRIPTION
    Registers a Windows Scheduled Task that runs `python -m jobscope serve
    --port <Port>` at logon, restarts it if it stops, and never times out. The
    server binds 127.0.0.1 only (localhost) -- nothing is exposed to the network,
    and your un-redacted applications never leave the machine. This is the private
    counterpart to the redacted GitHub Pages site.

.PARAMETER Port
    Local port to serve on. Default 8799.

.PARAMETER TaskName
    Scheduled task name. Default "jobscope serve".

.EXAMPLE
    ./scripts/register-serve-task.ps1
    ./scripts/register-serve-task.ps1 -Port 8790
#>
[CmdletBinding()]
param(
    [int]$Port = 8799,
    [string]$TaskName = "jobscope serve"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pyCmd) { throw "No Python found (.venv missing and 'python' not on PATH)." }
    $Py = $pyCmd.Source
}

# `python -m jobscope serve` builds the full (un-redacted) dashboard from the
# local DB and serves the directory over http.server. WorkingDirectory = repo
# root so the package resolves and config.yaml / data/ paths are found.
$action = New-ScheduledTaskAction -Execute $Py `
    -Argument "-m jobscope serve --port $Port" `
    -WorkingDirectory $RepoRoot

# At logon = "whenever the PC is alive" (you're signed in). StartWhenAvailable
# catches a missed logon; the restart settings revive it if it ever exits.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# Interactive current-user context: same profile that owns data/ + config.yaml.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName':"
Write-Host "  runs:  $Py -m jobscope serve --port $Port"
Write-Host "  when:  at logon; restarts within ~1 min if it stops; no time limit"
Write-Host "  local: http://127.0.0.1:$Port/  (localhost only -- your full Applications board)"
Write-Host ""
Write-Host "Start it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Stop it:       Stop-ScheduledTask  -TaskName '$TaskName'"
Write-Host "Remove it:     Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
