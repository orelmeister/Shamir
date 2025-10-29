"""
INTEGRATION PLAN: Market-On-Open Strategy

CURRENT PROBLEM:
- Bot starts at 9:25 AM, misses opening momentum
- By the time bot scans and enters, best gains are gone
- All trades go negative immediately

NEW SOLUTION:
- Scanner runs 8:00-9:20 AM (every 15 min)
- At 9:20 AM: Place MOO orders for top 3-5 stocks
- At 9:30 AM: Orders fill at opening price
- At 9:30:10 AM: Place limit sell at +1.8% profit
- Monitor stop loss every 5 seconds

STEP-BY-STEP IMPLEMENTATION:
============================

STEP 1: Modify IntradayTraderAgent to Add Pre-Market Phase
----------------------------------------------------------

In day_trading_agents.py, add to IntradayTraderAgent.run():

```python
def run(self):
    """Main trading loop with pre-market MOO strategy"""
    
    # PHASE 1: Pre-Market Scanner (8:00-9:20 AM ET)
    if self._is_premarket_window():
        self.log(logging.INFO, "=== PRE-MARKET PHASE ===")
        self.log(logging.INFO, "Running scanner to identify opening momentum...")
        
        # Run scanner every 15 minutes
        last_scan = 0
        while self._is_premarket_window():
            if time.time() - last_scan >= 900:  # 15 minutes
                self._run_premarket_scanner()
                last_scan = time.time()
            time.sleep(60)
    
    # PHASE 2: Place MOO Orders (9:20 AM ET)
    if self._is_moo_window():
        self.log(logging.INFO, "=== MOO ORDER PLACEMENT ===")
        self._place_moo_orders()
        
        # Wait for market open
        while not self._is_market_open():
            time.sleep(1)
        
        # Wait for fills
        time.sleep(10)
        self._setup_exits_for_moo_fills()
    
    # PHASE 3: Regular Intraday Trading (9:30 AM - 3:45 PM ET)
    while self._should_continue_trading():
        # ... existing trading loop ...
```

STEP 2: Add Helper Methods
---------------------------

```python
def _is_premarket_window(self):
    \"\"\"Check if 8:00-9:20 AM ET\"\"\"
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    return now.hour == 8 or (now.hour == 9 and now.minute < 20)

def _is_moo_window(self):
    \"\"\"Check if 9:20-9:28 AM ET (MOO order window)\"\"\"
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    return now.hour == 9 and 20 <= now.minute <= 28

def _run_premarket_scanner(self):
    \"\"\"Run Polygon scanner during pre-market\"\"\"
    self.log(logging.INFO, "Running pre-market scanner...")
    
    # Run intraday_scanner_polygon.py
    result = subprocess.run(
        [sys.executable, "intraday_scanner_polygon.py"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        # Load watchlist
        with open('day_trading_watchlist.json', 'r') as f:
            data = json.load(f)
            stocks = data.get('stocks', [])
        
        self.log(logging.INFO, f"Scanner found {len(stocks)} momentum stocks")
        return stocks
    else:
        self.log(logging.ERROR, f"Scanner failed: {result.stderr}")
        return []

def _place_moo_orders(self):
    \"\"\"Place Market-On-Open orders for top stocks\"\"\"
    # Load latest watchlist
    with open('day_trading_watchlist.json', 'r') as f:
        data = json.load(f)
        stocks = data.get('stocks', [])
    
    # Sort by momentum (ATR * volume)
    stocks_sorted = sorted(
        stocks,
        key=lambda x: x.get('atr_percent', 0) * x.get('volume', 0),
        reverse=True
    )
    
    # Take top 3-5 stocks
    top_stocks = stocks_sorted[:5]
    
    self.log(logging.INFO, f"Placing MOO orders for top {len(top_stocks)} stocks...")
    
    capital_per_position = self.account_value * self.allocation
    
    for stock in top_stocks:
        symbol = stock['symbol']
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            
            # Get approximate price
            ticker = self.ib.reqMktData(contract, '', False, False)
            self.ib.sleep(1)
            current_price = ticker.last or ticker.close or stock.get('close', 10)
            self.ib.cancelMktData(contract)
            
            # Calculate shares
            shares = int(capital_per_position / current_price)
            
            if shares < 1:
                self.log(logging.WARNING, f"Skipping {symbol}: price too high")
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
            
            # Store for tracking
            self.pending_orders[symbol] = {
                'trade': trade,
                'contract': contract,
                'shares': shares,
                'order_type': 'MOO',
                'timestamp': time.time()
            }
            
            self.log(logging.INFO, f"MOO order placed: {symbol} - {shares} shares @ ~${current_price:.2f}")
            
        except Exception as e:
            self.log(logging.ERROR, f"Error placing MOO for {symbol}: {e}")

def _setup_exits_for_moo_fills(self):
    \"\"\"Check MOO fills and place profit target orders\"\"\"
    self.log(logging.INFO, "Checking MOO fill statuses...")
    
    for symbol, order_data in list(self.pending_orders.items()):
        if order_data.get('order_type') != 'MOO':
            continue
        
        trade = order_data['trade']
        contract = order_data['contract']
        
        if trade.orderStatus.status == 'Filled':
            fill_price = trade.orderStatus.avgFillPrice
            filled_qty = trade.orderStatus.filled
            
            self.log(logging.INFO, f"MOO FILLED: {symbol} - {filled_qty} shares @ ${fill_price:.2f}")
            
            # Calculate targets
            tp_price = fill_price * 1.018  # +1.8%
            sl_price = fill_price * 0.991   # -0.9%
            
            # Place LIMIT SELL for take profit
            tp_order = LimitOrder('SELL', filled_qty, tp_price)
            tp_order.tif = 'DAY'
            tp_order.outsideRth = True
            tp_trade = self.ib.placeOrder(contract, tp_order)
            
            self.log(logging.INFO, f"Profit target set: {symbol} @ ${tp_price:.2f} (+1.8%)")
            
            # Store position
            self.positions[symbol] = {
                'quantity': filled_qty,
                'entry_price': fill_price,
                'contract': contract,
                'take_profit_price': tp_price,
                'stop_loss_price': sl_price,
                'take_profit_trade': tp_trade,
                'entry_time': time.time()
            }
            
            # Remove from pending
            del self.pending_orders[symbol]
            
        else:
            self.log(logging.WARNING, f"MOO NOT FILLED: {symbol} - Status: {trade.orderStatus.status}")
```

STEP 3: Update start_day_trader.bat
------------------------------------

Change start time from 9:25 AM to 8:00 AM:

```batch
@echo off
echo Starting Day Trader Bot with MOO Strategy...
echo.
echo Pre-Market Phase: 8:00-9:20 AM (Scanner)
echo MOO Orders:       9:20-9:28 AM (Place orders)
echo Market Open:      9:30 AM (Orders execute)
echo Intraday Trade:   9:30 AM-3:45 PM (Monitor positions)
echo.
pause

.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25
```

STEP 4: Update Task Scheduler (if using automated start)
---------------------------------------------------------

Change scheduled start time from 9:25 AM to 8:00 AM PT (11:00 AM ET)

EXPECTED RESULTS:
=================

Before (Current):
- Bot starts 9:25 AM PT (12:25 PM ET)
- Market already open 2h 55min
- Best momentum gone
- Entries at inflated prices
- Immediate losses

After (With MOO):
- Scanner runs 8:00-9:20 AM ET
- MOO orders placed 9:20 AM ET
- Orders fill 9:30 AM at opening price
- Capture opening momentum spike
- Profit target immediately active
- Stop loss monitored every 5 seconds

RISK MANAGEMENT:
- Limit to top 3-5 stocks (diversification)
- 25% allocation per position (existing)
- +1.8% profit target (existing)
- -0.9% stop loss (existing)
- Liquidate all at 3:45 PM ET (existing)

ADVANTAGES OVER CURRENT APPROACH:
1. ✅ Guaranteed execution at market open
2. ✅ No slippage from late entry
3. ✅ Capture opening momentum
4. ✅ No "PendingSubmit" issues (MOO is standard)
5. ✅ Pre-market analysis time (1h 20min)
6. ✅ Profit target active immediately

TESTING PLAN:
1. Test MOO order placement (tomorrow 9:20 AM)
2. Verify fills at 9:30 AM
3. Confirm profit target orders placed
4. Monitor stop loss execution
5. Validate EOD liquidation

FILES TO MODIFY:
- day_trading_agents.py (add MOO methods)
- start_day_trader.bat (change start time)
- Task Scheduler (if automated)

FILES CREATED:
- premarket_moo_strategy.py (reference implementation)
- MOO_INTEGRATION_PLAN.md (this file)
"""
