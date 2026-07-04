@echo off
REM ============================================================================
REM  jobscope - one-click "rerun the tool" button.
REM
REM  Double-click to refresh your data (scan -> match -> inbox), rebuild the
REM  redacted dashboard, and publish it to GitHub Pages in one step. Everything
REM  runs locally; your applications are redacted from the public site and stay
REM  visible only in your local "jobscope dashboard" view.
REM
REM  Tip: right-click -> Send to -> Desktop (create shortcut) to pin it, or pin
REM  the shortcut to the taskbar for a real button.
REM ============================================================================
setlocal
cd /d "%~dp0.."
where pwsh >nul 2>nul && (set "PSEXE=pwsh") || (set "PSEXE=powershell")
"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1" -Refresh -Force
echo.
echo Done. Live dashboard: https://rinz0x0cruz.github.io/jobscope/
pause
endlocal
