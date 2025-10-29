"""Check if profit target orders were placed""""""

from ib_insync import IBCheck if profit target orders exist for current positions

import ib_insync.util as ib_util"""

from datetime import datetimefrom ib_insync import IB, Stock, LimitOrder

import time

ib = IB()

ib_util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))ib = IB()

ib.connect('127.0.0.1', 4001, clientId=99)

print("="*80)

print("PROFIT TARGET ORDER CHECK")print("\n📊 Current Positions:")

print("="*80)print("=" * 80)

positions = ib.positions()

today = datetime.now().date()for pos in positions:

fills = [f for f in ib.fills() if f.time.date() == today]    print(f"{pos.contract.symbol:8} | {pos.position:6.0f} shares @ ${pos.avgCost:7.2f}")



bought = {}print("\n📋 Open Orders:")

for fill in fills:print("=" * 80)

    if fill.execution.side == 'BOT':open_orders = ib.openTrades()

        symbol = fill.contract.symbolfor trade in open_orders:

        if symbol not in bought:    order = trade.order

            bought[symbol] = []    contract = trade.contract

        bought[symbol].append(fill.execution.price)    status = trade.orderStatus.status

    print(f"{contract.symbol:8} | {order.action:4} {order.totalQuantity:4.0f} @ ${order.lmtPrice:7.2f} | {status}")

print(f"\nSymbols bought today: {len(bought)}")

print("\n🧪 Testing Profit Target Order Placement:")

all_trades = ib.trades()print("=" * 80)

sell_limits = []

# Test placing a profit target for UP (26 shares @ $1.47)

for trade in all_trades:test_symbol = "UP"

    if trade.order.action == 'SELL' and trade.order.orderType == 'LMT':test_quantity = 1  # Test with just 1 share

        if any(l.time.date() == today for l in trade.log if l.time):test_price = 1.50

            sell_limits.append(trade)

contract = Stock(test_symbol, 'SMART', 'USD')

print(f"SELL LIMIT orders (profit targets): {len(sell_limits)}")ib.qualifyContracts(contract)



if sell_limits:tp_order = LimitOrder('SELL', test_quantity, test_price)

    print("\n" + "="*80)tp_order.tif = 'GTC'

    for trade in sell_limits:tp_order.outsideRth = True

        symbol = trade.contract.symboltp_order.transmit = True

        limit = trade.order.lmtPrice

        status = trade.orderStatus.statusprint(f"\nPlacing test order: SELL {test_quantity} {test_symbol} @ ${test_price:.2f}")

        tp_trade = ib.placeOrder(contract, tp_order)

        if symbol in bought:ib.sleep(2)

            avg_buy = sum(bought[symbol]) / len(bought[symbol])

            pct = ((limit - avg_buy) / avg_buy) * 100print(f"Order status: {tp_trade.orderStatus.status}")

            print(f"\n{symbol}: TP ${limit:.2f} (+{pct:.2f}%) - {status}")print(f"Order log: {tp_trade.log}")

        else:

            print(f"\n{symbol}: TP ${limit:.2f} - {status}")if tp_trade.orderStatus.status in ['PreSubmitted', 'Submitted']:

else:    print("✅ Test order ACCEPTED")

    print("\n❌ NO PROFIT TARGET ORDERS!")elif tp_trade.orderStatus.status == 'Cancelled':

    print("Bot didn't place profit targets for entries")    print("❌ Test order CANCELLED")

    print(f"Reason: {tp_trade.orderStatus.whyHeld}")

print("\n" + "="*80)else:

ib.disconnect()    print(f"⚠️ Test order status: {tp_trade.orderStatus.status}")


# Cancel the test order
print("\nCancelling test order...")
ib.cancelOrder(tp_order)
ib.sleep(1)

ib.disconnect()
print("\n✅ Done")
