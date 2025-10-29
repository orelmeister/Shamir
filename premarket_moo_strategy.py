"""
PRE-MARKET ORDER PLACEMENT STRATEGY

IBKR supports Market-On-Open (MOO) orders which execute at market open!

KEY ORDER TYPES FOR PRE-MARKET:
1. MOO (Market-On-Open) - Executes at opening auction price
2. LOO (Limit-On-Open) - Limit order that executes at market open
3. MKT with outsideRth=True - Market order during extended hours

SOLUTION FOR OUR BOT:
====================

PHASE 1: Pre-Market Scanner (8:00-9:25 AM ET)
---------------------------------------------
- Polygon scanner runs every 15 minutes
- Identifies high-momentum stocks BEFORE market opens
- Ranks by: ATR, volume spike, price change

PHASE 2: Place MOO Orders (9:00-9:28 AM ET)  
--------------------------------------------
For top momentum stocks:

```python
from ib_insync import Order, MarketOrder

# Option A: Market-On-Open (MOO) - Guaranteed execution at opening price
moo_order = Order()
moo_order.action = 'BUY'
moo_order.totalQuantity = shares
moo_order.orderType = 'MOO'  # Market-On-Open
moo_order.tif = 'DAY'
moo_order.outsideRth = True

# Option B: Limit-On-Open (LOO) - Execute at open but with price protection
loo_order = Order()
loo_order.action = 'BUY'
loo_order.totalQuantity = shares
loo_order.orderType = 'LOO'  # Limit-On-Open
loo_order.lmtPrice = max_price  # Won't pay more than this
loo_order.tif = 'DAY'
loo_order.outsideRth = True
```

PHASE 3: Immediate Exit Setup (9:30:01 AM ET)
---------------------------------------------
Once MOO fills at 9:30 AM:

```python
# Get actual fill price from MOO order
fill_price = moo_trade.orderStatus.avgFillPrice

# Place LIMIT SELL at +1.8% profit
tp_price = fill_price * 1.018
tp_order = LimitOrder('SELL', shares, tp_price)
tp_order.tif = 'DAY'
tp_order.outsideRth = True

# Monitor for stop loss manually (bot checks every 5 seconds)
sl_price = fill_price * 0.991
if current_price <= sl_price:
    # Place immediate market sell
    sl_order = MarketOrder('SELL', shares)
    sl_order.tif = 'IOC'
    sl_order.outsideRth = True
```

WHY THIS WORKS:
===============

1. **MOO orders accepted from 9:00-9:28 AM ET**
   - IBKR queues them for opening auction
   - Execute at official opening price (9:30 AM)
   - NO slippage from late entry!

2. **Capture opening momentum**
   - Pre-market scanner finds the movers
   - MOO gets us in at open
   - Limit sell captures +1.8% profit

3. **Avoid PendingSubmit issues**
   - MOO is a standard IBKR order type
   - No special permissions needed
   - Guaranteed execution (for market orders)

4. **Time-in-Force (TIF) options:**
   - DAY = Order expires at market close
   - GTC = Good-Till-Cancelled (persists across days)
   - IOC = Immediate-Or-Cancel (fill instantly or cancel)

IMPLEMENTATION PLAN:
====================

1. Add pre-market scanner loop (8:00-9:25 AM)
2. At 9:20 AM: Place MOO orders for top 3-5 stocks
3. At 9:30 AM: MOO fills → immediately place limit sell at +1.8%
4. Monitor stop loss every 5 seconds
5. At 3:45 PM: Liquidate any remaining positions

CRITICAL TIMING:
- MOO orders must be placed BEFORE 9:28 AM ET
- After 9:28 AM, MOO orders rejected
- Use LOO or regular market orders after 9:28 AM

IBKR TIF VALUES:
- '' (empty) = Day order
- 'DAY' = Day order (explicit)
- 'GTC' = Good-Till-Cancelled  
- 'IOC' = Immediate-Or-Cancel
- 'GTD' = Good-Till-Date
- 'OPG' = At opening (similar to MOO)
- 'FOK' = Fill-Or-Kill

RECOMMENDED: Use 'DAY' for MOO/LOO, 'IOC' for stop-loss
"""

from ib_insync import IB, Stock, Order, MarketOrder, LimitOrder
import logging
from datetime import datetime
import pytz

