# Weekly Bot Modular Refactor - Implementation Summary

**Date:** November 3, 2025  
**Status:** IN PROGRESS (Phase 1 complete, Phases 2-4 pending)

## Problem Statement

The weekly bot (`main.py`) has become a monolithic 1,771-line script that:
- Fails frequently and is hard to debug
- Requires re-running all phases when one fails
- Has unreliable database coordination between day trader and weekly bot
- Causes excessive money loss due to difficult troubleshooting

## Solution Architecture

### New Structure
```
weekly_bot/
├── 01_data_aggregator.py      ✅ COMPLETE
├── 02_analyst.py               ⏳ PENDING  
├── 03_portfolio_manager.py     ⏳ PENDING
├── 04_monitor_positions.py     ⏳ PENDING
└── README.md                   📝 TODO

shared_state/
├── __init__.py                 ✅ COMPLETE
├── state_manager.py            ✅ COMPLETE
├── positions_state.json        ✅ COMPLETE
├── orders_state.json           ✅ COMPLETE
├── phase_state.json            ✅ COMPLETE
├── README.md                   ✅ COMPLETE
└── backup/                     (auto-created)

Root files:
├── sync_positions_from_ibkr.py ✅ COMPLETE
├── weekly_orchestrator.py      ⏳ PENDING
├── main.py                     (to be renamed main_legacy.py)
└── requirements.txt            (needs filelock added)
```

## Completed Work

### 1. Shared State Infrastructure ✅
**Files Created:**
- `shared_state/state_manager.py` - Thread-safe JSON state management with file locking
- `shared_state/positions_state.json` - Tracks all open positions (WEEKLY/DAY_TRADER tagged)
- `shared_state/orders_state.json` - Tracks all pending orders
- `shared_state/phase_state.json` - Tracks current phase execution state
- `shared_state/__init__.py` - Package initialization
- `shared_state/README.md` - Complete documentation with usage examples

**Key Features:**
- Thread-safe read/write with `filelock` library
- Automatic backups (keeps last 10)
- Source tagging ("WEEKLY" vs "DAY_TRADER")
- Atomic updates with file locking
- Recovery from corrupted JSON

### 2. IBKR Sync Utility ✅
**File:** `sync_positions_from_ibkr.py`

**Purpose:**
- Fetches current positions from IBKR
- Tags each position as "WEEKLY" or "DAY_TRADER" based on `day_trading_watchlist.json`
- Updates `shared_state/positions_state.json`
- Can be run standalone or called by either bot

**Usage:**
```powershell
python sync_positions_from_ibkr.py
```

### 3. Phase 1: Data Aggregator ✅
**File:** `weekly_bot/01_data_aggregator.py`

**Extracted from:** `main.py` lines 167-460 (DataAggregatorAgent class)

**Inputs:** None (fetches from FMP/Polygon APIs)
**Outputs:** 
- `full_market_data.json` (aggregated stock data)
- Updates `shared_state/phase_state.json`

**Features:**
- Three-tier news fetching (Polygon → FMP → yfinance)
- Pre-LLM revenue growth filter (≥10% CAGR)
- Market cap filtering ($50M-$350M)
- Concurrent API requests (10 workers)
- Standalone execution
- Phase state tracking

**Usage:**
```powershell
python weekly_bot/01_data_aggregator.py
```

### 4. Knowledge Graph Entities ✅
Created 8 entities and 11 relationships in Memory MCP:
- Weekly Bot Refactor (Project)
- Phase 1-4 (TradingPhase entities)
- Shared State JSON Schema (DataStructure)
- IBKR Sync Utility (UtilityScript)
- Weekly Orchestrator (ControlScript)

## Pending Work

### Phase 2: Analyst (IN PROGRESS)
**Extract from:** `main.py` lines 461-784 (AnalystAgent class)

**Key Components:**
- LLM analysis worker (DeepSeek/Gemini/Ollama)
- Monte Carlo simulation integration
- IBKR ticker validation
- Parallel processing with multiprocessing
- Top 5 stock selection

**Inputs:** `full_market_data.json`
**Outputs:** `full_analysis_results.json`, `ranked_tickers.json`

### Phase 3: Portfolio Manager
**Extract from:** `main.py` lines 785-1550 (PortfolioManagerAgent class)

**Key Components:**
- Portfolio evaluation (current positions)
- Rebalancing logic (5% threshold)
- MOO order placement
- Position size calculation
- IBKR trade execution

