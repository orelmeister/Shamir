"""
Debug why profit target orders aren't sticking
"""
from ib_insync import IB, Stock, LimitOrder
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=95)

# Test with UP position
symbol = "UP"
quantity = 50
entry_price = 1.48
profit_target = entry_price * 1.018

print(f"\n🧪 Testing profit target order for {symbol}")
print(f"Entry: ${entry_price:.2f}, Target: ${profit_target:.2f}, Qty: {quantity}")

# Create contract
contract = Stock(symbol, 'SMART', 'USD')
print(f"\nContract before qualification: {contract}")

# Qualify
qualified = ib.qualifyContracts(contract)
print(f"Qualified contracts: {qualified}")
print(f"Contract after qualification: {contract}")

# Create order
tp_order = LimitOrder('SELL', quantity, profit_target)
tp_order.tif = 'DAY'
tp_order.outsideRth = True
tp_order.transmit = True

print(f"\nOrder details:")
print(f"  Action: {tp_order.action}")
print(f"  Quantity: {tp_order.totalQuantity}")
print(f"  Limit Price: {tp_order.lmtPrice}")
print(f"  TIF: {tp_order.tif}")
print(f"  OutsideRTH: {tp_order.outsideRth}")
print(f"  Transmit: {tp_order.transmit}")

# Place order
print(f"\nPlacing order...")
tp_trade = ib.placeOrder(contract, tp_order)

# Wait and check status multiple times
for i in range(10):
    time.sleep(0.5)
    status = tp_trade.orderStatus.status
    print(f"  [{i*0.5:.1f}s] Status: {status}, Order ID: {tp_trade.order.orderId}")
    
    if status in ['Submitted', 'Filled', 'Cancelled']:
        break

print(f"\nFinal status: {tp_trade.orderStatus.status}")
print(f"Order ID: {tp_trade.order.orderId}")
print(f"Trade log:")
for entry in tp_trade.log:
    print(f"  {entry.time} | {entry.status} | {entry.message} | Error: {entry.errorCode}")

# Check if it's in open orders
print(f"\n📋 Checking open orders...")
ib.sleep(1)
open_trades = ib.openTrades()
up_orders = [t for t in open_trades if t.contract.symbol == 'UP']

if up_orders:
    print(f"✅ Found {len(up_orders)} UP orders:")
    for t in up_orders:
        print(f"   {t.order.action} {t.order.totalQuantity} @ ${t.order.lmtPrice:.2f} | {t.orderStatus.status}")
else:
    print(f"❌ No UP orders found in open trades!")

print("\nAll open orders:")
for t in open_trades:
    print(f"  {t.contract.symbol} {t.order.action} {t.order.totalQuantity} @ ${t.order.lmtPrice:.2f}")

ib.disconnect()
