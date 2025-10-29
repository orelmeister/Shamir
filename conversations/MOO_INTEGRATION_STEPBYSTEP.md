# MOO Integration - Step-by-Step Implementation Plan

## Overview
Add Market-On-Open (MOO) order placement as a **new pre-market phase** in the existing day trading bot workflow. This is an **additive change** - all existing logic remains functional.

## Current Bot Workflow (UNCHANGED)
```
9:25 AM ET: Bot starts
9:25-3:45 PM: Scanner runs every 15 minutes
              - Entry: Price > VWAP, ATR >= 0.3%, RSI < 60
              - Exit: +1.8% TP (LimitOrder) or -0.9% SL (manual monitoring)
3:45 PM ET: Liquidate all positions
```

## New Enhanced Workflow (WITH MOO)
```
8:00 AM ET: Bot starts early
8:00-9:20 AM: Scanner runs every 15 minutes (pre-market analysis)
              - Build watchlist of top momentum stocks
              
9:20-9:27 AM: MOO PLACEMENT PHASE (NEW)
              - Select top 3-5 stocks from watchlist
              - Place MOO orders (execute at 9:30 AM open)
              
9:30-9:31 AM: MOO FILL MONITORING (NEW)
              - Wait for MOO fills
              - Place profit targets (+1.8% LimitOrder)
              - Add to position tracking
              
9:31-3:45 PM: EXISTING LOGIC (UNCHANGED)
              - Scanner continues every 15 minutes
              - Can still enter new positions (if capital available)
              - Manual stop-loss monitoring
              
3:45 PM ET: EXISTING LIQUIDATION (UNCHANGED)
              - Liquidate all positions (MOO + any scanner entries)
```

## Key Principle: **Additive, Not Disruptive**
- ✅ MOO phase runs **before** existing scanner phase
- ✅ Existing scanner logic **completely unchanged**
- ✅ Existing position monitoring **completely unchanged**
- ✅ Existing liquidation logic **completely unchanged**
- ✅ MOO positions tracked in **same** `self.positions` dict
- ✅ If MOO fills fail, bot continues with regular scanner entries

## Code Changes Needed

### 1. Add MOO Constants (Top of IntradayTraderAgent)
```python
class IntradayTraderAgent:
    def __init__(self, ib, capital, allocation, ...):
        # ... existing __init__ code ...
        
        # MOO-specific state (NEW)
        self.moo_placed = False
        self.moo_monitored = False
        self.moo_trades = []
        self.moo_stocks = []
        
        # MOO timing (NEW)
        self.MOO_PLACEMENT_START = time(9, 20)  # 9:20 AM ET
        self.MOO_PLACEMENT_END = time(9, 27)    # 9:27 AM ET (1 min buffer)
        self.MOO_FILL_TIME = time(9, 30)        # 9:30 AM ET
```

