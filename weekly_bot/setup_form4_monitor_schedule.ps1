# Form 4 Monitoring Agent - Task Scheduler Setup
# Automatically creates Windows Task Scheduler task for daily monitoring

Write-Host "`n" -NoNewline
Write-Host "="*80 -ForegroundColor Cyan
Write-Host "FORM 4 MONITORING AGENT - TASK SCHEDULER SETUP" -ForegroundColor Cyan
Write-Host "="*80 -ForegroundColor Cyan
Write-Host ""

# Paths (adjust if needed)
$ScriptDir = "C:\Users\orelm\OneDrive\Documents\GitHub\trade\weekly_bot"
$PythonExe = "C:\Users\orelm\OneDrive\Documents\GitHub\trade\.venv-daytrader\Scripts\python.exe"
$ScriptPath = "$ScriptDir\form4_monitor_agent.py"

# Verify paths exist
Write-Host "[*] Verifying paths..." -ForegroundColor Yellow
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Python executable not found: $PythonExe" -ForegroundColor Red
    Write-Host "[HINT] Update `$PythonExe path in this script" -ForegroundColor Yellow
    exit 1
}
Write-Host "    [OK] Python: $PythonExe" -ForegroundColor Green

if (-not (Test-Path $ScriptPath)) {
    Write-Host "[ERROR] Script not found: $ScriptPath" -ForegroundColor Red
    Write-Host "[HINT] Update `$ScriptDir path in this script" -ForegroundColor Yellow
    exit 1
}
Write-Host "    [OK] Script: $ScriptPath" -ForegroundColor Green

# Check if task already exists
$TaskName = "Form4MonitoringAgent"
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "`n[!] Task '$TaskName' already exists" -ForegroundColor Yellow
    $Response = Read-Host "Overwrite? (y/n)"
    if ($Response -ne 'y' -and $Response -ne 'Y') {
        Write-Host "[*] Setup cancelled" -ForegroundColor Yellow
        exit 0
    }
    Write-Host "[*] Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create task components
Write-Host "`n[*] Creating scheduled task..." -ForegroundColor Yellow

# Action: Run Python script
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $ScriptDir

# Trigger: Daily at 5:00 PM
$Trigger = New-ScheduledTaskTrigger -Daily -At 5:00PM

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Register task
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Description "Daily monitoring of Form 4 insider trading positions with LLM-based hold/sell decisions" `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Force | Out-Null
    
    Write-Host "    [OK] Task registered successfully" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to register task: $_" -ForegroundColor Red
    exit 1
}

# Verify task was created
$CreatedTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $CreatedTask) {
    Write-Host "[ERROR] Task was not created" -ForegroundColor Red
    exit 1
}

# Success summary
Write-Host "`n" -NoNewline
Write-Host "="*80 -ForegroundColor Green
Write-Host "SUCCESS - TASK SCHEDULER CONFIGURED!" -ForegroundColor Green
Write-Host "="*80 -ForegroundColor Green
Write-Host ""
Write-Host "Task Name:        " -NoNewline -ForegroundColor Cyan
Write-Host "$TaskName" -ForegroundColor White
Write-Host "Schedule:         " -NoNewline -ForegroundColor Cyan
Write-Host "Daily at 5:00 PM" -ForegroundColor White
Write-Host "Script:           " -NoNewline -ForegroundColor Cyan
Write-Host "$ScriptPath" -ForegroundColor White
Write-Host "Next Run Time:    " -NoNewline -ForegroundColor Cyan
Write-Host "$($CreatedTask.Triggers[0].StartBoundary)" -ForegroundColor White
Write-Host ""
Write-Host "WHAT HAPPENS NEXT:" -ForegroundColor Yellow
Write-Host "  1. Agent runs automatically every day at 5:00 PM" -ForegroundColor White
Write-Host "  2. Checks all ACTIVE Form 4 positions" -ForegroundColor White
Write-Host "  3. LLM decides: HOLD / SELL / EXTEND" -ForegroundColor White
Write-Host "  4. Executes exits via IBKR if needed" -ForegroundColor White
Write-Host "  5. Saves daily monitoring report" -ForegroundColor White
Write-Host ""
Write-Host "MANAGEMENT:" -ForegroundColor Yellow
Write-Host "  View Task:        " -NoNewline -ForegroundColor Cyan
Write-Host "Open Task Scheduler (taskschd.msc)" -ForegroundColor White
Write-Host "  Test Now:         " -NoNewline -ForegroundColor Cyan
Write-Host "Right-click task -> Run" -ForegroundColor White
Write-Host "  View Logs:        " -NoNewline -ForegroundColor Cyan
Write-Host "weekly_bot\logs\monitor_agent_*.log" -ForegroundColor White
Write-Host "  Disable Task:     " -NoNewline -ForegroundColor Cyan
Write-Host "Right-click task -> Disable" -ForegroundColor White
Write-Host ""
Write-Host "="*80 -ForegroundColor Green
Write-Host ""
