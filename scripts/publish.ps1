#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build the jobscope web dashboard and publish it (whole-app auth: the public
    build ships no data, only a passphrase-encrypted blob) to gh-pages / GitHub Pages.

.DESCRIPTION
    Whole-app auth: the public build ships NO data. `jobscope dashboard --emit-json
    --public` emits an empty shell (no rows, applications, profile, funnel, or search
    terms); the un-redacted payload is AES-256-GCM encrypted into a separate blob the
    SPA unlocks in-browser with your passphrase. -Encrypted is therefore REQUIRED --
    this script refuses to publish without it. Bakes the shell into the Vite/React app
    in web/, builds it, and publishes web/dist to this repo's `gh-pages` branch, served
    at https://rinz0x0cruz.github.io/jobscope/. `main` is never touched and your
    database/config never leave your machine.

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
    REQUIRED. Bake the end-to-end encrypted full dashboard into the SPA: AES-256-GCM
    over your un-redacted data, decrypted only in the browser with a passphrase you
    enter. Prompted for the passphrase (or set $env:JOBSCOPE_APPS_PASSPHRASE, or store
    it via `jobscope secrets set JOBSCOPE_APPS_PASSPHRASE`).

.EXAMPLE
    ./scripts/publish.ps1 -Encrypted

.EXAMPLE
    ./scripts/publish.ps1 -Refresh -Encrypted -Force   # one-click: refresh data, then publish
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

# Whole-app auth: the public build ships NO data -- only the passphrase-encrypted blob
# can reveal anything -- so a non-encrypted publish would be a dead, unopenable site.
# Require -Encrypted, and fail fast before doing any work.
if (-not $Encrypted) {
    throw 'Refusing to publish without encryption: since the whole-app-auth change the public build ships no data, so a non-encrypted publish would be a dead, unopenable site. Re-run with -Encrypted (set $env:JOBSCOPE_APPS_PASSPHRASE, or store it via: jobscope secrets set JOBSCOPE_APPS_PASSPHRASE).'
}

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

# 1. Emit the locked (empty) public payload and bake it into the web app.
Write-Host "==> Emitting the locked (empty) public dashboard JSON (jobscope dashboard --emit-json --public)"
& $Py -m jobscope dashboard --emit-json --public
if ($LASTEXITCODE -ne 0) { throw "jobscope dashboard --emit-json --public failed (exit $LASTEXITCODE)" }

$PublicJson = Join-Path $RepoRoot "data\dashboard.public.json"
if (-not (Test-Path $PublicJson)) { throw "expected payload not found: $PublicJson" }
Copy-Item $PublicJson (Join-Path $RepoRoot "web\src\data\dashboard.json") -Force

# 1b. Optional: bake an end-to-end encrypted applications blob into the SPA so the
#     Applications tab can decrypt it in-browser (AES-256-GCM, passphrase-gated). This
#     must run BEFORE the build so Vite bakes web/src/data/applications.encrypted.json
#     into the bundle. Always clear a stale blob first, so a plain redacted publish can
#     never ship one. The un-redacted data never leaves your machine in the clear --
#     only the encrypted blob is published -- so it is safe to host publicly.
$EncMarker = Join-Path $RepoRoot "web\src\data\applications.encrypted.json"  # baked pointer
$SiteBlob  = Join-Path $RepoRoot "data\site.enc.json"                        # heavy ciphertext (gitignored)
Remove-Item $EncMarker, $SiteBlob -Force -ErrorAction SilentlyContinue
if ($Encrypted) {
    Write-Host "==> Emitting un-redacted data + encrypting the full dashboard for the SPA"
    & $Py -m jobscope dashboard --emit-json   # -> data\dashboard.json (has applications; gitignored, local only)
    if ($LASTEXITCODE -ne 0) { throw "jobscope dashboard --emit-json failed (exit $LASTEXITCODE)" }
    $FullJson = Join-Path $RepoRoot "data\dashboard.json"
    if (-not (Test-Path $FullJson)) { throw "expected payload not found: $FullJson" }

    # Passphrase resolution: env var (unattended) -> OS keychain (jobscope secrets
    # set JOBSCOPE_APPS_PASSPHRASE) -> hidden interactive prompt. Never echoed,
    # logged, or committed. The keychain path lets a scheduled task publish the
    # encrypted apps with no prompt (see scripts/register-publish-secure-task.ps1).
    $plain = $env:JOBSCOPE_APPS_PASSPHRASE
    $bstr = [IntPtr]::Zero
    if ([string]::IsNullOrEmpty($plain)) {
        $plain = (& $Py -c "import keyring,sys;from jobscope.core.config import KEYRING_SERVICE as s;v=keyring.get_password(s,'JOBSCOPE_APPS_PASSPHRASE');sys.stdout.write(v or '')" 2>$null)
    }
    if ([string]::IsNullOrEmpty($plain)) {
        $sec = Read-Host "Passphrase to encrypt your applications (8+ chars)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    try {
        # "-" skips the retired standalone page; write the heavy ciphertext blob
        # that the SPA fetches lazily on unlock.
        # 2>&1 so Node's status line doesn't trip PS 5.1's stop-on-native-stderr; the
        # real exit code is still checked below.
        $plain | node (Join-Path $RepoRoot "scripts\build-secure-apps.mjs") $FullJson (Join-Path $RepoRoot "scripts\apps-template.html") "-" $SiteBlob 2>&1 | ForEach-Object { Write-Host "  $_" }
        if ($LASTEXITCODE -ne 0) { throw "encrypting the dashboard blob failed (exit $LASTEXITCODE)" }
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        Remove-Variable plain -ErrorAction SilentlyContinue
    }
    # Bake only a tiny pointer to the lazily-fetched blob (keeps the public bundle lean).
    Set-Content -Path $EncMarker -Value '{"v":1,"url":"site.enc.json"}' -Encoding utf8 -NoNewline
    Write-Host "==> Encrypted full dashboard -> unlock with the header lock button"
}

