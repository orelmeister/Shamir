# Setup IBKR Gateway/TWS Auto-Start Task
# This ensures IBKR is running before the day trader starts

$taskName = "StartIBKRGateway"
$ibkrPath = "C:\Jts\tws.exe"  # Update this path to your TWS or Gateway installation

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "IBKR Gateway Auto-Start Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if IBKR is already running
$ibkrProcess = Get-Process | Where-Object {$_.ProcessName -like "*tws*" -or $_.ProcessName -like "*gateway*"}
if ($ibkrProcess) {
    Write-Host "✅ IBKR is currently running:" -ForegroundColor Green
    $ibkrProcess | Format-Table ProcessName, Id, StartTime -AutoSize
} else {
    Write-Host "⚠️  IBKR is NOT currently running" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "📝 To fix the connection issue, you have 2 options:" -ForegroundColor Cyan
Write-Host ""

Write-Host "OPTION 1: Keep IBKR Running 24/7" -ForegroundColor Yellow
Write-Host "  - Start TWS or Gateway manually before 6:00 AM" -ForegroundColor White
Write-Host "  - Enable 'Auto restart' in TWS settings" -ForegroundColor White
Write-Host "  - Configure auto-login (save credentials)" -ForegroundColor White
Write-Host "  - This is the RECOMMENDED approach" -ForegroundColor Green
Write-Host ""

Write-Host "OPTION 2: Auto-Start IBKR via Scheduled Task" -ForegroundColor Yellow
Write-Host "  - Creates task to start IBKR at 5:50 AM (10 min before bot)" -ForegroundColor White
Write-Host "  - PROBLEM: IBKR requires manual login (2FA)" -ForegroundColor Red
Write-Host "  - Won't work reliably without you being present" -ForegroundColor Red
Write-Host "  - Not recommended for unattended operation" -ForegroundColor Yellow
Write-Host ""

$response = Read-Host "Do you want to create the auto-start task anyway? (y/n)"

if ($response -ne 'y') {
    Write-Host ""
    Write-Host "✅ Recommended: Keep IBKR running manually" -ForegroundColor Green
    Write-Host ""
    Write-Host "Steps to ensure reliable operation:" -ForegroundColor Cyan
    Write-Host "1. Start TWS/Gateway manually" -ForegroundColor White
    Write-Host "2. Log in and enable 'Read-Only API'" -ForegroundColor White
    Write-Host "3. Configure Settings -> API -> Enable ActiveX and Socket Clients" -ForegroundColor White
    Write-Host "4. Set Socket port to 4001" -ForegroundColor White
    Write-Host "5. Leave TWS/Gateway running 24/7" -ForegroundColor White
    Write-Host "6. Enable auto-restart on connection loss" -ForegroundColor White
    Write-Host ""
    Write-Host "The day trader will connect at 6:00 AM automatically." -ForegroundColor Green
    exit
}

Write-Host ""
Write-Host "⚠️  WARNING: This requires manual intervention for login" -ForegroundColor Yellow
Write-Host ""

# Check if IBKR executable exists
if (-not (Test-Path $ibkrPath)) {
    Write-Host "❌ IBKR not found at: $ibkrPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please update the path in this script:" -ForegroundColor Yellow
    Write-Host "  Common locations:" -ForegroundColor White
    Write-Host "  - C:\Jts\tws.exe (Trader Workstation)" -ForegroundColor White
    Write-Host "  - C:\Users\$env:USERNAME\Jts\ibgateway\XXX\ibgateway.exe" -ForegroundColor White
    Write-Host ""
    exit 1
}

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

# Create the action (start IBKR)
$action = New-ScheduledTaskAction `
    -Execute $ibkrPath

# Create the trigger (Monday-Friday at 5:50 AM)
$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "5:50AM"

# Task settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Start IBKR Gateway/TWS before day trading bot (5:50 AM)" `
        -ErrorAction Stop
    
    Write-Host ""
    Write-Host "✅ Task scheduled successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠️  IMPORTANT NOTES:" -ForegroundColor Yellow
    Write-Host "1. This task will START IBKR but you must LOGIN manually" -ForegroundColor Red
    Write-Host "2. Without login, the bot cannot connect" -ForegroundColor Red
    Write-Host "3. You must be at your computer at 5:50 AM to complete login" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 BETTER SOLUTION:" -ForegroundColor Cyan
    Write-Host "   Keep IBKR running 24/7 with auto-restart enabled" -ForegroundColor White
    Write-Host "   This eliminates the need for daily manual login" -ForegroundColor White
    
} catch {
    Write-Host "❌ Error creating task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 Make sure you're running PowerShell as Administrator" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "📅 Schedule:" -ForegroundColor Cyan
Write-Host "   5:50 AM - IBKR Gateway starts (requires manual login)" -ForegroundColor White
Write-Host "   6:00 AM - Day trading bot starts" -ForegroundColor White
Write-Host ""
