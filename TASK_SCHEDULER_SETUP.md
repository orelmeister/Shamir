# ============================================================
# Windows Task Scheduler Setup Instructions
# ============================================================
# HOW TO SET UP AUTOMATED DAILY TRADING AT 7:00 AM
# ============================================================

## Step 1: Open Task Scheduler
1. Press `Win + R`
2. Type: `taskschd.msc`
3. Press Enter

## Step 2: Create New Task
1. Click "Create Task" (right sidebar)
2. **General Tab**:
   - Name: `Day Trading Bot - 7AM Start`
   - Description: `Automated day trading bot - runs at 7:00 AM ET daily`
   - Select: "Run whether user is logged on or not"
   - Select: "Run with highest privileges"
   - Configure for: Windows 10

## Step 3: Triggers Tab
1. Click "New..."
2. Begin the task: `On a schedule`
3. Settings: `Daily`
4. Start: `7:00:00 AM`
5. Recur every: `1 days`
6. Advanced settings:
   - ✅ Enabled
   - Stop task if it runs longer than: `10 hours` (trading day + buffer)

## Step 4: Actions Tab
1. Click "New..."
2. Action: `Start a program`
3. Program/script: `C:\Users\orelm\OneDrive\Documents\GitHub\trade\start_day_trader.bat`
4. Start in: `C:\Users\orelm\OneDrive\Documents\GitHub\trade`
5. Click OK

## Step 5: Conditions Tab
1. Power:
   - ✅ Start the task only if the computer is on AC power
   - ⬜ Stop if the computer switches to battery power
   - ✅ Wake the computer to run this task

## Step 6: Settings Tab
1. ✅ Allow task to be run on demand
2. ✅ Run task as soon as possible after a scheduled start is missed
3. If the task fails, restart every: `5 minutes`
4. Attempt to restart up to: `3 times`
5. ✅ If the running task does not end when requested, force it to stop

## Step 7: Save and Test
1. Click OK
2. Enter your Windows password if prompted
3. Right-click the task → "Run" to test immediately

## ============================================================
## IMPORTANT: Ensure TWS/IBG is Running
## ============================================================
The bot requires Interactive Brokers Trader Workstation (TWS) or 
IB Gateway to be running BEFORE 7:00 AM.

**Option A: Auto-start TWS/IBG (Recommended)**
1. Create another scheduled task for 6:50 AM
2. Program/script: `C:\Jts\tws.exe` (or your TWS path)
3. This gives TWS 10 minutes to connect before bot starts

**Option B: Manual start**
- Open TWS/IBG before 7:00 AM manually
- Ensure API connections are enabled (port 7497)

## ============================================================
## MONITORING THE BOT
## ============================================================

### Real-Time Monitoring (Terminal)
When you run manually:
```powershell
cd C:\Users\orelm\OneDrive\Documents\GitHub\trade
.\start_day_trader.bat manual
```
The "manual" parameter keeps the window open so you can watch.

### Log Files (Always Available)
The bot creates detailed logs in multiple locations:

1. **Daily Run Logs** (Main Source):
   - Location: `logs/day_trader_run_YYYYMMDD_HHMMSS.json`
   - Contains: Full activity log, all decisions, trades, errors
   - Format: JSON (easy to read/parse)

2. **IBKR Connection Logs**:
   - Location: `logs/ib_insync_YYYYMMDD_HHMMSS.log`
   - Contains: Connection status, API calls, data requests

3. **Reports** (End of Day):
   - Location: `reports/improvement/YYYYMMDD_improvement_report.json`
   - Contains: Performance analysis, trade statistics, recommendations

### How to Check Logs in VS Code
```powershell
# View today's most recent run log
Get-ChildItem logs\day_trader_run_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content | ConvertFrom-Json | Select-Object -First 100 | Format-List

# Or just open in VS Code
code (Get-ChildItem logs\day_trader_run_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
```

### Log File Structure
```json
{
  "timestamp": "2025-10-23 09:44:13,188",
  "level": "INFO",
  "agent": "IntradayTraderAgent",
  "message": "REPL - Price: $8.47, VWAP: $8.62, RSI: 41.15, ATR: 0.24%"
}
```

Each line shows:
- **timestamp**: Exact time of event
- **level**: INFO, WARNING, ERROR
- **agent**: Which component (Orchestrator, IntradayTraderAgent, etc.)
- **message**: What happened

## ============================================================
## QUICK MONITORING COMMANDS
## ============================================================

### Check if bot is running:
```powershell
Get-Process python | Where-Object {$_.MainWindowTitle -like "*day_trader*"}
```

### View latest log (last 50 lines):
```powershell
Get-Content (Get-ChildItem logs\day_trader_run_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | Select-Object -Last 50
```

### Count today's trades:
```powershell
$log = Get-Content (Get-ChildItem logs\day_trader_run_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | ConvertFrom-Json
($log | Where-Object {$_.message -like "*ENTRY SIGNAL*"}).Count
```

### Check for errors:
```powershell
$log = Get-Content (Get-ChildItem logs\day_trader_run_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1) | ConvertFrom-Json
$log | Where-Object {$_.level -eq "ERROR"}
```

## ============================================================
## TROUBLESHOOTING
## ============================================================

### Task doesn't start at 7:00 AM:
- Check Task Scheduler → Task History (enable if disabled)
- Verify computer was on/awake at 7:00 AM
- Check "Wake the computer to run this task" is enabled

### Bot starts but crashes:
- Check latest log file for ERROR messages
- Ensure TWS/IBG is running and API enabled
- Verify virtual environment exists: `.venv-daytrader`

### Can't see logs:
- Logs are created in `logs/` directory
- If empty, bot never started successfully
- Check Task Scheduler "Last Run Result" (should be 0x0 for success)

## ============================================================
## DAILY WORKFLOW
## ============================================================

**Automated (Recommended)**:
1. 6:50 AM - TWS/IBG auto-starts
2. 7:00 AM - Bot auto-starts
3. 7:00-9:30 AM - Bot prepares watchlist
4. 9:30 AM-4:00 PM - Bot trades
5. 4:00 PM - Bot liquidates, disconnects
6. Check logs at end of day

**Manual Override**:
1. Any time: Double-click `start_day_trader.bat`
2. Bot will start immediately (won't wait for 7:00 AM)
3. Terminal stays open so you can watch
4. Logs still saved normally

## ============================================================
## MONITORING FROM ANYWHERE
## ============================================================

To check bot status remotely:
1. Set up file sharing to access logs folder
2. Or use VS Code Remote to connect to your PC
3. Or read JSON logs programmatically (Python, etc.)

The log files are human-readable JSON - you can:
- Email them to yourself
- Upload to cloud storage
- Parse with any JSON reader
- View in any text editor
