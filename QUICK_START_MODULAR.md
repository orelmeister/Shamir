# 🚀 Quick Start Guide - Modular Weekly Bot

## Overview
The weekly bot is now split into **4 independent phases** that run sequentially. Each phase can be restarted individually if it fails, making debugging 10x easier.

---

## 🎯 Daily Workflow (Recommended)

### **Option 1: Full Cycle (First Run / Monday Morning)**
Use this when you need fresh market data (once per week or when markets change significantly).

```powershell
# Open PowerShell in your project directory
cd C:\Users\orelm\OneDrive\Documents\GitHub\trade

# Activate the weekly bot environment
.\.venv-weekly\Scripts\Activate.ps1

# Run the orchestrator
python weekly_orchestrator.py
```

**When prompted, select:** `1` (Full Cycle)

**What happens:**
1. ✅ **Phase 1** (Data Aggregation) - Fetches market data from 1600+ stocks (~10-15 min)
2. ✅ **Phase 2** (Analyst) - LLM analysis + Monte Carlo ranking (~5-10 min)
3. ✅ **Phase 3** (Portfolio Manager) - Rebalances to top 5 picks (~2 min)
4. ✅ **Phase 4** (Monitor) - Runs in background until market close

**Expected runtime:** 15-25 minutes total

---

### **Option 2: Quick Start (Daily Use / Fresh Analysis Only)**
Use this when `full_market_data.json` is already fresh (< 24 hours old).

```powershell
python weekly_orchestrator.py
```

**When prompted, select:** `2` (Quick Start)

**What happens:**
1. ⏭️ **Phase 1** SKIPPED (uses existing `full_market_data.json`)
2. ✅ **Phase 2** (Analyst) - Fresh LLM analysis with latest data
3. ✅ **Phase 3** (Portfolio Manager) - Rebalancing decision
4. ✅ **Phase 4** (Monitor) - Background monitoring

**Expected runtime:** 5-10 minutes total

**⚠️ Important:** If analysis was already run today and `full_analysis_results.json` exists, Phase 2 will load cached results (very fast).

---

## 🛠️ Advanced Workflows

### **Re-run Analysis Only (No Trading)**
If you want to re-analyze stocks without executing trades:

```powershell
python weekly_orchestrator.py
# Select: 3 (Analysis Only)
```

Use cases:
- Test different LLM models
- Compare analysis results
- Check top picks without committing to trades

---

### **Execute Trades with Existing Analysis**
If analysis is already done and you want to execute the rebalancing:

```powershell
python weekly_orchestrator.py
# Select: 4 (Rebalance Only)
```

Use cases:
- Analysis ran earlier, now market is open
- Previous rebalancing attempt failed
- Manual approval workflow (analyze → review → execute)

---

### **Monitor Positions Only**
If positions are already open and you just want monitoring:

```powershell
python weekly_orchestrator.py
# Select: 5 (Monitor Only)
```

Use cases:
- Bot crashed but positions are open
- Manual trades executed, need stop-loss monitoring
- Testing monitoring logic

---

## 📊 Understanding the Menu

```
1. Full Cycle          → Aggregation → Analysis → Rebalance → Monitor
2. Quick Start         → [Skip Aggregation] → Analysis → Rebalance → Monitor
3. Analysis Only       → [Skip Aggregation] → Analysis [Stop]
4. Rebalance Only      → [Use existing analysis] → Rebalance [Stop]
5. Monitor Only        → [Monitor existing positions] → Monitor until close
6. Exit                → Quit without running
```

---

## 📂 Understanding Generated Files

### **Phase Outputs**
| File | Created By | Purpose |
|------|-----------|---------|
| `full_market_data.json` | Phase 1 | Raw market data (1600+ stocks) |
| `full_analysis_results.json` | Phase 2 | LLM analysis for all stocks |
| `shared_state/phase_state.json` | Orchestrator | Current phase + top picks |
| `shared_state/positions_state.json` | Phase 3 & Day Trader | All open positions |
| `shared_state/position_tracking.json` | Phase 3 | Stop-loss tracking |

### **Logs**
All logs are in `logs/` directory:
```
logs/
├── orchestrator_20251104_070000.log       # Main workflow
├── data_aggregator_20251104_070100.log    # Phase 1
├── analyst_20251104_073000.log            # Phase 2
├── portfolio_manager_20251104_080000.log  # Phase 3
└── monitor_20251104_090000.log            # Phase 4
```

**💡 Tip:** If a phase fails, check its log file for details.

---

## 🔄 Coordination with Day Trader

### **How Bots Avoid Conflicts**

**Before the refactor:**
- ❌ Day trader could liquidate weekly positions by accident
- ❌ Weekly bot didn't know about day trading positions
- ❌ Position tracking was unreliable

**After the refactor:**
- ✅ `positions_state.json` tracks ALL positions
- ✅ Day trader reads `weekly_positions` and **skips them**
- ✅ Weekly bot reads `day_trader_positions` and **ignores them**
- ✅ No accidental liquidations!

