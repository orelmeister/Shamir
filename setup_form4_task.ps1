# Setup Form4 Strategy as Windows Scheduled Task
# Runs every Monday at 5:00 AM Pacific Time (8:00 AM Eastern Time)

$taskName = "Form4InsiderStrategy"
$scriptPath = "C:\Users\orelm\OneDrive\Documents\GitHub\trade\run_form4_strategy.bat"
$workingDir = "C:\Users\orelm\OneDrive\Documents\GitHub\trade"

# Remove existing task if it exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Removing existing task: $taskName"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create action to run the batch file
$action = New-ScheduledTaskAction -Execute $scriptPath -WorkingDirectory $workingDir

# Create trigger for Monday at 5:00 AM Pacific Time (8:00 AM Eastern)
# Note: Task Scheduler uses local time, so set to 5:00 AM PT
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "05:00"

# Task settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Create principal (run with highest privileges)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest

# Register the task
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Form4 Insider Trading Strategy - Runs every Monday at 5:00 AM PT (8:00 AM ET)"

Write-Host "`n✅ Form4 Strategy scheduled task created successfully!" -ForegroundColor Green
Write-Host "`nTask Details:" -ForegroundColor Cyan
Write-Host "  Name: $taskName"
Write-Host "  Schedule: Every Monday at 5:00 AM Pacific Time (8:00 AM Eastern Time)"
Write-Host "  Script: $scriptPath"
Write-Host "`nNext run time:"
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
Write-Host "  $($taskInfo.NextRunTime)" -ForegroundColor Yellow
Write-Host "`nTo disable: Disable-ScheduledTask -TaskName '$taskName'"
Write-Host "To enable: Enable-ScheduledTask -TaskName '$taskName'"
Write-Host "To remove: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
