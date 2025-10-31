# Monday November 4, 2025 - Bot Monitoring Checklist

## What Was Fixed on October 31, 2025

### Problem 1: MOO Orders Timing Issue
**Issue:** Bot attempted to place MOO orders at 9:28:39 AM ET (10 seconds past 9:28 AM cutoff)
- IBKR rejected with Error 321: "Invalid order type was entered"
- MOO orders must be submitted between 9:00-9:28:00 AM ET

**Solution Implemented:**
- Added smart time window checking with pytz timezone handling
- If between 9:28-9:30 AM: Wait for market open, then place LIMIT orders
- Automatic fallback detection: If MOO rejected by IBKR, retry with LIMIT orders
- Code location: `main.py` lines 733-769

### Problem 2: Invalid Ticker Selection (CPTN)
**Issue:** Monte Carlo selected CPTN as top pick (yearly Sharpe 1.32)
- IBKR Error 200: "No security definition has been found"
- Bot skipped trade, marked execution as SUCCESS but placed NO orders

**Solution Implemented:**
- Added `_validate_ticker_in_ibkr()` method to check ticker exists before trading
- Modified Monte Carlo selection to iterate through ranked list: [CPTN, ACRS, CVRX, EB, TYGO...]
- Bot now automatically skips invalid tickers and selects next valid one
- Code location: `main.py` lines 485-509 (selection logic) and 517-540 (validation method)

**Expected Result:** Bot will skip CPTN and trade ACRS (Monte Carlo weekly winner, Sharpe 10.00)

## Monday Morning Monitoring Tasks

### 1. Pre-Market (Before 9:00 AM ET)
- [ ] Check if bot is scheduled to start (Task Scheduler or manual)
- [ ] Verify IBKR Gateway/TWS is running and connected
- [ ] If using `--rerun-analysis` flag, ensure `full_market_data.json` and `full_analysis_results.json` exist from previous run

### 2. During Bot Startup (First 15 minutes)
Watch `bot_console.log` for these key events:

**Expected Log Sequence:**
```
[Analyst] - Running Monte Carlo simulation to find the top pick...
[Analyst] - ⚠️ Ticker CPTN not found in IBKR. Trying next...
[Analyst] - ✅ Selected valid ticker: ACRS
[Analyst] - Top pick from Monte Carlo is: ACRS
```

**Commands to Monitor:**
```powershell
# Watch real-time logs
Get-Content bot_console.log -Wait -Tail 20

# Check for validation messages
Get-Content bot_console.log | Select-String "Selected valid ticker|not found in IBKR|Top pick from Monte Carlo"

# Verify ticker validation ran
Get-Content bot_console.log | Select-String "Validated|contract details"
```

### 3. MOO Window (9:00-9:28 AM ET)
- [ ] Check if bot attempts MOO orders (should be between 9:00-9:28 AM)
- [ ] Verify no Error 321 rejections
- [ ] If rejected, confirm fallback logic triggers: "Waiting for market open to place LIMIT orders"

**Commands:**
```powershell
# Check MOO status
Get-Content bot_console.log | Select-String "MOO|Market-On-Open|9:28 AM|fallback|LIMIT orders"

# Check for order rejections
Get-Content bot_console.log | Select-String "Error 321|Invalid order type|rejected|Cancelled"
```

### 4. Market Open (9:30-9:35 AM ET)
- [ ] Verify ACRS order placed successfully
- [ ] Check order status in IBKR TWS/Gateway
- [ ] Confirm fill price logged
- [ ] Verify position appears in `weekly_bot_positions.json`

**Commands:**
```powershell
# Check trade execution
Get-Content bot_console.log | Select-String "BUY.*shares|Trade executed|filled|SUCCESS_REBALANCE"

# Check for execution errors
Get-Content bot_console.log | Select-String "Could not get valid market price|Skipping trade|FAILURE"

# Verify position tracking
Get-Content weekly_bot_positions.json | ConvertFrom-Json | Select-Object ticker, quantity, entry_price
```

### 5. Post-Execution Validation
- [ ] Check `trading_queue.json` shows `execution_complete` phase
- [ ] Verify `executed_trades` array is NOT empty
- [ ] Check IBKR account for actual position (not just log entry)
- [ ] Confirm stop loss and take profit levels set

**Commands:**
```powershell
# Check queue status
Get-Content trading_queue.json | ConvertFrom-Json | Select-Object phase, executed_trades

# Verify IBKR position
& .\.venv-weeklybot\Scripts\python.exe -c "from ib_insync import *; ib=IB(); ib.connect('127.0.0.1',4001,clientId=99); print([p.contract.symbol for p in ib.portfolio()]); ib.disconnect()"
```

## Success Criteria

✅ **Complete Success:**
- CPTN skipped with warning log
- ACRS validated and selected
- MOO or LIMIT order placed (depending on timing)
- Order filled successfully
- Position tracking updated
- No "Could not get valid market price" errors