### **Running Both Bots**

**1. Start Weekly Bot (Long-term holds)**
```powershell
# Terminal 1
python weekly_orchestrator.py
# Select: 1 or 2
```

**2. Start Day Trader (Intraday trades)**
```powershell
# Terminal 2
.\.venv-daytrader\Scripts\Activate.ps1
python day_trader.py --allocation 0.25
```

**3. Check Coordination**
```powershell
# View shared state
Get-Content shared_state\positions_state.json
```

**Expected output:**
```json
{
  "weekly_positions": ["AAPL", "TSLA", "NVDA"],
  "day_trader_positions": ["SOFI", "PLTR"],
  "last_updated": "2025-11-04T10:30:00"
}
```

---

## 🧪 Testing (Paper Trading)

### **Test the Weekly Bot (No Real Money)**

```powershell
# Make sure IBKR Paper Trading account is configured in TWS/Gateway
# Port: 4001 (paper) or 4002 (paper alternative)

# The bot automatically uses port 4001
python weekly_orchestrator.py
```

**⚠️ Important:**
- Weekly bot connects to `127.0.0.1:4001` with `clientId=1`
- Day trader connects to `127.0.0.1:4001` with `clientId=2`
- Make sure TWS or Gateway is running on port 4001

---

## 🐛 Troubleshooting

### **Problem: "phase_state.json not found"**
**Solution:** Run Option 1 (Full Cycle) first to initialize shared state.

```powershell
python weekly_orchestrator.py
# Select: 1
```

---

### **Problem: Phase 2 says "No stocks to analyze"**
**Cause:** Phase 1 didn't find any qualifying stocks OR `full_market_data.json` is missing.

**Solution:**
```powershell
# Delete old data and re-aggregate
Remove-Item full_market_data.json -ErrorAction SilentlyContinue
python weekly_orchestrator.py
# Select: 1 (Full Cycle)
```

---

### **Problem: "No top picks from analysis"**
**Cause:** LLM didn't find any BUY recommendations with confidence ≥75%.

**Solution:**
1. Check `full_analysis_results.json` to see what the LLM said:
```powershell
Get-Content full_analysis_results.json | ConvertFrom-Json | Select-Object ticker, decision, confidence
```

2. If all stocks are "HOLD", market conditions may not meet the aggressive growth criteria.

3. Options:
   - Wait for better market conditions
   - Lower `MIN_CONFIDENCE_SCORE` in `02_analyst.py` (line 15)
   - Use legacy `main_legacy.py` with different strategy

---

### **Problem: "Insufficient improvement - holding current positions"**
**Cause:** Current portfolio is already good enough (improvement < 5% threshold).

**What this means:**
- Weekly bot calculated expected returns for current vs optimized portfolio
- Difference is < 5%, so it's not worth rebalancing (avoid excessive trading)

**Options:**
1. **Keep current positions** (recommended - the bot is protecting you from overtrading)
2. Lower `REBALANCE_THRESHOLD` in `03_portfolio_manager.py` (line 23)
3. Force rebalancing by manually selling current positions first

**💡 This is INTENTIONAL behavior to reduce commissions and avoid churn.**

---

### **Problem: Phase fails with connection error**
**Cause:** IBKR TWS or Gateway is not running or wrong port.

**Solution:**
1. Check if TWS or Gateway is running
2. Verify port is 4001 (paper) or 4001 (live)
3. Check clientId conflicts:
   ```powershell
   # Weekly bot uses clientId=1
   # Day trader uses clientId=2
   # Don't run multiple instances with same clientId!
   ```

---

### **Problem: Monitor exits immediately**
**Cause:** Market is closed.

**Solution:** Monitor only runs during market hours (9:30 AM - 4:00 PM ET). If you run it outside hours, it will exit immediately. This is intentional.

**To test monitor:**
```powershell
# Wait for market open, then:
python weekly_orchestrator.py
# Select: 5 (Monitor Only)
```

---

## 📋 Daily Checklist

### **Monday Morning (Market Open at 9:30 AM ET)**
```powershell
# 1. Check if IBKR is running
# 2. Run weekly bot
python weekly_orchestrator.py
# Select: 1 (Full Cycle) or 2 (Quick Start if data is fresh)

# 3. (Optional) Start day trader in separate terminal
.\.venv-daytrader\Scripts\Activate.ps1
python day_trader.py --allocation 0.25
```

### **During Trading Hours**
- Monitor runs automatically in background
- Check `logs/monitor_*.log` for position updates
- Stop losses execute automatically (no action needed)

### **End of Day (3:45 PM - 4:00 PM ET)**
- Monitor stops automatically at market close
- Review logs:
  ```powershell
  # Check today's trades
  Get-Content logs\orchestrator_*.log | Select-String "✅|❌|🛑"
  ```

### **Weekday Maintenance**
- **Tuesday-Friday:** Use Option 2 (Quick Start) for fresh analysis
- **Weekend:** No action needed (market closed)
- **Monthly:** Run Option 1 (Full Cycle) to refresh entire dataset

