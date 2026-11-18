# First-run check: run the portal bot ONCE as SYSTEM (the account the service uses) and
# show its log. Chrome under SYSTEM has no desktop, so this proves the bot still logs in,
# downloads and backs up before the scheduler is trusted. Run as Administrator.
#
# The run is a normal `main.py --auto`: real documents are fetched and upserted by
# document number, the same as the "Run Now" button.
#
# ASCII only: Windows PowerShell 5.1 reads a BOM-less script as ANSI.
param(
    [int]$TimeoutMinutes = 20
)

$ErrorActionPreference = "Stop"
$Run = Join-Path $PSScriptRoot "ops-run.bat"
$LogFile = Join-Path $PSScriptRoot "logs\portal-once.log"
$TaskName = "ProductionHubPortalTest"

$arg = '/c ""{0}" portal-once"' -f $Run
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes ($TimeoutMinutes + 5))
Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null

try {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Running the bot once as SYSTEM (up to $TimeoutMinutes min) ..."
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    Start-Sleep -Seconds 5
    while ((Get-ScheduledTask -TaskName $TaskName).State -eq "Running" -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
    }
    $state = (Get-ScheduledTask -TaskName $TaskName).State
    if ($state -eq "Running") {
        Write-Host "[WARN] still running after $TimeoutMinutes min - stopping it." -ForegroundColor Yellow
        Stop-ScheduledTask -TaskName $TaskName
    }
} finally {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Write-Host ""
Write-Host "---- last 40 lines of $LogFile ----"
if (Test-Path $LogFile) {
    Get-Content $LogFile -Tail 40 -Encoding UTF8
} else {
    Write-Host "(no log written - the task did not start; check Task Scheduler history)"
}
