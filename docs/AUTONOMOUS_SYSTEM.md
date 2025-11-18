# Autonomous Day Trading Bot - Complete System Documentation

## 🤖 Overview

This autonomous day trading bot is a self-monitoring, self-evaluating, and self-improving trading system that combines algorithmic trading with AI-powered continuous improvement. It's designed to operate independently, learn from its performance, and optimize itself over time.

## 🏗️ Architecture

### Four-Layer Autonomous System

```
┌─────────────────────────────────────────────────────────┐
│                  Layer 4: Continuous Improvement        │
│  - Adaptive Thresholds                                  │
│  - Market Regime Detection                              │
│  - A/B Testing Framework                                │
│  - Strategy Evolution                                   │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│                  Layer 3: Self-Healing                  │
│  - Position Recovery (from IBKR sync)                   │
│  - Auto-Reconnection                                    │
│  - Health Monitoring                                    │
│  - Anomaly Detection                                    │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│                  Layer 2: Self-Evaluation               │
│  - Performance Analysis                                 │
│  - LLM-Powered Insights (DeepSeek)                      │
│  - Parameter Optimization                               │
│  - Daily Reports                                        │
└─────────────────────────────────────────────────────────┘
                            ↑
┌─────────────────────────────────────────────────────────┐
│                  Layer 1: Observability                 │
│  - OpenTelemetry Tracing                                │
│  - SQLite Trade Database                                │
│  - Performance Metrics                                  │
│  - Health Monitoring                                    │
└─────────────────────────────────────────────────────────┘
```

## 📦 Components

### 1. Observability (`observability.py`)

**Purpose**: Complete visibility into bot operations

**Features**:
- **OpenTelemetry Tracing**: Traces all trade executions and analysis operations
- **SQLite Database**: Stores all trades, daily metrics, health checks, parameter changes, and evaluations
- **Persistent Storage**: All data persists across bot restarts

**Database Schema**:
- `trades`: Every buy/sell with P&L, reason, metadata
- `daily_metrics`: Aggregate daily performance (win rate, total P&L, drawdown, etc.)
- `agent_health`: Health checks (CPU, memory, IBKR connection)
- `parameter_changes`: All parameter adjustments with reasons
- `evaluations`: LLM insights and performance evaluations

**Usage**:
```python
from observability import get_database, get_tracer

db = get_database()
tracer = get_tracer()

# Log a trade
db.log_trade({
    'symbol': 'AAPL',
    'action': 'BUY',
    'quantity': 100,
    'price': 150.25,
    'agent_name': 'IntradayTraderAgent',
    'reason': 'Entry signal: Price>VWAP, RSI<60'
})

# Trace an operation
with tracer.trace_trade_execution('AAPL', 'BUY'):
    # ... trade execution code ...
```

### 2. Self-Evaluation (`self_evaluation.py`)

**Purpose**: Analyze performance and generate improvement insights

**Components**:

#### PerformanceAnalyzer
- Calculates all trading metrics (win rate, P&L, drawdown, risk/reward)
- Generates LLM-powered insights using DeepSeek
- Suggests parameter optimizations
- Analyzes trade patterns

**Key Metrics Calculated**:
- Win rate
- Average win/loss
- Risk/reward ratio
- Max drawdown
- Average trade duration
- Capital efficiency

#### LLM Insights
Uses DeepSeek to analyze:
- Performance patterns
- Risk management effectiveness
- Parameter optimization opportunities
- Market regime adaptation
- Specific actionable recommendations

**Usage**:
```python
from self_evaluation import PerformanceAnalyzer

analyzer = PerformanceAnalyzer('IntradayTraderAgent')

# Analyze today
performance = analyzer.analyze_daily_performance()

# Get LLM insights
insights = analyzer.generate_llm_insights()

# Get parameter suggestions
suggestions = analyzer.get_parameter_suggestions()
```

#### SelfHealingMonitor
- Monitors CPU, memory, IBKR connection
- Detects critical issues
- Attempts auto-recovery
- Logs all health checks

### 3. Continuous Improvement (`continuous_improvement.py`)

**Purpose**: Adapt trading strategy to changing market conditions

**Components**:

#### MarketRegimeDetector
Detects 5 market regimes:
- **Trending Up**: Strong upward momentum
- **Trending Down**: Downward pressure
- **Ranging**: Sideways movement
- **High Volatility**: Elevated VIX, widen stops
- **Low Volatility**: Tighten criteria

Each regime triggers specific parameter adjustments.

#### AdaptiveThresholdManager
Manages dynamic parameters:
- `profit_target_pct` (0.8% - 3.0%)
- `stop_loss_pct` (0.5% - 2.0%)
- `rsi_lower_bound` (30 - 50)
- `rsi_upper_bound` (50 - 70)
- `atr_threshold_pct` (1.0% - 3.0%)
- `max_position_size_pct` (3.0% - 10.0%)

