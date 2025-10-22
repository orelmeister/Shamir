# Day Trading Bot Monitor Script
# Usage: .\monitor_bot.ps1 -allocation 0.25

param(
    [double]$allocation = 0.25,
    [switch]$live = $false
)

$pythonPath = "C:\Users\orelm\OneDrive\Documents\GitHub\trade\.venv-daytrader\Scripts\python.exe"
$scriptPath = "day_trader.py"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   DAY TRADING BOT MONITOR" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Allocation: $($allocation * 100)%" -ForegroundColor Yellow
Write-Host "Mode: $(if($live){'LIVE TRADING'}else{'PAPER TRADING'})" -ForegroundColor $(if($live){'Red'}else{'Green'})
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Build command
$args = @("--allocation", $allocation)
if ($live) {
    $args += "--live"
}

# Start the bot in background
$job = Start-Job -ScriptBlock {
    param($pythonPath, $scriptPath, $args)
    & $pythonPath $scriptPath $args
} -ArgumentList $pythonPath, $scriptPath, $args

Write-Host "✓ Bot started (Job ID: $($job.Id))" -ForegroundColor Green
Write-Host "✓ TWS connected (PID: $(Get-Process tws | Select-Object -First 1 -ExpandProperty Id))" -ForegroundColor Green
Write-Host ""

# Wait for log file to be created
Start-Sleep -Seconds 2

# Find the latest log file
$latestLog = Get-ChildItem "logs\day_trader_run_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($latestLog) {
    Write-Host "📊 Monitoring log: $($latestLog.Name)" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop monitoring (bot will continue running)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Monitor the log file
    Get-Content -Path $latestLog.FullName -Wait | ForEach-Object {
        try {
            $log = $_ | ConvertFrom-Json
            
            # Format timestamp
            $time = $log.timestamp.Split('T')[1].Split('.')[0]
            
            # Color code by level
            $color = switch ($log.level) {
                "ERROR" { "Red" }
                "WARNING" { "Yellow" }
                "INFO" { "White" }
                "DEBUG" { "Gray" }
                default { "White" }
            }
            
            # Highlight important events
            $message = $log.message
            if ($message -match "ENTRY SIGNAL|BOUGHT|SOLD|PROFIT|LOSS") {
                $color = "Green"
                Write-Host ""
                Write-Host ">>> [$time] $($log.agent): $message <<<" -ForegroundColor $color
                Write-Host ""
            }
            elseif ($message -match "ERROR|FAILED|Connection") {
                Write-Host "[$time] $($log.agent): $message" -ForegroundColor Red
            }
            elseif ($message -match "Phase|Starting|Finished") {
                Write-Host "[$time] $($log.agent): $message" -ForegroundColor Cyan
            }
            else {
                Write-Host "[$time] $($log.agent): $message" -ForegroundColor $color
            }
        }
        catch {
            # If not JSON, just print raw
            Write-Host $_ -ForegroundColor Gray
        }
    }
}
else {
    Write-Host "⚠ No log file found yet. Waiting for bot to initialize..." -ForegroundColor Yellow
    Write-Host "Check logs\ folder manually if bot doesn't start." -ForegroundColor Yellow
}

# Cleanup
Stop-Job -Job $job -ErrorAction SilentlyContinue
Remove-Job -Job $job -ErrorAction SilentlyContinue
