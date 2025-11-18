from ib_insync import *
from datetime import datetime
from collections import defaultdict

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=97)
ib.reqMarketDataType(3)

import time
time.sleep(2)

# Get all fills
fills = ib.fills()
today = datetime.now().strftime('%Y%m%d')
today_fills = [f for f in fills if f.time.strftime('%Y%m%d') == today]

print("\n" + "="*80)
print(f"ALL TRADES TODAY - {datetime.now().strftime('%B %d, %Y')}")
print("="*80)
print(f"\nTotal executions today: {len(today_fills)}\n")

if not today_fills:
    print("No trades executed today yet.")
    ib.disconnect()
    exit()

# Sort by time
today_fills = sorted(today_fills, key=lambda x: x.time)

print("="*80)
print("CHRONOLOGICAL TRADE LOG")
print("="*80)
for f in today_fills:
    time_str = f.time.strftime('%H:%M:%S')
    symbol = f.contract.symbol
    side = f.execution.side
    shares = int(f.execution.shares)
    price = f.execution.avgPrice
    value = shares * price
    print(f"{time_str} | {side:4} | {symbol:6} | {shares:4} @ ${price:.2f} = ${value:,.2f}")

# Calculate P&L by symbol
trades = defaultdict(lambda: {'buys': [], 'sells': []})

for f in today_fills:
    symbol = f.contract.symbol
    shares = int(f.execution.shares)
    price = f.execution.avgPrice
    side = f.execution.side
    
    if side == 'BOT':
        trades[symbol]['buys'].append((shares, price))
    else:  # SLD
        trades[symbol]['sells'].append((shares, price))

print("\n" + "="*80)
print("P&L BY SYMBOL")
print("="*80)

total_pnl = 0
completed_trades = []
open_positions = []

for symbol in sorted(trades.keys()):
    buys = trades[symbol]['buys']
    sells = trades[symbol]['sells']
    
    total_bought = sum([shares for shares, price in buys])
    total_sold = sum([shares for shares, price in sells])
    
    total_buy_cost = sum([shares * price for shares, price in buys])
    total_sell_revenue = sum([shares * price for shares, price in sells])
    
    print(f"\n{symbol}:")
    print(f"  Bought: {total_bought} shares for ${total_buy_cost:.2f}")
    if buys:
        avg_buy = total_buy_cost / total_bought
        print(f"    Avg: ${avg_buy:.2f}")
    
    print(f"  Sold: {total_sold} shares for ${total_sell_revenue:.2f}")
    if sells:
        avg_sell = total_sell_revenue / total_sold
        print(f"    Avg: ${avg_sell:.2f}")
    
    if total_sold > 0:
        # Calculate P&L on sold shares
        shares_closed = min(total_bought, total_sold)
        if shares_closed > 0:
            avg_buy_price = total_buy_cost / total_bought
            avg_sell_price = total_sell_revenue / total_sold
            pnl = (avg_sell_price - avg_buy_price) * shares_closed
            pnl_pct = (pnl / (avg_buy_price * shares_closed)) * 100
            
            print(f"  Realized P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
            total_pnl += pnl
            completed_trades.append((symbol, pnl))
    
    # Check for open positions
    net_position = total_bought - total_sold
    if net_position > 0:
        avg_cost = total_buy_cost / total_bought
        open_value = net_position * avg_cost
        print(f"  OPEN: {net_position} shares remaining @ ${avg_cost:.2f} avg = ${open_value:.2f}")
        open_positions.append((symbol, net_position, avg_cost))

print("\n" + "="*80)
print("COMMISSIONS BREAKDOWN")
print("="*80)

total_commission = 0
print("\nCommissions by trade:")
for f in today_fills:
    comm = f.commissionReport.commission if f.commissionReport else 0
    total_commission += comm
    if comm != 0:
        time_str = f.time.strftime('%H:%M:%S')
        symbol = f.contract.symbol
        side = f.execution.side
        shares = int(f.execution.shares)
        print(f"{time_str} | {side:4} | {symbol:6} | {shares:4} shares = ${comm:.4f}")

print(f"\n{'='*80}")
print(f"TOTAL COMMISSIONS: ${total_commission:.2f}")
print(f"Average per execution: ${total_commission/len(today_fills):.4f}")
print(f"{'='*80}")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)

if completed_trades:
    print("\nCompleted Trades (Realized P&L):")
    for symbol, pnl in completed_trades:
        color = "profit" if pnl > 0 else "loss"
        sign = "+" if pnl > 0 else ""
        print(f"  {symbol}: {sign}${pnl:.2f}")
    
    print(f"\n{'='*80}")
    print(f"TOTAL REALIZED P&L: ${total_pnl:.2f}")
    print(f"{'='*80}")
else:
    print("\nNo completed trades (all positions still open)")
    print(f"REALIZED P&L: $0.00")

if open_positions:
    print(f"\nOpen Positions from Today:")
    for symbol, shares, avg_cost in open_positions:
        print(f"  {symbol}: {shares} shares @ ${avg_cost:.2f}")

ib.disconnect()
