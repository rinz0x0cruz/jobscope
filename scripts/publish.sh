#!/usr/bin/env bash
# Render the redacted jobscope dashboard and publish it to the public
# jobscope-dashboard repo for GitHub Pages (mobile-viewable). The jobscope code repo
# can stay private; only the redacted snapshot is public, in a repo with a clean
# history. Your database/packages never leave your machine. Commits use the
# rinz0x0cruz identity.
#
# Usage: scripts/publish.sh [repo-url] [branch]
#   defaults: https://github.com/rinz0x0cruz/jobscope-dashboard.git  main
set -euo pipefail

# Force support: a --force flag (stripped here before positional parsing) or
# JOBSCOPE_PUBLISH_FORCE=1 bypasses the publish gate below.
FORCE="${JOBSCOPE_PUBLISH_FORCE:-}"
POSITIONAL=()
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done
set -- "${POSITIONAL[@]+"${POSITIONAL[@]}"}"

REPO="${1:-https://github.com/rinz0x0cruz/jobscope-dashboard.git}"
BRANCH="${2:-main}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# 1. Render the redacted dashboard.
echo "==> Rendering redacted dashboard (jobscope dashboard --public)"
PYTHONPATH=. "$PY" -m jobscope dashboard --public

PUBLIC_HTML="$REPO_ROOT/data/public-dashboard.html"
[ -f "$PUBLIC_HTML" ] || { echo "expected dashboard not found: $PUBLIC_HTML" >&2; exit 1; }

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

# 2. Publish index.html to the separate public dashboard repo via a persistent
#    (gitignored) clone. Only this machine pushes there, so a plain push is safe.
DASH_DIR="$REPO_ROOT/.dashboard-repo"
NAME="rinz0x0cruz"
EMAIL="rinz0x0cruz@users.noreply.github.com"

if [ ! -d "$DASH_DIR/.git" ]; then
    git clone --quiet "$REPO" "$DASH_DIR"
fi

cp "$PUBLIC_HTML" "$DASH_DIR/index.html"
touch "$DASH_DIR/.nojekyll"

cd "$DASH_DIR"
# Ensure we're on $BRANCH (create it on the first publish to an empty repo).
git checkout -q "$BRANCH" 2>/dev/null || git checkout -q -B "$BRANCH"
git add -A
if git diff --cached --quiet; then
    echo "==> No changes to publish."
else
    git -c user.name="$NAME" -c user.email="$EMAIL" \
        commit -q -m "chore: publish dashboard $(date -u +%FT%TZ)"
    git push -q -u origin "$BRANCH"
    echo "==> Published to $REPO ($BRANCH)."
fi
