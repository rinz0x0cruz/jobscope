#!/usr/bin/env bash
# Build the redacted jobscope web dashboard and publish it to jobscope's own gh-pages
# branch for GitHub Pages, served at https://rinz0x0cruz.github.io/jobscope/. Emits a
# redacted payload, bakes it into the Vite/React app (web/), builds it, and publishes
# web/dist. Only the redacted build is published; main is never touched and your
# database/config never leave your machine. Requires Node.js/npm. Commits use the
# rinz0x0cruz identity.
#
# Usage: scripts/publish.sh [--refresh] [--no-scan] [--encrypted] [--force] [repo-url] [branch]
#   --refresh    rerun scan -> match -> inbox first (fresh data on the published site)
#   --no-scan    with --refresh, skip the slow job scan (rescore + inbox only)
#   --encrypted  also bake an AES-256-GCM encrypted applications blob into the Applications tab (passphrase in browser)
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

# 1. Emit the redacted dashboard payload and bake it into the web app.
echo "==> Emitting redacted dashboard JSON (jobscope dashboard --emit-json --public)"
"$PY" -m jobscope dashboard --emit-json --public

PUBLIC_JSON="$REPO_ROOT/data/dashboard.public.json"
[ -f "$PUBLIC_JSON" ] || { echo "expected payload not found: $PUBLIC_JSON" >&2; exit 1; }
cp "$PUBLIC_JSON" "$REPO_ROOT/web/src/data/dashboard.json"

# 1b. Optional: bake an end-to-end encrypted applications blob into the SPA so the
#     Applications tab can decrypt it in-browser (AES-256-GCM, passphrase-gated). Must
#     run BEFORE the build so Vite bakes web/src/data/applications.encrypted.json into
#     the bundle. Clear a stale blob first so a plain redacted publish can't ship one.
#     The un-redacted data never leaves the machine in the clear -- only the encrypted
#     blob is published.
ENC_BLOB_JSON="$REPO_ROOT/web/src/data/applications.encrypted.json"
rm -f "$ENC_BLOB_JSON"
if [ -n "${ENCRYPTED:-}" ]; then
    echo "==> Emitting un-redacted data + encrypting applications for the SPA"
    "$PY" -m jobscope dashboard --emit-json   # -> data/dashboard.json (has applications; gitignored)
    FULL_JSON="$REPO_ROOT/data/dashboard.json"
    [ -f "$FULL_JSON" ] || { echo "expected payload not found: $FULL_JSON" >&2; exit 1; }
    PASS="${JOBSCOPE_APPS_PASSPHRASE:-}"
    if [ -z "$PASS" ]; then
        read -r -s -p "Passphrase to encrypt your applications (8+ chars): " PASS; echo
    fi
    # "-" skips the retired standalone page; write only the JSON blob the SPA imports.
    printf '%s' "$PASS" | node "$REPO_ROOT/scripts/build-secure-apps.mjs" "$FULL_JSON" "$REPO_ROOT/scripts/apps-template.html" "-" "$ENC_BLOB_JSON"
    unset PASS
    echo "==> Encrypted applications baked in -> unlock in the Applications tab"
fi

# 2. Build the web dashboard (Vite/React) with the redacted data (and, if --encrypted,
#    the encrypted applications blob) baked in.
echo "==> Building web dashboard (npm run build)"
( cd "$REPO_ROOT/web" && npm run build )

DIST="$REPO_ROOT/web/dist"
[ -f "$DIST/index.html" ] || { echo "expected build output not found: $DIST/index.html" >&2; exit 1; }

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
git add -A
if git diff --cached --quiet; then
    echo "==> No changes to publish."
else
    git -c user.name="$NAME" -c user.email="$EMAIL" \
        commit -q -m "chore: publish dashboard $(date -u +%FT%TZ)"
    git push -q origin "$BRANCH"
    echo "==> Published -> https://rinz0x0cruz.github.io/jobscope/"
fi
