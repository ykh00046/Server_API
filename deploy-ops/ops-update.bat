@echo off
REM Manual run of the watch + auto deploy step (the scheduled task calls ops-update.ps1
REM directly). Result: deploy-ops\update.log
REM One line on purpose: cmd parses it whole, so a pull that rewrites this file cannot
REM make cmd resume in the middle of new content.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ops-update.ps1" %* & exit /b