**Inputs:** `full_analysis_results.json`, `shared_state/positions_state.json`
**Outputs:** Updated positions, executed orders

### Phase 4: Position Monitoring
**Extract from:** `main.py` lines 1551+ (MonitoringAgent class)

**Key Components:**
- Stop loss monitoring (-10%)
- Trailing stop management (+20% trigger, 10% trail)
- RSI checks (oversold threshold: 40)
- Position exit execution
- Continuous monitoring loop

**Inputs:** `shared_state/positions_state.json`
**Outputs:** Exit orders, updated position state

### Weekly Orchestrator
**File:** `weekly_orchestrator.py` (NEW)

**Purpose:**
- Runs phases sequentially: 01 → 02 → 03 → 04
- Validates phase completion before proceeding
- Error handling with selective restart
- Independent phase logging
- Replaces monolithic `main.py` run loop

**Features:**
```python
def run_phase(phase_script):
    """
    Run a phase script and validate completion.
    Returns: success (bool), error_message (str)
    """
    # Execute phase script as subprocess
    # Check phase_state.json for completion
    # Handle errors with retry or skip logic
    # Log independently

def main():
    phases = [
        "weekly_bot/01_data_aggregator.py",
        "weekly_bot/02_analyst.py",
        "weekly_bot/03_portfolio_manager.py",
        "weekly_bot/04_monitor_positions.py"
    ]
    
    for phase in phases:
        success, error = run_phase(phase)
        if not success:
            handle_failure(phase, error)
```

## Day Trader Integration

### Required Changes to `day_trading_agents.py`

**Current:** Uses internal `self.positions` dict
**New:** Read/write `shared_state/positions_state.json`

**Key Modifications:**
1. Replace `_sync_positions_from_ibkr()` to use shared state
2. Tag new positions as source="DAY_TRADER"
3. Read weekly positions to avoid conflicts
4. Use `StateManager` for thread-safe updates

**Example:**
```python
from shared_state import get_positions, add_position, remove_position

# Before entry
weekly_positions = get_positions(source="WEEKLY")
my_positions = get_positions(source="DAY_TRADER")

# After buy
add_position({
    "symbol": symbol,
    "quantity": quantity,
    "entry_price": fill_price,
    "entry_date": datetime.now().isoformat(),
    "stop_loss": stop_loss_price,
    "source": "DAY_TRADER",
    "metadata": {"rsi": rsi, "vwap": vwap}
})

# After sell
remove_position(symbol, source="DAY_TRADER")
```

## Dependencies

### New Dependencies Required
```bash
pip install filelock
```

**Update `requirements.txt`:**
```
filelock>=3.12.0
```

## Testing Plan

### 1. Unit Tests
```powershell
# Test state manager
python -m pytest tests/test_state_manager.py

# Test IBKR sync (requires TWS/Gateway running)
python sync_positions_from_ibkr.py
```

### 2. Phase-by-Phase Testing
```powershell
# Test Phase 1 (data aggregation)
python weekly_bot/01_data_aggregator.py
# Verify: full_market_data.json exists and has valid data

# Test Phase 2 (analysis)
python weekly_bot/02_analyst.py
# Verify: full_analysis_results.json exists with ranked tickers

# Test Phase 3 (portfolio management) - PAPER MODE
python weekly_bot/03_portfolio_manager.py --paper
# Verify: Orders placed in IBKR paper account

# Test Phase 4 (monitoring) - PAPER MODE
python weekly_bot/04_monitor_positions.py --paper
# Verify: Stop losses execute correctly
```

### 3. Integration Testing
```powershell
# Run full orchestrator in paper mode
python weekly_orchestrator.py --paper

# Monitor logs
Get-Content logs/orchestrator_*.log -Tail 50 -Wait
```

### 4. Live Testing (Cautious)
```powershell
# Start with minimal capital allocation
python weekly_orchestrator.py --allocation 0.05  # 5% only

# Monitor closely for first week
python monitor_bot.py
```

## Migration Steps

### Step 1: Backup Current System
```powershell
# Backup main.py
Copy-Item main.py main_legacy.py

# Backup current positions file
Copy-Item weekly_bot_positions.json weekly_bot_positions_legacy.json

# Commit to Git
git add main_legacy.py weekly_bot_positions_legacy.json
git commit -m "Backup legacy weekly bot before modular refactor"
```

### Step 2: Install Dependencies
```powershell
pip install filelock
```

### Step 3: Initialize Shared State
```powershell
# Sync current IBKR positions into new state file
python sync_positions_from_ibkr.py
```

