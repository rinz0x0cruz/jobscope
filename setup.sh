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

echo "==> Scaffolding config + data dir"
python -m jobscope init

cat <<'EOF'

Done. Next: add your resume at data/resume.md, then:
  python -m jobscope resume import data/resume.md
  python -m jobscope scan && python -m jobscope match && python -m jobscope dashboard --open

Optional, to keep secrets in the OS keychain instead of a file
(Gmail sync, publish passphrase and outreach read them from there):
  pip install keyring && python -m jobscope secrets set JOBSCOPE_GMAIL_APP_PW

Optional, only for PDF export and 'apply --assist' (~200MB):
  pip install playwright==1.40.0 && python -m playwright install chromium
EOF
