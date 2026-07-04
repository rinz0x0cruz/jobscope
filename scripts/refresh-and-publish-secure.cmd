@echo off
REM ============================================================================
REM  jobscope - one-click SECURE publish (redacted dashboard + encrypted apps).
REM
REM  Double-click to refresh your applications (rescore + inbox sync -- NO
REM  job-board scan, so no rate-limit/429 stalls before the prompt), rebuild the
REM  redacted public dashboard, AND publish an end-to-end encrypted
REM  applications.html. You are prompted for a passphrase (hidden as you type).
REM  The un-redacted data is AES-256-GCM encrypted and only decrypts in your
REM  browser with that passphrase, so you can open it on your phone at
REM      https://rinz0x0cruz.github.io/jobscope/applications.html
REM
REM  Use a LONG passphrase (e.g. 4-5 random words) -- offline, it is the only
REM  thing protecting your application history.
REM  (Need fresh JOB listings too? run `scripts\publish.ps1 -Refresh -Encrypted
REM   -Force` when you are not being rate-limited.)
REM ============================================================================
setlocal
cd /d "%~dp0.."
where pwsh >nul 2>nul && (set "PSEXE=pwsh") || (set "PSEXE=powershell")
"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" -Refresh -NoScan -Encrypted -Force
echo.
echo Done. Dashboard:            https://rinz0x0cruz.github.io/jobscope/
echo Applications (passphrase):  https://rinz0x0cruz.github.io/jobscope/applications.html
pause
endlocal
