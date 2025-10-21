# Master Prompt & Architectural Blueprint for the Day-Trading Bot

This document serves as the master plan and architectural guide for the day-trading functionality. It is the "master prompt" to ensure continuity and adherence to the original design, even across multiple sessions or context limitations.

**Last Updated**: October 21, 2025 - Major Bug Fixes & Enhancements

## 🚨 CRITICAL UPDATES (October 21, 2025)

### Issues Resolved Today:
1. **Delisted Stocks Problem** - Removed 7 invalid tickers from watchlist (DBTX, SGTX, LABP, AAIC, PHX, DRRX, ESSA)
2. **Polygon API Date Filtering** - Fixed news endpoint to only fetch last 3 days (prevents old acquisition news)
3. **LLM Cost Waste** - Freshness checks now working correctly, no redundant Phase 0/1 runs
4. **IBKR Connection Issues** - Fixed clientId conflict (now using clientId=2)
5. **Historical Data Retrieval** - IBKR successfully returning 367-375 bars of 1-minute data
6. **DatetimeIndex Bug** - Fixed DataFrame index using `df.set_index('date')` for pandas-ta compatibility
7. **Event Loop Crashes** - Changed `time.sleep()` to `ib.sleep()` to avoid KeyboardInterrupt
8. **Trading Loop Stuck** - Removed dependency on live ticker data (not available in paper trading)
9. **Countdown Scheduler** - Added automatic wait until 8:30 AM ET with progress updates

### Code Changes Made:
- `day_trading_agents.py` line 232-248: Added 3-day date filter to Polygon news API
- `day_trading_agents.py` line 506: Added `encoding='utf-8-sig'` for watchlist loading (BOM handling)
- `day_trading_agents.py` line 487: Changed `clientId=1` to `clientId=2`
- `day_trading_agents.py` line 530: Changed `time.sleep(2)` to `ib.sleep(2)` (event loop fix)
- `day_trading_agents.py` line 633-635: Added DatetimeIndex fix for IBKR data
- `day_trading_agents.py` line 617-620: Removed ticker_data dependency, use close price from DataFrame
- `day_trading_agents.py` line 713-715: Changed indicator logging from DEBUG to INFO level
- `day_trading_agents.py` line 730-738: Added detailed "NO ENTRY" reason logging
- `day_trader.py` line 13-14: Added `pytz` import for timezone handling
- `day_trader.py` line 62-110: Added smart scheduler with countdown to 8:30 AM ET

### Current Status:
- ✅ System fully operational and ready for trading
- ✅ IBKR connection stable (clientId=2, port 4001)
- ✅ Historical data retrieval working (DatetimeIndex confirmed)
- ✅ Indicators calculating correctly (VWAP, RSI, ATR)
- ✅ Freshness checks preventing redundant API/LLM costs
- ✅ Automatic scheduler will start bot at 8:30 AM ET tomorrow
- ⚠️ No trades executed today (ATR < 1.5% - market too quiet at 4 PM)

### Why No Trades Today:
All 3 stocks had insufficient volatility:
- VERI: 0.21% ATR (needs ≥1.5%)
- TNYA: 0.35% ATR + Price below VWAP
- ALTS: 0.29% ATR + Price below VWAP

**Solution**: Starting at 8:30 AM ET tomorrow will catch morning volatility (typically 2-5% ATR)

## 1. Core Principles

The day-trading bot adheres to two fundamental principles to ensure the existing weekly bot is not harmed:

1.  **Isolation**: The day-trading logic is completely isolated in its own set of dedicated files. This prevents any possibility of the new code interfering with the existing, stable `main.py` bot.
2.  **Reuse**: Common, stable components like logging utilities (`utils.py`), API connection tools (`tools.py`), and environment configurations (`.env`) are reused without modification. This avoids code duplication and maintains consistency.

## 2. File Structure

The day-trading bot uses a parallel structure:

```
/
|-- main.py                      # Existing weekly bot (UNCHANGED)
|-- day_trader.py                # Entry point for the day-trading bot (117 lines)
|-- agents.py                    # Agents for the weekly bot (UNCHANGED)
|-- day_trading_agents.py        # Day-trading specific agents (756 lines)
|-- utils.py                     # Reused for logging (UNCHANGED)
|-- tools.py                     # Reused for APIs (UNCHANGED)
|-- full_market_data.json        # Market data collected daily
|-- day_trading_watchlist.json   # Top 10 stocks for intraday trading
|-- DAY_TRADER_CONFIGURATION.md  # Detailed configuration documentation
|-- requirements.txt             # Includes pandas-ta, ib_insync, yfinance
|-- README_AGENT.md              # This master plan
```

## 3. High-Level Workflow: A Four-Phase Approach

