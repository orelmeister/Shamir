# Weekly Bot - Modular Architecture

## Overview

The weekly bot has been refactored from a monolithic `main.py` (2000+ lines) into **4 standalone phase scripts** that communicate via shared JSON state files.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   weekly_orchestrator.py                     │
│  (Menu-driven workflow with 5 execution modes)               │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ├─► Phase 1: 01_data_aggregator.py
                   │   └─ Fetches market data → full_market_data.json
                   │
                   ├─► Phase 2: 02_analyst.py  
                   │   └─ LLM analysis + Monte Carlo → top_picks
                   │
                   ├─► Phase 3: 03_portfolio_manager.py
                   │   └─ Rebalancing with 5% threshold + stops
                   │
                   └─► Phase 4: 04_monitor_positions.py
                       └─ Continuous monitoring (until market close)

┌─────────────────────────────────────────────────────────────┐
│                      Shared State Files                      │
├─────────────────────────────────────────────────────────────┤
│  shared_state/phase_state.json         - Current phase       │
│  shared_state/positions_state.json     - All positions       │
│  shared_state/orders_state.json        - Pending orders      │
│  shared_state/position_tracking.json   - Stop-loss tracking  │
└─────────────────────────────────────────────────────────────┘
```

## Phase Scripts

### Phase 1: Data Aggregator (`01_data_aggregator.py`)
- Fetches market data from FMP/Polygon APIs
- Filters by market cap, volume, news sentiment
- Outputs: `full_market_data.json`
- Updates: `phase_state.json` → `aggregation_complete`

### Phase 2: Analyst (`02_analyst.py`)
- Parallel LLM analysis (DeepSeek/Gemini/Ollama)
- Monte Carlo simulation for ranking
- IBKR ticker validation
- Outputs: `full_analysis_results.json`
- Updates: `phase_state.json` → `analysis_complete` with `top_picks`

### Phase 3: Portfolio Manager (`03_portfolio_manager.py`)
- **Rebalancing threshold**: Only rebalances if expected return improves >5%
- **Position limits**: Max 5 positions (equal weight)
- **Stop-loss management**: -10% stop, +20% trailing stop trigger
- Outputs: Executed trades
- Updates: `phase_state.json` → `execution_complete`

### Phase 4: Position Monitor (`04_monitor_positions.py`)
- Runs continuously during market hours (5-minute intervals)
- Checks stop losses and trailing stops
- Auto-sells on stop hit
- Updates: `positions_state.json` as positions change

## Orchestrator Modes

Run: `python weekly_orchestrator.py`

**Menu Options:**
1. **Full Cycle** - Aggregation → Analysis → Rebalance → Monitor
2. **Quick Start** - Skip aggregation (uses existing `full_market_data.json`)
3. **Analysis Only** - Re-run analyst with existing data
4. **Rebalance Only** - Execute trades with existing analysis
5. **Monitor Only** - Start position monitoring
6. **Exit**

## Shared State Management

### `state_manager.py`
Thread-safe read/write functions with file locking:
```python
from shared_state.state_manager import read_state, write_state

# Read phase state
phase_data = read_state('phase_state')

