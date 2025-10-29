# Autonomous Day Trading Bot - AI Agent Instructions

## System Architecture

This is a **4-layer autonomous trading system** that self-monitors, self-evaluates, and self-improves:

```
Layer 4: Continuous Improvement (continuous_improvement.py)
  ↓ Adaptive parameters, market regime detection, A/B testing
Layer 3: Self-Healing (integrated in day_trading_agents.py)
  ↓ Position sync, health monitoring, auto-recovery
Layer 2: Self-Evaluation (self_evaluation.py)
  ↓ Performance analysis, LLM insights, parameter suggestions  
Layer 1: Observability (observability.py)
  ↓ OpenTelemetry tracing + SQLite database (trading_history.db)
```

**Two trading systems run independently:**
- **Weekly Bot** (`main.py`): Multi-agent portfolio rebalancing with LLM analysis
- **Day Trading Bot** (`day_trader.py`): Intraday VWAP momentum trading with autonomous capabilities

## Critical IBKR Connection Patterns

**ALWAYS use these exact connection patterns:**

```python
# Day Trading Bot: Port 4001, ClientId 2
port = 4001  # LIVE trading (Gateway or TWS)
client_id = 2  # Avoid conflicts with validators(2) and momentum(3)

# Use ib_insync.util.run() for Python 3.12+ compatibility
import ib_insync.util as ib_util
ib_util.run(self.ib.connectAsync('127.0.0.1', port, clientId=client_id))

# Weekly Bot: Port 4001, ClientId 1
ib.connect('127.0.0.1', 4001, clientId=1)
```

**Market data types:**
- `ib.reqMarketDataType(3)` = Delayed/frozen (FREE, always use this)
- `ib.reqMarketDataType(1)` = Live streaming (expensive subscription required)

## Day Trading Bot Workflow

**Pre-Market (7:00-9:30 AM ET):**
1. Phase 0 (7:00 AM): Data aggregation from FMP/Polygon APIs → `full_market_data.json`
2. Phase 1 (7:30 AM): LLM analysis (DeepSeek/Gemini) → `ranked_tickers.json` (confidence > 0.7)
3. Phase 1.5 (8:15 AM): IBKR contract validation → `validated_tickers.json`
4. Phase 1.75 (9:00 AM): Pre-market momentum analysis → `ranked_tickers.json` (final)

**Market Hours (9:30 AM - 4:00 PM ET):**
1. **CRITICAL FIRST STEP:** `_sync_positions_from_ibkr()` - Syncs existing positions to prevent "forgotten position" bugs
2. Scanner runs every 15 minutes (`scanner_interval = 900`) to refresh watchlist via `intraday_scanner_polygon.py`
3. Trading loop monitors every 5 seconds for entry/exit signals:
   - Entry: `price > VWAP`, `RSI < 60`, `ATR >= 0.3%` (lowered for 30-second bars)
   - Exit: +1.8% profit target OR -0.9% stop loss (manual monitoring, no IBKR Stop orders)
4. Health checks every 60 seconds for auto-healing

**End of Day (3:45 PM ET):**
1. Liquidate all positions with safety attributes: `order.tif='IOC'`, `order.outsideRth=True`
2. Run autonomous improvement cycle: analyze performance → LLM insights → update parameters
3. Save improvement report to `reports/improvement/improvement_YYYYMMDD_HHMMSS.json`

## Order Execution Patterns

**NEVER use MarketOrder for entries** - they get stuck in "PendingSubmit":
```python
# ✅ CORRECT: LimitOrder with aggressive pricing
entry_order = LimitOrder('BUY', shares, current_price * 1.005)  # +0.5%
```

**Manual stop-loss monitoring** (IBKR Stop orders rejected):
```python
# In position monitoring loop:
if current_price <= stop_loss_price:
    stop_order = MarketOrder('SELL', quantity)
    stop_order.tif = 'IOC'
    stop_order.outsideRth = True
    ib.placeOrder(contract, stop_order)
    # Wait up to 10 seconds for fill
```

**Take profit orders work with LimitOrder:**
```python
tp_order = LimitOrder('SELL', quantity, entry_price * 1.018)  # +1.8%
tp_trade = ib.placeOrder(contract, tp_order)
# Store tp_trade in positions dict for monitoring
```

## Autonomous System Integration

**Every trade MUST be logged to database:**
```python
from observability import get_database, get_tracer

db = get_database()
db.log_trade({
    'symbol': symbol,
    'action': 'BUY',
    'quantity': shares,
    'price': fill_price,
    'reason': 'VWAP momentum',
    'metadata': {'rsi': rsi_value, 'vwap': vwap, 'atr_pct': atr_pct}
})
```

**All major operations traced:**
```python
tracer = get_tracer()
with tracer.start_span('scanner_analysis'):
    # Scanner code here
    tracer.add_event('stocks_filtered', {'count': len(filtered)})
```

**End-of-day improvement cycle** (automatically runs in `IntradayTraderAgent.run()`):
```python
improvement_report = self.improvement_engine.daily_improvement_cycle()
# Automatically saves optimized parameters for tomorrow
```

## Critical State Management

**Position tracking dictionary structure:**
```python
self.positions[symbol] = {
    "quantity": filled_quantity,
    "entry_price": fill_price,
    "contract": contract,
    "atr_pct": atr_pct,  # Can be None for MOO entries
    "take_profit_trade": tp_trade,  # Track to check if filled
    "stop_loss_price": stop_loss_price,  # For manual monitoring
    "entry_type": "MOO" or "SCANNER",  # Tag entry source
    "entry_time": time.time()
}
```