class PreMarketOrderPlacer:
    """
    Places Market-On-Open orders for high-momentum stocks identified by scanner.
    """
    
    def __init__(self, ib: IB):
        self.ib = ib
        self.moo_trades = {}  # Track MOO orders
        
    def is_moo_window(self):
        """Check if we're in MOO order window (9:00-9:28 AM ET)"""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        
        # MOO orders accepted 9:00-9:28 AM ET
        moo_start = now.replace(hour=9, minute=0, second=0)
        moo_end = now.replace(hour=9, minute=28, second=0)
        
        return moo_start <= now <= moo_end
    
    def place_moo_orders(self, watchlist, capital_per_position):
        """
        Place Market-On-Open orders for top momentum stocks.
        
        Args:
            watchlist: List of {'symbol': 'ABC', 'atr': 0.5, 'volume': 1000000}
            capital_per_position: Dollar amount to invest per stock
        
        Returns:
            Dict of {symbol: trade} for placed MOO orders
        """
        if not self.is_moo_window():
            logging.warning("Not in MOO window (9:00-9:28 AM ET). Orders may be rejected.")
        
        # Sort by momentum (ATR * volume)
        watchlist_sorted = sorted(
            watchlist, 
            key=lambda x: x.get('atr', 0) * x.get('volume', 0),
            reverse=True
        )
        
        # Take top 3-5 stocks
        top_stocks = watchlist_sorted[:5]
        
        logging.info(f"Placing MOO orders for {len(top_stocks)} stocks...")
        
        for stock in top_stocks:
            symbol = stock['symbol']
            
            try:
                # Get approximate current price
                contract = Stock(symbol, 'SMART', 'USD')
                ticker = self.ib.reqMktData(contract, '', False, False)
                self.ib.sleep(1)
                
                current_price = ticker.last or ticker.close or stock.get('price', 10)
                self.ib.cancelMktData(contract)
                
                # Calculate shares
                shares = int(capital_per_position / current_price)
                
                if shares < 1:
                    logging.warning(f"Skipping {symbol}: Price ${current_price:.2f} too high for ${capital_per_position} allocation")
                    continue
                
                # Create Market-On-Open order
                moo_order = Order()
                moo_order.action = 'BUY'
                moo_order.totalQuantity = shares
                moo_order.orderType = 'MOO'  # Market-On-Open
                moo_order.tif = 'DAY'
                moo_order.outsideRth = True  # Allow extended hours
                moo_order.transmit = True
                
                # Place order
                trade = self.ib.placeOrder(contract, moo_order)
                self.moo_trades[symbol] = {
                    'trade': trade,
                    'contract': contract,
                    'shares': shares,
                    'expected_price': current_price
                }
                
                logging.info(f"✅ MOO order placed: {symbol} - {shares} shares @ ~${current_price:.2f}")
                
            except Exception as e:
                logging.error(f"Error placing MOO for {symbol}: {e}")
        
        return self.moo_trades
    
    def wait_for_fills_and_setup_exits(self):
        """
        Wait for MOO orders to fill at 9:30 AM, then immediately place profit target orders.
        """
        logging.info("Waiting for MOO orders to fill at market open (9:30 AM ET)...")
        
        # Wait until 9:30:10 AM ET (give 10 seconds for fills)
        et = pytz.timezone('US/Eastern')
        while True:
            now = datetime.now(et)
            if now.hour == 9 and now.minute >= 30:
                break
            self.ib.sleep(1)
        
        # Check fills
        self.ib.sleep(10)  # Wait 10 seconds for fills to process
        
        positions = {}
        
        for symbol, moo_data in self.moo_trades.items():
            trade = moo_data['trade']
            contract = moo_data['contract']
            
            if trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                filled_qty = trade.orderStatus.filled
                
                logging.info(f"🎯 MOO FILLED: {symbol} - {filled_qty} shares @ ${fill_price:.2f}")
                
                # Calculate profit target (+1.8%)
                tp_price = fill_price * 1.018
                sl_price = fill_price * 0.991
                
                # Place LIMIT SELL for take profit
                tp_order = LimitOrder('SELL', filled_qty, tp_price)
                tp_order.tif = 'DAY'
                tp_order.outsideRth = True
                tp_trade = self.ib.placeOrder(contract, tp_order)
                
                logging.info(f"📈 Profit target placed: {symbol} SELL @ ${tp_price:.2f} (+1.8%)")
                
                # Store position for stop-loss monitoring
                positions[symbol] = {
                    'contract': contract,
                    'quantity': filled_qty,
                    'entry_price': fill_price,
                    'take_profit_price': tp_price,
                    'stop_loss_price': sl_price,
                    'take_profit_trade': tp_trade
                }
                
            else:
                logging.warning(f"⚠️  MOO NOT FILLED: {symbol} - Status: {trade.orderStatus.status}")
        
        return positions


def test_moo_strategy():
    """Test script for MOO order placement"""
    
    # Connect to IBKR
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=99)
    
    # Sample watchlist from Polygon scanner
    watchlist = [
        {'symbol': 'CX', 'atr': 0.52, 'volume': 4300000, 'price': 10.50},
        {'symbol': 'DJT', 'atr': 1.44, 'volume': 1800000, 'price': 16.48},
        {'symbol': 'TV', 'atr': 0.57, 'volume': 1000000, 'price': 8.20}
    ]
    
    # Create placer
    placer = PreMarketOrderPlacer(ib)
    
    # Check if in MOO window
    if placer.is_moo_window():
        print("✅ In MOO window - placing orders...")
        
        # Place MOO orders
        moo_trades = placer.place_moo_orders(watchlist, capital_per_position=1000)
        
        # Wait for fills and setup exits
        positions = placer.wait_for_fills_and_setup_exits()
        
        print(f"\n📊 {len(positions)} positions opened with profit targets set!")
        
    else:
        print("⏰ Not in MOO window (9:00-9:28 AM ET)")
        print(f"   Current time: {datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S ET')}")
    
    ib.disconnect()


if __name__ == "__main__":
    test_moo_strategy()