**Safety**: All parameters have bounds to prevent extreme values.

#### ABTestingFramework
- Run A/B tests on strategy variations
- Alternate parameters by day
- Statistical evaluation
- Automatic winner selection

#### ContinuousImprovementEngine
Orchestrates daily improvement cycle:
1. Analyze performance
2. Generate LLM insights
3. Get parameter suggestions
4. Update thresholds (high priority only)
5. Detect market regime
6. Save improvement report

**Usage**:
```python
from continuous_improvement import ContinuousImprovementEngine

engine = ContinuousImprovementEngine('IntradayTraderAgent')

# Run daily cycle
report = engine.daily_improvement_cycle(market_data)

# Get optimized parameters
params = engine.get_trading_parameters(market_data)
```

### 4. Integrated Trading Agent (`day_trading_agents.py`)

**Enhancements to IntradayTraderAgent**:

1. **Initialization**: Creates all autonomous components
2. **Trade Logging**: Every trade logged to database with full metadata
3. **Tracing**: All trade executions wrapped in OpenTelemetry spans
4. **Health Checks**: Periodic health monitoring every 5 minutes
5. **Auto-Recovery**: Attempts reconnection if IBKR disconnects
6. **End-of-Day Cycle**: Runs improvement cycle after market close

**Autonomous Features Active**:
- ✅ Position sync from IBKR on startup (prevents lost positions)
- ✅ Trade logging with P&L calculation
- ✅ OpenTelemetry tracing
- ✅ Periodic health checks
- ✅ Auto-reconnection on IBKR disconnect
- ✅ Daily performance analysis
- ✅ LLM-powered insights generation
- ✅ Parameter optimization
- ✅ Improvement reports

## 🚀 Usage

### Running the Bot

```bash
# Activate virtual environment
.\.venv-daytrader\Scripts\Activate.ps1

# Run the bot
python day_trader.py --allocation 0.25
```

The bot will:
1. Connect to IBKR
2. Load watchlist
3. Sync existing positions from IBKR
4. Trade during market hours with health monitoring
5. Liquidate positions at end of day
6. Run improvement cycle
7. Generate daily report

### Testing the Autonomous System

```bash
python test_autonomous_system.py
```

This comprehensive test suite validates:
- ✅ Observability infrastructure (database, tracing)
- ✅ Self-evaluation (performance analysis, LLM insights)
- ✅ Continuous improvement (regime detection, adaptive thresholds)
- ✅ Self-healing (health monitoring)
- ✅ Full improvement cycle

### Viewing Results

**Trading History Database**:
```python
from observability import get_database

db = get_database()

# Get today's trades
trades = db.get_trades_by_date('2025-10-23', 'IntradayTraderAgent')

# Get daily metrics
metrics = db.get_daily_metrics('2025-10-23', 'IntradayTraderAgent')

# Get recent performance
metrics_range = db.get_metrics_range('2025-10-01', '2025-10-23')
```

**Improvement Reports**:
Located in `reports/improvement/improvement_report_YYYY-MM-DD.json`

Contains:
- Performance metrics
- LLM insights and assessment
- Parameter recommendations
- Parameter changes made
- Market regime detected

## 📊 What Gets Logged

### Every Trade
- Symbol, action (BUY/SELL), quantity, price
- Entry/exit prices, P&L, P&L %
- Reason for trade
- Technical indicators at trade time (VWAP, RSI, ATR)
- Capital at trade time
- Position size percentage

### Daily Metrics
- Total trades, winning/losing trades
- Total P&L, P&L percentage
- Win rate, avg win, avg loss
- Risk/reward ratio
- Max drawdown
- Average trade duration
- Positions held at EOD

### Health Checks
- CPU usage percentage
- Memory usage (MB)
- IBKR connection status
- Timestamp, status (healthy/degraded/critical)

### Parameter Changes
- Parameter name
- Old value → New value
- Reason for change
- Who approved (AUTO for self-adjustments)

### Evaluations
- Date range analyzed
- Evaluation type (daily_llm_analysis, etc.)
- Performance score
- LLM insights
- Recommendations

## 🧠 LLM Integration

The bot uses **DeepSeek** for intelligent analysis:

**What the LLM Analyzes**:
- Today's trading performance
- 7-day performance trends
- Win/loss patterns
- Risk management effectiveness

**What the LLM Provides**:
- Overall performance assessment
- Key insights (3-5 bullet points)
- Risk analysis
- Specific parameter recommendations with values
- Top 3 action items for tomorrow

**LLM Prompt Structure**:
```
System: You are an expert quantitative trading analyst...
User: 
  - Today's performance metrics
  - Recent trades sample
  - 7-day trend
  - Current strategy parameters
  
  Please provide:
  1. Performance assessment
  2. Key insights
  3. Risk analysis
  4. Parameter recommendations
  5. Action items
```

