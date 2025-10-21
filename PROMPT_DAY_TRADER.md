# Day Trading Bot - Master Prompt & Development Guide

This is the comprehensive prompt file for the **Day Trading Bot** system. Use this document when working on, debugging, or extending the day trading functionality.

---

## 🎯 SYSTEM OVERVIEW

**Purpose**: Fully autonomous day trading bot that:
- Analyzes 302+ small-cap stocks daily
- Uses LLM analysis to find 10 best intraday opportunities
- Executes algorithmic trades during market hours (9:30 AM - 4:00 PM ET)
- Paper trading mode (safety first, can switch to live)

**Current Status**: ✅ Fully operational as of October 21, 2025

---

## 📁 FILE STRUCTURE

### Core Files
- `day_trader.py` (182 lines) - Main orchestrator with scheduler
- `day_trading_agents.py` (840 lines) - All three agent classes
- `day_trader_requirements.txt` - Python dependencies
- `README_AGENT.md` - Architecture blueprint
- `DAY_TRADER_CONFIGURATION.md` - Detailed configuration

### Supporting Files (Shared)
- `utils.py` - Logging, timezone utilities
- `market_hours.py` - Market open/close checker
- `tools.py` - API connections (FMP, Polygon, DeepSeek, Gemini)
- `.env` - API keys (NEVER commit this file)

### Data Files (Regenerated Daily)
- `full_market_data.json` - 302+ stocks with news (Phase 0)
- `day_trading_watchlist.json` - Top 10 stocks (Phase 1)
- `logs/day_trader_run_*.json` - Execution logs

---

## 🚀 HOW TO RUN

### Standard Run (Auto-scheduler)
```powershell
.\.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25
```

**What happens:**
- If run after 4 PM: Waits until 8:30 AM next day (shows live countdown)
- If run before 8:30 AM: Waits until 8:30 AM today
- If run 8:30 AM - 4 PM: Starts immediately

### Manual Phase Control
```python
# Skip to Phase 2 (trading only, use existing watchlist)
orchestrator.run_intraday_trading()

# Force fresh data collection
import os
os.remove('full_market_data.json')
os.remove('day_trading_watchlist.json')
```

---

## 🏗️ ARCHITECTURE - THREE PHASES

### Phase 0: Data Aggregation (8:30-8:45 AM)
**Agent**: `DataAggregatorAgent`
**Purpose**: Collect fresh market data

**Screening Criteria:**
- Market Cap: $50M - $350M (small-cap sweet spot)
- Price: > $1 (avoid penny stocks)
- Volume: > 50K daily average
- Exchanges: NYSE, NASDAQ only
- Country: USA only
- **Must have news in last 3 days**

**Data Sources:**
1. **FMP API** (primary):
   - Stock screener for candidates
   - Company profiles (sector, industry, description)
   - Real-time quotes (price, volume, market cap)
   - Key metrics (PE ratio, EPS, revenue)

2. **Polygon API** (news):
   - `/v2/reference/news` endpoint
   - Filters: Last 3 days only, 50 articles limit
   - Includes: title, description, author, published_utc, article_url

3. **yfinance** (fallback):
   - Used when FMP data incomplete
   - Gets: longName, sector, industry, market cap

**Output**: `full_market_data.json` (~302 stocks with comprehensive data)

**Freshness Check**: Skips if file exists with today's date

---

### Phase 1: Pre-Market Analysis (8:45-9:15 AM)
**Agent**: `WatchlistAnalystAgent`
**Purpose**: LLM analyzes all stocks, selects top 10

**LLM Strategy:**
- **Primary**: DeepSeek Reasoner (cheap, fast, good reasoning)
- **Fallback**: Google Gemini 2.0 Flash
- **Parallel Processing**: 15 worker threads (optimal from testing)

**Analysis Prompt (4 Sections):**

1. **News Catalyst Analysis**
   - Timing: Is news fresh? (today/yesterday ideal)
   - Sentiment: Positive surprise? Acquisition? FDA approval?
   - Trader Attention: Will this get noticed?