# 2. Build the web dashboard (Vite/React) with the redacted data (and, if -Encrypted,
#    the encrypted applications blob) baked in.
Write-Host "==> Building web dashboard (npm run build)"
Push-Location (Join-Path $RepoRoot "web")
try {
    # npm/Vite print progress and a benign lottie-web `eval` warning to stderr; under
    # ErrorActionPreference=Stop (e.g. Windows PowerShell 5.1, where the native-stderr
    # guard at the top is a no-op) that aborts the publish right before the push. Relax
    # it here and gate on the exit code instead (2>&1 merges stderr into the stream so
    # it just prints).
    $eapPrev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    npm run build 2>&1 | ForEach-Object { Write-Host $_ }
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $eapPrev
    if ($buildExit -ne 0) { throw "web build failed (exit $buildExit)" }
}
finally { Pop-Location }

$Dist = Join-Path $RepoRoot "web\dist"
if (-not (Test-Path (Join-Path $Dist "index.html"))) { throw "expected build output not found: $Dist\index.html" }

# Ship the heavy encrypted blob as a separate file next to the SPA (fetched lazily
# on unlock), so the public bundle never carries the un-redacted ciphertext.
if ($Encrypted -and (Test-Path $SiteBlob)) {
    Copy-Item $SiteBlob (Join-Path $Dist "site.enc.json") -Force
    Write-Host "==> Bundled encrypted blob -> $Dist\site.enc.json (lazy-fetched on unlock)"
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

# Sync the persistent clone to the remote head before rebuilding on top. Another
# publisher (e.g. the cloud refresh Action) may have pushed to $Branch since our last
# publish; without this our push would be a non-fast-forward and get rejected. gh-pages
# is a disposable build artifact, so hard-resetting to origin is always safe.
Push-Location $DashDir
$eapSync = $ErrorActionPreference
$ErrorActionPreference = "Continue"
git fetch --quiet origin $Branch 2>&1 | ForEach-Object { Write-Host $_ }
git checkout -q $Branch 2>&1 | ForEach-Object { Write-Host $_ }
git reset --hard "origin/$Branch" 2>&1 | ForEach-Object { Write-Host $_ }
$ErrorActionPreference = $eapSync
Pop-Location

# Replace the published files with the fresh build (hashed asset names change per
# build). Encrypted applications are now baked into the SPA (Applications tab), so the
# retired standalone applications.html is cleared from gh-pages on the next publish.
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

    # Selective staging per AGENTS.md: `git add .` stages the wholesale build replacement
    # (new + modified + removed old hashed assets; git >=2.0 stages removals), scoped to this
    # dedicated, gitignored gh-pages clone. The source tree is never blanket-staged.
    git add . 2>&1 | ForEach-Object { Write-Host $_ }
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
