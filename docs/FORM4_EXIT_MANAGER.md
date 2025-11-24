# Form 4 Exit Manager - Setup Guide

## Overview

The **Form 4 Exit Manager** monitors your Form 4 positions and makes intelligent exit decisions using multi-agent LLM debate (DeepSeek + Gemini).

## Features

✅ **Automatic Position Tracking** - Syncs with IBKR to monitor P&L  
✅ **Multi-Agent Exit Decisions** - DeepSeek + Gemini debate whether to hold/sell  
✅ **Smart Exit Triggers** - Profit targets, stop losses, time limits, insider reversals  
✅ **Automatic Execution** - Places sell orders via IBKR when consensus reached  
✅ **Complete Logging** - Every decision saved with reasoning  
✅ **Manual Review Flags** - Alerts when models disagree  

## Exit Logic

### Exit Triggers:

1. **Profit Target**: +15% gain → Strong SELL signal
2. **Stop Loss**: -8% loss → Immediate exit
3. **Time Limit**: 21 days max hold → Force review
4. **Insider Reversal**: Insiders started selling → Red flag
5. **Thesis Broken**: Original analysis invalidated

### Decision Process:

```
1. Load approved positions
2. Query IBKR for current prices/P&L
3. Check for new insider activity (reversals)
4. Fetch recent news
5. Multi-agent debate: HOLD or SELL?
   - DeepSeek analyzes independently
   - Gemini analyzes independently
   - If agree: Execute consensus
   - If disagree: Flag for manual review
6. Execute sell order if SELL consensus
7. Log everything
```

## Running the Exit Manager

### Option 1: Manual Run (Recommended for Testing)

**Windows PowerShell:**
```powershell
# Dry run (analyze only, no trades)
& .\start_form4_exit_manager.bat --dry-run

# Live trading (execute sells)
& .\start_form4_exit_manager.bat

# Continuous monitoring (checks every hour)
& .\start_form4_exit_manager.bat --continuous
```

**Direct Python:**
```powershell
.\.venv-weekly\Scripts\python.exe weekly_bot\form4_exit_manager.py --dry-run
```

### Option 2: Task Scheduler (Automated Daily Runs)

**Setup Windows Task Scheduler:**

1. Open **Task Scheduler** (search in Start menu)

2. Click **"Create Basic Task"**

3. **Name**: `Form 4 Exit Manager - Daily`

4. **Trigger**: Daily at **4:30 PM** (after market close)

5. **Action**: Start a program
   - **Program**: `C:\Users\orelm\OneDrive\Documents\GitHub\trade\start_form4_exit_manager.bat`
   - **Start in**: `C:\Users\orelm\OneDrive\Documents\GitHub\trade`

6. **Conditions**:
   - ✅ Run only if computer is on AC power (uncheck for laptop)
   - ✅ Wake computer to run this task

7. **Settings**:
   - ✅ Run task as soon as possible after scheduled start is missed
   - ✅ Stop task if it runs longer than 30 minutes

**Advanced XML Configuration** (optional):

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2025-11-19T16:30:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>C:\Users\orelm\OneDrive\Documents\GitHub\trade\start_form4_exit_manager.bat</Command>
      <WorkingDirectory>C:\Users\orelm\OneDrive\Documents\GitHub\trade</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```

### Option 3: Server Deployment

**Run on a dedicated server/VPS:**

```bash
# Install as systemd service (Linux)
sudo nano /etc/systemd/system/form4-exit.service
```

```ini
[Unit]
Description=Form 4 Exit Manager
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/trade
ExecStart=/home/trader/trade/.venv-weekly/bin/python /home/trader/trade/weekly_bot/form4_exit_manager.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable form4-exit.service
sudo systemctl start form4-exit.service
sudo systemctl status form4-exit.service
```

## Configuration

**Edit exit parameters** in `form4_exit_manager.py`:

```python
# Exit Parameters (lines 61-64)
PROFIT_TARGET_PCT = 15.0   # Take profit at +15%
STOP_LOSS_PCT = -8.0       # Stop loss at -8%
FORCE_EXIT_DAYS = 21       # Force review after 21 days
CHECK_INTERVAL = 3600      # Check every hour (3600 seconds)
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Analyze positions but DON'T execute trades (safe testing) |
| `--continuous` | Run continuously with hourly checks (monitoring mode) |
| *(none)* | Single run: analyze and execute exits if needed |

## Output Files

### Exit Logs:
`weekly_bot/form4_reports/exit_logs/exit_{SYMBOL}_{TIMESTAMP}.json`

