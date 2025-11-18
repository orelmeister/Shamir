#!/usr/bin/env python3
"""Analyze today's trading P&L including commissions."""

from ib_insync import *
import time
from observability import get_database
from datetime import datetime

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)
time.sleep(1)

# Get today's trades from database
db = get_database()
trades = db.get_trades_by_date('2025-10-30')

# Get current positions
positions = ib.positions()
position_dict = {p.contract.symbol: p for p in positions}

print("\n" + "="*100)
print("TODAY'S TRADING SUMMARY - October 30, 2025")
print("="*100)

# Group trades by symbol
buy_trades = {}
for trade in trades:
    if trade['action'] == 'BUY':
        symbol = trade['symbol']
        if symbol not in buy_trades:
            buy_trades[symbol] = {
                'quantity': trade['quantity'],
                'entry_price': trade['price'],
                'entry_time': trade['timestamp'],
                'cost_basis': trade['quantity'] * trade['price']
            }

print(f"\nTOTAL POSITIONS OPENED: {len(buy_trades)}")
print(f"COMMISSION COST: ${len(buy_trades) * 1.00:.2f} (${1.00} per trade)")

# Calculate P&L for each position
total_cost_basis = 0
total_current_value = 0
total_pnl = 0
still_open = []
closed_positions = []

print("\n" + "-"*100)
print(f"{'SYMBOL':<8} {'QTY':<6} {'ENTRY $':<10} {'CURRENT $':<12} {'COST BASIS':<12} {'CURRENT VALUE':<15} {'P&L $':<10} {'P&L %':<8} {'STATUS'}")
print("-"*100)

for symbol, trade_info in sorted(buy_trades.items()):
    qty = trade_info['quantity']
    entry = trade_info['entry_price']
    cost_basis = trade_info['cost_basis']
    
    total_cost_basis += cost_basis
    
    # Check if still in positions
    if symbol in position_dict:
        pos = position_dict[symbol]
        current_price = pos.marketPrice
        current_value = pos.marketValue
        pnl = pos.unrealizedPNL
        pnl_pct = (pnl / cost_basis) * 100 if cost_basis > 0 else 0
        status = "OPEN"
        still_open.append(symbol)
        total_current_value += current_value
        total_pnl += pnl
    else:
        # Position was closed - assume liquidated at entry (0% gain for now)
        current_price = entry
        current_value = cost_basis
        pnl = 0.0
        pnl_pct = 0.0
        status = "CLOSED"
        closed_positions.append(symbol)
        total_current_value += current_value
    
    print(f"{symbol:<8} {qty:<6} ${entry:<9.4f} ${current_price:<11.4f} ${cost_basis:<11.2f} ${current_value:<14.2f} ${pnl:<9.2f} {pnl_pct:>6.2f}%  {status}")

print("-"*100)

# Calculate commission impact
total_commission = len(buy_trades) * 1.00
gross_pnl = total_pnl
net_pnl = gross_pnl - total_commission
net_pnl_pct = (net_pnl / total_cost_basis) * 100 if total_cost_basis > 0 else 0

print(f"\n{'TOTALS:':<8} {'--':<6} {'--':<10} {'--':<12} ${total_cost_basis:<11.2f} ${total_current_value:<14.2f} ${gross_pnl:<9.2f}")

print("\n" + "="*100)
print("FINANCIAL SUMMARY")
print("="*100)
print(f"Total Capital Deployed:        ${total_cost_basis:>10.2f}")
print(f"Current Portfolio Value:       ${total_current_value:>10.2f}")
print(f"Gross P&L (before commissions): ${gross_pnl:>9.2f}  ({(gross_pnl/total_cost_basis)*100:>6.2f}%)")
print(f"Commission Cost:               -${total_commission:>9.2f}")
print(f"{'─'*50}")
print(f"NET P&L (after commissions):    ${net_pnl:>9.2f}  ({net_pnl_pct:>6.2f}%)")

print("\n" + "="*100)
print("POSITION STATUS")
print("="*100)
print(f"Still Open:  {len(still_open)} positions - {', '.join(still_open) if still_open else 'None'}")
print(f"Closed:      {len(closed_positions)} positions - {', '.join(closed_positions) if closed_positions else 'None'}")

print("\n" + "="*100)
print("POTENTIAL ANALYSIS (If all hit +4% target)")
print("="*100)
potential_gross = total_cost_basis * 0.04
potential_net = potential_gross - total_commission
potential_net_pct = (potential_net / total_cost_basis) * 100

print(f"Potential Gross Profit:        ${potential_gross:>10.2f}  (+4.00%)")
print(f"Commission Cost:               -${total_commission:>9.2f}")
print(f"Potential Net Profit:           ${potential_net:>9.2f}  ({potential_net_pct:>6.2f}%)")

print("\n" + "="*100)
print("BREAKEVEN ANALYSIS")
print("="*100)
breakeven_pct = (total_commission / total_cost_basis) * 100
print(f"Breakeven Required:            +{breakeven_pct:.2f}% (to cover commissions)")
print(f"Current Performance:            {net_pnl_pct:+.2f}%")
if net_pnl >= 0:
    print(f"✅ ABOVE BREAKEVEN by ${net_pnl:.2f}")
else:
    print(f"❌ BELOW BREAKEVEN by ${abs(net_pnl):.2f}")

print("\n" + "="*100)

ib.disconnect()
