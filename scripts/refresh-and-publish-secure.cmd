@echo off
REM ============================================================================
REM  jobscope - one-click SECURE publish (redacted dashboard + encrypted apps).
REM
REM  Double-click to publish your end-to-end encrypted applications into the
REM  dashboard's Applications tab from your CURRENT data. It makes NO scan, NO
REM  match, and NO inbox/AI calls, so nothing can rate-limit (429) you before the
REM  prompt -- it just rebuilds the redacted public dashboard with the encrypted
REM  applications blob baked in, then asks for a passphrase (hidden as you type).
REM  The un-redacted data is AES-256-GCM encrypted and only decrypts in your
REM  browser with that passphrase, so you can open it on your phone at
REM      https://rinz0x0cruz.github.io/jobscope/  (Applications tab)
REM
REM  Use a LONG passphrase (e.g. 4-5 random words) -- offline, it is the only
REM  thing protecting your application history.
REM  (Want to pull fresh jobs/emails first? run `scripts\publish.ps1 -Refresh
REM   -Encrypted -Force` -- but that makes scan + AI calls that can 429 on a
REM   busy free-tier key.)
REM ============================================================================
setlocal
cd /d "%~dp0.."
where pwsh >nul 2>nul && (set "PSEXE=pwsh") || (set "PSEXE=powershell")
"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" -Encrypted -Force
echo.
echo Done. Dashboard:            https://rinz0x0cruz.github.io/jobscope/
echo Applications (passphrase):  https://rinz0x0cruz.github.io/jobscope/  (Applications tab)
pause
endlocal
