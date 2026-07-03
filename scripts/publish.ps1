#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build the redacted jobscope web dashboard and publish it to jobscope's own
    gh-pages branch, served via GitHub Pages.

.DESCRIPTION
    Emits a redacted dashboard payload (`jobscope dashboard --emit-json --public` -- no
    referral contacts, rationale, resume labels, application funnel, or search terms),
    bakes it into the Vite/React app in web/, builds it, and publishes web/dist to this
    repo's `gh-pages` branch, which GitHub Pages serves at
    https://rinz0x0cruz.github.io/jobscope/. Only the redacted build is published;
    `main` is never touched and your database/config never leave your machine.

    Requires Node.js/npm for the web build. Safe to run from a scheduled task;
    commits use the local rinz0x0cruz identity.

.PARAMETER Repo
    HTTPS URL of the repo whose gh-pages branch hosts the dashboard.

.PARAMETER Branch
    Branch GitHub Pages serves from. Default "gh-pages".

.EXAMPLE
    ./scripts/publish.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo = "https://github.com/rinz0x0cruz/jobscope.git",
    [string]$Branch = "gh-pages",
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

# 1. Emit the redacted dashboard payload and bake it into the web app.
Write-Host "==> Emitting redacted dashboard JSON (jobscope dashboard --emit-json --public)"
$env:PYTHONPATH = "."
& $Py -m jobscope dashboard --emit-json --public
if ($LASTEXITCODE -ne 0) { throw "jobscope dashboard --emit-json --public failed (exit $LASTEXITCODE)" }

$PublicJson = Join-Path $RepoRoot "data\dashboard.public.json"
if (-not (Test-Path $PublicJson)) { throw "expected payload not found: $PublicJson" }
Copy-Item $PublicJson (Join-Path $RepoRoot "web\src\data\dashboard.json") -Force

# 2. Build the web dashboard (Vite/React) with the redacted data baked in.
Write-Host "==> Building web dashboard (npm run build)"
Push-Location (Join-Path $RepoRoot "web")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "web build failed (exit $LASTEXITCODE)" }
}
finally { Pop-Location }

$Dist = Join-Path $RepoRoot "web\dist"
if (-not (Test-Path (Join-Path $Dist "index.html"))) { throw "expected build output not found: $Dist\index.html" }

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

# 3. Publish web/dist to this repo's gh-pages branch via a persistent, single-branch
#    (gitignored) clone. Only this machine pushes there, so a plain push is safe, and
#    main is never touched.
$DashDir = Join-Path $RepoRoot ".dashboard-repo"
$Name  = "rinz0x0cruz"
$Email = "rinz0x0cruz@users.noreply.github.com"

if (-not (Test-Path (Join-Path $DashDir ".git"))) {
    git clone --quiet --branch $Branch --single-branch $Repo $DashDir
    if ($LASTEXITCODE -ne 0) { throw "clone of $Repo ($Branch) failed (is a credential cached?)" }
}

# Replace the published files with the fresh build (hashed asset names change per build).
Get-ChildItem $DashDir -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force
Copy-Item (Join-Path $Dist "*") $DashDir -Recurse -Force
New-Item -ItemType File -Path (Join-Path $DashDir ".nojekyll") -Force | Out-Null

Push-Location $DashDir
try {
    git checkout -q $Branch

    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "==> No changes to publish."
    } else {
        $stamp = (Get-Date).ToUniversalTime().ToString("o")
        git -c user.name=$Name -c user.email=$Email commit -q -m "chore: publish dashboard $stamp"
        if ($LASTEXITCODE -ne 0) { throw "commit failed" }
        git push -q origin $Branch
        if ($LASTEXITCODE -ne 0) { throw "push failed (is a credential cached / remote reachable?)" }
        Write-Host "==> Published -> https://rinz0x0cruz.github.io/jobscope/"
    }
}
finally {
    Pop-Location
}