2. **Volatility & Momentum Indicators**
   - Historical moves: Does this stock move big?
   - Volume spikes: Is volume 2-3x normal?
   - ATR: Historical volatility percentage

3. **Fundamental Risk Assessment**
   - Revenue: Does company have real business?
   - Market Cap: Is it tradeable? ($50M-$350M)
   - Business Clarity: Biotech? Tech? Clear model?

4. **Day Trading Viability**
   - Liquidity: Can we enter/exit easily?
   - Entry/Exit: Clear price levels?
   - Risk/Reward: Worth the risk?

**Confidence Score Scale:**
- 0.90-1.0: Exceptional (multiple catalysts, proven volatility)
- 0.75-0.89: Strong (clear catalyst, good volume)
- 0.70-0.74: Moderate (acceptable but monitor closely)
- < 0.70: Reject (too risky or unclear)

**Output**: `day_trading_watchlist.json` - Top 10 stocks with:
- ticker
- primaryExchange
- confidence_score
- reasoning
- model (which LLM analyzed it)

**Freshness Check**: Skips if file exists with today's date

---

### Phase 2: Intraday Trading (9:30 AM - 4:00 PM)
**Agent**: `IntradayTraderAgent`
**Purpose**: Execute algorithmic trades (NO LLM - pure speed)

**Connection:**
- Interactive Brokers TWS/Gateway (port 4001)
- clientId=2 (to avoid conflicts)
- Paper trading: Account U21952129

**Capital Allocation:**
- User specifies: `--allocation 0.25` (25% of account)
- Example: $2,000 account × 25% = $500 for day trading
- Divided equally: $500 ÷ 10 stocks = $50 per stock
- **Safety**: Never exceeds available cash

**Technical Indicators (pandas-ta):**
- **VWAP**: Volume-weighted average price (trend indicator)
- **RSI(14)**: Relative strength (0-100, overbought/oversold)
- **ATR(14)**: Average True Range (volatility %)

**Entry Rules (ALL must be true):**
1. No existing position in this stock
2. **Price > VWAP** (upward momentum)
3. **RSI < 60** (not overbought)
4. **ATR ≥ 1.5%** (sufficient volatility)

**Exit Rules (Whichever hits first):**
1. **Profit Target**: +1.4% gain
2. **Stop Loss**: -0.8% loss
3. **Market Close**: 4:00 PM ET (liquidate all positions)

**Trade Execution:**
- Order Type: Market orders (immediate execution)
- Routing: SMART (IBKR finds best price)
- Position Tracking: In-memory dictionary
- Logging: Every trade logged with price, quantity, P&L

**Data Loop:**
- Check every 5 seconds: `ib.sleep(5)`
- Fetch 1-minute bars from IBKR: `reqHistoricalData()`
- 367-375 bars typical (full trading day)
- DatetimeIndex required for pandas-ta

---

## 🐛 COMMON ISSUES & FIXES

### Issue 1: DatetimeIndex Error
**Symptom**: `WARNING: Historical data has invalid index type: RangeIndex`

**Cause**: IBKR `util.df()` sometimes doesn't set DatetimeIndex properly

**Fix**: Force DatetimeIndex after creating DataFrame:
```python
df = util.df(bars)
if 'date' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
    df.set_index('date', inplace=True)
```
**Location**: `day_trading_agents.py` line 633-635

---

### Issue 2: KeyboardInterrupt During Sleep
**Symptom**: Bot crashes with `KeyboardInterrupt` during countdown

**Cause**: Using `time.sleep()` instead of `ib.sleep()` in event loop

**Fix**: Always use `ib.sleep()` when IBKR connection is active:
```python
# WRONG:
time.sleep(2)

# CORRECT:
self.ib.sleep(2)
```
**Location**: `day_trading_agents.py` line 530

---

### Issue 3: No Trades Executed
**Symptom**: Bot runs but never buys anything

**Possible Causes:**
1. **ATR too low** (< 1.5%):
   - Check logs: `ATR 0.21% < 1.5% (low volatility)`
   - Solution: Run during morning hours (9:30-10:30 AM) for higher volatility
   - Or lower threshold: Change `1.5` to `0.5` in line 726