# Write updated state
write_state('phase_state', {'current_phase': 'analysis_complete', ...})
```

### State Files

**`phase_state.json`** - Current workflow phase
```json
{
  "current_phase": "analysis_complete",
  "top_picks": [...],
  "timestamp": "2025-11-04T10:30:00"
}
```

**`positions_state.json`** - All open positions
```json
{
  "weekly_positions": ["AAPL", "TSLA"],
  "day_trader_positions": ["NVDA"],
  "last_updated": "2025-11-04T10:30:00"
}
```

**`position_tracking.json`** - Stop-loss tracking
```json
{
  "AAPL": {
    "entry_price": 180.50,
    "stop_loss_price": 162.45,
    "trailing_stop_active": true,
    "highest_price": 195.20
  }
}
```

## Benefits of Modular Design

### ✅ **Easier Debugging**
- Each phase is ~300 lines (vs 2000-line monolith)
- Clear logs per phase: `logs/analyst_20251104_103000.log`
- Can run individual phases in isolation

### ✅ **Selective Restarts**
- Phase 2 failed? Restart only analysis (don't re-aggregate)
- Phase 3 rejected trade? Debug portfolio manager alone
- No need to restart entire workflow

### ✅ **Better Observability**
- Each phase writes structured logs
- Shared state = single source of truth
- Easy to see where failures occur

### ✅ **Testable**
- Each phase script is standalone
- Can mock shared state files for testing
- Unit test individual phases independently

### ✅ **Coordination with Day Trader**
- Both bots read `positions_state.json`
- Day trader knows which positions are weekly holds
- No accidental liquidation of long-term positions

## Migration from Legacy `main.py`

### What Changed
- **Before**: Monolithic orchestrator with 4 agent classes
- **After**: 4 standalone scripts + orchestrator + shared state

### What Stayed the Same
- Same IBKR connection logic
- Same LLM analysis prompts
- Same Monte Carlo simulation
- Same stop-loss rules (-10%, +20% trailing)

### Preserved Legacy System
- Original `main.py` will be renamed to `main_legacy.py`
- Available as fallback if needed
- All logic preserved, just reorganized

## Running the Modular System

### First Time Setup
```powershell
# Ensure shared_state directory exists (auto-created on first run)
python weekly_orchestrator.py
# Select Option 1 (Full Cycle)
```

### Quick Daily Run (Existing Data)
```powershell
python weekly_orchestrator.py
# Select Option 2 (Quick Start)
# Uses yesterday's aggregation, runs fresh analysis
```

### Debug Analysis Only
```powershell
# Manually run analyst phase
cd weekly_bot
python 02_analyst.py
```

### Monitor Positions
```powershell
python weekly_orchestrator.py
# Select Option 5 (Monitor Only)
# Runs until market close
```

## Logs Structure

```
logs/
├── orchestrator_20251104_070000.log  # Main workflow
├── data_aggregator_20251104_070100.log
├── analyst_20251104_073000.log
│   ├── analyst_worker_20251104_073000_0.log  # Parallel workers
│   ├── analyst_worker_20251104_073000_1.log
│   └── ...
├── portfolio_manager_20251104_080000.log
└── monitor_20251104_090000.log
```

## Next Steps

1. **Integrate with Day Trader** - Update `day_trading_agents.py` to read `positions_state.json`
2. **Test in Paper Mode** - Validate orchestrator with IBKR paper account
3. **Add Pre-Market MOO** - Implement MOO order placement in Portfolio Manager (Phase 3)
4. **Create Launcher Script** - Simple `start_weekly_bot.bat` wrapper

## Configuration

All configuration is at the top of each phase script:
- `IB_HOST`, `IB_PORT` - IBKR connection
- `MAX_POSITIONS` - Position limit (default: 5)
- `REBALANCE_THRESHOLD` - Min improvement to rebalance (default: 5%)
- `STOP_LOSS_PCT` - Stop loss percentage (default: 10%)
- `CHECK_INTERVAL` - Monitor check frequency (default: 300s)

## Troubleshooting

**Q: Phase X failed with "phase_state.json not found"**  
A: Run Option 1 (Full Cycle) first to initialize shared state

**Q: "No top picks from analysis"**  
A: LLM found no high-confidence BUY recommendations. Check `full_analysis_results.json`

**Q: Rebalancing skipped ("insufficient improvement")**  
A: Current portfolio expected return is within 5% of optimized. This is intentional to avoid excessive trading.

**Q: Monitor exits immediately**  
A: Market is closed. Monitor only runs during market hours (9:30 AM - 4:00 PM ET).

## Support

- Phase logs: `logs/<phase_name>_<timestamp>.log`
- Shared state: `shared_state/*.json`
- Legacy system: `main_legacy.py` (fallback)
