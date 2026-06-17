@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Production Hub - Update and Restart

REM Pull latest pushed code, sync submodule + deps, then restart headless.
REM Local gitignored files (.env, api/.../*_settings.json, database/) are preserved.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [1/4] git pull (fast-forward only)...
git pull --ff-only
if errorlevel 1 (
    echo [ERROR] git pull failed - resolve local changes/divergence and retry.
    pause
    exit /b 1
)

echo [2/4] submodule update (webcloring-pdf)...
git submodule update --init --recursive

echo [3/4] dependencies (requirements.lock.txt)...
"%PY%" -m pip install -r requirements.lock.txt -q

echo [4/4] restart...
call stop.bat
call start.bat

echo.
echo [OK] Updated to latest and restarted.