2. **Price below VWAP**:
   - Check logs: `Price $1.82 <= VWAP $1.86`
   - Solution: Wait for bullish momentum

3. **RSI too high**:
   - Check logs: `RSI 62.50 >= 60 (overbought)`
   - Solution: Stock already ran up, wait for pullback

**Debug Logging**: All reasons logged at INFO level (line 730-738)

---

### Issue 4: IBKR Connection Failed
**Symptom**: `Error connecting to IBKR: Connection refused`

**Checklist:**
1. ✅ TWS/Gateway running?
2. ✅ Port 4001 configured? (File → Global Configuration → API → Settings)
3. ✅ "Enable ActiveX and Socket Clients" checked?
4. ✅ clientId=2 not already in use?
5. ✅ Paper Trading account selected?

**Test Connection:**
```python
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=2)
print(ib.accountSummary())  # Should show account details
```

---

### Issue 5: Stale Data Not Refreshing
**Symptom**: Using yesterday's news/watchlist

**Cause**: Freshness check comparing wrong dates

**Fix**: Delete stale files manually:
```powershell
Remove-Item -Path "full_market_data.json" -Force
Remove-Item -Path "day_trading_watchlist.json" -Force
```

**Prevention**: Automated in scheduler (runs at 8:30 AM before Phase 0)

---

### Issue 6: Polygon API Old News
**Symptom**: News from weeks/months ago being analyzed

**Cause**: Missing date filter in API call

**Fix**: Add 3-day filter (line 232-248):
```python
from datetime import datetime, timedelta
cutoff_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
polygon_url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&published_utc.gte={cutoff_date}&limit=50&apiKey={api_key}"
```

---

## 🔧 CONFIGURATION

### Environment Variables (.env)
```bash
# Required
FMP_API_KEY=your_fmp_key
POLYGON_API_KEY=your_polygon_key
DEEPSEEK_API_KEY=your_deepseek_key
GEMINI_API_KEY=your_gemini_key

# IBKR Connection
IBKR_HOST=127.0.0.1
IBKR_PORT=4001
IBKR_CLIENT_ID=2
```

### Trading Parameters
Located in `IntradayTraderAgent.__init__()`:
```python
self.profit_target_pct = 0.014  # 1.4% profit target
self.stop_loss_pct = 0.008      # 0.8% stop loss
self.atr_threshold = 1.5        # Minimum ATR % for entry
```

### Parallel Processing
Located in `WatchlistAnalystAgent`:
```python
max_workers = 15  # Optimal from testing (5-30 range)
```

---

## 📊 MONITORING & LOGS

### Log Files
- Location: `logs/day_trader_run_YYYYMMDD_HHMMSS.json`
- Format: JSON-structured logging
- Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Key Log Messages
```
[COUNTDOWN] 15h 47m 32s remaining...  # Scheduler countdown
[MORNING] Good morning! It's 8:30 AM ET  # Bot starting
Phase 0: Checking market data freshness  # Data collection
Phase 1: Checking watchlist freshness  # LLM analysis
IBKR data for VERI: 367 bars, index=DatetimeIndex  # Data OK
VERI - Price: $6.01, VWAP: $6.01, RSI: 40.50, ATR: 0.21%  # Indicators
NO ENTRY for VERI: ATR 0.21% < 1.5%  # Why no trade
ENTRY SIGNAL for TNYA: Buying 10 shares  # Trade executed
BOUGHT 10 shares of TNYA at $1.85  # Trade confirmed
```

### Performance Metrics (to track)
- Total trades executed
- Win rate (% profitable trades)
- Average profit per trade
- Average holding time
- ATR at entry (volatility correlation)
- Best performing hours (9:30-10:30 AM typically)

---

## 🚨 CRITICAL RULES

