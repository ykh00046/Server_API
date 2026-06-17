@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Production Hub - Start (Headless)

REM Headless run: API + Dashboard, no GUI. Minimized windows so logs are visible.
REM Windowless autostart: use start_hidden.vbs. Stop: stop.bat.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ================================================
echo  Production Hub - Headless [no GUI]
echo  API       : http://localhost:8000/docs
echo  Dashboard : http://localhost:8502
echo  Stop      : stop.bat
echo ================================================

start "Production Hub - API" /min "%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000
start "Production Hub - Dashboard" /min "%PY%" -m streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8502 --server.headless true

echo [OK] API / Dashboard started in minimized windows.
