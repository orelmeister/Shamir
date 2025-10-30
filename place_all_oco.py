from ib_insync import *
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=98)
ib.reqMarketDataType(3)  # Delayed data

# Get all positions
positions = ib.positions()
print(f'\n📊 Found {len(positions)} positions\n')

for pos in positions:
    symbol = pos.contract.symbol
    quantity = int(pos.position)
    avg_cost = pos.avgCost
    
    if symbol == 'SKYX':
        print(f'⏭️  Skipping {symbol} (protected position)')
        continue
    
    if quantity <= 0:
        continue
    
    # Qualify contract
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    
    # Use avgCost as entry price
    entry_price = avg_cost
    
    # Calculate targets
    take_profit = entry_price * 1.026  # +2.6%
    stop_loss = entry_price * 0.987    # -1.3%
    
    # Create OCA group
    oca_group = f'OCA_{symbol}_{int(time.time())}'
    
    # Take profit order (LIMIT SELL)
    tp_order = LimitOrder('SELL', quantity, round(take_profit, 2))
    tp_order.ocaGroup = oca_group
    tp_order.ocaType = 1  # Cancel remaining on fill
    tp_order.tif = 'DAY'
    tp_order.outsideRth = False
    
    # Stop loss order (STOP SELL)
    sl_order = StopOrder('SELL', quantity, round(stop_loss, 2))
    sl_order.ocaGroup = oca_group
    sl_order.ocaType = 1  # Cancel remaining on fill
    sl_order.tif = 'DAY'
    sl_order.outsideRth = False
    
    # Place orders
    tp_trade = ib.placeOrder(contract, tp_order)
    sl_trade = ib.placeOrder(contract, sl_order)
    
    print(f'✅ {symbol}: {quantity} shares @ ${entry_price:.2f}')
    print(f'   TP: ${take_profit:.2f} (+2.6%)')
    print(f'   SL: ${stop_loss:.2f} (-0.9%)')
    print(f'   OCA: {oca_group}\n')
    
    time.sleep(0.3)  # Small delay between orders

print('🎯 OCO brackets placed on all positions!')
ib.disconnect()