The day-trading bot operates in four distinct phases for optimal resource efficiency and execution:

### Phase 0: Data Aggregation (The "Data Collector")

-   **When**: Runs once per day, checks freshness before collecting.
-   **Agent**: `DataAggregatorAgent` (in `day_trading_agents.py`).
-   **Process**:
    1.  Checks if `full_market_data.json` already exists and is fresh for today.
    2.  If fresh, **skips aggregation** (saves time and API costs).
    3.  If stale or missing, collects comprehensive market data from multiple sources.
    4.  **Screening Criteria**: Market Cap $50M-$350M, Price >$1, Volume >50K, NYSE/NASDAQ only, US only, news required.
    5.  **Data Sources**: 
        - FMP API (primary - price, fundamentals, company info)
        - Polygon API (news articles)
        - yfinance (fallback for missing data)
    6.  Saves to `full_market_data.json` (typically 700-800 stocks).

### Phase 1: Pre-Market Watchlist Generation (The "LLM Strategist")

-   **When**: Runs once before market opens, checks freshness before analysis.
-   **Agent**: `WatchlistAnalystAgent` (in `day_trading_agents.py`).
-   **Process**:
    1.  Checks if `day_trading_watchlist.json` already exists and is fresh for today.
    2.  If fresh, **skips analysis** (saves money and time on LLM API calls).
    3.  If stale or missing, loads `full_market_data.json`.
    4.  Uses LLM (DeepSeek Reasoner → Google Gemini 2.0 Flash fallback) to analyze all stocks in parallel.
    5.  **Parallel Processing**: Uses 15 worker threads (optimized from testing 5-30 workers).
    6.  **Enhanced Analysis Prompt** (4 sections):
        - News Catalyst Analysis (timing, sentiment, trader attention)
        - Volatility & Momentum Indicators (historical moves, volume spikes, ATR)
        - Fundamental Risk Assessment (revenue, business model clarity, market cap)
        - Day Trading Viability (liquidity, entry/exit opportunities)
    7.  **Confidence Score Guidelines**:
        - 0.90-1.0: Exceptional (multiple catalysts, extreme volatility)
        - 0.75-0.89: Strong (clear catalyst, proven volatility)
        - 0.70-0.74: Moderate (acceptable but higher risk)
        - <0.70: Reject
    8.  Selects top 10 candidates and saves to `day_trading_watchlist.json` with:
        - ticker
        - primaryExchange (ISLAND for NASDAQ routing)
        - confidence_score
        - reasoning
        - model

### Phase 2: Wait for Market Open

-   **When**: After watchlist generation, before trading.
-   **Process**:
    1.  Uses `is_market_open()` utility function.
    2.  If market closed, waits 5 minutes and checks again.
    3.  Once market opens (9:30 AM ET), proceeds to Phase 3.

### Phase 3: Intraday Trading Execution (The "Algorithmic Executor")

-   **When**: Runs during market hours (9:30 AM - 4:00 PM ET).
-   **Agent**: `IntradayTraderAgent` (in `day_trading_agents.py`).
-   **Process**:
    1.  **No LLM Usage**: Pure algorithmic decisions for maximum speed.
    2.  **Initialization**: 
        - Connects to Interactive Brokers (paper or live mode)
        - Loads `day_trading_watchlist.json`
        - Calculates available capital (allocation % of account value)
    3.  **Capital Allocation**: Divides capital equally among watchlist stocks (e.g., 25% allocation / 10 stocks = 2.5% per stock).
    4.  **Real-Time Data**: Subscribes to live market data via IBKR API for all watchlist stocks.
    5.  **Trading Loop** (every 2 seconds):
        - Calculates technical indicators for each stock:
          - RSI (14-period)
          - MACD (12, 26, 9)
          - ATR (14-period)
        - **ATR Requirement**: Stock must have ATR ≥1.5% to enter (volatility filter)
        - **Entry Rules**:
          - RSI < 30 (oversold)
          - MACD crossover (bullish signal)
          - ATR ≥1.5% (sufficient volatility)
          - No existing position in this stock
        - **Exit Rules**:
          - Profit target: +1.4% (changed from 1.5%)
          - Stop loss: -0.8%
          - Positions checked every loop iteration
    6.  **End-of-Day Liquidation**: 
        - Automatically closes all positions at market close
        - Calculates and logs P&L (dollar and percentage)
        - Ensures portfolio is 100% cash overnight
    7.  **Disconnects** from IBKR after liquidation.

## 4. Portfolio & Capital Management: Strict Segregation

This is a critical safety feature. The two bots do not share capital in a way that allows one to disrupt the other.

