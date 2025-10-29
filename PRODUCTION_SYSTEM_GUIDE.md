# Production Trading System - Complete Guide

## 🤖 System Overview

This is a **fully autonomous, fault-tolerant day trading system** with two coordinated bots:

```
┌─────────────────────────────────────────────────────────┐
│              TRADING BOT SUPERVISOR                      │
│  (Monitors & auto-restarts both bots)                   │
└────────────┬───────────────────────────┬────────────────┘
             │                           │
    ┌────────▼────────┐         ┌───────▼────────┐
    │  EXIT MANAGER   │         │  DAY TRADER    │
    │  (Port 4001)    │◄───────►│  (Port 4001)   │
    │  ClientId: 10   │  DB     │  ClientId: 2   │
    └─────────────────┘         └────────────────┘
             │                           │
             └────────────┬──────────────┘
                          │
                 ┌────────▼────────┐
                 │   DATABASE      │
                 │ (Shared State)  │
                 │ - Active Pos    │
                 │ - Closed Today  │
                 └─────────────────┘
```

### Two Bot Architecture

**Exit Manager** (Persistent):
- Runs continuously during market hours
- Monitors ALL positions for profit targets (+1.8%) and stop losses (-0.9%)
- Uses portfolio data (no subscription required)
- Never restarts unless crashed
- ClientId: 10

**Day Trader** (Restartable):
- Handles entry signals based on VWAP/RSI/ATR
- Can restart if crashes (supervisor auto-recovers)
- Checks database before every entry
- Prevents re-entry of closed positions
- ClientId: 2

**Supervisor** (Orchestrator):
- Monitors both bots' health
- Auto-restarts Day Trader if crashed
- Immediately restarts Exit Manager if crashed (critical!)
- Displays system status every 5 minutes
- Coordinates via database

---

## 📊 Database Coordination

### Shared State Tables

**`active_positions`** - Current open positions:
```sql
CREATE TABLE active_positions (
    symbol TEXT UNIQUE,
    quantity INTEGER,
    entry_price REAL,
    entry_timestamp TEXT,
    agent_name TEXT,
    profit_target_price REAL,
    stop_loss_price REAL,
    status TEXT DEFAULT 'OPEN',
    last_updated TEXT,
    metadata TEXT
)
```

**`closed_positions_today`** - Re-entry prevention:
```sql
CREATE TABLE closed_positions_today (
    symbol TEXT,
    close_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    profit_loss_pct REAL,
    agent_name TEXT,
    timestamp TEXT,
    UNIQUE(symbol, close_date)
)
```

### Coordination Flow

**Day Trader Entry:**
1. Scanner identifies potential entry
2. Check `is_position_active(symbol)` → Skip if true
3. Check `was_closed_today(symbol)` → Skip if true
4. Place entry order
5. Call `add_active_position()` → Register in database
6. Exit Manager automatically sees new position

**Exit Manager Exit:**
1. Monitor portfolio for stop loss or profit target
2. Execute exit order
3. Call `remove_active_position()` → Marks as closed_today
4. Day Trader automatically prevented from re-entry

**Daily Reset:**
- Supervisor calls `clear_closed_today()` at start
- Clears yesterday's closed positions
- Allows fresh entries for new day

---

## 🚀 Quick Start

### Prerequisites

1. **IBKR Gateway or TWS running**
   - Port: 4001
   - API enabled
   - Socket client access allowed

2. **Python environment**
   - Virtual environment: `.venv-daytrader`
   - All dependencies installed

3. **Market data**
   - Free delayed data sufficient
   - No subscription required

### Starting the System

**Option 1: Supervisor (RECOMMENDED)**
```powershell
# Start both bots with coordination
.\start_supervisor.bat
```

**Option 2: Individual Bots**
```powershell
# Terminal 1: Start Exit Manager
.\start_exit_manager.bat

# Terminal 2: Start Day Trader (wait 5 seconds after Exit Manager)
& .\.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25
```

### Stopping the System

**Graceful shutdown:**
- Press `Ctrl+C` in supervisor window
- Both bots stop cleanly
- All positions remain in IBKR (Exit Manager can resume)

