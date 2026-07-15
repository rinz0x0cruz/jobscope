#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-time seed for the cloud "refresh" workflow's encrypted DB branch.

.DESCRIPTION
    Encrypts your local data/jobscope.db with $env:JOBSCOPE_DB_KEY (the same value you
    store as the JOBSCOPE_DB_KEY repo secret) and force-pushes it to the `data` branch,
    so the scheduled workflow starts from your real history instead of an empty DB. The
    branch contains the current and one last-known-good encrypted generation in a single,
    force-replaced commit. Safe to re-run whenever you want the cloud DB to match your
    local one.

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
$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "no project Python at $python -- run setup.ps1 first" }
if ([string]::IsNullOrEmpty($env:JOBSCOPE_DB_KEY)) {
    throw "set `$env:JOBSCOPE_DB_KEY (the same value as the JOBSCOPE_DB_KEY repo secret) before running"
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("js-seed-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Push-Location $RepoRoot
    try {
        & $python -m jobscope.core.snapshot $db
        if ($LASTEXITCODE -ne 0) { throw "local database validation failed (exit $LASTEXITCODE)" }
    }
    finally { Pop-Location }

    # crypt-file.mjs prints a status line to stderr; under ErrorActionPreference=Stop
    # (Windows PowerShell 5.1) that would abort the seed, so relax it around the node
    # call and gate on the exit code instead (2>&1 merges the line so it just prints).
    $eapPrev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    node (Join-Path $RepoRoot "scripts\crypt-file.mjs") encrypt $db (Join-Path $tmp "jobscope.db.enc") 2>&1 |
        ForEach-Object { Write-Host $_ }
    $encExit = $LASTEXITCODE
    $ErrorActionPreference = $eapPrev
    if ($encExit -ne 0) { throw "encryption failed (exit $encExit)" }

    $verifyDb = Join-Path $tmp "jobscope.verify.db"
    $ErrorActionPreference = "Continue"
    node (Join-Path $RepoRoot "scripts\crypt-file.mjs") decrypt (Join-Path $tmp "jobscope.db.enc") $verifyDb 2>&1 |
        ForEach-Object { Write-Host $_ }
    $decExit = $LASTEXITCODE
    $ErrorActionPreference = $eapPrev
    if ($decExit -ne 0) { throw "encryption verification failed (exit $decExit)" }
    if ((Get-FileHash $db).Hash -ne (Get-FileHash $verifyDb).Hash) {
        throw "encryption verification failed (decrypted bytes differ)"
    }
    Remove-Item $verifyDb -Force
    Copy-Item (Join-Path $tmp "jobscope.db.enc") (Join-Path $tmp "jobscope.db.previous.enc")

    Push-Location $tmp
    try {
        git init -q
        git checkout -q -b data
        git add jobscope.db.enc jobscope.db.previous.enc
        git -c user.name="rinz0x0cruz" -c user.email="rinz0x0cruz@users.noreply.github.com" `
            commit -q -m "seed encrypted db"
        # git streams its push progress + the final "To <url>" summary to stderr;
        # under ErrorActionPreference=Stop (Windows PowerShell 5.1) that summary line
        # aborts the seed *after* the push has already landed, so relax EAP around the
        # push and gate on the exit code instead (same fix as the node call above).
        $eapPush = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        git push --force $Repo data 2>&1 | ForEach-Object { Write-Host $_ }
        $pushExit = $LASTEXITCODE
        $ErrorActionPreference = $eapPush
        if ($pushExit -ne 0) { throw "push failed (is a credential cached / remote reachable?)" }
    }
    finally { Pop-Location }

    Write-Host "==> Seeded the encrypted DB to the 'data' branch. The refresh workflow now starts from your history."
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