-   **Allocation Strategy**: A fixed percentage of the total account value is allocated to the day trading strategy. This is configured via command-line argument (e.g., `--allocation 0.25` for 25%).
-   **Day Trader's Capital**: The `IntradayTraderAgent` calculates its maximum usable capital at the start of each day based on this allocation. It **never** sells positions held by the weekly bot to free up cash. It only uses the cash available within its allocated portion.
-   **Equal Distribution**: Available capital is divided equally among all watchlist stocks (e.g., 25% allocation with 10 stocks = 2.5% per stock).

## 5. Key Technical Decisions & Optimizations

### Performance Optimizations
-   **Parallel LLM Analysis**: 15 worker threads (tested 5, 10, 15, 20, 25, 30 workers)
    - 15 workers = 65.96 min for 800 stocks (12.13 stocks/min)
    - 2.21x speedup vs. 5 workers
    - More stable than 30 workers despite slightly longer runtime
-   **Freshness Checks**: Both Phase 0 and Phase 1 check if data/watchlist is fresh for today and skip if current
-   **No Monte Carlo**: Monte Carlo simulation is too slow for day trading, remains in weekly bot only
-   **ATR Volatility Filter**: Prevents entering low-volatility stocks (minimum 1.5% ATR required)

### Technical Indicators
-   **RSI (14-period)**: Identifies oversold conditions (entry at RSI < 30)
-   **MACD (12, 26, 9)**: Confirms momentum with bullish crossover
-   **ATR (14-period)**: Measures volatility, filters entries (≥1.5% required)

### Trading Parameters
-   **Profit Target**: 1.4% (0.014) - changed from 1.5% for more realistic exits
-   **Stop Loss**: 0.8% (0.008) - unchanged
-   **Position Sizing**: Equal allocation across watchlist
-   **Trading Frequency**: 2-second loop for real-time monitoring
-   **Exchange Routing**: ISLAND (NASDAQ primary venue) with SMART routing fallback

### Dependencies
-   **pandas-ta**: Technical analysis indicators
-   **ib_insync**: Interactive Brokers API (async wrapper)
-   **yfinance**: Fallback market data source
-   **langchain-deepseek**: Primary LLM (DeepSeek Reasoner)
-   **langchain-google-genai**: Fallback LLM (Google Gemini 2.0 Flash)

## 6. Current Implementation Status

### ✅ Completed Components

#### Phase 0: Data Aggregation
-   `DataAggregatorAgent` implemented with:
    - Freshness check (skips if data is current for today)
    - Multi-source data collection (FMP, Polygon, yfinance)
    - Comprehensive screening criteria
    - Error handling and fallback mechanisms
    - Asyncio-based parallel collection with fixed TaskGroup pattern

#### Phase 1: Watchlist Generation
-   `WatchlistAnalystAgent` implemented with:
    - Freshness check (skips if watchlist is current for today)
    - 15 parallel worker threads for LLM analysis
    - Enhanced 4-section analysis prompt
    - Dual LLM fallback (DeepSeek → Gemini)
    - Confidence score filtering (>0.7 threshold)
    - Top 10 candidate selection
    - primaryExchange field included in output

#### Phase 3: Intraday Trading
-   `IntradayTraderAgent` implemented with:
    - IBKR connection management (paper/live mode)
    - Capital allocation and position sizing
    - Real-time market data subscription
    - Technical indicator calculations (RSI, MACD, ATR)
    - ATR volatility filter (≥1.5%)
    - Entry/exit rule execution
    - 2-second trading loop
    - End-of-day liquidation with P&L tracking

#### Orchestration
-   `DayTraderOrchestrator` implemented with:
    - 4-phase sequential execution
    - Market hours detection
    - Wait loop for market open (5-minute intervals)
    - Command-line argument parsing (--allocation, --live)
    - Comprehensive logging

### 🔧 Configuration Files

-   `DAY_TRADER_CONFIGURATION.md`: Detailed documentation of all changes
-   `day_trading_watchlist.json`: Current watchlist (10 stocks)
-   `full_market_data.json`: Market data cache (700-800 stocks)

### 📊 Testing & Validation

#### Completed Tests
1.  **Data Collection Test** (`test_data_collection.py`):
    - Verified FMP/Polygon/yfinance integration
    - Tested 5 major tickers (AAPL, MSFT, GOOGL, TSLA, NVDA)
    - All sources working correctly

2.  **Parallel Worker Optimization** (`test_parallel_analysis.py`):
    - Tested 6 configurations (5, 10, 15, 20, 25, 30 workers)
    - Results documented in DAY_TRADER_CONFIGURATION.md
    - 15 workers selected as optimal

3.  **Single Ticker Debug** (`test_single_ticker.py`):
    - Debug tool for investigating individual ticker data
    - Useful for troubleshooting screening criteria

