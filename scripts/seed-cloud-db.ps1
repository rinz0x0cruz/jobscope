#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-time seed for the cloud "refresh" workflow's encrypted DB branch.

.DESCRIPTION
    Encrypts your local data/jobscope.db with $env:JOBSCOPE_DB_KEY (the same value you
    store as the JOBSCOPE_DB_KEY repo secret) and force-pushes it as jobscope.db.enc to
    the `data` branch, so the scheduled workflow starts from your real history instead of
    an empty DB. Only the encrypted blob is pushed; the `data` branch is a single,
    force-replaced commit (no history). Safe to re-run whenever you want the cloud DB to
    match your local one.

.PARAMETER Repo
    HTTPS URL of the repo whose `data` branch holds the encrypted DB.
#>
[CmdletBinding()]
param([string]$Repo = "https://github.com/rinz0x0cruz/jobscope.git")

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$db = Join-Path $RepoRoot "data\jobscope.db"
if (-not (Test-Path $db)) { throw "no local DB at $db -- run jobscope (scan/inbox) first" }
if ([string]::IsNullOrEmpty($env:JOBSCOPE_DB_KEY)) {
    throw "set `$env:JOBSCOPE_DB_KEY (the same value as the JOBSCOPE_DB_KEY repo secret) before running"
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("js-seed-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    node (Join-Path $RepoRoot "scripts\crypt-file.mjs") encrypt $db (Join-Path $tmp "jobscope.db.enc")
    if ($LASTEXITCODE -ne 0) { throw "encryption failed" }

    Push-Location $tmp
    try {
        git init -q
        git checkout -q -b data
        git add jobscope.db.enc
        git -c user.name="rinz0x0cruz" -c user.email="rinz0x0cruz@users.noreply.github.com" `
            commit -q -m "seed encrypted db"
        git push --force $Repo data 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { throw "push failed (is a credential cached / remote reachable?)" }
    }
    finally { Pop-Location }

    Write-Host "==> Seeded the encrypted DB to the 'data' branch. The refresh workflow now starts from your history."
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
