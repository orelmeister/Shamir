from ib_insync import *
import time

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=95)

# Get all positions opened today
positions = [p for p in ib.positions() if p.position > 0]
print(f"\n{'='*60}")
print(f"Found {len(positions)} positions to protect with OCO brackets")
print(f"{'='*60}\n")

# Symbols opened today (excluding SKYX and BFLY which are older)
today_symbols = ['RCAT', 'BYND', 'CEPU', 'SUPV', 'BCAX', 'MLTX', 'WULF', 'UDMY', 'CWH', 'RITM', 'INDI', 'UP']

for pos in positions:
    symbol = pos.contract.symbol
    quantity = int(pos.position)
    
    # Skip if not from today
    if symbol not in today_symbols:
        print(f"⏭️  Skipping {symbol} (not from today)")
        continue
    
    print(f"\n📊 {symbol}: {quantity} shares")
    
    # Create contract
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    
    # Get current market price
    ib.reqMarketDataType(3)  # Delayed data
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(2)
    
    # Try to get current price
    price = ticker.last or ticker.close or ticker.marketPrice()
    if not price or price <= 0:
        print(f"   ❌ No price data available, skipping")
        ib.cancelMktData(contract)
        continue
    
    ib.cancelMktData(contract)
    
    print(f"   Current price: ${price:.2f}")
    
    # Calculate OCO levels
    take_profit_price = price * 1.026  # +2.6%
    stop_loss_price = price * 0.991    # -0.9%
    
    print(f"   Take Profit: ${take_profit_price:.2f} (+2.6%)")
    print(f"   Stop Loss: ${stop_loss_price:.2f} (-0.9%)")
    
    # Create OCA group
    oca_group = f"OCA_{symbol}_{int(time.time())}"
    
    # Take Profit order (LIMIT SELL)
    tp_order = LimitOrder('SELL', quantity, take_profit_price)
    tp_order.ocaGroup = oca_group
    tp_order.ocaType = 1  # Cancel all when one fills
    tp_order.tif = 'DAY'
    tp_order.outsideRth = False
    
    # Stop Loss order (STOP SELL)
    sl_order = StopOrder('SELL', quantity, stop_loss_price)
    sl_order.ocaGroup = oca_group
    sl_order.ocaType = 1  # Cancel all when one fills
    sl_order.tif = 'DAY'
    sl_order.outsideRth = False
    
    # Place both OCO orders
    tp_trade = ib.placeOrder(contract, tp_order)
    sl_trade = ib.placeOrder(contract, sl_order)
    
    print(f"   ✅ OCO Bracket placed (Group: {oca_group})")
    
    ib.sleep(0.5)

print(f"\n{'='*60}")
print(f"✅ All OCO brackets placed successfully!")
print(f"{'='*60}\n")

ib.disconnect()