### DO NOT:
1. ❌ Modify `main.py` (weekly bot is isolated)
2. ❌ Commit `.env` file (contains API keys)
3. ❌ Commit data files (`*.json` except requirements)
4. ❌ Run live trading without extensive paper testing
5. ❌ Use `time.sleep()` when IBKR connection active
6. ❌ Ignore ATR warnings (prevents bad trades)
7. ❌ Trade without stop losses
8. ❌ Exceed available cash allocation

### ALWAYS:
1. ✅ Test in paper trading first
2. ✅ Check logs after runs
3. ✅ Verify IBKR connection before market open
4. ✅ Monitor during first hour (9:30-10:30 AM)
5. ✅ Use `ib.sleep()` for event loop compatibility
6. ✅ Let bot liquidate at 4 PM (don't manually intervene)
7. ✅ Keep this prompt file updated with changes
8. ✅ Document bugs and fixes in README_AGENT.md

---

## 🔄 DAILY WORKFLOW

### Pre-Market (8:30 AM ET)
1. Bot wakes from overnight sleep
2. Deletes stale data files
3. Phase 0: Fetches news for 302+ stocks (15 min)
4. Phase 1: LLM selects top 10 (20 min)
5. Waits for 9:30 AM market open

### Market Hours (9:30 AM - 4:00 PM)
1. Phase 2: Connects to IBKR
2. Subscribes to 10 stock data feeds
3. Checks indicators every 5 seconds
4. Enters trades when conditions met
5. Exits at profit/loss targets or 4 PM

### After Hours (4:00 PM+)
1. All positions liquidated
2. Logs final P&L
3. Disconnects from IBKR
4. Enters countdown mode for tomorrow

---

## 🎓 LEARNING RESOURCES

### Key Concepts
- **VWAP**: Price weighted by volume (trend indicator)
- **RSI**: Momentum oscillator (overbought/oversold)
- **ATR**: Volatility measure (% price range)
- **Market Orders**: Execute immediately at best price
- **SMART Routing**: IBKR finds best exchange

### Useful Libraries
- `ib_insync`: Python wrapper for IBKR API
- `pandas-ta`: Technical analysis indicators
- `pytz`: Timezone handling (ET conversions)
- `yfinance`: Fallback market data

### Documentation Links
- IBKR API: https://interactivebrokers.github.io/tws-api/
- pandas-ta: https://github.com/twopirllc/pandas-ta
- FMP API: https://site.financialmodelingprep.com/developer/docs
- Polygon: https://polygon.io/docs/stocks/getting-started

---

## 📝 VERSION HISTORY

**October 21, 2025** - Major Release
- ✅ Fixed all critical bugs (9 total)
- ✅ Added auto-scheduler with live countdown
- ✅ Stable IBKR connection (clientId=2)
- ✅ DatetimeIndex fix for pandas-ta
- ✅ 3-day news filter for Polygon
- ✅ Enhanced logging and debugging
- ✅ System fully operational and tested

**Next Planned Features:**
- Dynamic position sizing based on volatility
- Trailing stop losses for winners
- Multi-timeframe analysis (5-min + 15-min bars)
- Correlation analysis (avoid similar positions)
- Performance analytics dashboard

---

## 🆘 GETTING HELP

### Debugging Checklist
1. Check logs: `logs/day_trader_run_*.json`
2. Verify IBKR connection: `ib.isConnected()`
3. Test indicators: Print df.tail() with VWAP/RSI/ATR
4. Check ATR values: Should be > 1.5% for entry
5. Verify market hours: `is_market_open()`

### Common Error Messages
| Error | Meaning | Fix |
|-------|---------|-----|
| `Connection refused` | IBKR not running | Start TWS/Gateway |
| `Invalid index type: RangeIndex` | DatetimeIndex missing | Add df.set_index('date') |
| `KeyboardInterrupt` | Wrong sleep function | Use ib.sleep() not time.sleep() |
| `No historical data` | Symbol delisted | Remove from watchlist |
| `ATR < 1.5%` | Too quiet to trade | Wait or lower threshold |

---

**Last Updated**: October 21, 2025
**Status**: Production Ready (Paper Trading)
**Maintainer**: Check README_AGENT.md for latest changes
