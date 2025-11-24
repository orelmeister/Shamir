# Setup Form 4 Exit Manager - Task Scheduler
# Run this script as Administrator: Right-click > Run as Administrator

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "FORM 4 EXIT MANAGER - TASK SCHEDULER SETUP" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "`n[ERROR] This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host "[INFO] Right-click this script and select 'Run as Administrator'`n" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "`n[OK] Running with Administrator privileges" -ForegroundColor Green

# Paths
$pythonExe = "C:\Users\orelm\OneDrive\Documents\GitHub\trade\.venv-weekly\Scripts\python.exe"
$scriptPath = "weekly_bot\form4_exit_manager.py"
$workingDir = "C:\Users\orelm\OneDrive\Documents\GitHub\trade"

# Verify paths exist
if (-not (Test-Path $pythonExe)) {
    Write-Host "`n[ERROR] Python executable not found: $pythonExe" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

if (-not (Test-Path "$workingDir\$scriptPath")) {
    Write-Host "`n[ERROR] Exit manager script not found: $workingDir\$scriptPath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] All paths verified" -ForegroundColor Green

# Create scheduled task
Write-Host "`n[CREATING] Scheduled Task..." -ForegroundColor Yellow

try {
    # Define action (what to run)
    $action = New-ScheduledTaskAction `
        -Execute $pythonExe `
        -Argument $scriptPath `
        -WorkingDirectory $workingDir
    
    # Define trigger (when to run)
    # 7:30 AM PT = 10:30 AM ET (1.5 hours after market open)
    # Catches morning volatility, reasonable California time
    $trigger = New-ScheduledTaskTrigger `
        -Daily `
        -At "7:30AM"
    
    # Define settings
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    
    # Define principal (run as current user with highest privileges)
    $principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Highest
    
    # Register task
    $task = Register-ScheduledTask `
        -TaskName "Form4 Exit Manager - Daily" `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Monitors Form 4 insider trading positions daily at 7:30 AM PT (10:30 AM ET) for exit decisions using multi-agent debate (DeepSeek + Gemini). Runs 1 hour after market open to catch morning momentum. Automatically executes sell orders when both models agree." `
        -Force
    
    Write-Host "[SUCCESS] Task created successfully!" -ForegroundColor Green
    
    # Display task details
    Write-Host "`n=================================================================" -ForegroundColor Cyan
    Write-Host "TASK DETAILS" -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Cyan
    Write-Host "Task Name:   Form4 Exit Manager - Daily"
    Write-Host "Schedule:    Daily at 7:30 AM PT (10:30 AM ET)"
    Write-Host "Action:      Run exit manager (analyze positions, execute sells)"
    Write-Host "User:        $env:USERNAME"
    Write-Host "Status:      Ready"
    Write-Host "`nThe task will:"
    Write-Host "  1. Run at 7:30 AM PT (10:30 AM ET) daily"
    Write-Host "  2. Market open at 6:30 AM PT (9:30 AM ET)"
    Write-Host "  3. Analyzes positions 1 hour after market open"
    Write-Host "  4. Catches morning volatility and momentum"
    Write-Host "  5. Connect to IBKR and load Form 4 positions"
    Write-Host "  6. Multi-agent debate (DeepSeek + Gemini) for each position"
    Write-Host "  7. Execute sell orders if both models agree"
    Write-Host "  8. Save exit logs to form4_reports/exit_logs/"
    Write-Host "`n=================================================================" -ForegroundColor Cyan
    
    # Test run option
    Write-Host "`n[OPTION] Would you like to test the task now? (y/n): " -ForegroundColor Yellow -NoNewline
    $testRun = Read-Host
    
    if ($testRun -eq 'y' -or $testRun -eq 'Y') {
        Write-Host "`n[TESTING] Running task manually..." -ForegroundColor Yellow
        Start-ScheduledTask -TaskName "Form4 Exit Manager - Daily"
        Write-Host "[OK] Task started - check logs for results" -ForegroundColor Green
        Write-Host "[INFO] Log location: logs\form4_exit_manager_*.log" -ForegroundColor Cyan
    }
    
    Write-Host "`n[INFO] To view task in Task Scheduler:" -ForegroundColor Cyan
    Write-Host "       taskschd.msc" -ForegroundColor White
    Write-Host "`n[INFO] To run task manually:" -ForegroundColor Cyan
    Write-Host "       Start-ScheduledTask -TaskName 'Form4 Exit Manager - Daily'" -ForegroundColor White
    Write-Host "`n[INFO] To disable task:" -ForegroundColor Cyan
    Write-Host "       Disable-ScheduledTask -TaskName 'Form4 Exit Manager - Daily'" -ForegroundColor White
    Write-Host "`n[INFO] To remove task:" -ForegroundColor Cyan
    Write-Host "       Unregister-ScheduledTask -TaskName 'Form4 Exit Manager - Daily' -Confirm:`$false" -ForegroundColor White
    
} catch {
    Write-Host "`n[ERROR] Failed to create task: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host "SETUP COMPLETE!" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to exit"