### 2. Add MOO Placement Method
```python
def place_moo_orders(self):
    """
    Place Market-On-Open orders for top momentum stocks.
    Called once between 9:20-9:27 AM ET.
    """
    self.log(logging.INFO, "=" * 80)
    self.log(logging.INFO, "🚀 MOO PLACEMENT PHASE - Market-On-Open Orders")
    self.log(logging.INFO, "=" * 80)
    
    # Get top stocks from latest scanner results
    top_stocks = self.get_top_moo_candidates(max_stocks=5)
    
    if not top_stocks:
        self.log(logging.WARNING, "No suitable stocks for MOO orders")
        return
    
    self.log(logging.INFO, f"Selected {len(top_stocks)} stocks for MOO orders:")
    for symbol in top_stocks:
        self.log(logging.INFO, f"  • {symbol}")
    
    # Place MOO orders
    for symbol in top_stocks:
        # Check if we have capital
        if len(self.positions) >= self.max_positions:
            self.log(logging.WARNING, f"Max positions reached, skipping {symbol}")
            continue
        
        try:
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Calculate position size
            ticker = self.ib.reqTickers(contract)[0]
            self.ib.sleep(0.5)
            
            estimated_price = ticker.last or ticker.close or ticker.bid
            if not estimated_price:
                self.log(logging.WARNING, f"Could not get price for {symbol}, skipping")
                continue
            
            capital_for_position = self.capital * self.allocation
            shares = int(capital_for_position / estimated_price)
            
            if shares < 1:
                self.log(logging.WARNING, f"Insufficient capital for {symbol}, skipping")
                continue
            
            # Create MOO order
            moo_order = Order()
            moo_order.action = 'BUY'
            moo_order.totalQuantity = shares
            moo_order.orderType = 'MOO'  # Market-On-Open
            moo_order.tif = 'DAY'
            moo_order.outsideRth = True
            moo_order.transmit = True
            
            # Place order
            trade = self.ib.placeOrder(contract, moo_order)
            
            self.log(logging.INFO, f"✅ MOO order placed: {symbol} x{shares} shares @ ~${estimated_price:.2f}")
            
            # Track MOO trade
            self.moo_trades.append({
                'symbol': symbol,
                'trade': trade,
                'shares': shares,
                'estimated_price': estimated_price
            })
            self.moo_stocks.append(symbol)
            
        except Exception as e:
            self.log(logging.ERROR, f"Failed to place MOO order for {symbol}: {e}")
    
    self.moo_placed = True
    self.log(logging.INFO, f"MOO placement complete: {len(self.moo_trades)} orders placed")

def get_top_moo_candidates(self, max_stocks=5):
    """
    Select top stocks for MOO orders based on pre-market momentum.
    Uses latest scanner results from watchlist.
    """
    # Get watchlist (from latest scanner run)
    if not self.watchlist:
        self.log(logging.WARNING, "Watchlist empty, no MOO candidates")
        return []
    
    # Sort by momentum (price change, volume, ATR)
    # For now, use top N from watchlist
    # TODO: Add pre-market momentum scoring
    
    candidates = self.watchlist[:max_stocks]
    
    return candidates
```

### 3. Add MOO Fill Monitoring Method
```python
def monitor_moo_fills(self):
    """
    Monitor MOO order fills at market open (9:30 AM).
    Place profit targets immediately after fills.
    """
    self.log(logging.INFO, "=" * 80)
    self.log(logging.INFO, "📊 MOO FILL MONITORING - Checking Market Open Executions")
    self.log(logging.INFO, "=" * 80)
    
    if not self.moo_trades:
        self.log(logging.INFO, "No MOO trades to monitor")
        return
    
    # Wait 30 seconds for fills
    self.log(logging.INFO, "Waiting for MOO fills (30 seconds)...")
    
    for i in range(30):
        self.ib.sleep(1)
        
        # Check each MOO trade
        for moo in self.moo_trades:
            trade = moo['trade']
            symbol = moo['symbol']
            
            # Skip if already processed
            if moo.get('processed'):
                continue
            
            status = trade.orderStatus.status
            
            if status == 'Filled':
                # MOO filled!
                fill_price = trade.orderStatus.avgFillPrice
                filled_qty = trade.orderStatus.filled
                
                self.log(logging.INFO, f"✅ MOO FILLED: {symbol} - {filled_qty} shares @ ${fill_price:.2f}")
                
                # Calculate profit target and stop loss
                take_profit = fill_price * (1 + self.take_profit_pct)
                stop_loss = fill_price * (1 - self.stop_loss_pct)
                
                # Place profit target (LimitOrder)
                tp_order = LimitOrder('SELL', filled_qty, take_profit)
                tp_trade = self.ib.placeOrder(trade.contract, tp_order)
                
                self.log(logging.INFO, f"   📈 Profit target: ${take_profit:.2f} (+{self.take_profit_pct*100:.1f}%)")
                self.log(logging.INFO, f"   🛑 Stop loss: ${stop_loss:.2f} (-{self.stop_loss_pct*100:.1f}%)")
                
                # Add to positions (SAME dict as scanner entries)
                self.positions[symbol] = {
                    "quantity": filled_qty,
                    "entry_price": fill_price,
                    "contract": trade.contract,
                    "atr_pct": None,  # No ATR for MOO entries
                    "take_profit_trade": tp_trade,
                    "stop_loss_price": stop_loss,
                    "entry_type": "MOO"  # Tag as MOO entry
                }
                
                moo['processed'] = True
                
            elif status in ['Cancelled', 'ApiCancelled', 'Inactive']:
                self.log(logging.WARNING, f"❌ MOO FAILED: {symbol} - {status}")
                moo['processed'] = True
    
    # Summary
    filled_count = sum(1 for m in self.moo_trades if m.get('processed') and 
                      m['trade'].orderStatus.status == 'Filled')
    
    self.log(logging.INFO, f"MOO fill monitoring complete: {filled_count}/{len(self.moo_trades)} filled")
    self.moo_monitored = True
```

