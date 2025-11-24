# Schedule Day Trading Bot in Windows Task Scheduler
# Runs Monday-Friday at 6:00 AM Pacific Time (pre-market preparation)

$taskName = "DayTradingBot"
$scriptPath = "C:\Users\orelm\OneDrive\Documents\GitHub\trade"
$pythonExe = "$scriptPath\.venv-daytrader\Scripts\python.exe"
$dayTraderScript = "$scriptPath\day_trader.py"
$logPath = "$scriptPath\logs\task_scheduler.log"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Day Trading Bot - Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "⚠️  Task '$taskName' already exists." -ForegroundColor Yellow
    $response = Read-Host "Do you want to update it? (y/n)"
    if ($response -ne 'y') {
        Write-Host "Cancelled." -ForegroundColor Red
        exit
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✅ Removed existing task" -ForegroundColor Green
}

# Create the action (what to run)
$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "day_trader.py --allocation 1.0" `
    -WorkingDirectory $scriptPath

# Create the trigger (when to run)
# Runs Monday-Friday at 6:00 AM Pacific Time
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "6:00AM"

# Task settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

# Principal (run with highest privileges)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Automated day trading bot - Runs Mon-Fri at 6:00 AM PT (pre-market)" `
        -ErrorAction Stop
    
    Write-Host ""
    Write-Host "✅ Task scheduled successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📅 Schedule Details:" -ForegroundColor Cyan
    Write-Host "   Task Name: $taskName" -ForegroundColor White
    Write-Host "   Start Time: 6:00 AM Pacific Time" -ForegroundColor White
    Write-Host "   Days: Monday - Friday" -ForegroundColor White
    Write-Host "   Script: $dayTraderScript" -ForegroundColor White
    Write-Host "   Capital Limit: `$1,000" -ForegroundColor White
    Write-Host ""
    Write-Host "⏰ Timeline (Pacific Time):" -ForegroundColor Cyan
    Write-Host "   6:00 AM - Bot starts, data aggregation (Phase 0)" -ForegroundColor White
    Write-Host "   6:30 AM - LLM analysis (Phase 1)" -ForegroundColor White
    Write-Host "   6:45 AM - IBKR validation (Phase 1.5)" -ForegroundColor White
    Write-Host "   7:00 AM - Pre-market momentum (Phase 1.75)" -ForegroundColor White
    Write-Host "   9:30 AM - Market opens, trading begins" -ForegroundColor White
    Write-Host "   4:00 PM - Market closes, positions liquidated" -ForegroundColor White
    Write-Host ""
    Write-Host "🔧 Management Commands:" -ForegroundColor Cyan
    Write-Host "   View task:     Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "   Run now:       Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "   Disable task:  Disable-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "   Enable task:   Enable-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host "   Remove task:   Unregister-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host ""
    Write-Host "📊 Monitor Logs:" -ForegroundColor Cyan
    Write-Host "   Get-Content logs\day_trader_run_*.json -Tail 50" -ForegroundColor White
    Write-Host ""
    
    # Show next run time
    $task = Get-ScheduledTask -TaskName $taskName
    $nextRun = (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime
    if ($nextRun) {
        Write-Host "⏭️  Next scheduled run: $nextRun" -ForegroundColor Green
    }
    
} catch {
    Write-Host "❌ Error creating task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 Make sure you're running PowerShell as Administrator" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "🎉 Setup complete! The bot will run automatically." -ForegroundColor Green
Write-Host ""

# Optional: Ask if user wants to test run now
$testRun = Read-Host "Would you like to test run the task now? (y/n)"
if ($testRun -eq 'y') {
    Write-Host ""
    Write-Host "▶️  Starting task..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $taskName
    Write-Host "✅ Task started. Check logs folder for output." -ForegroundColor Green
    Write-Host ""
    Write-Host "Monitor with: Get-Content logs\day_trader_run_*.json -Tail 50 -Wait" -ForegroundColor White
}
