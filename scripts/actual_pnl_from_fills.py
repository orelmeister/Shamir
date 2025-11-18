#!/usr/bin/env python3
"""Calculate actual P&L from IBKR fills."""

from ib_insync import *
from collections import defaultdict

# Connect to IBKR
ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)
ib.sleep(1)

# Get today's fills
fills = ib.fills()
today_fills = [f for f in fills if '2025-10-30' in str(f.time)]

buys = [f for f in today_fills if f.execution.side == 'BOT']
sells = [f for f in today_fills if f.execution.side == 'SLD']

print("\n" + "="*100)
print("TODAY'S ACTUAL TRADING - October 30, 2025")
print("="*100)
print(f"\nTotal Executions: {len(today_fills)}")
print(f"BUY executions: {len(buys)}")
print(f"SELL executions: {len(sells)}")

# Match buys and sells
positions = defaultdict(lambda: {'buys': [], 'sells': []})

for buy in buys:
    positions[buy.contract.symbol]['buys'].append({
        'shares': buy.execution.shares,
        'price': buy.execution.avgPrice,
        'value': buy.execution.shares * buy.execution.avgPrice
    })

for sell in sells:
    positions[sell.contract.symbol]['sells'].append({
        'shares': sell.execution.shares,
        'price': sell.execution.avgPrice,
        'value': sell.execution.shares * sell.execution.avgPrice
    })

print("\n" + "="*100)
print(f"{'SYMBOL':<8} {'BUY QTY':<9} {'BUY AVG':<10} {'SELL QTY':<9} {'SELL AVG':<10} {'COST':<12} {'PROCEEDS':<12} {'P&L $':<10} {'P&L %'}")
print("-"*100)

total_cost = 0
total_proceeds = 0
total_pnl = 0
positions_traded = 0

for symbol in sorted(positions.keys()):
    pos = positions[symbol]
    
    if pos['buys'] and pos['sells']:
        positions_traded += 1
        
        # Calculate totals
        buy_shares = sum(b['shares'] for b in pos['buys'])
        buy_value = sum(b['value'] for b in pos['buys'])
        buy_avg = buy_value / buy_shares if buy_shares > 0 else 0
        
        sell_shares = sum(s['shares'] for s in pos['sells'])
        sell_value = sum(s['value'] for s in pos['sells'])
        sell_avg = sell_value / sell_shares if sell_shares > 0 else 0
        
        pnl = sell_value - buy_value
        pnl_pct = (pnl / buy_value * 100) if buy_value > 0 else 0
        
        total_cost += buy_value
        total_proceeds += sell_value
        total_pnl += pnl
        
        print(f"{symbol:<8} {buy_shares:<9.0f} ${buy_avg:<9.4f} {sell_shares:<9.0f} ${sell_avg:<9.4f} ${buy_value:<11.2f} ${sell_value:<11.2f} ${pnl:<9.2f} {pnl_pct:>+6.2f}%")

print("-"*100)
print(f"{'TOTALS':<8} {'--':<9} {'--':<10} {'--':<9} {'--':<10} ${total_cost:<11.2f} ${total_proceeds:<11.2f} ${total_pnl:<9.2f} {(total_pnl/total_cost*100) if total_cost > 0 else 0:>+6.2f}%")

# Calculate with commissions
commissions = (len(buys) + len(sells)) * 0.50  # $0.50 per side
net_pnl = total_pnl - commissions
net_pnl_pct = (net_pnl / total_cost * 100) if total_cost > 0 else 0

print("\n" + "="*100)
print("FINANCIAL SUMMARY")
print("="*100)
print(f"Positions traded:              {positions_traded}")
print(f"Total capital deployed:        ${total_cost:>10.2f}")
print(f"Total proceeds:                ${total_proceeds:>10.2f}")
print(f"Gross P&L:                     ${total_pnl:>10.2f}  ({(total_pnl/total_cost*100) if total_cost > 0 else 0:>+6.2f}%)")
print(f"Commission cost:               -${commissions:>9.2f}")
print(f"{'─'*60}")
print(f"NET P&L (after commissions):   ${net_pnl:>10.2f}  ({net_pnl_pct:>+6.2f}%)")

print("\n" + "="*100 + "\n")

ib.disconnect()
