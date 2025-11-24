# Day Trading Bot - Task Scheduler Guide

## ✅ Setup Complete

The **DayTradingBot** task is now scheduled to run automatically on **Monday-Friday at 6:00 AM Pacific Time**.

## 📋 Task Details

- **Task Name:** DayTradingBot
- **Schedule:** Monday-Friday, 6:00 AM PT
- **Command:** `python.exe day_trader.py --allocation 1.0`
- **Working Directory:** `C:\Users\orelm\OneDrive\Documents\GitHub\trade`
- **Capital Limit:** $1,000 (hard-coded in day_trading_agents.py)
- **Max Runtime:** 12 hours (auto-terminates at 6:00 PM)

## ⏰ Daily Timeline (Pacific Time)

```
6:00 AM  - Bot starts
           ├─ Phase 0: Data aggregation (FMP/Polygon APIs)
6:30 AM  - Phase 1: LLM analysis (DeepSeek/Gemini)
6:45 AM  - Phase 1.5: IBKR contract validation
7:00 AM  - Phase 1.75: Pre-market momentum analysis
9:30 AM  - Market opens → Trading begins
           ├─ Scanner refreshes every 5 minutes
           ├─ Position monitoring every 1 second
           ├─ Entry: VWAP momentum + RSI < 60 + ATR >= 0.3%
           ├─ Exit: +1.8% profit OR -0.9% stop loss
4:00 PM  - Market closes → All positions liquidated
           ├─ Daily performance analysis
           ├─ Autonomous improvement cycle
           └─ Reports saved to reports/improvement/
```

## 🔧 Management Commands

### View Task Status
```powershell
Get-ScheduledTask -TaskName "DayTradingBot"
Get-ScheduledTaskInfo -TaskName "DayTradingBot"
```

### Run Task Manually (Test)
```powershell
Start-ScheduledTask -TaskName "DayTradingBot"
```

### Disable Task (Temporarily)
```powershell
Disable-ScheduledTask -TaskName "DayTradingBot"
```

### Enable Task
```powershell
Enable-ScheduledTask -TaskName "DayTradingBot"
```

### Remove Task (Permanently)
```powershell
Unregister-ScheduledTask -TaskName "DayTradingBot" -Confirm:$false
```

## 📊 Monitoring

### Real-Time Log Monitoring
```powershell
Get-Content logs\day_trader_run_*.json -Tail 50 -Wait
```

### Check Capital Limit
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Fixed Day Trading Budget"
```

### View Latest Logs
```powershell
Get-Content logs\day_trader_run_*.json -Tail 50
```

### Check Position Isolation
```powershell
& .\.venv-daytrader\Scripts\python.exe -c "
from observability import get_database
db = get_database()
dt = db.get_positions_by_agent('day_trader')
f4 = db.get_positions_by_agent('form4_strategy')
print(f'Day Trader: {len(dt)} positions')
print(f'Form4 Strategy: {len(f4)} positions')
"
```

### Database Query (All Day Trader Trades)
```powershell
& .\.venv-daytrader\Scripts\python.exe -c "
from observability import get_database
import pandas as pd
db = get_database()
trades = db.get_trades_by_agent('day_trader')
df = pd.DataFrame(trades)
print(df[['timestamp', 'symbol', 'action', 'quantity', 'price', 'reason']].tail(10))
"
```

## ✅ Monday Morning Checklist (Nov 25)

### Pre-Market (6:00-9:30 AM)

**1. Verify Task Started Automatically**
```powershell
Get-ScheduledTaskInfo -TaskName "DayTradingBot"
# Check LastRunTime shows 6:00 AM today
```

**2. Monitor Phase Progression**
```powershell
Get-Content logs\day_trader_run_*.json -Tail 50 -Wait
# Look for:
# - "Phase 0: Data aggregation started"
# - "Phase 1: LLM analysis completed"
# - "Phase 1.5: Validated X/Y contracts"
# - "Phase 1.75: Pre-market momentum complete"
```

**3. Verify Capital Limit**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Fixed Day Trading Budget"
# Should show: "Fixed Day Trading Budget: $1000.00"
```

**4. Check Watchlist Generation**
```powershell
Test-Path day_trading_watchlist.json
Get-Content day_trading_watchlist.json | ConvertFrom-Json | Measure-Object
# Should have 5-10 stocks ready for trading
```

### Market Open (9:30 AM)

**5. Verify Position Sync Isolation**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Position sync completed"
# Should show Form4 positions detected but NOT synced
```

**6. Monitor First Entry**
```powershell
Get-Content logs\day_trader_run_*.json -Tail 50 -Wait
# Look for:
# - "Entry signal: VWAP momentum"
# - "Placed LimitOrder: BUY X shares at $Y.YY"
# - Position added to tracking
```

**7. Verify Capital Allocation**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Capital per stock"
# Example: "Capital per stock: $125.00 (across 8 stocks)"
```

### Throughout Day

**8. Monitor Scanner Refresh (Every 5 Minutes)**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Scanner analysis completed"
# Should see entries every 5 minutes (300 seconds)
```

**9. Check Position Monitoring (Every 1 Second)**
```powershell
# Logs will be verbose - only check if issues arise
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Monitoring" -Context 0,2
```

### End of Day (4:00 PM)

**10. Verify Liquidation**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Liquidation"
# Should show all day_trader positions closed
```

**11. Check Final Performance**
```powershell
& .\.venv-daytrader\Scripts\python.exe analyze_today.py
# Shows P&L, win rate, improvement insights
```

**12. Verify Form4 Positions Untouched**
```powershell
& .\.venv-daytrader\Scripts\python.exe quick_position_check.py
# Form4 positions should still be open
```

