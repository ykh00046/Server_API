@echo off
chcp 65001 > nul
title Production Hub - Stop

REM Headless stop: kill processes listening on API(8000) / Dashboard(8502).

echo Stopping Production Hub - API 8000 / Dashboard 8502 ...
set "FOUND="
for %%P in (8000 8502) do (
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do (
        taskkill /PID %%A /F >nul 2>&1 && (
            echo   port %%P PID %%A stopped
            set "FOUND=1"
        )
    )
)
if not defined FOUND echo   nothing listening on 8000/8502
echo Done.
