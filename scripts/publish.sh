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
