# 🚀 Quick Start Guide

**Get your day trading bot running in 10 minutes.**

---

## Step 1: Prerequisites ✅

### Required Software
- [ ] Python 3.12 or higher
- [ ] Interactive Brokers Gateway or TWS
- [ ] Paper Trading Account (recommended for testing)

### API Keys Needed
```bash
DEEPSEEK_API_KEY=sk-...        # Required - LLM analysis
FMP_API_KEY=...                 # Required - Market data
POLYGON_API_KEY=...             # Required - Technical indicators
GOOGLE_API_KEY=...              # Optional - Backup LLM
```

**Get API Keys:**
- DeepSeek: https://platform.deepseek.com/
- FMP: https://site.financialmodelingprep.com/
- Polygon: https://polygon.io/

---

## Step 2: Installation 📦

```powershell
# Clone and navigate to repository
cd C:\Users\orelm\OneDrive\Documents\GitHub\trade

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Step 3: Configuration ⚙️

### Create `.env` file in root directory:

```env
# API Keys
DEEPSEEK_API_KEY=sk-your-deepseek-key-here
FMP_API_KEY=your-fmp-key-here
POLYGON_API_KEY=your-polygon-key-here
GOOGLE_API_KEY=your-google-key-here

# IBKR Settings (usually defaults work)
IBKR_HOST=127.0.0.1
IBKR_PORT=4001
IBKR_CLIENT_ID=4
```

---

## Step 4: Start IBKR Gateway 🏦

1. **Open IBKR Gateway** (or TWS if you prefer)
2. **Login** to your paper trading account
3. **Configure API Settings:**
   - Enable ActiveX and Socket Clients
   - Socket Port: **4001**
   - Master API Client ID: Leave blank (or set to 0)
   - Read-Only API: **Unchecked**
4. **Connect**

### Verify Connection

```powershell
python -c "from ib_insync import IB; ib = IB(); ib.connect('127.0.0.1', 4001, clientId=99); print('✅ Connected!'); ib.disconnect()"
```

Expected output: `✅ Connected!`

---

## Step 5: First Test Run 🧪

### Manual Run (Recommended First Time)

```powershell
# Activate virtual environment
.venv\Scripts\activate

# Run bot with 10% capital allocation
python day_trader.py --allocation 0.10
```

### What to Expect

The bot will:
1. ✅ Screen 1600+ tickers (6:55 AM ET or immediately if testing)
2. ✅ Collect market data
3. ✅ Analyze with DeepSeek AI and select top 8 stocks
4. ✅ Validate stocks with IBKR
5. ✅ Calculate pre-market momentum
6. ✅ Start trading at 9:30 AM ET

### During Market Hours

Watch for:
- `ENTRY SIGNAL` - Bot found a trading opportunity
- `Placing BUY limit order` - Order submitted
- `PENDING BUY FILLED` - Position acquired
- `PROFIT TARGET` / `STOP LOSS` - Position closed
- `📊 Daily P&L: $+X.XX (+X.XX%)` - Progress toward 1.8% target

---

## Step 6: Monitor Performance 📊

### View Live Logs

```powershell
# In a new terminal window
python view_logs.py --live
```

### Check Positions

```powershell
# See current positions from today's watchlist
python liquidate_today.py

# See ALL positions (including old ones)
python liquidate_all.py
```

### Important Files

```
logs/day_trader_run_YYYYMMDD_HHMMSS.json   # Today's trading log
day_trading_watchlist.json                 # Today's 8 stocks
trading_performance.db                     # Performance metrics
trading_history.db                         # All historical trades
```

---

## Step 7: Automated Scheduling 🤖

### Windows Task Scheduler Setup

1. **Open Task Scheduler**
2. **Create Basic Task**
   - Name: `Day Trading Bot`
   - Trigger: **Daily at 6:55 AM**
   - Action: **Start a program**
     - Program: `C:\path\to\start_day_trader.bat`
     - Start in: `C:\Users\orelm\OneDrive\Documents\GitHub\trade`
3. **Configure for:**
   - Run whether user is logged on or not: ✅
   - Run with highest privileges: ✅
   - Hidden: ✅ (optional)

### Test Scheduled Task

```powershell
# Right-click task → Run
# Check logs folder for new log file
```

---

## Common Issues & Solutions 🔧

### Issue: "Error 201: Available settled cash... 2.97 USD"
**Solution**: ✅ Already fixed! Bot uses `ExcessLiquidity` now.

### Issue: Orders stuck in "PendingSubmit"
**Solution**: ✅ Already fixed! Bot uses limit orders now.

### Issue: Old positions locking buying power
```powershell
# Wait for market to open, then:
python liquidate_all.py
```

### Issue: Bot not connecting to IBKR
- Verify Gateway is running on port 4001
- Check API settings enabled in Gateway
- Try changing clientId in command: `python day_trader.py --allocation 0.10`

### Issue: DeepSeek API errors
- Check API key in `.env`
- Verify you have credits: https://platform.deepseek.com/
- Rate limit: 10 requests/minute

---

## Daily Checklist ✓

**Before Market Open (9:25 AM ET):**
- [ ] IBKR Gateway running and connected
- [ ] No error emails/notifications from previous day
- [ ] Check for old positions: `python liquidate_today.py`
- [ ] Verify API keys not expired

**After Market Close (4:05 PM ET):**
- [ ] Review today's trades in logs
- [ ] Check daily P&L achieved 1.8% or understand why not
- [ ] Verify all positions liquidated
- [ ] Review any errors in log file

---

## Next Steps 🎯

1. **Paper trade for 2 weeks** - Build confidence in the system
2. **Review strategy documentation** - See `STRATEGY_CHANGES.md`
3. **Understand autonomous features** - See `AUTONOMOUS_SYSTEM_README.md`
4. **Monitor performance metrics** - Check `trading_performance.db`
5. **Adjust parameters if needed** - See `DAY_TRADER_CONFIGURATION.md`

---

## Getting Help 💬

**Documentation:**
- Strategy details: `STRATEGY_CHANGES.md`
- Configuration: `DAY_TRADER_CONFIGURATION.md`
- Pre-trading checklist: `PRE_TRADING_CHECKLIST.md`
- Task scheduling: `TASK_SCHEDULER_SETUP.md`

**Quick Debug:**
```powershell
# Check IBKR connection
python -c "from ib_insync import IB; ib = IB(); ib.connect('127.0.0.1', 4001, clientId=99); print(f'Account: {ib.accountSummary()[0].account}'); ib.disconnect()"

# Check API keys loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('DeepSeek:', 'OK' if os.getenv('DEEPSEEK_API_KEY') else 'MISSING'); print('FMP:', 'OK' if os.getenv('FMP_API_KEY') else 'MISSING')"
```

---

**Ready to trade! 🎉**

Remember: Start with paper trading and monitor closely for the first week.