---

## 🆘 Emergency: Revert to Legacy System

If the modular system has issues, you can instantly revert to the original monolithic bot:

```powershell
python main_legacy.py
```

**When to use legacy:**
- Modular system has a bug
- Need proven stable system during critical trading
- Testing/comparing results

**💡 Both systems can coexist!** Use whichever works best for you.

---

## 📞 Getting Help

### **Check Logs First**
```powershell
# View most recent orchestrator log
Get-Content logs\orchestrator_*.log -Tail 50

# View specific phase log
Get-Content logs\analyst_*.log -Tail 50
```

### **Check Shared State**
```powershell
# View current phase
Get-Content shared_state\phase_state.json | ConvertFrom-Json

# View all positions
Get-Content shared_state\positions_state.json | ConvertFrom-Json

# View position tracking (stops)
Get-Content shared_state\position_tracking.json | ConvertFrom-Json
```

### **Useful Debug Commands**
```powershell
# List all phase scripts
Get-ChildItem weekly_bot\*.py

# Check if data files exist
Test-Path full_market_data.json
Test-Path full_analysis_results.json

# View top 5 analyzed stocks
Get-Content full_analysis_results.json | ConvertFrom-Json | Select-Object -First 5 ticker, decision, confidence

# Check IBKR connection
python test_connection.py
```

---

## 🎓 Understanding the 5% Rebalancing Threshold

**Why does the bot sometimes refuse to trade?**

The weekly bot uses **portfolio optimization** to determine if rebalancing is worth it:

1. **Calculates expected return** of current portfolio
2. **Calculates expected return** of optimized portfolio (top 5 picks)
3. **Compares improvement**:
   - If improvement > 5% → **REBALANCE** ✅
   - If improvement < 5% → **HOLD** 🔒

**Example:**
```
Current Portfolio: AAPL, MSFT, GOOGL (expected return: 12%)
Optimized Portfolio: NVDA, TSLA, AMD (expected return: 12.3%)
Improvement: 0.3% / 12% = 2.5%
Decision: HOLD (2.5% < 5% threshold)
```

**Why 5%?**
- Avoids excessive trading (commissions add up!)
- Reduces tax implications (short-term capital gains)
- Prevents churn from minor market fluctuations

**To change the threshold:**
Edit `weekly_bot/03_portfolio_manager.py` line 23:
```python
REBALANCE_THRESHOLD = 0.05  # Change to 0.03 for 3% threshold
```

---

## 🚀 Pro Tips

### **Speed Up Daily Runs**
```powershell
# Always use Quick Start if data is < 24 hours old
python weekly_orchestrator.py
# Select: 2
```

### **Run Individual Phases for Debugging**
```powershell
# Test just the analyst
cd weekly_bot
python 02_analyst.py

# Test just portfolio manager
python 03_portfolio_manager.py
```

### **Force Fresh Analysis**
```powershell
# Delete cached analysis to force re-run
Remove-Item full_analysis_results.json
python weekly_orchestrator.py
# Select: 2 (Quick Start)
```

### **Monitor Multiple Logs in Real-Time**
```powershell
# Terminal 1: Orchestrator
Get-Content logs\orchestrator_*.log -Wait -Tail 10

# Terminal 2: Monitor
Get-Content logs\monitor_*.log -Wait -Tail 10
```

---

## 📈 Expected Performance

### **Phase Runtimes**
| Phase | Runtime | Can Skip? |
|-------|---------|-----------|
| Phase 1: Data Aggregation | 10-15 min | ✅ Yes (use cached data) |
| Phase 2: Analyst | 5-10 min | ✅ Yes (use cached analysis) |
| Phase 3: Portfolio Manager | 1-2 min | ❌ No |
| Phase 4: Monitor | Continuous | ✅ Yes (if no positions) |

### **Full Cycle vs Quick Start**
```
Full Cycle:     15-25 minutes (all phases)
Quick Start:    5-10 minutes (skip aggregation)
Rebalance Only: 1-2 minutes (skip aggregation + analysis)
```

---

## ✅ Success Indicators

**You'll know it's working when you see:**

1. **Orchestrator log shows:**
   ```
   ✅ Phase 1 completed successfully
   ✅ Phase 2 completed successfully  
   ✅ Phase 3 completed successfully
   ✅ Monitor started (PID: 12345)
   ```

2. **Shared state files exist:**
   ```powershell
   ls shared_state\*.json
   # Should show: phase_state.json, positions_state.json, orders_state.json
   ```

3. **IBKR shows orders/positions** matching the log output

4. **Monitor log shows position updates** every 5 minutes

---

## 🎉 You're Ready!

**Start with:**
```powershell
python weekly_orchestrator.py
# Select: 1 (Full Cycle) for first run
# Select: 2 (Quick Start) for daily use
```

**Questions?** Check the logs first, then review the troubleshooting section above.

**Happy trading! 🚀**
