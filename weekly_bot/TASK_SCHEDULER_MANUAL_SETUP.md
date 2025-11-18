# Form 4 Monitoring Agent - Task Scheduler Setup Guide

## Overview

This document provides instructions for setting up the Form 4 Monitoring Agent to run automatically every day at 5:00 PM via Windows Task Scheduler.

**What the agent does:**
- Loads active Form 4 positions from database
- Checks each position (price, news, insider activity)
- Uses LLM to decide: HOLD / SELL / EXTEND
- Executes exits via IBKR automatically
- Generates daily monitoring reports

---

## Option 1: Automated Setup (PowerShell) ⭐ RECOMMENDED

### Quick Setup (30 seconds)

1. **Open PowerShell as Administrator**
   - Press `Win + X`
   - Select "Windows PowerShell (Admin)" or "Terminal (Admin)"

2. **Navigate to project directory**
   ```powershell
   cd C:\Users\orelm\OneDrive\Documents\GitHub\trade\weekly_bot
   ```

3. **Run setup script**
   ```powershell
   .\setup_form4_monitor_schedule.ps1
   ```

4. **Done!** Task Scheduler is now configured.

### Troubleshooting PowerShell

**Error: "Execution policy does not allow scripts"**

Temporarily allow scripts for this session:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_form4_monitor_schedule.ps1
```

**Error: "Paths not found"**

Edit `setup_form4_monitor_schedule.ps1` and update these lines:
```powershell
$ScriptDir = "YOUR_PATH_HERE\weekly_bot"
$PythonExe = "YOUR_PATH_HERE\.venv-daytrader\Scripts\python.exe"
```

---

## Option 2: Manual Setup (GUI Method)

### Step 1: Open Task Scheduler

1. Press `Win + R`
2. Type: `taskschd.msc`
3. Press Enter

### Step 2: Create Basic Task

1. In the right panel, click **"Create Basic Task..."**
2. **Name**: `Form4MonitoringAgent`
3. **Description**: `Daily monitoring of Form 4 insider trading positions with LLM-based hold/sell decisions`
4. Click **"Next"**

### Step 3: Set Trigger

1. Select: **"Daily"**
2. Click **"Next"**
3. **Start**: Today's date
4. **Time**: `5:00 PM` (17:00)
5. **Recur every**: `1 days`
6. Click **"Next"**

### Step 4: Set Action

1. Select: **"Start a program"**
2. Click **"Next"**
3. **Program/script**: Browse and select:
   ```
   C:\Users\orelm\OneDrive\Documents\GitHub\trade\.venv-daytrader\Scripts\python.exe
   ```
4. **Add arguments**:
   ```
   form4_monitor_agent.py
   ```
5. **Start in** (important!):
   ```
   C:\Users\orelm\OneDrive\Documents\GitHub\trade\weekly_bot
   ```
6. Click **"Next"**

### Step 5: Finish Setup

1. Check **"Open the Properties dialog for this task when I click Finish"**
2. Click **"Finish"**

### Step 6: Configure Advanced Settings

In the Properties dialog that opens:

#### General Tab:
- ✅ Check "Run whether user is logged on or not"
- ✅ Check "Run with highest privileges" (if needed)
- **Configure for**: Windows 11 (or your OS version)

#### Triggers Tab:
- Double-click the trigger to edit
- ✅ Check "Enabled"
- Verify time is 5:00 PM daily

#### Actions Tab:
- Verify Python executable path
- Verify script path
- Verify working directory

#### Conditions Tab:
- ✅ Check "Start only if the following network connection is available" → Select "Any connection"
- ❌ Uncheck "Start the task only if the computer is on AC power"
- ❌ Uncheck "Stop if the computer switches to battery power"

#### Settings Tab:
- ✅ Check "Allow task to be run on demand"
- ✅ Check "Run task as soon as possible after a scheduled start is missed"
- ✅ Check "If the task fails, restart every: 1 minute" (Attempt restart: 3 times)
- **If the running task does not end when requested**: Stop the existing instance
- **Stop the task if it runs longer than**: 1 hour

#### Click "OK" to save

### Step 7: Test the Task

1. Find the task in Task Scheduler Library
2. Right-click → **"Run"**
3. Check the "Last Run Result" column (should show "0x0" for success)
4. Verify logs were created: `weekly_bot\logs\monitor_agent_*.log`

---

## Verification Checklist

After setup (either method), verify:

- [ ] Task appears in Task Scheduler Library
- [ ] Task name is "Form4MonitoringAgent"
- [ ] Trigger is set to Daily at 5:00 PM
- [ ] Action points to correct Python executable
- [ ] Working directory is set to `weekly_bot`
- [ ] Task runs successfully when manually triggered
- [ ] Log files are created in `weekly_bot/logs/`
- [ ] Agent connects to IBKR successfully
- [ ] Agent reads database correctly

### Test Run Command:

```powershell
# Manual test (run from project root)
& .\.venv-daytrader\Scripts\python.exe weekly_bot\form4_monitor_agent.py
```

Expected output:
```
================================================================================
FORM 4 MONITORING AGENT - DAILY CHECK
================================================================================
[+] Monitoring X active positions
...
[+] Daily monitoring complete
```

---

## Managing the Task

### View Task Details
1. Open Task Scheduler (`taskschd.msc`)
2. Navigate to: Task Scheduler Library
3. Find "Form4MonitoringAgent"
4. Double-click to view properties

### Disable Task
1. Right-click task → **"Disable"**
2. Task won't run until re-enabled

### Enable Task
1. Right-click task → **"Enable"**

### Delete Task
1. Right-click task → **"Delete"**
2. Confirm deletion

### View Task History
1. Right-click task → **"Properties"**
2. Go to **"History"** tab
3. Review all executions

### Change Schedule
1. Right-click task → **"Properties"**
2. Go to **"Triggers"** tab
3. Edit trigger
4. Change time or frequency
5. Click "OK"

---

## Log Files

### Location:
```
weekly_bot\logs\monitor_agent_YYYYMMDD_HHMMSS.log
```

### Monitoring Reports:
```
weekly_bot\form4_reports\monitoring\daily_monitoring_YYYYMMDD_HHMMSS.json
```

### View Latest Log:
```powershell
Get-Content weekly_bot\logs\monitor_agent_*.log -Tail 50
```

### View Latest Report:
```powershell
Get-Content weekly_bot\form4_reports\monitoring\daily_monitoring_*.json | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