**Emergency stop:**
```powershell
# Liquidate all positions immediately
& .\.venv-daytrader\Scripts\python.exe liquidate_all.py
```

---

## 📈 Trading Logic

### Entry Conditions (Day Trader)

**Standard Entry:**
- Price > VWAP
- RSI < 60 (not overbought)
- ATR ≥ 0.3% (30-second bars have lower ATR than daily)
- NOT in `active_positions`
- NOT in `closed_positions_today`

**Gap-and-Go Entry (bypasses VWAP):**
- Pre-market gap ≥ 5%
- RSI < 60
- NOT in database (same checks)

### Exit Conditions (Exit Manager)

**Profit Target:**
- Price ≥ entry_price * 1.018 (+1.8%)
- LimitOrder placed at entry
- Automatic fill when hit

**Stop Loss:**
- Price ≤ entry_price * 0.991 (-0.9%)
- Bot-monitored (no IBKR Stop order)
- MarketOrder placed when triggered
- 10-second timeout with IOC flag

### Re-Entry Protection

**After stop loss:**
- Symbol added to `closed_positions_today`
- Day Trader checks database before every entry
- Re-entry blocked until next day

**After profit target:**
- Same protection applies
- Prevents chasing same stock

---

## 🔧 Configuration

### Capital Allocation

```powershell
# Start with 25% of capital (recommended)
.\start_supervisor.bat  # Default: 25%

# Or manually specify allocation:
python day_trader.py --allocation 0.10  # 10%
python day_trader.py --allocation 0.50  # 50% (aggressive)
```

### Profit/Stop Parameters

Edit `day_trading_agents.py`:
```python
# Line ~1035
def __init__(self, orchestrator, allocation, paper_trade=True, 
             profit_target_pct=0.018,  # +1.8%
             stop_loss_pct=0.009):     # -0.9%
```

### Health Check Interval

Edit `day_trading_agents.py`:
```python
# Line ~1069
self.health_check_interval = 60  # seconds (1 min)
```

### Scanner Refresh

Edit `day_trading_agents.py`:
```python
# Line ~1707 (scanner interval)
if time.time() - last_scanner_refresh > 900:  # 15 minutes
```

---

## 📝 Monitoring & Logs

### Real-Time Status

**Supervisor displays:**
- Bot status (🟢 RUNNING / 🔴 STOPPED)
- Active positions count
- Closed today count
- Total P&L today

**Example output:**
```
================================================================================
📊 Supervisor Status - 14:32:15
================================================================================
Exit Manager: 🟢 RUNNING
Day Trader:   🟢 RUNNING

📈 Active Positions: 3
📉 Closed Today: 12
   Total P&L Today: +2.34%
================================================================================
```

### Log Files

**Day Trader logs:**
```
logs/day_trader_run_YYYYMMDD_HHMMSS.json
```

**View latest:**
```powershell
Get-Content logs\day_trader_run_*.json -Tail 50
```

### Database Queries

**Active positions:**
```python
from observability import get_database
db = get_database()

positions = db.get_active_positions()
for pos in positions:
    print(f"{pos['symbol']}: {pos['quantity']} @ ${pos['entry_price']:.2f}")
```

**Today's closed positions:**
```python
closed = db.get_closed_today()
for pos in closed:
    print(f"{pos['symbol']}: {pos['exit_reason']} - {pos['profit_loss_pct']:+.2f}%")
```

**Query all trades:**
```python
trades = db.get_trades_by_date('2025-10-29')
total_pnl = sum(t.get('profit_loss_pct', 0) for t in trades)
print(f"Total P&L: {total_pnl:+.2f}%")
```

---

## 🛡️ Error Handling

### Automatic Recovery

**Day Trader crashes:**
- Supervisor detects crash (poll returns non-None)
- Automatically restarts Day Trader
- Database state preserved
- Exit Manager continues protecting positions

**Exit Manager crashes:**
- 🚨 CRITICAL: Supervisor immediately restarts
- Positions synced from IBKR on reconnect
- Stop loss monitoring resumes
- No positions left unprotected