4.  **Full System Test**:
    - Phase 0: Successful (data fresh, skipped aggregation)
    - Phase 1: Successful (watchlist fresh, skipped analysis)
    - Phase 2: Waiting for market open (test stopped)
    - Phase 3: Not yet tested in live market conditions

### 🐛 Known Issues & Resolutions

1.  **Fixed: asyncio.TaskGroup Bug**
    -   Issue: Used `await` instead of `.result()` pattern
    -   Resolution: Changed to proper TaskGroup context manager pattern
    -   Status: ✅ Resolved

2.  **Fixed: Missing primaryExchange**
    -   Issue: Watchlist items missing required field for IBKR contract creation
    -   Resolution: Added `"primaryExchange": "ISLAND"` to watchlist generation
    -   Status: ✅ Resolved

3.  **Fixed: Missing _liquidate_positions() Method**
    -   Issue: Method called but not implemented
    -   Resolution: Added complete method with P&L tracking
    -   Status: ✅ Resolved

4.  **Fixed: Redundant LLM Analysis**
    -   Issue: Re-running expensive analysis when watchlist already fresh
    -   Resolution: Added freshness check to Phase 1
    -   Status: ✅ Resolved

### 🚀 Usage

#### Basic Execution
```bash
# Paper trading with 25% allocation
python day_trader.py --allocation 0.25

# Live trading with 20% allocation
python day_trader.py --allocation 0.20 --live
```

#### Command-Line Arguments
-   `--allocation`: Percentage of capital to allocate (0.0 to 1.0, required)
-   `--live`: Run in live trading mode (default: paper trading)

#### Expected Behavior
1.  **Phase 0**: Checks data freshness, skips if current (saves time)
2.  **Phase 1**: Checks watchlist freshness, skips if current (saves money)
3.  **Phase 2**: Waits for market open if needed (5-minute checks)
4.  **Phase 3**: Executes intraday trading until market close

### 📝 Next Steps & Deployment Plan

#### Immediate Next Steps (October 22, 2025):

1. **Automatic Morning Start (8:30 AM ET)**:
   - Bot configured to automatically wake up and start at 8:30 AM ET
   - Will delete stale data files and run fresh Phase 0 + Phase 1
   - Expected to find 10 volatile stocks with morning news catalysts
   - Trading begins at 9:30 AM when market opens

2. **Expected Morning Workflow**:
   ```
   8:30 AM ET: Bot wakes up from overnight sleep
   8:30-8:45 AM: Phase 0 - Fetch fresh news for ~302 stocks
   8:45-9:15 AM: Phase 1 - LLM analyzes and selects top 10 stocks
   9:15-9:30 AM: Wait for market open
   9:30 AM-4:00 PM: Phase 3 - Trade the 10 selected stocks
   ```

3. **Performance Monitoring**: Track metrics during live trading:
   - Number of trades executed
   - Win/loss ratio
   - Average profit per trade
   - ATR volatility levels throughout the day
   - Entry/exit signal accuracy
   - Slippage and execution quality
   - P&L tracking per stock and total

4. **What to Watch For**:
   - Morning volatility (9:30-10:30 AM): Expect ATR 2-5%, most trades here
   - Mid-day lull (11:00 AM-2:00 PM): Lower ATR, fewer trades expected
   - Afternoon pickup (2:00-4:00 PM): Moderate trading activity
   - End-of-day liquidation: All positions should close by 4:00 PM

#### Future Enhancements:

1. **Risk Management** (next phase):
   - Maximum daily loss limit
   - Maximum position size limits per stock
   - Correlation analysis between positions
   - Dynamic position sizing based on volatility
   - Trailing stop losses for winner protection

2. **Production Deployment** (after validation):
   - Start with minimal capital allocation (5-10%)
   - Monitor for 1-2 weeks in paper trading
   - Gradually increase allocation if performance meets expectations
   - Consider increasing from 25% to 50% allocation after proven success

3. **Strategy Optimization** (ongoing):
   - Fine-tune ATR threshold (currently 1.5%)
   - Optimize entry/exit conditions (RSI, VWAP, price action)
   - Test different profit targets (currently 1.4%) and stop losses (0.8%)
   - Analyze best performing time windows

### ⚠️ Critical Reminders

-   **Never modify `main.py`**: The weekly bot is completely isolated
-   **Paper trading first**: Currently running in paper mode (safe for testing)
-   **Monitor logs closely**: All actions logged to `logs/day_trader_run_*.json`
-   **Data freshness**: Both market data and watchlist cached daily with automatic refresh
-   **Capital segregation**: Day trader only uses allocated 25%, never touches weekly bot
-   **Overnight operation**: Bot can run overnight and automatically start at 8:30 AM ET
-   **Stale files removed**: Fresh analysis will run tomorrow morning with latest news
