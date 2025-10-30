#!/usr/bin/env python3
"""Check if IART has OCO brackets in IBKR."""

from ib_insync import *
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=98)
time.sleep(1)

# Get all open trades (which include the orders)
trades = ib.openTrades()
print(f"\n{'='*80}")
print(f"TOTAL OPEN ORDERS: {len(trades)}")
print(f"{'='*80}\n")

# Filter for IART
iart_trades = [t for t in trades if t.contract.symbol == 'IART']
print(f"IART Orders: {len(iart_trades)}")

for trade in iart_trades:
    order = trade.order
    # Extract price based on order type
    if order.orderType == 'LMT':
        price = order.lmtPrice if order.lmtPrice else 0
    elif order.orderType == 'STP':
        price = order.auxPrice if order.auxPrice else 0
    else:
        price = 0
    
    print(f"  {order.action} {order.totalQuantity} IART @ ${price:.2f} ({order.orderType})")
    print(f"    OCA Group: {order.ocaGroup if order.ocaGroup else 'None'}")
    print(f"    Order ID: {order.orderId}")
    print(f"    Status: {trade.orderStatus.status}")
    print()

# Get current positions
positions = ib.positions()
iart_pos = [p for p in positions if p.contract.symbol == 'IART']
if iart_pos:
    print(f"\nIART Position: {iart_pos[0].position} shares @ ${iart_pos[0].avgCost:.2f}")

ib.disconnect()
