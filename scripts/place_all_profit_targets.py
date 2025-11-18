"""
Place profit target orders for ALL current positions at +1.8%
"""
from ib_insync import IB, Stock, LimitOrder
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=96)

print("\n📊 Current Positions:")
print("=" * 80)

positions = ib.positions()
if not positions:
    print("No positions found")
    ib.disconnect()
    exit()

print(f"Found {len(positions)} positions\n")

# First, cancel any existing SELL orders to avoid duplicates
print("🧹 Canceling existing SELL orders...")
existing_trades = ib.openTrades()
cancelled_count = 0
for trade in existing_trades:
    if trade.order.action == 'SELL':
        symbol = trade.contract.symbol
        print(f"   Cancelling: {symbol} SELL {trade.order.totalQuantity}")
        ib.cancelOrder(trade.order)
        cancelled_count += 1
        ib.sleep(0.3)

if cancelled_count > 0:
    print(f"✅ Cancelled {cancelled_count} existing SELL orders\n")
    ib.sleep(1)
else:
    print("   No existing SELL orders to cancel\n")

# Now place profit target orders for all positions
print("📈 Placing Profit Target Orders (+1.8%):")
print("-" * 80)

success_count = 0
failed_count = 0

for pos in positions:
    symbol = pos.contract.symbol
    quantity = abs(pos.position)
    entry_price = pos.avgCost
    
    # Calculate profit target (+1.8%)
    profit_target = entry_price * 1.018
    
    try:
        # Create and qualify contract
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        # Create profit target order
        tp_order = LimitOrder('SELL', quantity, profit_target)
        tp_order.tif = 'DAY'
        tp_order.outsideRth = True
        tp_order.transmit = True
        
        # Place order
        tp_trade = ib.placeOrder(contract, tp_order)
        ib.sleep(0.5)
        
        # Check status
        if tp_trade.orderStatus.status in ['PreSubmitted', 'Submitted']:
            print(f"✅ {symbol:8} | {quantity:4.0f} shares @ ${entry_price:7.2f} → SELL @ ${profit_target:7.2f} | Order ID: {tp_trade.order.orderId}")
            success_count += 1
        else:
            print(f"⚠️  {symbol:8} | Status: {tp_trade.orderStatus.status}")
            failed_count += 1
            
    except Exception as e:
        print(f"❌ {symbol:8} | Error: {e}")
        failed_count += 1

print("-" * 80)
print(f"\n✅ Successfully placed {success_count} profit target orders")
if failed_count > 0:
    print(f"⚠️  Failed to place {failed_count} orders")

# Verify orders are in IBKR
print("\n📋 Verifying Open Orders:")
print("-" * 80)
open_trades = ib.openTrades()
sell_orders = [t for t in open_trades if t.order.action == 'SELL']

if sell_orders:
    for trade in sell_orders:
        symbol = trade.contract.symbol
        qty = trade.order.totalQuantity
        price = trade.order.lmtPrice
        status = trade.orderStatus.status
        print(f"{symbol:8} | SELL {qty:4.0f} @ ${price:7.2f} | {status}")
else:
    print("⚠️  No SELL orders found in IBKR!")

ib.disconnect()
print("\n✅ Done!")