## 🔄 Daily Workflow

### Morning (Pre-Market)
1. Bot starts
2. Connects to IBKR
3. Syncs existing positions (critical!)
4. Loads optimized parameters from yesterday's improvement cycle

### During Market Hours
1. Monitors watchlist stocks every 5 seconds
2. Executes trades based on signals
3. Logs every trade to database
4. Traces all operations
5. Performs health checks every 5 minutes
6. Auto-recovers from connection issues

### End of Day
1. Liquidates all positions (with safety net for forgotten positions)
2. Runs performance analysis
3. Generates LLM insights
4. Gets parameter suggestions
5. Updates parameters (high priority only)
6. Detects market regime
7. Saves improvement report
8. Disconnects from IBKR

### Next Day Impact
- Updated parameters are used automatically
- Market regime adjustments applied
- Pattern recognition from previous trades
- Continuous learning cycle

## ⚙️ Configuration

### Current Strategy Parameters
```python
# Entry Criteria
- Price > VWAP
- 40 < RSI < 60
- ATR > 1.5%

# Exit Criteria
- Profit Target: +1.4%
- Stop Loss: -0.8%
- End-of-Day: Liquidate all positions

# Position Sizing
- Max 5% of capital per position
- Capital allocation: 25% (configurable)
```

### Adaptive Ranges (Auto-Adjusted)
```python
# Profit target can adjust: 0.8% - 3.0%
# Stop loss can adjust: 0.5% - 2.0%
# RSI lower bound: 30 - 50
# RSI upper bound: 50 - 70
# ATR threshold: 1.0% - 3.0%
```

### Market Regime Adjustments
**High Volatility**:
- Profit target: ×1.3
- Stop loss: ×1.3
- Position size: ×0.7
- ATR threshold: ×1.2

**Low Volatility**:
- Profit target: ×0.9
- Stop loss: ×0.9
- ATR threshold: ×0.8

**Trending Up**:
- Profit target: ×1.2
- Stop loss: ×0.9
- Position size: ×1.1
- RSI range: 45-65

**Trending Down**:
- Position size: ×0.6
- ATR threshold: ×1.3
- RSI range: 35-55

## 🔐 Safety Features

### Parameter Bounds
All parameters have min/max limits to prevent extreme values.

### High-Priority Only Auto-Updates
Only high-priority suggestions are applied automatically. Medium/low priority require manual review.

### Position Sync on Startup
Critical fix: Bot syncs with IBKR positions on every start to prevent "forgotten" positions.

### End-of-Day Safety Net
Double liquidation check:
1. Liquidate tracked positions
2. Query IBKR for any untracked positions in watchlist
3. Liquidate those too

### Health Monitoring
- CPU usage alerts
- Memory usage alerts
- IBKR connection monitoring
- Auto-recovery attempts

## 📈 Performance Tracking

### Real-Time
- Every trade logged with full context
- Continuous tracing of all operations
- Health checks every 5 minutes

### Daily
- Comprehensive performance analysis
- LLM-generated insights
- Parameter optimization
- Improvement reports

### Historical
- SQLite database with full trade history
- 30-day rolling analysis for parameter suggestions
- Trend analysis across weeks/months

## 🛠️ Files Created

```
observability.py              # OpenTelemetry + SQLite infrastructure
self_evaluation.py           # Performance analysis + LLM insights
continuous_improvement.py    # Adaptive thresholds + regime detection
test_autonomous_system.py    # Comprehensive test suite
trading_history.db           # SQLite database (auto-created)
reports/improvement/         # Daily improvement reports (auto-created)
```

## 🎯 Next Steps

### Tomorrow's Trading Session
1. **Let it run autonomously** - All systems operational
2. **Monitor the database** - Check trades, metrics, health
3. **Review improvement report** - See what the bot learned
4. **Observe parameter changes** - Track adaptations

### Optional Enhancements
1. **Add email notifications** for daily reports
2. **Create dashboard** to visualize performance
3. **Implement more regime detection indicators**
4. **Add Slack/Discord alerts** for critical events
5. **Create backtesting framework** for A/B tests

## 📝 Notes

- **DeepSeek API Key Required**: For LLM insights, ensure `DEEPSEEK_API_KEY` is in `.env`
- **IBKR Connection**: Must be running TWS/Gateway on port 4001
- **Database Location**: `trading_history.db` in project root
- **Reports Location**: `reports/improvement/` directory

## 🎉 Success Criteria

The autonomous system is working when you see:
1. ✅ Trades logged to database with full metadata
2. ✅ Daily metrics calculated and stored
3. ✅ LLM insights generated at end of day
4. ✅ Parameters adjusted based on performance
5. ✅ Improvement reports saved
6. ✅ Health checks passing
7. ✅ Positions synced correctly on startup

**You now have a fully autonomous, self-improving trading bot!** 🚀