**Capital allocation:**
- Uses `ExcessLiquidity` NOT `SettledCash` (bypasses PDT restrictions)
- Allocation parameter (0.10-0.25) splits capital across max 4-8 positions
- Recalculates per-stock capital: `capital_per_stock = (excess_liquidity * allocation) / len(watchlist)`

## ATR Threshold Reality

**30-second bars vs daily bars have VASTLY different ATR scales:**
- Daily ATR: 1.5-3.0% is normal volatility
- 30-second ATR: 0.13-0.4% is normal (much lower!)
- **Current threshold:** `atr_pct >= 0.3%` (lowered from 1.0%)
- Expect 9,000+ rejections on quiet days - this is NORMAL

## File Organization

**Generated watchlists (order matters):**
1. `us_tickers.json` - Universe of 1600+ stocks (Phase -1)
2. `full_market_data.json` - News + fundamentals (Phase 0)
3. `ranked_tickers.json` - LLM scored (Phase 1)
4. `validated_tickers.json` - IBKR tradable (Phase 1.5)
5. `day_trading_watchlist.json` - Final intraday scanner output (every 15 min)

**Database:**
- `trading_history.db` - SQLite with 5 tables (trades, daily_metrics, agent_health, parameter_changes, evaluations)
- Use WAL mode for concurrent access: `PRAGMA journal_mode=WAL`
- Query trades: `db.get_trades_by_date('2025-10-29')`

**Logs:**
- `logs/day_trader_run_YYYYMMDD_HHMMSS.json` - Structured JSON logs
- View latest: `Get-Content logs\day_trader_run_*.json -Tail 50`

## Common Pitfalls

1. **Event loop crashes:** Use `ib.sleep()` NOT `time.sleep()` inside IBKR loops
2. **Orders stuck in PendingSubmit:** Always add `order.tif='IOC'` and `order.outsideRth=True` for immediate execution
3. **Position sync forgotten:** ALWAYS call `_sync_positions_from_ibkr()` before trading loop starts
4. **DatetimeIndex errors:** pandas_ta requires DatetimeIndex: `df.set_index('date', inplace=True)`
5. **ClientId conflicts:** Day bot=2, validators=2, momentum=3, weekly=1, tests=97
6. **ATR threshold too high:** 0.3% is correct for 30-second bars, not 1.0%
7. **Scanner not refreshing:** Watchlist must reload every 15 minutes via subprocess call to `intraday_scanner_polygon.py`

## Testing Commands

```powershell
# Test IBKR connection
& .\.venv-daytrader\Scripts\python.exe test_connection.py

# Run day trader (25% capital)
& .\.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25

# Analyze today's session
& .\.venv-daytrader\Scripts\python.exe analyze_today.py

# Check logs
Get-Content logs\day_trader_run_*.json -Tail 50 | Select-Object -Last 10

# Test MOO orders (pre-market only)
& .\.venv-daytrader\Scripts\python.exe test_moo_orders.py
```

## LLM Integration Patterns

**DeepSeek for analysis** (primary):
```python
llm = ChatDeepSeek(model="deepseek-chat", temperature=0.1)
```

**Gemini 2.0 Flash for fallback:**
```python
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp", temperature=0.1)
```

**Graceful degradation:** All LLM features are optional - bot works without API keys by using heuristic-based analysis instead.

## Performance Optimization

- **6 parallel workers:** `ThreadPoolExecutor(max_workers=6)` for watchlist analysis
- **Database WAL mode:** 3x faster concurrent writes
- **4 indexes:** Trade lookups <1ms with proper indexing
- **Health checks:** Every 60 seconds (configurable via `health_check_interval`)
- **Scanner interval:** 900 seconds (15 minutes) for intraday watchlist refresh

## Market Hours Logic

```python
from market_hours import is_market_open

# Check before trading
if is_market_open():
    self._run_trading_loop()
```

**Market hours:** 9:30 AM - 4:00 PM ET (Mon-Fri, excluding holidays)
**Pre-market:** 4:00 AM - 9:30 AM ET (data available, no trading)
**After-hours:** 4:00 PM - 8:00 PM ET (no bot activity)

## Data Sources

**Polygon API (Primary):** Used for all historical data and intraday bars
- IBKR historical data has proven unreliable in testing
- Use Polygon for pre-market analysis, scanner updates, and technical indicators
- 30-second and 1-minute aggregates available
- API key required in `.env` file

**IBKR API (Secondary):** Only for order execution and position management
- Connection, account info, placing orders
- Position sync, portfolio queries
- NOT used for historical price data

## Current Development Focus

**Priority:** Day Trading Bot only
- Weekly portfolio bot (`main.py`) is functional but not actively developed
- All new features and improvements go to day trading system
- Focus on autonomous capabilities and profitability optimization

## MOO Strategy Status

**Market-On-Open (MOO) orders** - IN PROGRESS:
- Test script created: `test_moo_orders.py` (validates API behavior)
- Integration planned but not yet complete in `day_trading_agents.py`
- Purpose: Capture opening momentum at 9:30 AM instead of entering late
- Next steps: Complete test validation, then integrate MOO placement phase

**When implementing MOO:**
1. Run `test_moo_orders.py` between 9:00-9:27 AM ET to validate
2. Add `_place_moo_orders()` and `_monitor_moo_fills()` methods
3. Integrate into main loop before existing scanner phase (additive, not replacement)
4. MOO orders only accepted by IBKR during 9:00-9:28 AM ET window
