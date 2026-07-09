#!/usr/bin/env bash
# Build the jobscope web dashboard and publish it to jobscope's own gh-pages branch for
# GitHub Pages, served at https://rinz0x0cruz.github.io/jobscope/. Whole-app auth: the
# published build ships NO data -- an empty shell plus an AES-256-GCM blob that only your
# passphrase can unlock in-browser -- so --encrypted is REQUIRED (this script refuses to
# publish without it). Bakes the shell into the Vite/React app (web/), builds it, and
# publishes web/dist. main is never touched and your database/config never leave your
# machine. Requires Node.js/npm. Commits use the rinz0x0cruz identity.
#
# Usage: scripts/publish.sh [--refresh] [--no-scan] [--encrypted] [--force] [repo-url] [branch]
#   --refresh    rerun scan -> match -> inbox first (fresh data on the published site)
#   --no-scan    with --refresh, skip the slow job scan (rescore + inbox only)
#   --encrypted  REQUIRED: bake the AES-256-GCM encrypted full dashboard the site unlocks with your passphrase (in-browser)
#   defaults: https://github.com/rinz0x0cruz/jobscope.git  gh-pages
set -euo pipefail

# Force support: a --force flag (stripped here before positional parsing) or
# JOBSCOPE_PUBLISH_FORCE=1 bypasses the publish gate below.
FORCE="${JOBSCOPE_PUBLISH_FORCE:-}"
REFRESH=""
NOSCAN=""
ENCRYPTED=""
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --refresh) REFRESH=1 ;;
        --no-scan) NOSCAN=1 ;;
        --encrypted) ENCRYPTED=1 ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done
set -- "${POSITIONAL[@]+"${POSITIONAL[@]}"}"

REPO="${1:-https://github.com/rinz0x0cruz/jobscope.git}"
BRANCH="${2:-gh-pages}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
export PYTHONPATH=.

# Whole-app auth: the public build ships NO data -- only the passphrase-encrypted blob
# can reveal anything -- so a non-encrypted publish would be a dead, unopenable site.
# Require --encrypted, and fail fast before doing any work.
if [ -z "${ENCRYPTED:-}" ]; then
    {
        echo "error: refusing to publish without encryption."
        echo "  Since the whole-app-auth change the public build ships no data, so a"
        echo "  non-encrypted publish would be a dead, unopenable site. Re-run with --encrypted"
        echo "  (set JOBSCOPE_APPS_PASSPHRASE, or store it: jobscope secrets set JOBSCOPE_APPS_PASSPHRASE)."
    } >&2
    exit 2
fi

# 0. Optional data refresh: rerun the pipeline so the published site reflects the latest
#    jobs and application emails. --refresh runs scan -> match -> inbox first; --no-scan
#    skips the slow networked job scan and just rescores + syncs the inbox.
if [ -n "${REFRESH:-}" ]; then
    if [ -z "${NOSCAN:-}" ]; then
        echo "==> Scanning job boards (jobscope scan)"
        "$PY" -m jobscope scan
    fi
    echo "==> Rescoring matches (jobscope match)"
    "$PY" -m jobscope match
    echo "==> Syncing inbox (jobscope inbox)"
    "$PY" -m jobscope inbox
fi

# 1. Emit the locked (empty) public payload and bake it into the web app.
echo "==> Emitting the locked (empty) public dashboard JSON (jobscope dashboard --emit-json --public)"
"$PY" -m jobscope dashboard --emit-json --public

PUBLIC_JSON="$REPO_ROOT/data/dashboard.public.json"
[ -f "$PUBLIC_JSON" ] || { echo "expected payload not found: $PUBLIC_JSON" >&2; exit 1; }
cp "$PUBLIC_JSON" "$REPO_ROOT/web/src/data/dashboard.json"

