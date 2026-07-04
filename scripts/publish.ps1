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

.PARAMETER Refresh
    Rerun the local pipeline (scan -> match -> inbox) before building, so the published
    site reflects the latest jobs and application emails.

.PARAMETER NoScan
    With -Refresh, skip the slow networked job scan; only rescore matches and sync the
    inbox (a fast, applications-focused refresh).

.PARAMETER Encrypted
    Also publish an end-to-end encrypted applications page (web/dist/applications.html):
    AES-256-GCM over your un-redacted applications, decrypted only in the browser with a
    passphrase you enter. Prompted for the passphrase (or set $env:JOBSCOPE_APPS_PASSPHRASE).

.EXAMPLE
    ./scripts/publish.ps1

.EXAMPLE
    ./scripts/publish.ps1 -Refresh -Force   # one-click: refresh data, then publish

.EXAMPLE
    ./scripts/publish.ps1 -Refresh -Encrypted -Force   # + encrypted applications page
#>
[CmdletBinding()]
param(
    [string]$Repo = "https://github.com/rinz0x0cruz/jobscope.git",
    [string]$Branch = "gh-pages",
    [switch]$Refresh,
    [switch]$NoScan,
    [switch]$Encrypted,
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
$env:PYTHONPATH = "."

# 0. Optional data refresh: rerun the pipeline so the published site reflects the latest
#    jobs and application emails. -Refresh runs scan -> match -> inbox first; -NoScan
#    skips the slow networked job scan and just rescores + syncs the inbox.
if ($Refresh) {
    if (-not $NoScan) {
        Write-Host "==> Scanning job boards (jobscope scan)"
        & $Py -m jobscope scan
        if ($LASTEXITCODE -ne 0) { throw "jobscope scan failed (exit $LASTEXITCODE)" }
    }
    Write-Host "==> Rescoring matches (jobscope match)"
    & $Py -m jobscope match
    if ($LASTEXITCODE -ne 0) { throw "jobscope match failed (exit $LASTEXITCODE)" }
    Write-Host "==> Syncing inbox (jobscope inbox)"
    & $Py -m jobscope inbox
    if ($LASTEXITCODE -ne 0) { throw "jobscope inbox failed (exit $LASTEXITCODE)" }
}

# 1. Emit the redacted dashboard payload and bake it into the web app.
Write-Host "==> Emitting redacted dashboard JSON (jobscope dashboard --emit-json --public)"
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

# 2b. Optional: an end-to-end encrypted applications page (AES-256-GCM, decrypted only in
#     your browser with a passphrase). The un-redacted data never leaves your machine in
#     the clear -- only the encrypted blob is published -- so it is safe to host publicly.
if ($Encrypted) {
    Write-Host "==> Emitting un-redacted data + encrypting applications.html"
    & $Py -m jobscope dashboard --emit-json   # -> data\dashboard.json (has applications; gitignored, local only)
    if ($LASTEXITCODE -ne 0) { throw "jobscope dashboard --emit-json failed (exit $LASTEXITCODE)" }
    $FullJson = Join-Path $RepoRoot "data\dashboard.json"
    if (-not (Test-Path $FullJson)) { throw "expected payload not found: $FullJson" }

    # Passphrase via env var (scheduled runs) or a hidden prompt. Never echoed, logged, or committed.
    $plain = $env:JOBSCOPE_APPS_PASSPHRASE
    $bstr = [IntPtr]::Zero
    if ([string]::IsNullOrEmpty($plain)) {
        $sec = Read-Host "Passphrase to encrypt applications.html (8+ chars)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    try {
        # 2>&1 so Node's status line doesn't trip PS 5.1's stop-on-native-stderr; the
        # real exit code is still checked below.
        $plain | node (Join-Path $RepoRoot "scripts\build-secure-apps.mjs") $FullJson (Join-Path $RepoRoot "scripts\apps-template.html") (Join-Path $Dist "applications.html") 2>&1 | ForEach-Object { Write-Host "  $_" }
        if ($LASTEXITCODE -ne 0) { throw "encrypting applications.html failed (exit $LASTEXITCODE)" }
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        Remove-Variable plain -ErrorAction SilentlyContinue
    }
    Write-Host "==> applications.html built -> unlock at https://rinz0x0cruz.github.io/jobscope/applications.html"
}

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
    git clone --quiet --branch $Branch --single-branch $Repo $DashDir 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "clone of $Repo ($Branch) failed (is a credential cached?)" }
}

# Replace the published files with the fresh build (hashed asset names change per build).
Get-ChildItem $DashDir -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force
Copy-Item (Join-Path $Dist "*") $DashDir -Recurse -Force
New-Item -ItemType File -Path (Join-Path $DashDir ".nojekyll") -Force | Out-Null

Push-Location $DashDir
# git writes warnings (LF/CRLF) and push status to stderr; under Windows PowerShell 5.1
# with ErrorActionPreference=Stop that aborts the script, so relax it here and gate on
# $LASTEXITCODE instead (2>&1 merges stderr into the output stream so it just prints).
$eapPrev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    git checkout -q $Branch 2>&1 | ForEach-Object { Write-Host $_ }

    git add -A 2>&1 | ForEach-Object { Write-Host $_ }
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "==> No changes to publish."
    } else {
        $stamp = (Get-Date).ToUniversalTime().ToString("o")
        git -c user.name=$Name -c user.email=$Email commit -q -m "chore: publish dashboard $stamp" 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { throw "commit failed" }
        git push -q origin $Branch 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { throw "push failed (is a credential cached / remote reachable?)" }
        Write-Host "==> Published -> https://rinz0x0cruz.github.io/jobscope/"
    }
}
finally {
    $ErrorActionPreference = $eapPrev
    Pop-Location
}
