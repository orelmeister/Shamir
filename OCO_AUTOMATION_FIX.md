# OCO Bracket Automation - Implementation Complete

**Date:** October 30, 2025  
**Status:** ✅ IMPLEMENTED

## Problem Statement

The day trading bot had OCO bracket logic implemented but it failed at market open due to connection timeout. Manual script `place_all_oco.py` was used to place brackets on 13 positions. Need to integrate automatic OCO placement into main bot workflow.

## Root Cause Analysis

1. **Connection Timeout at Market Open** (6:32 AM PT / 9:30 AM ET)
   - Bot crashed with `TimeoutError` on clientId=2
   - Default 4-second timeout too short
   - No retry logic
   - Prevented OCO bracket placement code from executing

2. **Position Sync Missing OCO Brackets**
   - `_sync_positions_from_ibkr()` only placed profit targets (LimitOrder)
   - No stop-loss orders
   - No OCA group linking

3. **MOO Fill Monitoring Missing OCO Brackets**
   - `_monitor_moo_fills()` only placed profit targets
   - No stop-loss orders
   - No OCA group linking

## Solutions Implemented

### 1. Connection Robustness (Lines 1075-1130)

**Changes to `_connect_to_brokerage()`:**

✅ **Connection Reuse**
- Check if already connected from pre-market phase
- Skip reconnection if `self.ib.isConnected() == True`
- Prevents duplicate connection attempts

✅ **Retry Logic**
- 3 attempts with 5-second delays
- Increased timeout from 4→10 seconds
- Detailed logging for each attempt
- Graceful failure with clear error messages

```python
# Before: Single attempt with 4-second timeout
ib_util.run(self.ib.connectAsync('127.0.0.1', port, clientId=client_id))

# After: 3 attempts with 10-second timeout
for attempt in range(1, max_retries + 1):
    ib_util.run(self.ib.connectAsync('127.0.0.1', port, clientId=client_id, timeout=10))
    if connected: return
    time.sleep(retry_delay)
```

### 2. Position Sync with OCO Brackets (Lines 1236-1275)

**Changes to `_sync_positions_from_ibkr()`:**

✅ **OCO Bracket Creation**
- Creates OCA (One-Cancels-All) group: `OCA_{symbol}_{timestamp}`
- Places both Take Profit (LimitOrder) AND Stop Loss (StopOrder)
- Links orders via `ocaGroup` and `ocaType=1`

✅ **Position Tracking Enhanced**
- Stores `stop_loss_trade` reference
- Stores `take_profit_price` and `stop_loss_price`
- Stores `oca_group` for monitoring

```python
# Before: Only profit target
tp_order = LimitOrder('SELL', quantity, take_profit)
tp_trade = self.ib.placeOrder(contract, tp_order)

# After: OCO bracket
oca_group = f"OCA_{symbol}_{int(time.time())}"

tp_order = LimitOrder('SELL', quantity, take_profit)
tp_order.ocaGroup = oca_group
tp_order.ocaType = 1

sl_order = StopOrder('SELL', quantity, stop_loss)
sl_order.ocaGroup = oca_group
sl_order.ocaType = 1

tp_trade = self.ib.placeOrder(contract, tp_order)
sl_trade = self.ib.placeOrder(contract, sl_order)
```

### 3. MOO Fill Monitoring with OCO Brackets (Lines 1551-1585)

**Changes to `_monitor_moo_fills()`:**

✅ **OCO Bracket After Fill**
- Same OCA group creation pattern
- Places Take Profit + Stop Loss immediately after MOO fill
- Enhanced logging with OCA group info

✅ **Position Entry Updated**
- Adds `stop_loss_trade`, `take_profit_price`, `oca_group` fields
- Consistent with scanner entry format

### 4. Scanner Entry Already Has OCO Brackets ✅

**No changes needed to scanner entry logic** (Lines 1938-2000):
- Already implements complete OCO bracket placement
- Waits for BUY fill, then places TP + SL with OCA group
- Code was correct, just never executed due to connection crash

