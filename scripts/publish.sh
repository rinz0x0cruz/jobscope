#!/usr/bin/env bash
# Render the redacted jobscope dashboard and publish it to gh-pages for GitHub Pages
# (mobile-viewable). Your database and packages stay local; only the redacted
# snapshot reaches GitHub. Commits use the rinz0x0cruz identity so a global (work)
# git identity never leaks into gh-pages history.
#
# Usage: scripts/publish.sh [branch] [remote]   (defaults: gh-pages origin)
set -euo pipefail

BRANCH="${1:-gh-pages}"
REMOTE="${2:-origin}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# 1. Render the redacted dashboard.
echo "==> Rendering redacted dashboard (jobscope dashboard --public)"
PYTHONPATH=. "$PY" -m jobscope dashboard --public

PUBLIC_HTML="$REPO_ROOT/data/public-dashboard.html"
[ -f "$PUBLIC_HTML" ] || { echo "expected dashboard not found: $PUBLIC_HTML" >&2; exit 1; }

# 2. Publish to gh-pages through a detached worktree so `main` is never disturbed.
WORKTREE="$REPO_ROOT/.gh-pages"
NAME="rinz0x0cruz"
EMAIL="rinz0x0cruz@users.noreply.github.com"

cleanup() {
    git worktree remove --force "$WORKTREE" 2>/dev/null || true
    rm -rf "$WORKTREE"
}
# Clean any stale worktree left by an interrupted run, then on exit.
cleanup
trap cleanup EXIT

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git worktree add --quiet "$WORKTREE" "$BRANCH"
else
    git worktree add --quiet --detach "$WORKTREE" HEAD
    ( cd "$WORKTREE" && git checkout --orphan "$BRANCH" && git rm -rf --quiet . >/dev/null 2>&1 || true )
fi

# Publish exactly { index.html, .nojekyll }.
find "$WORKTREE" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp "$PUBLIC_HTML" "$WORKTREE/index.html"
touch "$WORKTREE/.nojekyll"

cd "$WORKTREE"
git add -A
if git diff --cached --quiet; then
    echo "==> No changes to publish."
else
    git -c user.name="$NAME" -c user.email="$EMAIL" \
        commit -q -m "chore: publish dashboard $(date -u +%FT%TZ)"
    git push -q "$REMOTE" "$BRANCH"
    echo "==> Published to $REMOTE/$BRANCH."
fi