### Step 4: Test Individual Phases
```powershell
# Test Phase 1
python weekly_bot/01_data_aggregator.py

# Test Phase 2
python weekly_bot/02_analyst.py

# (Complete Phases 3 & 4 first)
```

### Step 5: Test Orchestrator
```powershell
# Dry run in paper mode
python weekly_orchestrator.py --paper --dry-run
```

### Step 6: Update Day Trader
```powershell
# Modify day_trading_agents.py to use shared state
# Test day trader separately
python day_trader.py --allocation 0.10 --paper
```

### Step 7: Go Live (Gradually)
```powershell
# Week 1: 5% allocation, monitor closely
python weekly_orchestrator.py --allocation 0.05

# Week 2: Increase if successful
python weekly_orchestrator.py --allocation 0.15

# Week 3+: Full allocation if proven stable
python weekly_orchestrator.py --allocation 0.25
```

## Benefits

### Debugging
**Before:** 1,771-line monolith, unclear which section failed
**After:** 4 independent scripts, clear blame assignment

### Restarts
**Before:** Must re-run entire cycle (aggregation → analysis → trading)
**After:** Restart only the failed phase, reuse cached data

### Monitoring
**Before:** Single log file with mixed concerns
**After:** 4 separate log files, phase-specific errors

### State Management
**Before:** Database coordination issues between bots
**After:** Simple JSON files with file locking, single source of truth

### Development
**Before:** Afraid to touch main.py (might break everything)
**After:** Modify one phase at a time, test independently

## Next Steps

1. **Complete Phase 2-4 Extraction** (AI Agent)
   - Extract AnalystAgent → `02_analyst.py`
   - Extract PortfolioManagerAgent → `03_portfolio_manager.py`
   - Extract MonitoringAgent → `04_monitor_positions.py`

2. **Create Orchestrator** (AI Agent)
   - Build `weekly_orchestrator.py`
   - Implement phase validation
   - Add error handling and retry logic

3. **Update Day Trader** (AI Agent + User Review)
   - Modify `day_trading_agents.py` to use shared state
   - Test position coordination

4. **Testing & Validation** (User + AI Agent)
   - Paper trading for 1 week
   - Monitor for errors
   - Validate state coordination

5. **Production Deployment** (User Decision)
   - Gradual rollout (5% → 15% → 25%)
   - Monitor performance
   - Keep legacy system as backup

## Files Modified/Created

### Created ✅
- `weekly_bot/01_data_aggregator.py` (323 lines)
- `shared_state/state_manager.py` (294 lines)
- `shared_state/__init__.py` (28 lines)
- `shared_state/README.md` (135 lines)
- `shared_state/positions_state.json` (empty template)
- `shared_state/orders_state.json` (empty template)
- `shared_state/phase_state.json` (empty template)
- `sync_positions_from_ibkr.py` (146 lines)

### To Be Created ⏳
- `weekly_bot/02_analyst.py`
- `weekly_bot/03_portfolio_manager.py`
- `weekly_bot/04_monitor_positions.py`
- `weekly_orchestrator.py`

### To Be Modified ⏳
- `day_trading_agents.py` (add shared state integration)
- `requirements.txt` (add filelock)

### To Be Renamed ⏳
- `main.py` → `main_legacy.py`

## Rollback Plan

If the new system fails:
```powershell
# Restore legacy system
Copy-Item main_legacy.py main.py
Copy-Item weekly_bot_positions_legacy.json weekly_bot_positions.json

# Restart weekly bot the old way
.\start_weekly_bot.bat
```

## Success Metrics

- ✅ Each phase can run independently
- ✅ Phase failures don't require full restart
- ✅ Shared state coordination works (no conflicts)
- ✅ Debugging time reduced by 50%+
- ✅ Money loss incidents reduced
- ✅ System uptime improved

## Questions & Decisions

1. **Shared state directory location:** `shared_state/` at root level ✅
2. **Preserve main.py:** Yes, rename to `main_legacy.py` ✅
3. **Use database vs JSON:** JSON files with file locking ✅
4. **Day trader integration:** Use same shared state files ✅
5. **Orchestrator scheduling:** Separate script that calls phase scripts ✅

## Contact & Support

**User:** orelmeister  
**Project:** Autonomous Day Trading Bot  
**Repository:** Shamir (GitHub)  
**Branch:** master (refactor to be done on new branch)

---

**Last Updated:** November 3, 2025  
**Next Review:** After Phase 2-4 extraction complete
