# Watch + pull-based auto deploy for Production Data Hub (Server_API) on the ops PC.
#
# Runs every 10 minutes (task ProductionHubUpdate, registered by ops-install).
#   1. task settings: no 72h execution limit on the service tasks
#   2. self-heal: API not answering /healthz, or a role task not running -> start it
#   3. deploy: git fetch -> pull --ff-only -> submodule -> dependencies -> restart
#      only the roles whose files changed
# Everything is logged to deploy-ops\update.log. The script is parsed in full before
# it runs, so `git pull` may safely replace this file mid-run.
#
# ASCII only: Windows PowerShell 5.1 reads a BOM-less script as ANSI.
param(
    [switch]$NoPull
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Log = Join-Path $PSScriptRoot "update.log"
$Py = Join-Path $Root ".venv\Scripts\python.exe"

$ApiTask = "ProductionHubApi"
$PortalTask = "ProductionHubPortal"
$WatcherTask = "ProductionHubWatcher"
$ApiPort = 8000
$HealthUrl = "http://127.0.0.1:$ApiPort/healthz"

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Get-HttpStatus([string]$Url, [int]$TimeoutSec = 10) {
    # Any HTTP answer counts as "alive" (a 500 is an app problem, not a dead process).
    try {
        return [int](Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec).StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

function Test-TaskExists([string]$Name) {
    return [bool](Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue)
}

function Get-TaskState([string]$Name) {
    $t = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($t) { return [string]$t.State }
    return "Missing"
}

function Invoke-Native([string]$Label, [scriptblock]$Block) {
    # Run a native command, send its output to the log, return its exit code.
    $out = & $Block 2>&1 | Out-String
    $code = $LASTEXITCODE
    $out = $out.Trim()
    if ($out) { Write-Log "$Label :: $($out -replace '\s*\r?\n\s*', ' | ')" }
    return $code
}

function Stop-RoleProcesses([string]$Pattern) {
    # Stop only this repo's processes for one role, by PID (never by image name).
    $rootRx = [regex]::Escape($Root)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $rootRx -and $_.CommandLine -match $Pattern } |
        ForEach-Object { & taskkill.exe /PID $_.ProcessId /T /F 2>&1 | Out-Null }
}

function Restart-Api {
    Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    & schtasks.exe /End /TN $ApiTask 2>&1 | Out-Null
    & schtasks.exe /Run /TN $ApiTask 2>&1 | Out-Null
    $status = 0
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Seconds 5
        $status = Get-HttpStatus $HealthUrl 5
        if ($status -ne 0) { break }
    }
    if ($status -eq 200) {
        Write-Log "API restart verified health=200"
    } else {
        Write-Log "API RESTART VERIFY FAILED health=$status"
    }
}

function Restart-Role([string]$Task, [string]$Pattern) {
    & schtasks.exe /End /TN $Task 2>&1 | Out-Null
    Stop-RoleProcesses $Pattern
    & schtasks.exe /Run /TN $Task 2>&1 | Out-Null
    Start-Sleep -Seconds 5
    Write-Log "$Task restarted state=$(Get-TaskState $Task)"
}

$PortalPattern = 'ops_launch\.py"?\s+portal'
$WatcherPattern = 'ops_launch\.py"?\s+watcher'

# --- single instance -------------------------------------------------------------
$mutex = New-Object System.Threading.Mutex($false, "Global\ProductionHubUpdate")
$owned = $false
try { $owned = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $owned = $true }
if (-not $owned) { exit 0 }

try {
    if (-not (Test-TaskExists $ApiTask)) {
        Write-Log "service tasks not installed - run deploy-ops\ops-install.bat as Administrator"
        exit 0
    }

    # --- 1. task settings ----------------------------------------------------------
    $out = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "ensure-task-settings.ps1") 2>&1 | Out-String
    $settingsCode = $LASTEXITCODE
    if ($out.Trim()) { Write-Log $out.Trim() }
    if ($settingsCode -eq 10) {
        Write-Log "task settings fixed - restarting services once"
        Restart-Api
        Restart-Role $PortalTask $PortalPattern
        Restart-Role $WatcherTask $WatcherPattern
    }

    # --- 2. self-heal --------------------------------------------------------------
    if ((Get-HttpStatus $HealthUrl) -eq 0) {
        Start-Sleep -Seconds 15
        if ((Get-HttpStatus $HealthUrl) -eq 0) {
            Write-Log "health check failed twice - restarting API"
            Restart-Api
        }
    }
    foreach ($t in @($PortalTask, $WatcherTask)) {
        if ((Test-TaskExists $t) -and (Get-TaskState $t) -eq "Ready") {
            Write-Log "$t is not running - starting it"
            & schtasks.exe /Run /TN $t 2>&1 | Out-Null
        }
    }

    if ($NoPull) { exit 0 }

    # --- 3. pull-based deploy ------------------------------------------------------
    & git.exe -C $Root fetch origin 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { exit 0 }   # offline: try again next run

    $old = (& git.exe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    $new = (& git.exe -C $Root rev-parse "@{u}" 2>$null | Out-String).Trim()
    if (-not $old -or -not $new -or $old -eq $new) { exit 0 }

    Write-Log "update found: $($old.Substring(0,7)) -> $($new.Substring(0,7))"
    $code = Invoke-Native "git pull" { & git.exe -C $Root pull --ff-only }
    if ($code -ne 0) {
        Write-Log "GIT PULL FAILED - resolve local changes on this PC; services untouched"
        exit 0
    }
    $code = Invoke-Native "submodule" { & git.exe -C $Root submodule update --init --recursive }
    if ($code -ne 0) {
        Write-Log "SUBMODULE UPDATE FAILED - the bot is still on the old revision; NOT restarting"
        exit 0
    }

    $changed = @(& git.exe -C $Root diff --name-only $old HEAD 2>$null)
    $depsChanged = [bool]($changed | Where-Object { $_ -match '^requirements' -or $_ -eq 'webcloring-pdf' })
    if ($depsChanged) {
        $code = Invoke-Native "pip" { & $Py -m pip install --quiet --disable-pip-version-check -r (Join-Path $Root "requirements.lock.txt") }
        if ($code -eq 0 -and (Test-Path (Join-Path $Root "webcloring-pdf\requirements.txt"))) {
            $code = Invoke-Native "pip bot" { & $Py -m pip install --quiet --disable-pip-version-check -r (Join-Path $Root "webcloring-pdf\requirements.txt") }
        }
        if ($code -ne 0) {
            Write-Log "PIP INSTALL FAILED - keeping the running processes, NOT restarting"
            exit 0
        }
    }

    $launcherChanged = [bool]($changed | Where-Object { $_ -match '^deploy-ops/ops[-_](run|launch)' })
    $apiChanged = $depsChanged -or $launcherChanged -or [bool]($changed | Where-Object { $_ -match '^(api|shared)/' })
    $portalChanged = $depsChanged -or $launcherChanged
    $watcherChanged = $launcherChanged -or [bool]($changed | Where-Object { $_ -match '^(tools|shared)/' })

    if ($apiChanged) { Restart-Api }
    if ($portalChanged) { Restart-Role $PortalTask $PortalPattern }
    if ($watcherChanged) { Restart-Role $WatcherTask $WatcherPattern }
    if (-not ($apiChanged -or $portalChanged -or $watcherChanged)) {
        Write-Log "no service files changed - nothing restarted"
    }
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
