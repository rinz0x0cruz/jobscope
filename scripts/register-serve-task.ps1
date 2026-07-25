#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Keep the LOCAL jobscope dashboard (full -- includes your Applications board)
    running whenever you are logged on, at http://127.0.0.1:<port>/.

.DESCRIPTION
    Registers a hidden Windows Scheduled Task that runs Jobscope through `uv`
    at logon, restarts it after unexpected stops, and never times out. The
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
$Uv = (Get-Command uv -ErrorAction Stop).Source
$Requirements = Join-Path $RepoRoot "requirements.lock"
if (-not (Test-Path $Requirements)) { throw "Missing locked dependencies: $Requirements" }
$Py = (& $Uv python find --system 3.12).Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Py)) { throw "uv could not find Python 3.12." }
$Runtime = Join-Path $env:LOCALAPPDATA "jobscope\runtime"
& $Uv venv $Runtime --python $Py --clear
if ($LASTEXITCODE -ne 0) { throw "Could not create the Jobscope task runtime." }
$RuntimePy = Join-Path $Runtime "Scripts\python.exe"
& $Uv pip install --python $RuntimePy --requirements $Requirements
if ($LASTEXITCODE -ne 0) { throw "Could not install locked Jobscope dependencies." }
$Pyw = Join-Path $Runtime "Scripts\pythonw.exe"
if (-not (Test-Path $Pyw)) { throw "Missing windowless Python executable: $Pyw" }
$CommandArgs = "-m jobscope serve --port $Port"

# `python -m jobscope serve` builds the full (un-redacted) dashboard from the
# local DB and serves the directory over http.server. WorkingDirectory = repo
# root so the package resolves and config.yaml / data/ paths are found.
$action = New-ScheduledTaskAction -Execute $Pyw `
    -Argument $CommandArgs `
    -WorkingDirectory $RepoRoot

# At logon = "whenever the PC is alive" (you're signed in). StartWhenAvailable
# catches a missed logon; the restart settings revive it if it ever exits.
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -Hidden `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# pythonw keeps this current-user task off the interactive desktop.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName':"
Write-Host "  runs:  $Pyw $CommandArgs"
Write-Host "  when:  hidden at logon; up to 3 retries at 5-minute intervals; no time limit"
Write-Host "  local: http://127.0.0.1:$Port/  (localhost only -- your full Applications board)"
Write-Host ""
Write-Host "Start it now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Stop it:       Stop-ScheduledTask  -TaskName '$TaskName'"
Write-Host "Remove it:     Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