**IBKR disconnection:**
- Both bots detect lost connection
- Attempt reconnection every 30 seconds
- Database state preserved during outage
- Logs all reconnection attempts

### Manual Recovery

**If supervisor crashes:**
```powershell
# 1. Check active positions
& .\.venv-daytrader\Scripts\python.exe -c "from observability import get_database; db = get_database(); print(db.get_active_positions())"

# 2. Restart supervisor
.\start_supervisor.bat

# 3. Verify both bots running
# Check supervisor status output
```

**If database corruption:**
```powershell
# Database has WAL mode + backups
# Check integrity:
sqlite3 trading_history.db "PRAGMA integrity_check;"

# If corrupted, restore from backup (daily backups in /archive)
```

---

## 🧪 Testing

### Pre-Production Checklist

**1. Test IBKR connection:**
```powershell
& .\.venv-daytrader\Scripts\python.exe test_connection.py
```

**2. Test database coordination:**
```powershell
# Start Exit Manager
.\start_exit_manager.bat

# In another terminal, check database:
python -c "from observability import get_database; db = get_database(); print('Active:', len(db.get_active_positions()))"
```

**3. Test re-entry protection:**
```powershell
# 1. Enter position manually via IBKR
# 2. Exit Manager will sync it
# 3. Close position via Exit Manager
# 4. Day Trader should skip that symbol
```

**4. Test crash recovery:**
```powershell
# Start supervisor, then manually kill Day Trader process
# Supervisor should auto-restart within 30 seconds
```

### Paper Trading

**ALWAYS test new strategies in paper mode first:**
```python
# day_trader.py line ~34
self.paper_trade = True  # ✅ Safe

# Only change to False after successful paper testing:
self.paper_trade = False  # ⚠️ LIVE MONEY
```

---

## 🔥 Common Issues

### Issue 1: "Position already active" on startup

**Cause:** Database out of sync with IBKR

**Solution:**
```python
# Exit Manager automatically syncs on startup
# Or manually clear:
from observability import get_database
db = get_database()
db.cursor.execute("DELETE FROM active_positions")
db.conn.commit()
```

### Issue 2: Day Trader not entering positions

**Check 1:** Watchlist empty?
```powershell
Get-Content day_trading_watchlist.json
```

**Check 2:** Re-entry protection blocking?
```python
from observability import get_database
db = get_database()
print(db.get_closed_today())  # Should show blocked symbols
```

**Check 3:** Scanner running?
```powershell
# Scanner should refresh every 15 minutes
# Check logs for "Scanner refresh"
```

### Issue 3: Stop losses not triggering

**Check 1:** Exit Manager running?
```powershell
# Should see process in Task Manager
# Or check supervisor status
```

**Check 2:** Portfolio data available?
```python
# Exit Manager uses portfolio data (no subscription)
# Check logs for "Portfolio positions: X"
```

**Check 3:** Price data updating?
```powershell
# Check Exit Manager logs for price updates
# Should see "Current price: $X.XX" every 10 seconds
```

### Issue 4: BYND infinite loop (short sale error)

**Cause:** Duplicate SELL orders (profit target + stop loss)

**Solution:** Already fixed in Exit Manager
- Wait 2 seconds after cancel
- Detect cancel failures
- Track failed sells
- Skip problem symbols

---

## 📚 Advanced Usage

### Running Outside Market Hours

**Pre-market (4:00 AM - 9:30 AM ET):**
- Data aggregation phase runs at 7:00 AM
- Pre-market analysis runs at 7:30 AM
- Ticker validation runs at 8:15 AM
- MOO orders placed 9:00-9:27 AM (future feature)

**After-hours (4:00 PM - 8:00 PM ET):**
- Bots automatically stop trading at 3:45 PM
- End-of-day liquidation runs
- Improvement cycle analyzes performance
- Database remains accessible

### Custom Scanner Logic

Edit `intraday_scanner_polygon.py` to customize:
```python
# Line ~150 - Momentum threshold
if momentum_score >= 0.7:  # 70% confidence
    filtered.append(stock)

# Line ~120 - Volume filter
if volume_ratio > 2.0:  # 2x average volume
    candidates.append(ticker)
```

