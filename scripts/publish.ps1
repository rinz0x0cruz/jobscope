#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Render the redacted jobscope dashboard and publish it to the public
    jobscope-dashboard repo so it is viewable from a phone via GitHub Pages.

.DESCRIPTION
    Runs `jobscope dashboard --public` to produce a redacted, self-contained HTML
    (no referral contacts, application funnel, or search terms), then pushes it as
    index.html to a separate PUBLIC repo (jobscope-dashboard) whose Pages site serves
    it. The jobscope code repo can stay private; only the redacted snapshot is public,
    in a repo with a clean history. Your database/packages never leave your machine.

    Safe to run from a scheduled task. Commits use the local rinz0x0cruz identity.

.PARAMETER Repo
    HTTPS URL of the public dashboard repo to publish to.

.PARAMETER Branch
    Branch GitHub Pages serves from on that repo. Default "main".

.EXAMPLE
    ./scripts/publish.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo = "https://github.com/rinz0x0cruz/jobscope-dashboard.git",
    [string]$Branch = "main",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
# Native commands (git) signal failure via $LASTEXITCODE; some git calls return
# non-zero by design (ref-missing / diff-quiet), so don't let PS 7.3+ throw on them.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Resolve the venv interpreter, falling back to PATH.
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

# 1. Render the redacted dashboard.
Write-Host "==> Rendering redacted dashboard (jobscope dashboard --public)"
$env:PYTHONPATH = "."
& $Py -m jobscope dashboard --public
if ($LASTEXITCODE -ne 0) { throw "jobscope dashboard --public failed (exit $LASTEXITCODE)" }

$PublicHtml = Join-Path $RepoRoot "data\public-dashboard.html"
if (-not (Test-Path $PublicHtml)) { throw "expected dashboard not found: $PublicHtml" }

# Publish gate: only the designated publisher (the machine that ran
# register-publish-task.ps1, which wrote .publish-primary) pushes, to avoid double
# git pushes. Rendering above always runs; only the push below is gated. Use -Force
# to override.
$Marker = Join-Path $RepoRoot ".publish-primary"
if (-not $Force) {
    if (-not (Test-Path $Marker)) { Write-Host "==> Not the designated publisher (no .publish-primary marker). Skipping push. Run scripts/register-publish-task.ps1 here to designate this machine, or pass -Force."; return }
    $MarkerHost = (Get-Content $Marker -TotalCount 1).Trim()
    if ($MarkerHost -and $MarkerHost -ne $env:COMPUTERNAME) { Write-Host "==> Marker names '$MarkerHost', not this machine '$env:COMPUTERNAME'. Skipping push. Pass -Force to override."; return }
}

# 2. Publish index.html to the separate public dashboard repo via a persistent
#    (gitignored) clone. Only this machine pushes there, so a plain push is safe.
$DashDir = Join-Path $RepoRoot ".dashboard-repo"
$Name  = "rinz0x0cruz"
$Email = "rinz0x0cruz@users.noreply.github.com"

if (-not (Test-Path (Join-Path $DashDir ".git"))) {
    git clone --quiet $Repo $DashDir
    if ($LASTEXITCODE -ne 0) { throw "clone of $Repo failed (is a credential cached?)" }
}

Copy-Item $PublicHtml (Join-Path $DashDir "index.html") -Force
New-Item -ItemType File -Path (Join-Path $DashDir ".nojekyll") -Force | Out-Null

Push-Location $DashDir
try {
    # Ensure we're on $Branch (create it on the first publish to an empty repo).
    git rev-parse --verify --quiet $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { git checkout -q $Branch } else { git checkout -q -B $Branch }

    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "==> No changes to publish."
    } else {
        $stamp = (Get-Date).ToUniversalTime().ToString("o")
        git -c user.name=$Name -c user.email=$Email commit -q -m "chore: publish dashboard $stamp"
        if ($LASTEXITCODE -ne 0) { throw "commit failed" }
        git push -q -u origin $Branch
        if ($LASTEXITCODE -ne 0) { throw "push failed (is a credential cached / remote reachable?)" }
        Write-Host "==> Published to $Repo ($Branch)."
    }
}
finally {
    Pop-Location
}
