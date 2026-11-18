# One-time setup of Production Data Hub (Server_API) as headless services on the ops PC.
# Run through ops-install.bat as Administrator. Safe to run again (idempotent).
#
# Creates:
#   ProductionHubApi      SYSTEM, at boot   uvicorn :8000
#   ProductionHubPortal   SYSTEM, at boot   webcloring-pdf scheduler (main.py --schedule)
#   ProductionHubWatcher  SYSTEM, at boot   DB watcher daemon
#   ProductionHubUpdate   installing user, every 10 min   watch + git auto deploy
# and the marker deploy-ops\.service-mode, which tells manager.py to observe only.
#
# ASCII only: Windows PowerShell 5.1 reads a BOM-less script as ANSI.
param(
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Run = Join-Path $PSScriptRoot "ops-run.bat"
$Py = Join-Path $Root ".venv\Scripts\python.exe"

function Step([string]$m) { Write-Host $m -ForegroundColor Cyan }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] Run ops-install.bat as Administrator (SYSTEM boot tasks need it)." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] git not found on PATH." -ForegroundColor Red
    exit 1
}

Step "[1/5] venv + dependencies"
if (-not (Test-Path $Py)) {
    $made = $false
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        & py.exe -3.12 -m venv (Join-Path $Root ".venv") 2>$null
        $made = ($LASTEXITCODE -eq 0) -and (Test-Path $Py)
    }
    if (-not $made) {
        & python.exe -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Py)) {
            Write-Host "[ERROR] could not create .venv (Python 3.12 recommended)." -ForegroundColor Red
            exit 1
        }
    }
}
& $Py --version
& $Py -m pip install --quiet --disable-pip-version-check -r (Join-Path $Root "requirements.lock.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] pip install failed." -ForegroundColor Red; exit 1 }

Step "[2/5] portal bot (submodule) + its dependencies"
& git.exe -C $Root submodule update --init --recursive
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] submodule update failed - see update.bat notes; the portal task will not work until fixed." -ForegroundColor Yellow
}
$botReq = Join-Path $Root "webcloring-pdf\requirements.txt"
if (Test-Path $botReq) {
    & $Py -m pip install --quiet --disable-pip-version-check -r $botReq
    if ($LASTEXITCODE -ne 0) { Write-Host "[WARN] bot dependency install failed." -ForegroundColor Yellow }
}

Step "[3/5] scheduled tasks"
$serviceSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$system = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$atBoot = New-ScheduledTaskTrigger -AtStartup

$roles = [ordered]@{
    "ProductionHubApi"     = "api"
    "ProductionHubPortal"  = "portal"
    "ProductionHubWatcher" = "watcher"
}
foreach ($name in $roles.Keys) {
    $arg = '/c ""{0}" {1}"' -f $Run, $roles[$name]
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg -WorkingDirectory $Root
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $atBoot -Principal $system `
        -Settings $serviceSettings -Force | Out-Null
    Write-Host "  registered $name (SYSTEM, at boot)"
}

$me = "$env:USERDOMAIN\$env:USERNAME"
$updateArg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $PSScriptRoot "ops-update.ps1")
$updateAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $updateArg -WorkingDirectory $Root
$every10 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 10)
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $me
$updatePrincipal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Highest
$updateSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "ProductionHubUpdate" -Action $updateAction -Trigger @($every10, $atLogon) `
    -Principal $updatePrincipal -Settings $updateSettings -Force | Out-Null
Write-Host "  registered ProductionHubUpdate ($me, every 10 min; needs this user logged on for git)"

Step "[4/5] firewall + service-mode marker"
if (-not (Get-NetFirewallRule -DisplayName "ProductionHub API 8000" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "ProductionHub API 8000" -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort 8000 | Out-Null
}
Set-Content -Path (Join-Path $PSScriptRoot ".service-mode") -Encoding ASCII `
    -Value "Task Scheduler owns the API / portal / watcher lifecycle. Delete this file to give it back to manager.py."

Step "[5/5] start"
if ($NoStart) {
    Write-Host "  -NoStart: tasks registered but not started."
} else {
    $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "[WARN] port 8000 is already in use (manager.py still running the API?)." -ForegroundColor Yellow
        Write-Host "       Quit the manager from the tray, then run:  schtasks /Run /TN ProductionHubApi" -ForegroundColor Yellow
        Write-Host "       (also /Run ProductionHubPortal and ProductionHubWatcher). Nothing was started now." -ForegroundColor Yellow
    } else {
        foreach ($name in $roles.Keys) { & schtasks.exe /Run /TN $name | Out-Null }
        Start-Sleep -Seconds 12
        try {
            $code = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/healthz" -UseBasicParsing -TimeoutSec 10).StatusCode
        } catch { $code = 0 }
        Write-Host "  health http://127.0.0.1:8000/healthz -> $code"
    }
}

Write-Host ""
Write-Host "Done. Logs: deploy-ops\logs\{api,portal,watcher}.log and deploy-ops\update.log" -ForegroundColor Green
Write-Host "Check the portal bot once under SYSTEM (README, 'first run check')." -ForegroundColor Green
exit 0
