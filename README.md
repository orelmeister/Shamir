# 🤖 Autonomous Day Trading Bot - Production System

**An intelligent, fault-tolerant trading system with dual-bot coordination.**

A fully autonomous day trading system featuring **coordinated bot architecture** with database-driven state management, automatic crash recovery, and complete re-entry protection.

[![Status](https://img.shields.io/badge/Status-Production_Ready-success)]()
[![Architecture](https://img.shields.io/badge/Architecture-Coordinated_Dual_Bot-blue)]()
[![Platform](https://img.shields.io/badge/Broker-Interactive_Brokers-orange)]()

---

## 🚀 Latest: Production System v2.0 (October 29, 2025)

### ⭐ NEW: Coordinated Dual-Bot Architecture

**Two specialized bots working together via shared database:**

1. **Exit Manager** (Persistent)
   - Monitors ALL positions for profit targets (+1.8%) and stop losses (-0.9%)
   - Runs continuously during market hours
   - Uses portfolio data (no subscription required)
   - Auto-restarts if crashed (critical protection)

2. **Day Trader** (Entry Specialist)
   - Handles entry signals (VWAP/RSI/ATR analysis)
   - Checks database before every entry (no duplicates)
   - Re-entry protection (can't trade closed symbols)
   - Restartable without losing state

3. **Supervisor** (Orchestrator)
   - Manages both bots as subprocesses
   - Health monitoring every 30 seconds
   - Auto-restart on crashes
   - Real-time status display

### 🔄 Database Coordination

**Shared state prevents costly mistakes:**
- **`active_positions`** table - Both bots see current positions
- **`closed_positions_today`** table - Prevents re-entry after exits
- **Real-time sync** - Sub-second coordination
- **Fault tolerance** - Survives bot restarts/crashes

**Example coordination flow:**
```
Day Trader: Check database → Symbol not active → Place BUY → Log to database
Exit Manager: Sync positions → See new position → Monitor for exits → Execute SELL → Log to database
Day Trader: Check database → Symbol closed today → SKIP (re-entry protection)
```

### ✅ Production Features

- ✅ **No duplicate positions** - Database prevents conflicts
- ✅ **Re-entry protection** - Can't chase losing stocks
- ✅ **Automatic crash recovery** - Supervisor restarts failed bots
- ✅ **Complete audit trail** - All actions logged to database
- ✅ **Real-time monitoring** - Status display every 5 minutes
- ✅ **Graceful shutdown** - Ctrl+C stops all bots cleanly

---

## 📋 Quick Start

### Start the Complete System (RECOMMENDED)

```powershell
# Start both bots with supervisor (auto-coordination)
.\start_supervisor.bat
```

### Manual Startup (Advanced)

```powershell
# Terminal 1: Start Exit Manager
.\start_exit_manager.bat

# Terminal 2: Start Day Trader (wait 5 seconds after Exit Manager)
& .\.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25
```

### Check System Status

```powershell
# Quick status check
python check_system_status.py

# Test database coordination
python test_database_coordination.py
```

---

## 📚 Documentation

**NEW Production Guides:**
- **[PRODUCTION_SYSTEM_GUIDE.md](PRODUCTION_SYSTEM_GUIDE.md)** - Complete system documentation (450+ lines)
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Technical implementation details

**Core Documentation:**
- **[AUTONOMOUS_SYSTEM_README.md](AUTONOMOUS_SYSTEM_README.md)** - Autonomous capabilities
- **[DAY_TRADER_CONFIGURATION.md](DAY_TRADER_CONFIGURATION.md)** - Configuration guide

---

## 🎯 Current System Status (October 29, 2025)

### ✅ Recent Major Improvements

**Production System v2.0 (Today):**
- Implemented dual-bot coordination via database
- Added supervisor for fault-tolerant operation
- Database shared state with 11 coordination methods
- Complete re-entry protection
- Automatic crash recovery
- Real-time system status monitoring

**Previous Updates (October 22-28, 2025):**

1. **Pattern Day Trader (PDT) Handling** ✓- Auto-tuning based on system hardware (8 threads, 32GB RAM)

   - Bot now uses `ExcessLiquidity` instead of `SettledCash`

   - Bypasses PDT buying power restrictions**4. Repository Cleanup** 

   - Correctly allocates capital even after multiple day trades- Archived 36 redundant files (12.3 MB)

- Organized into archive/ with subdirectories

2. **Order Execution Fixed** ✓- Retained all core operational files

   - Switched from MarketOrder to LimitOrder- Created comprehensive documentation

   - Uses aggressive pricing (+0.5% buy, -0.5% sell)

   - No longer requires expensive IBKR market data subscriptions---



3. **Daily Profit Target Strategy** ✓##  System Architecture

   - Tracks starting capital on bot startup

   - Monitors cumulative daily P&L### Two-Bot System

   - Auto-liquidates and stops when +1.8% reached

   - Prevents re-entry on stocks sold for profit#### 1. **Weekly Portfolio Bot** (Original)

   - Allows re-entry only after stop losses (with momentum recovery)Multi-agent system for long-term portfolio management:

- **Data Aggregator Agent**: Screens stocks via FMP API

### 🔧 Known Limitations- **Analyst Agent**: LLM analysis with Monte Carlo filtering

- **Market Closed Trading**: Cannot liquidate positions when market is closed (4:00 PM - 9:30 AM ET)- **Portfolio Manager Agent**: Full portfolio rebalancing via IBKR

- **PDT Restrictions**: Paper trading account simulates real PDT rules after 4+ day trades- **Monitoring Agent**: Post-cycle analysis and reporting

- **Overnight Positions**: Old positions from previous sessions may lock buying power

#### 2. **Day Trading Bot** (Enhanced with Autonomous System)

---High-frequency intraday trading with autonomous capabilities:

- **Watchlist Analyst**: Pre-market stock analysis and filtering

## 🏗️ Architecture- **Intraday Trader**: Real-time VWAP momentum trading with RSI/ATR

- **Autonomous Components**:

### Multi-Phase Trading System  - Observability (tracing + database)

  - Self-Evaluation (performance metrics + LLM)

```  - Self-Healing (auto-recovery + health monitoring)

Phase -1: Ticker Universe Refresh (6:55 AM ET)  - Continuous Improvement (adaptive optimization)

   └─> Screens 1600+ tickers via FMP API

   ---

Phase 0: Data Collection (7:00 AM ET)

   └─> Aggregates market data for analysis##  Autonomous System Features

   

Phase 1: LLM Watchlist Analysis (7:30 AM ET)### Layer 1: Observability Infrastructure

   └─> DeepSeek AI analyzes and selects top 8 stocks**Files**: observability.py

   

Phase 1.5: Ticker Validation (8:15 AM ET)**SQLite Database** (trading_history.db):

   └─> Validates tradability via IBKR- trades: Every buy/sell with P&L, metadata (RSI, VWAP, ATR)

   - daily_metrics: Win rate, total P&L, drawdown, Sharpe ratio

Phase 1.75: Pre-Market Momentum (9:00 AM ET)- agent_health: CPU, memory, IBKR connection status

   └─> Calculates gap percentages and momentum scores- parameter_changes: Optimization history with reasons

   - evaluations: LLM insights and recommendations

Phase 2: Intraday Trading (9:30 AM - 4:00 PM ET)

   └─> VWAP + RSI + ATR entry logic**OpenTelemetry Tracing**:

   └─> Monitors profit targets and stop losses- Distributed tracing for all trading operations

   └─> Tracks daily P&L toward 1.8% goal- Trade execution spans with timing

```- Database operations traced

- Full observability stack

### Key Components

**Performance**: WAL mode + 4 indexes for 3-10x faster operations

| File | Purpose |

|------|---------|### Layer 2: Self-Evaluation & Insights

| `day_trader.py` | Main orchestrator - manages all phases |**Files**: self_evaluation.py

| `day_trading_agents.py` | Core trading logic - IntradayTraderAgent |

| `data_aggregator.py` | Market data collection |**Performance Analyzer**:

| `ticker_screener_fmp.py` | Initial universe screening |- 15+ metrics: Win rate, P&L, drawdown, Sharpe ratio, risk/reward

| `observability.py` | OpenTelemetry tracing + SQLite logging |- Average trade duration analysis

| `self_evaluation.py` | Performance analysis |- Position size optimization

| `continuous_improvement.py` | Adaptive parameter tuning |- Capital efficiency tracking

| `market_hours.py` | Market schedule handling |

| `tools.py` | Shared utilities |**AI Insights** (Optional):

- DeepSeek LLM integration for daily analysis

---- Actionable recommendations

- Pattern recognition

## 📊 Trading Strategy- Graceful degradation if API key not set



### Entry Signals**Health Monitor**:

- CPU and memory monitoring

**Gap-and-Go Strategy** (Primary):- IBKR connection checks

- Pre-market gap ≥ 5%- Auto-recovery attempts

- RSI < 60 (not overbought)- Health checks every 60 seconds

- Triggers momentum-based entries

### Layer 3: Self-Healing

**Standard VWAP Strategy** (Secondary):**Files**: day_trading_agents.py (integrated)

- Price > VWAP (uptrend)

- ATR ≥ 1.0% (sufficient volatility)**Position Sync**:

- RSI < 60 (not overbought)- Queries IBKR on startup for all positions

- Syncs positions matching watchlist

### Exit Rules- Prevents " forgotten position\ bugs

- Warns about positions not in watchlist

| Condition | Action | Re-Entry Allowed? |

|-----------|--------|-------------------|**Auto-Recovery**:

| **Profit Target Hit** (1.8% normal, 1.1% recovery) | Sell all shares | ❌ No (done for day) |- Detects IBKR disconnections

| **Stop Loss Hit** (0.9%) | Sell all shares | ✅ Yes (if momentum returns) |- Automatic reconnection attempts

| **Daily Target Reached** (+1.8% cumulative) | Liquidate everything, stop trading | N/A (bot stops) |- Health status: normal, warning, critical

- Healing actions based on status

### Position Management

- **Max 1 position per stock** at any time### Layer 4: Continuous Improvement

- **Capital allocation**: 10% of ExcessLiquidity divided equally across 8 stocks**Files**: continuous_improvement.py

- **Recovery trades**: Lower profit target (1.1%) after stop loss re-entry

**Market Regime Detection**:

---- 5 regimes: trending up/down, high/low volatility, ranging

- Automatic detection from price data

## 🚀 Quick Start- Regime-based parameter adjustments



### Prerequisites**Adaptive Thresholds**:

```bash- Dynamic profit target (0.8-3.0%)

# Required Software- Dynamic stop loss (0.5-2.0%)

- Python 3.12+- Adaptive position sizing (3-10%)

- Interactive Brokers Gateway (port 4001)- Safety bounds prevent extreme values

- TWS Paper Trading Account

**A/B Testing Framework**:

# API Keys (in .env file)- Test strategy variations

- DEEPSEEK_API_KEY=your_key_here- Alternate strategies by day

- GOOGLE_API_KEY=your_key_here (optional)- Track performance by variant

- FMP_API_KEY=your_key_here- Statistical comparison

- POLYGON_API_KEY=your_key_here

```**Daily Improvement Cycle**:

1. Analyze day''s performance

### Installation2. Generate LLM insights (if available)

3. Get parameter suggestions

```bash4. Apply high-priority changes automatically

# 1. Clone repository5. Detect market regime for next day

cd trade6. Generate JSON report



# 2. Create virtual environment---

python -m venv .venv

.venv\Scripts\activate## Performance Optimizations



# 3. Install dependencies### System Requirements

pip install -r requirements.txt- **CPU**: 4+ cores (optimized for 8 threads)

- **RAM**: 16+ GB (tested with 32GB)

# 4. Configure environment- **Disk**: SSD recommended for database performance

# Edit .env with your API keys- **Network**: Stable connection for IBKR API



# 5. Start IBKR Gateway### Optimization Features

# Login to paper trading account, set port to 4001**Parallel Processing**:

- 6 parallel workers (system threads - 2 for OS)

# 6. Run the bot- ThreadPoolExecutor for concurrent operations

python day_trader.py --allocation 0.10- 5x faster watchlist analysis

```

**Database Performance**:

### Scheduled Automation- WAL mode for concurrent reads/writes

- 4 performance indexes on key columns

```batch- 10MB cache (configurable based on RAM)

:: Run start_day_trader.bat via Windows Task Scheduler- Query speed: <1ms with indexes

:: Scheduled for: Daily at 6:55 AM ET

:: Action: Start program**Resource Monitoring**:

:: Program: C:\path\to\start_day_trader.bat- Dynamic configuration based on system specs

```- Auto-tuning for optimal performance

- Health checks every 60 seconds

See `TASK_SCHEDULER_SETUP.md` for detailed scheduling instructions.- Graceful degradation under load



---### Current Performance Metrics

| Operation | Speed | Optimization |

## 📈 Performance Tracking|-----------|-------|--------------|

| Watchlist Analysis (10 stocks) | 2-3s | 6 parallel workers |

### Autonomous Systems| Database Trade Log | 30ms | WAL mode |

| Database Query | <1ms | 4 indexes |

**1. Observability** 📊| Health Check Detection | 60s | Frequent monitoring |

- OpenTelemetry distributed tracing

- SQLite database with 5 tables (trades, spans, metrics, parameters, improvements)---

- Real-time performance monitoring

## Setup and Configuration

**2. Self-Evaluation** 🔍

- Analyzes win rate, profit factor, Sharpe ratio### 1. Environment Variables

- DeepSeek LLM generates improvement insightsCreate a .env file:

- Tracks parameter effectiveness over time`

# API Keys

**3. Continuous Improvement** 🔄FMP_API_KEY=\your_fmp_api_key\

- Adaptive thresholds based on market conditionsPOLYGON_API_KEY=\your_polygon_api_key\

- Market regime detection (trending/choppy)DEEPSEEK_API_KEY=\your_deepseek_api_key\ # Optional for LLM insights

- Auto-suggests parameter adjustmentsGOOGLE_CLOUD_PROJECT=\your_gcp_project\



**4. Self-Healing** 🛡️# IBKR Configuration

- Position sync on startupIB_HOST=\127.0.0.1\

- Health monitoring every 60 secondsIB_PORT=\4001\ # 4001 for Gateway, 7497 for TWS paper

- Auto-recovery from connection issues`



### View Performance### 2. Install Dependencies



```bash**For Weekly Bot**:

# View live trading logs`

python view_logs.py --livepip install -r requirements.txt

`

# Check positions

python liquidate_today.py  # Shows today's positions**For Day Trading Bot**:

`

# Manual liquidationpip install -r day_trader_requirements.txt

python liquidate_all.py    # Liquidates ALL positions`

```

Includes:

---- ib_insync - IBKR API

- pandas, pandas-ta - Data analysis

## 🔑 Configuration Files- langchain-deepseek - LLM integration

- opentelemetry-* - Tracing infrastructure

| File | Purpose | Auto-Generated? |- psutil - System monitoring

|------|---------|-----------------|- aiohttp - Async HTTP requests

| `day_trading_watchlist.json` | Daily stock picks from LLM | ✅ Yes (daily 7:30 AM) |

| `validated_tickers.json` | IBKR-validated symbols | ✅ Yes (daily 8:15 AM) |### 3. IBKR Setup

| `us_tickers.json` | Full ticker universe | ✅ Yes (daily 6:55 AM) |1. Install and run IBKR Gateway or TWS

| `full_market_data.json` | Aggregated market data | ✅ Yes (daily 7:00 AM) |2. Enable API connections in settings

| `trading_performance.db` | Performance database | ✅ Yes (auto-created) |3. Paper trading: Port 4001 (Gateway) or 7497 (TWS)

| `trading_history.db` | Historical trades | ✅ Yes (auto-created) |4. Live trading: Port 4002 (Gateway) or 7496 (TWS)



------



## 🛠️ Maintenance & Troubleshooting## How to Run



### Common Issues### Weekly Portfolio Bot



**Problem**: Orders rejected with "Order rejected - reason: Available settled cash... 2.97 USD"**Standard Run** (local LLM when market closed):

- **Cause**: Pattern Day Trader restriction after 4+ day trades`

- **Solution**: ✅ Fixed! Bot now uses `ExcessLiquidity` which bypasses thispython main.py

`

**Problem**: Orders stuck in "PendingSubmit" status

- **Cause**: Paper trading account doesn't support market orders well**Force Online LLMs**:

- **Solution**: ✅ Fixed! Bot now uses limit orders with aggressive pricing`

python main.py --force-online

**Problem**: Old positions locking up buying power`

- **Solution**: Run `python liquidate_all.py` after market opens (9:30 AM)

- **Alternative**: Reset paper trading account in IBKR Client Portal**Scheduled Mode** (run only on specific days):

`

### Daily Checklistpython main.py --run-days Monday Thursday

python main.py --run-days Wednesday --interval 30

- [ ] IBKR Gateway running and connected (port 4001)`

- [ ] No old positions locking capital (check via `liquidate_today.py`)

- [ ] API keys valid and not rate-limited### Day Trading Bot

- [ ] Sufficient disk space for logs (~100MB/day)

**Standard Run** (25% capital allocation):

---`

python day_trader.py --allocation 0.25

## 📂 Project Structure`



```**Custom Allocation**:

trade/`

├── day_trader.py              # Main orchestratorpython day_trader.py --allocation 0.5 # 50% allocation

├── day_trading_agents.py      # Trading logic`

├── data_aggregator.py         # Data collection

├── ticker_screener_fmp.py     # Universe screening**What Happens**:

├── observability.py           # Tracing system1. Connects to IBKR (port 4001, client ID 2)

├── self_evaluation.py         # Performance analysis2. Syncs existing positions from IBKR

├── continuous_improvement.py  # Adaptive tuning3. Loads watchlist from day_trading_watchlist.json

├── market_hours.py            # Schedule management4. Calculates capital per stock

├── tools.py                   # Utilities5. Monitors every 5 seconds for entry/exit signals

├── liquidate_today.py         # Position liquidator (watchlist only)6. Health checks every 60 seconds

├── liquidate_all.py           # Emergency liquidator (ALL positions)7. At 3:55 PM: Liquidates all positions

├── view_logs.py               # Log viewer8. After close: Runs improvement cycle, generates report

├── start_day_trader.bat       # Windows launcher

├── .env                       # API keys (GITIGNORED)---

├── requirements.txt           # Python dependencies

├── day_trader_requirements.txt # Minimal dependencies## Trading Strategy (Day Trader)

│

├── logs/                      # Trading logs (JSON format)### Entry Criteria

├── reports/                   # Performance reports1. **Price > VWAP** (20-period)

├── archive/                   # Old files (not used in production)2. **RSI < 60** (14-period)

│3. **ATR > 1.5%** (minimum volatility)

├── STRATEGY_CHANGES.md        # Strategy evolution documentation4. **Sufficient capital** available

├── DAY_TRADER_CONFIGURATION.md # Detailed configuration guide

├── AUTONOMOUS_SYSTEM_README.md # Autonomous features documentation### Exit Criteria

├── PROMPT_DAY_TRADER.md       # LLM prompt for analysis1. **Profit Target**: +1.4% from entry

├── PROMPT_WEEKLY_BOT.md       # Weekly bot prompt (legacy)2. **Stop Loss**: -0.8% from entry

├── PRE_TRADING_CHECKLIST.md   # Daily startup checklist3. **EOD**: 3:55 PM automatic liquidation

└── TASK_SCHEDULER_SETUP.md    # Automation setup guide

```### Position Sizing

- Equal allocation across watchlist

---- Example: 25% allocation, 10 stocks = 2.5% per stock

- Calculated from total portfolio value

## 🔐 Security & Best Practices

---

1. **Never commit `.env`** - Contains API keys

2. **Use paper trading first** - Test thoroughly before live trading## Project Structure

3. **Monitor daily** - Check logs at end of each trading day

4. **Backup databases** - `trading_performance.db` and `trading_history.db``

5. **Review performance weekly** - Analyze win rate and profit factortrade/

6. **Update dependencies monthly** - `pip install --upgrade -r requirements.txt` main.py # Weekly bot entry point

 day_trader.py # Day trader entry point

--- agents.py # Weekly bot agents

 day_trading_agents.py # Day trader agents (enhanced)

## 📝 Recent Strategy Changes tools.py # Shared trading tools

 utils.py # Utility functions

### October 27, 2025 market_hours.py # Market hours checker

- **Fixed PDT restrictions**: Now uses `ExcessLiquidity` for capital allocation

- **Fixed order execution**: Switched to limit orders (+0.5%/-0.5% aggressive) observability.py # NEW: Tracing + Database

- **Implemented daily profit target**: Bot stops after +1.8% cumulative gain self_evaluation.py # NEW: Performance analysis + LLM

- **Added recovery trade logic**: Lower 1.1% target for re-entries after stop loss continuous_improvement.py # NEW: Adaptive optimization

- **Prevents overtrading**: No re-entry on stocks sold for profit performance_config.py # NEW: Auto-tuning config



See `STRATEGY_CHANGES.md` for complete evolution history. trading_history.db # SQLite database (auto-created)

 day_trading_watchlist.json # Current watchlist

--- .env # Environment variables



## 📞 Support & Documentation logs/ # Daily run logs

 day_trader_run_*.json

- **Configuration Details**: `DAY_TRADER_CONFIGURATION.md` reports/ # Performance reports

- **Strategy Documentation**: `STRATEGY_CHANGES.md` improvement/

- **Autonomous Features**: `AUTONOMOUS_SYSTEM_README.md` improvement_report_*.json

- **Pre-Trading Checklist**: `PRE_TRADING_CHECKLIST.md`

- **Task Scheduling**: `TASK_SCHEDULER_SETUP.md` archive/ # Archived old files

 old_tests/

--- old_logs/

 old_documentation/

## ⚖️ Legal Disclaimer old_data_files/



**This software is for educational purposes only.**  Documentation/

 AUTONOMOUS_SYSTEM_README.md # Autonomous system guide

- Not financial advice AUTONOMOUS_BOT_PLAN.md # Original implementation plan

- No guarantee of profits PERFORMANCE_OPTIMIZATION.md # Performance guide

- Trading involves risk of loss OPTIMIZATION_SUMMARY.md # Optimization results

- Test thoroughly in paper trading before using real money TESTING_VERIFICATION_REPORT.md # Test results

- Author assumes no liability for trading losses PRE_TRADING_CHECKLIST.md # Daily checklist

 CLEANUP_SUMMARY.md # Cleanup documentation

--- DAY_TRADER_CONFIGURATION.md # Day trader config

 PROMPT_*.md # Agent prompts

## 📊 Statistics (as of October 27, 2025)`



| Metric | Value |---

|--------|-------|

| **Daily Target** | +1.8% |## Testing & Validation

| **Stop Loss** | -0.9% |

| **Recovery Target** | +1.1% |### Run System Tests

| **Max Positions** | 8 (one per stock) |`

| **Capital Allocation** | 10% of ExcessLiquidity |# Test autonomous system components

| **Trading Hours** | 9:30 AM - 4:00 PM ET |python test_autonomous_system.py

| **Automated Phases** | 6 (from 6:55 AM) |

# Test position sync

---python test_position_sync.py



**Built with ❤️ for consistent, disciplined day trading.**# Test performance optimizations

python test_optimizations.py

*Last Updated: October 27, 2025*

# Verify all optimizations active
python verify_optimizations.py

# Analyze system hardware
python system_analysis.py

# Check performance config
python performance_config.py
`

### Test Results (October 22, 2025)
- All 7 test suites passed (100%)
- Database WAL mode verified
- 4 performance indexes created
- All autonomous components initialized
- 6 parallel workers configured
- Query speed: <1ms
- 11.77 GB RAM available (optimal)

---

## Disclaimer

This software is for educational purposes only. Trading stocks involves risk, and you can lose money. Past performance does not guarantee future results. Always do your own research and consult with a financial advisor before making investment decisions.

The autonomous features (self-healing, self-evaluation, continuous improvement) are experimental and should be monitored closely. While designed to improve performance, they can also make changes that may not always be optimal.

**Use at your own risk.** The authors are not responsible for any financial losses incurred from using this software.

---

**Built with for algorithmic trading**

**Status**: Production Ready 
**Last Updated**: October 22, 2025 
**Version**: 2.0.0 (Autonomous System)