### LLM Analysis Integration

**Primary:** DeepSeek (faster, cheaper)
```python
llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1)
```

**Fallback:** Gemini 2.0 Flash
```python
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp", temperature=0.1)
```

**Disable LLM** (heuristic-only mode):
```python
# Set API keys to empty in .env:
DEEPSEEK_API_KEY=
GOOGLE_API_KEY=
```

---

## 🎯 Performance Optimization

### Current Settings (Optimized)

- **6 parallel workers** for watchlist analysis
- **Database WAL mode** for concurrent access
- **4 indexes** on trades table
- **Health checks every 60 seconds**
- **Scanner refresh every 15 minutes**
- **Position monitoring every 10 seconds**

### Tuning for Speed

**Faster scanner updates:**
```python
# Line ~1707 in day_trading_agents.py
if time.time() - last_scanner_refresh > 600:  # 10 min instead of 15
```

**More aggressive entries:**
```python
# Lower ATR threshold (more stocks qualify)
if atr_pct >= 0.2:  # Was 0.3%
```

**Tighter stop losses:**
```python
# Reduce loss tolerance
self.stop_loss_pct = 0.005  # -0.5% instead of -0.9%
```

---

## 📞 Support & Troubleshooting

### Debug Mode

**Enable verbose logging:**
```python
# day_trader.py line ~40
logging.basicConfig(level=logging.DEBUG)  # Was INFO
```

**Database query logging:**
```python
# observability.py line ~150
self.conn.set_trace_callback(print)  # Log all SQL
```

### Emergency Procedures

**1. Market crash - liquidate immediately:**
```powershell
python liquidate_all.py
```

**2. IBKR connection lost - restart Gateway:**
```powershell
# Stop supervisor (Ctrl+C)
# Restart IBKR Gateway
# Start supervisor again
```

**3. Database locked:**
```powershell
# Kill all Python processes
taskkill /F /IM python.exe

# Restart supervisor
.\start_supervisor.bat
```

---

## 📖 Additional Resources

**Key Documentation:**
- `AUTONOMOUS_SYSTEM_README.md` - Autonomous capabilities
- `DAY_TRADER_CONFIGURATION.md` - Detailed configuration
- `TASK_SCHEDULER_SETUP.md` - Windows automation
- `.github/copilot-instructions.md` - AI agent instructions

**Important Scripts:**
- `analyze_today.py` - Performance analysis
- `view_logs.py` - Interactive log viewer
- `check_orders.py` - Order status checker
- `monitor_live.py` - Real-time position monitor

**Conversations Archive:**
- `conversations/session_YYYYMMDD.md` - Development history
- `conversations/SESSION_ANALYSIS_YYYYMMDD.md` - Analysis reports

---

## ✅ Production Checklist

Before running with real money:

- [ ] Test IBKR connection (test_connection.py)
- [ ] Verify database integrity
- [ ] Confirm paper trading works (24+ hours)
- [ ] Test stop loss execution (manual trigger)
- [ ] Test profit target execution
- [ ] Test re-entry protection
- [ ] Test crash recovery (kill Day Trader)
- [ ] Test End-of-day liquidation (3:45 PM)
- [ ] Review last 7 days of paper trades
- [ ] Set appropriate capital allocation (start low!)
- [ ] Enable trade notifications (future feature)
- [ ] Verify backup strategy working

**Start conservatively:**
- Day 1-7: 10% allocation
- Day 8-14: 15% allocation
- Day 15+: 25% allocation (if profitable)

---

## 🚨 Risk Warning

**This is an autonomous trading system that can lose money.**

- Start with paper trading
- Use small capital allocation initially
- Monitor closely for first 2 weeks
- Stop losses can fail in fast markets
- IBKR connection can drop
- Database can corrupt
- Code bugs can cause losses

**Always have manual oversight and emergency stop procedures.**

---

*Last Updated: October 29, 2025*
*Version: 2.0 - Production-Ready Coordinated System*
