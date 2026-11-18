@echo off
chcp 65001 >nul
setlocal
REM Headless service launcher, one role per scheduled task (no console, logs to files).
REM   ops-run.bat api          uvicorn api.main:app on 8000        (task ProductionHubApi)
REM   ops-run.bat portal       webcloring-pdf main.py --schedule    (task ProductionHubPortal)
REM   ops-run.bat watcher      tools\watcher.py --daemon (1h)       (task ProductionHubWatcher)
REM   ops-run.bat portal-once  one bot run (main.py --auto), used by test-portal-as-system.ps1
REM Registered by ops-install.bat as SYSTEM / at boot, so the services come back
REM after a Windows Update reboot without anyone logging in.
REM
REM Each run line ends with "& exit /b" on the same line: cmd parses a line whole, so
REM an auto-deploy pull that rewrites this file while the service runs cannot make cmd
REM resume in the middle of new content when the service exits.

set "ROLE=%~1"
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
cd /d "%ROOT%"

set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] .venv not found. Run deploy-ops\ops-install.bat first.
    exit /b 1
)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
REM Unbuffered so the last lines before a crash reach the log.
set PYTHONUNBUFFERED=1

REM Logs (git-ignored): deploy-ops\logs\<role>.log = raw stdout/stderr, rotated here at
REM start (10MB x 3). The API also keeps its own rotating logs\app.log.
set "LOG_DIR=%~dp0logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if /i "%ROLE%"=="api" goto run_api
if /i "%ROLE%"=="portal" goto run_portal
if /i "%ROLE%"=="portal-once" goto run_portal_once
if /i "%ROLE%"=="watcher" goto run_watcher
echo usage: ops-run.bat api^|portal^|watcher^|portal-once
exit /b 2

:run_api
set "OUT=%LOG_DIR%\api.log"
call :rotate "%OUT%"
echo [%DATE% %TIME%] ops-run api start >> "%OUT%"
REM Access log off: it would flood api.log (stdout has no in-process rotation).
"%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --no-access-log >> "%OUT%" 2>&1 & call echo [%%DATE%% %%TIME%%] api exited code=%%ERRORLEVEL%% >> "%OUT%" & exit /b

:run_portal
set "OUT=%LOG_DIR%\portal.log"
call :rotate "%OUT%"
echo [%DATE% %TIME%] ops-run portal start >> "%OUT%"
"%PY%" "%~dp0ops_launch.py" portal >> "%OUT%" 2>&1 & call echo [%%DATE%% %%TIME%%] portal exited code=%%ERRORLEVEL%% >> "%OUT%" & exit /b

:run_portal_once
set "OUT=%LOG_DIR%\portal-once.log"
echo [%DATE% %TIME%] ops-run portal-once start > "%OUT%"
"%PY%" "%~dp0ops_launch.py" portal-once >> "%OUT%" 2>&1 & call echo [%%DATE%% %%TIME%%] portal-once exited code=%%ERRORLEVEL%% >> "%OUT%" & exit /b

:run_watcher
set "OUT=%LOG_DIR%\watcher.log"
call :rotate "%OUT%"
echo [%DATE% %TIME%] ops-run watcher start >> "%OUT%"
"%PY%" "%~dp0ops_launch.py" watcher >> "%OUT%" 2>&1 & call echo [%%DATE%% %%TIME%%] watcher exited code=%%ERRORLEVEL%% >> "%OUT%" & exit /b

:rotate
REM Keep each log under ~10MB: shift .1..3 and start fresh.
if not exist "%~1" exit /b 0
if %~z1 LSS 10485760 exit /b 0
if exist "%~1.3" del /q "%~1.3"
if exist "%~1.2" move /y "%~1.2" "%~1.3" >nul
if exist "%~1.1" move /y "%~1.1" "%~1.2" >nul
move /y "%~1" "%~1.1" >nul
exit /b 0