⚠️ **Partial Success:**
- Ticker validation works but order fails for other reason
- Need to investigate order placement logic

❌ **Failure:**
- Bot still tries to trade CPTN (validation not working)
- All tickers in Monte Carlo list rejected as invalid
- Bot crashes during validation

## Fallback Actions

**If ACRS also invalid:**
- Check next pick in Monte Carlo rankings: CVRX (monthly winner, Sharpe 6.82)
- Manually override by modifying `trading_queue.json` before execution phase

**If MOO timing still fails:**
- Start bot earlier (before 8:00 AM) to ensure completion by 9:00 AM
- Use `--rerun-analysis` to skip expensive LLM calls and speed up

**If all Monte Carlo picks invalid:**
- Use highest LLM confidence pick instead: NXXT (0.92) or ACTG (0.90)
- Add ticker validation to data aggregation phase to filter out invalid tickers earlier

## Code Changes Summary

### File: `main.py`

**Change 1: Ticker Validation Loop (Lines ~485-509)**
```python
# OLD: Selected first ticker without validation
top_pick = next((rec for rec in buy_recommendations if rec['ticker'] == top_pick_ticker[0]), None)

# NEW: Iterate through ranked list and validate each
for ticker in top_pick_ticker_list:
    candidate = next((rec for rec in buy_recommendations if rec['ticker'] == ticker), None)
    if candidate:
        if self._validate_ticker_in_ibkr(ticker):
            top_pick = candidate
            self.log(logging.INFO, f"✅ Selected valid ticker: {ticker}")
            break
        else:
            self.log(logging.WARNING, f"⚠️ Ticker {ticker} not found in IBKR. Trying next...")
```

**Change 2: New Validation Method (Lines ~517-540)**
```python
def _validate_ticker_in_ibkr(self, ticker):
    """Quick validation to check if ticker exists in IBKR before trading."""
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=1)
        contract = Stock(ticker, 'SMART', 'USD')
        details = ib.reqContractDetails(contract)
        ib.disconnect()
        
        if not details:
            self.log(logging.WARNING, f"No contract details found for {ticker}")
            return False
        
        self.log(logging.DEBUG, f"Validated {ticker}: {details[0].contract.symbol}")
        return True
        
    except Exception as e:
        self.log(logging.ERROR, f"Ticker validation failed for {ticker}: {e}")
        if ib.isConnected():
            ib.disconnect()
        return False
```

**Change 3: MOO Fallback Logic (Already implemented, Lines 733-769)**
- Time window checking with pytz
- Automatic wait if between 9:28-9:30 AM
- Fallback to LIMIT orders after market open

## Post-Monday Actions

### If Successful:
- [ ] Document actual trade details (entry price, quantity, fill time)
- [ ] Update this checklist with any unexpected behavior
- [ ] Consider adding ticker validation to earlier phases (data aggregation)
- [ ] Monitor ACRS performance throughout the week

### If Issues Found:
- [ ] Save error logs to dedicated file
- [ ] Test ticker validation in isolation
- [ ] Consider adding more robust error handling
- [ ] May need to pre-validate entire universe of tickers

## GitHub Commit Message Template

```
Fix ticker validation and MOO timing for weekly bot

- Add automatic ticker validation before trade execution
- Skip invalid tickers (CPTN) and select next from Monte Carlo rankings
- Implement MOO fallback to LIMIT orders when past 9:28 AM cutoff
- Add pytz timezone handling for accurate NY market hours
- Expected to trade ACRS (Sharpe 10.00) instead of invalid CPTN

Fixes:
- Issue #1: MOO orders rejected at 9:28:39 AM (10 sec too late)
- Issue #2: CPTN ticker not found in IBKR (Error 200)

Tested: Validation logic added, ready for Monday morning execution
```

---

## Quick Reference Commands

```powershell
# Start bot with cached analysis
& .\.venv-weeklybot\Scripts\python.exe main.py --rerun-analysis --force-online

# Monitor logs live
Get-Content bot_console.log -Wait -Tail 30

# Check current positions
& .\.venv-weeklybot\Scripts\python.exe -c "from ib_insync import *; ib=IB(); ib.connect('127.0.0.1',4001,clientId=99); [print(f'{p.contract.symbol}: {p.position} @ ${p.averageCost:.2f}') for p in ib.portfolio()]; ib.disconnect()"

# View Monte Carlo rankings
$results = Get-Content full_analysis_results.json | ConvertFrom-Json; $results | Where-Object { $_.decision -eq 'BUY' -and $_.confidence -ge 0.80 } | Select-Object ticker, confidence | Sort-Object -Property confidence -Descending | Format-Table

# Check queue status
Get-Content trading_queue.json | ConvertFrom-Json | ConvertTo-Json -Depth 10
```
