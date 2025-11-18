#!/usr/bin/env python3
"""Quick P&L check using account values."""

from ib_insync import *
from observability import get_database

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)
ib.sleep(2)

# Get account summary
account_values = ib.accountSummary()
unrealized_pnl = 0
net_liquidation = 0

for av in account_values:
    if av.tag == 'UnrealizedPnL':
        unrealized_pnl = float(av.value)
    elif av.tag == 'NetLiquidation':
        net_liquidation = float(av.value)

# Get today's trades
db = get_database()
trades = db.get_trades_by_date('2025-10-30')
buy_trades = [t for t in trades if t['action'] == 'BUY']

print("\n" + "="*80)
print("TODAY'S TRADING SUMMARY - October 30, 2025")
print("="*80)

print(f"\nPOSITIONS OPENED TODAY: {len(buy_trades)} trades")
print("\nTrades:")
for i, trade in enumerate(buy_trades, 1):
    cost = trade['quantity'] * trade['price']
    print(f"  {i:2}. {trade['symbol']:<8} {trade['quantity']:>3} shares @ ${trade['price']:.4f} = ${cost:>8.2f}")

total_cost = sum(t['quantity'] * t['price'] for t in buy_trades)
print(f"\n{'TOTAL COST BASIS:':<30} ${total_cost:>10.2f}")

# Calculate commissions
commissions = len(buy_trades) * 1.00
print(f"{'COMMISSION COST:':<30} -${commissions:>9.2f} ({len(buy_trades)} trades × $1.00)")

# Account P&L
print(f"\n{'ACCOUNT UNREALIZED P&L:':<30} ${unrealized_pnl:>10.2f}")
print(f"{'NET LIQUIDATION VALUE:':<30} ${net_liquidation:>10.2f}")

# Net after commissions
net_pnl = unrealized_pnl - commissions
net_pnl_pct = (net_pnl / total_cost * 100) if total_cost > 0 else 0

print("\n" + "="*80)
print("BOTTOM LINE")
print("="*80)
print(f"{'Unrealized P&L (gross):':<30} ${unrealized_pnl:>10.2f}")
print(f"{'Commission costs:':<30} -${commissions:>9.2f}")
print(f"{'─'*80}")
print(f"{'NET P&L (after commissions):':<30} ${net_pnl:>10.2f}  ({net_pnl_pct:>+6.2f}%)")

# Breakeven analysis
breakeven_pct = (commissions / total_cost) * 100
print(f"\n{'Breakeven required:':<30} +{breakeven_pct:.2f}%")
print(f"{'Current performance:':<30} {net_pnl_pct:+.2f}%")

if net_pnl >= 0:
    print(f"\n✅ PROFITABLE - ${net_pnl:.2f} above breakeven")
else:
    print(f"\n❌ UNDERWATER - ${abs(net_pnl):.2f} below breakeven")

# Potential analysis
potential_gross = total_cost * 0.04
potential_net = potential_gross - commissions
potential_net_pct = (potential_net / total_cost) * 100

print("\n" + "="*80)
print("POTENTIAL ANALYSIS")
print("="*80)
print(f"If all 14 positions hit +4% target:")
print(f"  Potential Gross Profit:       ${potential_gross:>10.2f}  (+4.00%)")
print(f"  After commissions:            ${potential_net:>10.2f}  ({potential_net_pct:>+6.2f}%)")

print("="*80 + "\n")

ib.disconnect()
