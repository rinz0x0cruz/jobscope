#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Render the redacted jobscope dashboard and publish it to the gh-pages branch
    so it is viewable from a phone via GitHub Pages.

.DESCRIPTION
    Runs `jobscope dashboard --public` to produce a redacted, self-contained HTML
    (no referral contacts, application funnel, or search terms), then copies it as
    index.html onto an orphan `gh-pages` branch through a throwaway git worktree and
    pushes it. Your database and packages stay local; only the redacted snapshot
    reaches GitHub.

    Safe to run from a scheduled task. Commits use the local rinz0x0cruz identity so
    a global (work) git identity never leaks into gh-pages history.

.PARAMETER Branch
    Branch that GitHub Pages serves from. Default "gh-pages".

.PARAMETER Remote
    Git remote to push to. Default "origin".

.EXAMPLE
    ./scripts/publish.ps1
#>
[CmdletBinding()]
param(
    [string]$Branch = "gh-pages",
    [string]$Remote = "origin"
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

# 2. Publish to gh-pages through a detached worktree so `main` is never disturbed.
$WorkTree = Join-Path $RepoRoot ".gh-pages"
$Name  = "rinz0x0cruz"
$Email = "rinz0x0cruz@users.noreply.github.com"

# Clean any stale worktree left by an interrupted run.
if (Test-Path $WorkTree) {
    git worktree remove --force $WorkTree 2>$null
    if (Test-Path $WorkTree) { Remove-Item -Recurse -Force $WorkTree -ErrorAction SilentlyContinue }
}

git show-ref --verify --quiet "refs/heads/$Branch"
$branchExists = ($LASTEXITCODE -eq 0)

try {
    if ($branchExists) {
        git worktree add --quiet $WorkTree $Branch
        if ($LASTEXITCODE -ne 0) { throw "git worktree add failed" }
    } else {
        git worktree add --quiet --detach $WorkTree HEAD
        if ($LASTEXITCODE -ne 0) { throw "git worktree add (detach) failed" }
        Push-Location $WorkTree
        git checkout --orphan $Branch
        git rm -rf --quiet . 2>$null
        Pop-Location
    }

    # Publish exactly { index.html, .nojekyll }.
    Get-ChildItem -Path $WorkTree -Force |
        Where-Object { $_.Name -ne ".git" } |
        Remove-Item -Recurse -Force
    Copy-Item $PublicHtml (Join-Path $WorkTree "index.html") -Force
    New-Item -ItemType File -Path (Join-Path $WorkTree ".nojekyll") -Force | Out-Null

    Push-Location $WorkTree
    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "==> No changes to publish."
    } else {
        $stamp = (Get-Date).ToUniversalTime().ToString("o")
        git -c user.name=$Name -c user.email=$Email commit -q -m "chore: publish dashboard $stamp"
        if ($LASTEXITCODE -ne 0) { Pop-Location; throw "commit failed" }
        git push -q $Remote $Branch
        if ($LASTEXITCODE -ne 0) { Pop-Location; throw "push failed (is a credential cached / remote reachable?)" }
        Write-Host "==> Published to $Remote/$Branch."
    }
    Pop-Location
}
finally {
    git worktree remove --force $WorkTree 2>$null
    if (Test-Path $WorkTree) { Remove-Item -Recurse -Force $WorkTree -ErrorAction SilentlyContinue }
}