**Example:**
```json
{
  "timestamp": "2025-11-19 16:30:00",
  "position": {
    "symbol": "WM",
    "quantity": 1,
    "entry_price": 212.86,
    "current_price": 245.50,
    "pnl_dollars": 32.64,
    "pnl_pct": 15.3,
    "days_held": 14
  },
  "decision": {
    "decision": "SELL",
    "confidence": 0.95,
    "reasoning": "CONSENSUS: Profit target exceeded (15.3% > 15%), no insider selling, positive momentum",
    "urgency": "MEDIUM",
    "agreement_score": 1.0,
    "deepseek_view": {...},
    "gemini_view": {...}
  },
  "execution": {
    "status": "FILLED",
    "fill_price": 245.50,
    "pnl_dollars": 32.64,
    "pnl_pct": 15.3
  }
}
```

### Logs:
`logs/form4_exit_manager_{TIMESTAMP}.log`

## Integration with Form 4 Strategy

### Workflow:

```
Sunday: Form 4 Strategy (05_form4_strategy.py)
├─ Analyzes insider signals
├─ Multi-agent debate for entries
├─ Executes BUY orders
└─ Saves approved_positions_YYYYMMDD_HHMMSS.json

Daily: Exit Manager (form4_exit_manager.py)
├─ Loads most recent approved_positions file
├─ Syncs with IBKR portfolio
├─ Tracks P&L for each position
├─ Multi-agent debate for exits
└─ Executes SELL orders when consensus reached
```

## Multi-Agent Debate Example

**Scenario:** WM up +15.3% after 14 days

**DeepSeek Analysis:**
```
Decision: SELL
Confidence: 95%
Reasoning: Profit target exceeded, hold period reasonable, 
no negative signals. Lock in gains.
```

**Gemini Analysis:**
```
Decision: SELL
Confidence: 90%
Reasoning: +15% target hit, waste management sector stable, 
take profit and redeploy capital.
```

**Consensus:**
```
✓ Both agree: SELL
✓ High confidence: 92.5%
✓ Agreement score: 1.0 (strong consensus)
→ Execute sell order immediately
```

## Troubleshooting

### Issue: "No approved positions to monitor"
**Solution:** Run `05_form4_strategy.py` first to create positions

### Issue: "Cannot proceed without IBKR connection"
**Solution:** 
- Ensure IBKR Gateway/TWS is running
- Check port 4001 is accessible
- Verify ClientId 11 is not in use

### Issue: "Both models failed - using rule-based decision"
**Solution:**
- Check API keys in `.env`:
  ```
  DEEPSEEK_API_KEY=your-key
  GOOGLE_API_KEY=your-key
  ```
- Verify API credits/quota

### Issue: Models disagree (manual review required)
**Action:** This is intentional! Check the exit log to see both perspectives:
- `deepseek_view`: DeepSeek's reasoning
- `gemini_view`: Gemini's reasoning
- Make manual decision based on both analyses

## Best Practices

1. **Always test with `--dry-run` first** before live trading
2. **Review exit logs daily** to understand decisions
3. **Monitor disagreement cases** - often the most insightful
4. **Adjust parameters** based on your risk tolerance
5. **Keep IBKR Gateway running** during market hours
6. **Check logs** if positions aren't exiting as expected

## Safety Features

✅ **Conservative default**: Models disagree → HOLD (don't exit)  
✅ **Stop losses**: Automatic exit at -8% to protect capital  
✅ **Force exits**: Maximum 21-day hold prevents "forgotten positions"  
✅ **Insider reversal detection**: Exits when insiders start selling  
✅ **Complete audit trail**: Every decision logged with reasoning  

## Monitoring Schedule Recommendations

| Frequency | Use Case | Setup |
|-----------|----------|-------|
| **Once Daily (4:30 PM)** | Recommended for most users | Task Scheduler |
| **2-3x Daily** | Active management, quick exits | Task Scheduler (multiple) |
| **Continuous (hourly)** | Maximum monitoring | `--continuous` flag |
| **Weekly** | Very long-term holders | Manual runs |

## Next Steps

1. **Test in dry-run mode:**
   ```powershell
   & .\start_form4_exit_manager.bat --dry-run
   ```

2. **Review the analysis** - Check what decisions it would make

3. **Enable live trading** when comfortable:
   ```powershell
   & .\start_form4_exit_manager.bat
   ```

4. **Set up Task Scheduler** for daily automated runs

5. **Monitor logs** and adjust parameters as needed

## Questions?

- Check `logs/form4_exit_manager_*.log` for detailed execution logs
- Review `exit_logs/exit_*.json` for decision reasoning
- Adjust parameters in `form4_exit_manager.py` lines 61-64
- Test with `--dry-run` anytime you're unsure

---

**Remember:** This is a complementary system to your Form 4 buying strategy. It ensures you:
- Lock in profits when targets hit
- Cut losses before they grow
- Exit when original thesis breaks
- Never hold "forgotten positions"

**The multi-agent debate ensures exit decisions are as rigorous as your entry decisions!**
