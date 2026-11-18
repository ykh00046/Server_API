# Ensure long-running scheduled tasks are never killed by Task Scheduler.
#
# A task created with defaults gets "Stop the task if it runs longer than 3 days"
# (ExecutionTimeLimit PT72H). For a server that means a silent TerminateProcess
# exactly 72h after each start (seen on the flow dashboard, 2026-11-15 and 11-18).
#
# Exit codes: 0 = all fine, 10 = at least one task changed (caller should restart
# the services so the running instances are replaced), 1 = could not check/change.
param(
    [string[]]$TaskName = @("ProductionHubApi", "ProductionHubPortal", "ProductionHubWatcher")
)

$changedAny = $false
$failed = $false

foreach ($name in $TaskName) {
    try {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
    } catch {
        Write-Output "ensure-task-settings: cannot read task ${name}: $($_.Exception.Message)"
        $failed = $true
        continue
    }

    $s = $task.Settings
    $changes = @()
    if ($s.ExecutionTimeLimit -ne "PT0S") {
        $changes += "ExecutionTimeLimit $($s.ExecutionTimeLimit) -> PT0S"
        $s.ExecutionTimeLimit = "PT0S"
    }
    if ($s.StopIfGoingOnBatteries) {
        $changes += "StopIfGoingOnBatteries -> False"
        $s.StopIfGoingOnBatteries = $false
    }
    if ($s.DisallowStartIfOnBatteries) {
        $changes += "DisallowStartIfOnBatteries -> False"
        $s.DisallowStartIfOnBatteries = $false
    }
    if ($changes.Count -eq 0) { continue }

    try {
        Set-ScheduledTask -InputObject $task -ErrorAction Stop | Out-Null
    } catch {
        Write-Output "ensure-task-settings: update ${name} failed: $($_.Exception.Message)"
        $failed = $true
        continue
    }
    Write-Output "ensure-task-settings: ${name} updated: $($changes -join '; ')"
    $changedAny = $true
}

if ($changedAny) { exit 10 }
if ($failed) { exit 1 }
exit 0
