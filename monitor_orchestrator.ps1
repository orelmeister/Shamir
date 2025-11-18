Write-Host '================================================' -ForegroundColor Cyan
Write-Host 'WEEKLY BOT MONITOR - Watching for activity...' -ForegroundColor Cyan
Write-Host '================================================' -ForegroundColor Cyan
Write-Host ''

while ($true) {
    Clear-Host
    Write-Host '================================================' -ForegroundColor Cyan
    Write-Host 'WEEKLY BOT MONITOR' -ForegroundColor Cyan
    Write-Host 'Press Ctrl+C to stop monitoring' -ForegroundColor Yellow
    Write-Host '================================================' -ForegroundColor Cyan
    Write-Host ''
    
    # Check phase state
    Write-Host '[PHASE STATE]' -ForegroundColor Green
    if (Test-Path shared_state\phase_state.json) {
        $state = Get-Content shared_state\phase_state.json | ConvertFrom-Json
        Write-Host \"Current Phase: $($state.current_phase)\" -ForegroundColor White
        Write-Host \"Last Updated: $($state.last_updated)\" -ForegroundColor Gray
        if ($state.last_error) {
            Write-Host \"Last Error: $($state.last_error)\" -ForegroundColor Red
        }
    }
    Write-Host ''
    
    # Check latest orchestrator log
    Write-Host '[LATEST ORCHESTRATOR LOG]' -ForegroundColor Green
    $latestLog = Get-ChildItem logs\orchestrator_*.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestLog) {
        Write-Host \"Log File: $($latestLog.Name)\" -ForegroundColor White
        Write-Host \"Last 5 lines:\" -ForegroundColor Gray
        Get-Content $latestLog.FullName -Tail 5 | ForEach-Object { Write-Host \"  $_\" -ForegroundColor White }
    } else {
        Write-Host 'No orchestrator logs found yet' -ForegroundColor Yellow
    }
    Write-Host ''
    
    # Check for running Python processes
    Write-Host '[RUNNING PROCESSES]' -ForegroundColor Green
    $pythonProcs = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-30) }
    if ($pythonProcs) {
        $pythonProcs | Select-Object Id, ProcessName, @{Name='Runtime';Expression={(Get-Date) - $_.StartTime}} | Format-Table | Out-String | Write-Host
    } else {
        Write-Host 'No recent Python processes detected' -ForegroundColor Yellow
    }
    
    Start-Sleep -Seconds 5
}
