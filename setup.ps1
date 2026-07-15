# jobscope setup (Windows / PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "==> Creating virtualenv (.venv)"
python -m venv .venv

Write-Host "==> Activating"
. .\.venv\Scripts\Activate.ps1

Write-Host "==> Upgrading pip"
python -m pip install --upgrade pip

Write-Host "==> Installing dependencies"
pip install -r requirements.lock

Write-Host "==> Installing Chromium (Playwright) for PDF + assisted apply"
python -m playwright install chromium

Write-Host "==> Scaffolding config + data dir"
python -m jobscope init

Write-Host ""
Write-Host "Done. Next: add your resume at data\resume.md, then:"
Write-Host "  python -m jobscope resume import data\resume.md"
Write-Host "  python -m jobscope scan; python -m jobscope match; python -m jobscope dashboard --open"