### 4. Modify Main Run Loop (CRITICAL - Additive Only)
```python
def run(self):
    """
    Main trading loop with MOO pre-market phase.
    
    Timeline:
    8:00 AM - 9:20 AM: Pre-market scanner (build watchlist)
    9:20 AM - 9:27 AM: Place MOO orders
    9:30 AM - 9:31 AM: Monitor MOO fills
    9:31 AM - 3:45 PM: Existing scanner + monitoring (UNCHANGED)
    3:45 PM: Liquidate all positions (UNCHANGED)
    """
    
    self.log(logging.INFO, "=" * 80)
    self.log(logging.INFO, "BOT STARTING - Enhanced with MOO Pre-Market Phase")
    self.log(logging.INFO, "=" * 80)
    
    # Change start time to 8:00 AM for pre-market scanner
    START_HOUR = 8  # Was 9
    START_MINUTE = 0  # Was 25
    
    # Wait for market hours (or pre-market start)
    while True:
        now_et = datetime.now(self.et_tz)
        current_time = now_et.time()
        
        # Start at 8:00 AM ET
        if current_time >= time(START_HOUR, START_MINUTE):
            break
        
        sleep_seconds = 60
        self.log(logging.INFO, f"Waiting for start time (8:00 AM ET). Current time: {now_et.strftime('%I:%M:%S %p')} ET")
        time.sleep(sleep_seconds)
    
    self.log(logging.INFO, f"Bot starting at {datetime.now(self.et_tz).strftime('%I:%M:%S %p')} ET")
    
    # Main trading loop
    while True:
        try:
            now_et = datetime.now(self.et_tz)
            current_time = now_et.time()
            
            # === PHASE 1: MOO PLACEMENT (9:20-9:27 AM) ===
            if (self.MOO_PLACEMENT_START <= current_time < self.MOO_PLACEMENT_END 
                and not self.moo_placed):
                
                self.log(logging.INFO, "⏰ MOO PLACEMENT WINDOW - Placing pre-market orders")
                self.place_moo_orders()
            
            # === PHASE 2: MOO FILL MONITORING (9:30 AM) ===
            elif (current_time >= self.MOO_FILL_TIME 
                  and self.moo_placed 
                  and not self.moo_monitored):
                
                self.log(logging.INFO, "⏰ MARKET OPENED - Monitoring MOO fills")
                self.monitor_moo_fills()
            
            # === PHASE 3: EXISTING SCANNER LOGIC (UNCHANGED) ===
            # Check if it's time to scan
            if self.should_run_scanner():
                self.log(logging.INFO, "⏰ Scanner interval reached - Running scan")
                self.scanner_logic()
                self.last_scan_time = time.time()
            
            # === PHASE 4: EXISTING POSITION MONITORING (UNCHANGED) ===
            if self.positions:
                self.monitor_positions()
            
            # === PHASE 5: EXISTING EOD LIQUIDATION (UNCHANGED) ===
            if current_time >= time(15, 45):
                self.log(logging.INFO, "⏰ End of day (3:45 PM ET) - Liquidating all positions")
                self.liquidate_all_positions()
                break
            
            # Sleep between iterations
            time.sleep(5)
            
        except KeyboardInterrupt:
            self.log(logging.INFO, "Bot stopped by user")
            break
        except Exception as e:
            self.log(logging.ERROR, f"Error in main loop: {e}")
            time.sleep(30)
    
    self.log(logging.INFO, "Bot shutdown complete")
```