## Testing Checklist

Before tomorrow's session (Oct 31, 5:00 AM PT):

- [ ] Clear cache: `ranked_tickers.json`, `day_trading_watchlist.json`
- [ ] Start supervisor fresh
- [ ] Monitor connection logs at market open (6:30 AM PT)
  - Should see "✅ Already connected" or "Connection attempt 1/3"
  - Should NOT see "TimeoutError"
- [ ] Verify OCO brackets placed after MOO fills (6:30:30 AM PT)
  - Log should show "OCO Bracket: TP @ $X.XX, SL @ $Y.YY"
  - Log should show "OCA Group: OCA_SYMBOL_TIMESTAMP"
- [ ] Check IBKR orders portal
  - Each position should have 2 orders (LimitOrder + StopOrder)
  - Both orders should show same OCA group
- [ ] Test restart scenario
  - If bot restarts mid-session, `_sync_positions_from_ibkr()` should place OCO brackets on existing positions

## Expected Behavior

### Pre-Market Phase (5:00-6:30 AM PT)
1. Bot connects clientId=2 during Phase 1.75
2. Connection remains open through pre-market

### Market Open (6:30 AM PT)
1. `_connect_to_brokerage()` detects existing connection
2. Logs: "✅ Already connected to IBKR from pre-market phase"
3. Skips reconnection attempt
4. `_sync_positions_from_ibkr()` called
5. If positions exist from previous runs, places OCO brackets

### MOO Fill Monitoring (6:30:00-6:30:30 AM PT)
1. `_monitor_moo_fills()` checks each MOO trade
2. When status='Filled':
   - Calculate TP (+2.6%) and SL (-0.9%)
   - Create OCA group
   - Place LimitOrder SELL (TP) with ocaGroup
   - Place StopOrder SELL (SL) with ocaGroup
   - Log: "OCO Bracket: TP @ $X.XX, SL @ $Y.YY"
   - Store position with both trade references

### Scanner Entries (Throughout Day)
1. Entry signal detected (price > VWAP, RSI < 60, ATR >= 0.3%)
2. Place MarketOrder BUY
3. Wait up to 3 seconds for fill
4. When status='Filled':
   - Calculate TP and SL from actual fill price
   - Create OCA group
   - Place LimitOrder SELL (TP)
   - Place StopOrder SELL (SL)
   - Log: "OCO Bracket placed"

## Rollback Plan

If issues occur, revert changes:
```powershell
git checkout HEAD -- day_trading_agents.py
```

Then manually run `place_all_oco.py` as emergency backup.

## Files Modified

- `day_trading_agents.py` (3 functions updated)
  - `_connect_to_brokerage()` - Connection retry logic
  - `_sync_positions_from_ibkr()` - OCO brackets on synced positions
  - `_monitor_moo_fills()` - OCO brackets after MOO fills

## Files NOT Modified

- `place_all_oco.py` - Emergency script (keep as backup)
- `day_trader.py` - Pre-market orchestration (no changes needed)
- `supervisor.py` - Already fixed earlier today

## Success Metrics

**Tomorrow's session should show:**
1. ✅ No connection timeouts at market open
2. ✅ OCO brackets on all positions automatically
3. ✅ Zero manual intervention required
4. ✅ Stop losses protect every position immediately after entry
5. ✅ Position tracking accurate (no "0 positions" bug)

## Additional Notes

**Capital Allocation:** 25% of account = ~$88/stock with 4-5 positions max

**OCO Parameters:**
- Take Profit: +2.6% (entry_price * 1.026)
- Stop Loss: -0.9% (entry_price * 0.991)
- Order Type: DAY orders (expire at market close)
- Outside RTH: False (regular hours only)

**OCA Group Naming:**
- Format: `OCA_{SYMBOL}_{TIMESTAMP}`
- Example: `OCA_RCAT_1730304746`
- Unique per position to avoid conflicts

---

**Implementation Complete:** All changes committed and ready for tomorrow's session.
