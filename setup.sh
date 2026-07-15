#!/usr/bin/env bash
# jobscope setup (macOS / Linux)
set -euo pipefail

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv

echo "==> Activating"
# shellcheck disable=SC1091
. .venv/bin/activate

echo "==> Upgrading pip"
python -m pip install --upgrade pip

echo "==> Installing dependencies"
pip install -r requirements.lock

echo "==> Installing Chromium (Playwright) for PDF + assisted apply"
python -m playwright install chromium

echo "==> Scaffolding config + data dir"
python -m jobscope init

cat <<'EOF'

Done. Next: add your resume at data/resume.md, then:
  python -m jobscope resume import data/resume.md
  python -m jobscope scan && python -m jobscope match && python -m jobscope dashboard --open
EOF
