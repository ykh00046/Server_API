@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Production Hub - Update
set "ROOT=%~dp0"

REM Stop THIS repo's processes (manager + API/Dashboard/Portal), pull latest,
REM sync deps. Then start with manager.bat. Gitignored files (.env,
REM *_settings.json, database/) are preserved. Other projects are not touched.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/4] stop this repo's manager + services...
powershell -NoProfile -Command "$r=[regex]::Escape(($env:ROOT).TrimEnd('\')); Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -match $r } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [2/4] git pull (fast-forward only)...
git pull --ff-only
if errorlevel 1 (
    echo [ERROR] git pull failed - resolve local changes/divergence and retry.
    pause
    exit /b 1
)

echo [3/4] submodule + dependencies...
git submodule update --init --recursive
"%PY%" -m pip install -r requirements.lock.txt -q

echo.
echo [OK] Updated. Now run manager.bat to start.
pause
