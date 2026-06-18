@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM Tray launcher (no console). Manager hides to the system tray; right-click
REM the tray icon to show the window or fully quit. Because manager spawns
REM children with sys.executable, pythonw makes API/Dashboard consoleless too.
REM Autostart: put a shortcut to this file in shell:startup.

set "PYW=.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"

start "" "%PYW%" manager.py
