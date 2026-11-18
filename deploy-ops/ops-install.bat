@echo off
chcp 65001 >nul
REM Run as Administrator. Registers the headless service tasks (see ops-install.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ops-install.ps1" %*
echo.
pause