# 1b. Optional: encrypt the FULL un-redacted dashboard for the whole-site unlock.
#     The heavy ciphertext ships as a separate lazily-fetched file (dist/site.enc.json);
#     only a tiny pointer is baked into the bundle (before the build), so the public
#     redacted build stays lean. Clear stale artifacts first so a plain redacted publish
#     can't ship one. The un-redacted data never leaves the machine in the clear -- only
#     the AES-256-GCM ciphertext (useless without the passphrase) is published.
ENC_MARKER="$REPO_ROOT/web/src/data/applications.encrypted.json"  # baked pointer
SITE_BLOB="$REPO_ROOT/data/site.enc.json"                          # heavy ciphertext (gitignored)
rm -f "$ENC_MARKER" "$SITE_BLOB"
if [ -n "${ENCRYPTED:-}" ]; then
    echo "==> Emitting un-redacted data + encrypting the full dashboard for the SPA"
    "$PY" -m jobscope dashboard --emit-json   # -> data/dashboard.json (has applications; gitignored)
    FULL_JSON="$REPO_ROOT/data/dashboard.json"
    [ -f "$FULL_JSON" ] || { echo "expected payload not found: $FULL_JSON" >&2; exit 1; }
    PASS="${JOBSCOPE_APPS_PASSPHRASE:-}"
    if [ -z "$PASS" ]; then
        read -r -s -p "Passphrase to encrypt your applications (8+ chars): " PASS; echo
    fi
    # "-" skips the retired standalone page; write the heavy ciphertext blob the SPA fetches lazily.
    printf '%s' "$PASS" | node "$REPO_ROOT/scripts/build-secure-apps.mjs" "$FULL_JSON" "$REPO_ROOT/scripts/apps-template.html" "-" "$SITE_BLOB"
    unset PASS
    # Bake only a tiny pointer to the lazily-fetched blob (keeps the public bundle lean).
    printf '%s' '{"v":1,"url":"site.enc.json"}' > "$ENC_MARKER"
    echo "==> Encrypted full dashboard -> unlock with the header lock button"
fi

# 2. Build the web dashboard (Vite/React) with the redacted data (and, if --encrypted,
#    the encrypted applications blob) baked in.
echo "==> Building web dashboard (npm run build)"
( cd "$REPO_ROOT/web" && npm run build )

DIST="$REPO_ROOT/web/dist"
[ -f "$DIST/index.html" ] || { echo "expected build output not found: $DIST/index.html" >&2; exit 1; }

# Ship the heavy encrypted blob as a separate file next to the SPA (fetched lazily
# on unlock), so the public bundle never carries the un-redacted ciphertext.
if [ -n "${ENCRYPTED:-}" ] && [ -f "$SITE_BLOB" ]; then
    cp "$SITE_BLOB" "$DIST/site.enc.json"
    echo "==> Bundled encrypted blob -> $DIST/site.enc.json (lazy-fetched on unlock)"
fi

# Publish gate: only the designated publisher (the machine that ran
# register-publish-task.ps1, which wrote .publish-primary) pushes, to avoid double
# git pushes. Rendering above always runs; only the push below is gated. Use --force
# (or JOBSCOPE_PUBLISH_FORCE=1) to override.
MARKER="$REPO_ROOT/.publish-primary"
if [ -z "${FORCE:-}" ]; then
    if [ ! -f "$MARKER" ]; then echo "==> Not the designated publisher (no .publish-primary marker). Skipping push. Run scripts/register-publish-task.ps1 (or create the marker) here, or pass --force."; exit 0; fi
    MHOST="$(head -n1 "$MARKER" | tr -d '[:space:]')"
    HOSTN="$(hostname)"
    if [ -n "$MHOST" ] && [ "$MHOST" != "$HOSTN" ]; then echo "==> Marker names '$MHOST', not this machine '$HOSTN'. Skipping push. Pass --force to override."; exit 0; fi
fi

# 3. Publish web/dist to this repo's gh-pages branch via a persistent, single-branch
#    (gitignored) clone. Only this machine pushes there, so a plain push is safe, and
#    main is never touched.
DASH_DIR="$REPO_ROOT/.dashboard-repo"
NAME="rinz0x0cruz"
EMAIL="rinz0x0cruz@users.noreply.github.com"

if [ ! -d "$DASH_DIR/.git" ]; then
    git clone --quiet --branch "$BRANCH" --single-branch "$REPO" "$DASH_DIR"
fi

# Replace the published files with the fresh build (hashed asset names change per build).
find "$DASH_DIR" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -R "$DIST/." "$DASH_DIR/"
touch "$DASH_DIR/.nojekyll"

cd "$DASH_DIR"
git checkout -q "$BRANCH"
# Selective staging per AGENTS.md: `git add .` stages the wholesale build replacement
# (new + modified + removed old hashed assets; git >=2.0 stages removals), scoped to this
# dedicated, gitignored gh-pages clone. The source tree is never blanket-staged.
git add .
if git diff --cached --quiet; then
    echo "==> No changes to publish."
else
    git -c user.name="$NAME" -c user.email="$EMAIL" \
        commit -q -m "chore: publish dashboard $(date -u +%FT%TZ)"
    git push -q origin "$BRANCH"
    echo "==> Published -> https://rinz0x0cruz.github.io/jobscope/"
fi
