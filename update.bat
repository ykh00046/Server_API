@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Production Hub - Update
set "ROOT=%~dp0"

REM Stop THIS repo's processes (manager + API/Portal), pull latest,
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
REM The bot's live config (webcloring-pdf\src\config\config.json) was a tracked
REM file until 2026-10-08 and the manager writes jobs into it, so on an ops PC it
REM is always "modified" and `git submodule update` refuses the checkout. Park a
REM copy, reset the tracked file, update, then put the live copy back (the new
REM revision ignores config.json and ships config.example.json instead).
set "BOTCFG=webcloring-pdf\src\config\config.json"
set "BOTCFG_BAK=webcloring-pdf\src\config\config.json.live.bak"
git -C webcloring-pdf ls-files --error-unmatch src/config/config.json >nul 2>&1
if not errorlevel 1 (
    git -C webcloring-pdf diff --quiet -- src/config/config.json
    if errorlevel 1 (
        echo   bot config.json has local edits - keeping a copy and resetting the tracked file...
        copy /Y "%BOTCFG%" "%BOTCFG_BAK%" >nul
        git -C webcloring-pdf checkout -- src/config/config.json
    )
)
git submodule update --init --recursive
if errorlevel 1 (
    echo [ERROR] submodule update failed - the bot is still on the OLD revision.
    echo         Run: git -C webcloring-pdf status   and resolve, then re-run update.bat
    pause
    exit /b 1
)
if exist "%BOTCFG_BAK%" (
    if not exist "%BOTCFG%" (
        move /Y "%BOTCFG_BAK%" "%BOTCFG%" >nul
        echo   bot config.json restored from the local copy ^(now untracked^).
    ) else (
        echo   NOTE: %BOTCFG_BAK% kept - config.json already present.
    )
)
"%PY%" -m pip install -r requirements.lock.txt -q

echo.
echo [OK] Updated. Now run manager.bat to start.
pause