### 5. Update Liquidation (UNCHANGED - Just Handle MOO Positions)
```python
def liquidate_all_positions(self):
    """
    Liquidate all positions at end of day.
    Works for both MOO and scanner entries (same position dict).
    """
    if not self.positions:
        self.log(logging.INFO, "No positions to liquidate")
        return
    
    self.log(logging.INFO, f"Liquidating {len(self.positions)} position(s)...")
    
    for symbol, position in list(self.positions.items()):
        try:
            # ... EXISTING LIQUIDATION CODE (UNCHANGED) ...
            # Works for MOO positions because they're in same dict
            
            # Log entry type for analysis
            entry_type = position.get('entry_type', 'SCANNER')
            self.log(logging.INFO, f"LIQUIDATED {symbol} ({entry_type} entry): ${pnl:.2f} ({pnl_pct:+.2f}%)")
            
        except Exception as e:
            self.log(logging.ERROR, f"Failed to liquidate {symbol}: {e}")
```

## Testing Plan

### Test 1: MOO Order Validation (BEFORE INTEGRATION)
**File**: `test_moo_orders.py`
**When**: Tomorrow 9:00-9:27 AM ET
**What**:
- Place 1-share MOO order for SIRI (~$5)
- Verify order acceptance
- Check callbacks: PendingSubmit → PreSubmitted → Submitted
- Verify fill at 9:30 AM
- Cancel order (safety measure)

**Success Criteria**:
- ✅ Order accepted (status = Submitted)
- ✅ Callbacks received correctly
- ✅ Order queued until 9:30 AM
- ✅ No "PendingSubmit" stuck issues

### Test 2: Integration Test (AFTER MOO VALIDATION)
**When**: After Test 1 passes, next trading day
**What**:
- Run bot with MOO integration
- Let MOO phase execute (9:20-9:30 AM)
- Verify profit targets placed after fills
- Verify scanner continues after MOO (9:31+ AM)
- Verify EOD liquidation includes MOO positions

**Success Criteria**:
- ✅ MOO orders placed in 9:20-9:27 window
- ✅ MOO fills at 9:30 AM
- ✅ Profit targets placed immediately
- ✅ Scanner runs normally after MOO
- ✅ EOD liquidation works for all positions
- ✅ No conflicts between MOO and scanner entries

## Rollback Plan

If MOO integration causes issues:

1. **Quick Disable**: Set flag at top of `run()`:
   ```python
   ENABLE_MOO = False  # Set to False to disable MOO
   
   if ENABLE_MOO and self.MOO_PLACEMENT_START <= current_time < ...:
       self.place_moo_orders()
   ```

2. **Full Rollback**: Remove MOO code blocks (clearly marked with `# NEW`)

3. **Bot still functional**: All existing logic unchanged, just remove MOO phase

## Risk Mitigation

- ✅ Test MOO separately before integration
- ✅ MOO phase is isolated (doesn't modify existing code)
- ✅ Quick disable flag available
- ✅ Same position tracking (no separate systems)
- ✅ MOO failures don't block scanner entries
- ✅ Start with small position sizes (existing allocation)

## Expected Improvement

**Problem**: Bot enters after market opens, misses momentum
**Solution**: MOO orders capture opening price at 9:30 AM

**Before MOO**:
- First entry: ~9:40 AM (after first scanner run)
- Missing: Opening surge (+2-5% in first 10 minutes)

**After MOO**:
- First entry: 9:30:00 AM (market open)
- Capturing: Full opening momentum

**Estimated Impact**:
- 3-5 MOO fills per day @ +1.8% target
- Capturing opening volatility (highest of day)
- Should convert from -$25/day losses to +$50-100/day gains