---

## Troubleshooting

### Task Runs But Does Nothing

**Check:**
1. **IBKR Connection**: Is IBKR Gateway/TWS running?
2. **Database**: Does `trading_history.db` exist?
3. **Active Positions**: Are there positions with `status='ACTIVE'`?
4. **Python Environment**: Is `.venv-daytrader` activated?

**Solution:**
```powershell
# Test manually
& .\.venv-daytrader\Scripts\python.exe weekly_bot\form4_monitor_agent.py
```

### Task Says "Success" But No Logs

**Issue**: Working directory not set correctly

**Solution**:
1. Edit task properties
2. Go to "Actions" tab
3. Set "Start in" to: `C:\Users\orelm\OneDrive\Documents\GitHub\trade\weekly_bot`

### "Python Not Found" Error

**Issue**: Python path incorrect

**Solution**:
1. Find correct Python path:
   ```powershell
   Get-Command python | Select-Object -ExpandProperty Source
   ```
2. Update task action with correct path

### Database Not Found

**Issue**: Database path incorrect

**Solution**:
Agent looks for `trading_history.db` in project root. Verify it exists:
```powershell
Test-Path trading_history.db
```

### LLM Not Available Error

**Issue**: Missing API keys

**Solution**:
Set environment variables (user-level, persistent):
```powershell
[System.Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY', 'your-key-here', 'User')
```

Or add to `.env` file in project root:
```
DEEPSEEK_API_KEY=your-key-here
GOOGLE_API_KEY=your-key-here
```

### IBKR Connection Failed

**Issue**: IBKR not running or wrong port

**Solution**:
1. Verify IBKR Gateway/TWS is running
2. Check port in agent script (default: 4001)
3. Verify ClientId is unique (agent uses 11)

---

## Security Notes

- Task runs under your user account
- Credentials stored in Windows Credential Manager
- API keys loaded from `.env` file (not in task config)
- IBKR credentials handled by IBKR Gateway/TWS

---

## Support

**Questions?**
- Check logs: `weekly_bot\logs\monitor_agent_*.log`
- Review reports: `weekly_bot\form4_reports\monitoring\`
- Test manually before debugging Task Scheduler

**Common Commands:**
```powershell
# View all scheduled tasks
Get-ScheduledTask | Where-Object {$_.TaskName -like "*Form4*"}

# Check task status
Get-ScheduledTaskInfo -TaskName "Form4MonitoringAgent"

# Test agent manually
& .\.venv-daytrader\Scripts\python.exe weekly_bot\form4_monitor_agent.py

# View latest log
Get-Content weekly_bot\logs\monitor_agent_*.log -Tail 50
```

---

**Setup Complete!** 🎉

Your monitoring agent will now run automatically every day at 5:00 PM, checking all active positions and making intelligent hold/sell decisions.