## 🎯 Success Criteria

- ✅ Task runs automatically at 6:00 AM PT
- ✅ Capital limited to exactly $1,000 (verified in logs)
- ✅ Form4 positions remain isolated (not synced or traded)
- ✅ Day trader positions tagged with `agent_name='day_trader'` in database
- ✅ Scanner refreshes every 5 minutes (not 15)
- ✅ Position monitoring every 1 second (not 5)
- ✅ All day_trader positions closed by 4:00 PM PT
- ✅ Improvement report generated and saved

## 🚨 Troubleshooting

### Task Didn't Run

**Check if task exists:**
```powershell
Get-ScheduledTask -TaskName "DayTradingBot"
```

**Check last run status:**
```powershell
Get-ScheduledTaskInfo -TaskName "DayTradingBot"
# LastTaskResult: 0 = Success, anything else = error
```

**Manually trigger to test:**
```powershell
Start-ScheduledTask -TaskName "DayTradingBot"
```

### Capital Over $1,000

**Verify code implementation:**
```powershell
Select-String -Path "day_trading_agents.py" -Pattern "fixed_day_trading_budget"
# Should show: fixed_day_trading_budget = 1000.0
```

**Check logs for calculation:**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "Available for Day Trading"
# Should never exceed $1,000.00
```

### Form4 Positions Interfered With

**Check database ownership:**
```powershell
& .\.venv-daytrader\Scripts\python.exe -c "
from observability import get_database
db = get_database()
all_trades = db.get_trades_by_date('2025-11-25')
for t in all_trades:
    print(f\"{t['timestamp']} - {t['agent_name']} - {t['action']} {t['symbol']}\")
"
```

**Expected output:**
- All Form4 trades: `agent_name='form4_strategy'`
- All day trades: `agent_name='day_trader'`
- No overlap in symbols between agents

### No Entries All Day

**Check ATR threshold (common issue):**
```powershell
Select-String -Path "logs\day_trader_run_*.json" -Pattern "ATR too low"
# On quiet days, expect 9000+ rejections - this is NORMAL
```

**Check scanner found stocks:**
```powershell
Get-Content day_trading_watchlist.json | ConvertFrom-Json | Measure-Object
# Should have at least 3-5 stocks
```

**Check IBKR connection:**
```powershell
& .\.venv-daytrader\Scripts\python.exe test_connection.py
```

## 🔄 Next Week Schedule

The task will automatically run:
- **Monday, Nov 25** at 6:00 AM
- **Tuesday, Nov 26** at 6:00 AM
- **Wednesday, Nov 27** at 6:00 AM (half-day before Thanksgiving)
- **Thursday, Nov 28** - SKIPPED (Thanksgiving - market closed)
- **Friday, Nov 29** at 6:00 AM (Black Friday - half day, closes 1:00 PM)

**Note:** Bot will detect market closed days and skip trading automatically.

## 📈 Performance Tracking

All trades logged to database: `databases/trading_history.db`

**Daily Performance Query:**
```powershell
& .\.venv-daytrader\Scripts\python.exe -c "
from observability import get_database
import pandas as pd
from datetime import date

db = get_database()
metrics = db.get_daily_metrics('day_trader', date.today().isoformat())
print(f'P&L: \${metrics[\"pnl\"]:.2f}')
print(f'Win Rate: {metrics[\"win_rate\"]:.1%}')
print(f'Trades: {metrics[\"trades_count\"]}')
"
```

**Weekly Summary:**
```powershell
& .\.venv-daytrader\Scripts\python.exe -c "
from observability import get_database
from datetime import date, timedelta
import pandas as pd

db = get_database()
end = date.today()
start = end - timedelta(days=7)

trades = db.get_trades_by_agent('day_trader')
df = pd.DataFrame(trades)
df['timestamp'] = pd.to_datetime(df['timestamp'])
week_trades = df[df['timestamp'] >= pd.Timestamp(start)]

print(f'Total Trades: {len(week_trades)}')
print(f'Total Volume: \${week_trades[\"quantity\"] * week_trades[\"price\"]:.2f}')
print(f'Most Traded: {week_trades[\"symbol\"].value_counts().head(3)}')
"
```

## 🛡️ Safety Features

1. **Capital Limit:** Hard-coded $1,000 maximum
2. **Position Isolation:** Database ownership prevents cross-agent interference
3. **Auto-Liquidation:** All positions closed by 4:00 PM
4. **Health Monitoring:** Every 60 seconds
5. **Auto-Healing:** Position sync, connection recovery
6. **Stop Losses:** Manual monitoring at -0.9% (not IBKR orders)
7. **Network Requirement:** Task won't run without internet
8. **Battery Safe:** Won't stop if laptop unplugged

## 📞 Emergency Actions

### Stop Trading Immediately
```powershell
# Find the Python process
Get-Process python | Where-Object {$_.Path -like "*daytrader*"}

# Kill it (replace PID)
Stop-Process -Id <PID> -Force
```

### Disable Future Runs
```powershell
Disable-ScheduledTask -TaskName "DayTradingBot"
```

### Close All Positions Manually
```powershell
& .\.venv-daytrader\Scripts\python.exe -c "
from ib_insync import IB, util
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)
positions = ib.positions()
for p in positions:
    if p.position > 0:
        order = MarketOrder('SELL', p.position)
        order.tif = 'IOC'
        order.outsideRth = True
        ib.placeOrder(p.contract, order)
print('All positions liquidated')
"
```

---

**Setup Date:** November 24, 2025  
**Next Run:** Monday, November 25, 2025 at 6:00 AM PT  
**Capital Limit:** $1,000  
**Status:** ✅ Active and Ready
