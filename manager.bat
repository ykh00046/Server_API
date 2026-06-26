@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM Tray launcher (no console). Manager hides to the system tray; right-click
REM the tray icon to show the window or fully quit. Children (API/Dashboard/
REM Portal) are spawned with sys.executable, so pythonw keeps them consoleless.
REM Autostart: put a shortcut to this file in shell:startup.

set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"

start "" "%PYW%" "%~dp0manager.py"
