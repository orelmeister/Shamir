"""Complete IBKR trading report for today"""
from ib_insync import IB
import ib_insync.util as ib_util
from datetime import datetime
from collections import defaultdict

print("="*80)
print("IBKR TRADING REPORT - October 29, 2025")
print("="*80)

ib = IB()
ib_util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))

today = datetime.now().date()
all_fills = ib.fills()
today_fills = [f for f in all_fills if f.time.date() == today]

print(f"\nTotal fills: {len(today_fills)}\n")

if today_fills:
    by_symbol = defaultdict(list)
    for fill in today_fills:
        by_symbol[fill.contract.symbol].append(fill)
    
    print("="*80)
    print("TRADES BY SYMBOL")
    print("="*80)
    
    total_pnl = 0
    winners = 0
    losers = 0
    
    for symbol in sorted(by_symbol.keys()):
        fills = by_symbol[symbol]
        print(f"\n{symbol}:")
        
        buys = []
        sells = []
        
        for fill in fills:
            side = fill.execution.side
            qty = fill.execution.shares
            price = fill.execution.price
            time = fill.time.strftime("%H:%M:%S")
            comm = fill.commissionReport.commission if fill.commissionReport else 0
            
            if side == 'BOT':
                buys.append((qty, price, comm))
                print(f"  BUY:  {qty:3} @ ${price:7.2f} at {time} (comm ${comm:.2f})")
            else:
                sells.append((qty, price, comm))
                print(f"  SELL: {qty:3} @ ${price:7.2f} at {time} (comm ${comm:.2f})")
        
        if buys and sells:
            buy_cost = sum(q*p+c for q,p,c in buys)
            sell_proceeds = sum(q*p-c for q,p,c in sells)
            pnl = sell_proceeds - buy_cost
            pnl_pct = (pnl/buy_cost)*100 if buy_cost > 0 else 0
            total_pnl += pnl
            
            if pnl > 0:
                winners += 1
                print(f"  ✅ PROFIT: ${pnl:.2f} ({pnl_pct:+.2f}%)")
            else:
                losers += 1
                print(f"  ❌ LOSS: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        
        elif buys:
            cost = sum(q*p+c for q,p,c in buys)
            qty = sum(q for q,p,c in buys)
            print(f"  📊 OPEN: {qty} shares, ${cost:.2f}")
        
        elif sells:
            proceeds = sum(q*p-c for q,p,c in sells)
            print(f"  ⚠️  OLD POSITION: ${proceeds:.2f}")
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\nWinners: {winners}, Losers: {losers}")
    if winners + losers > 0:
        print(f"Win Rate: {winners/(winners+losers)*100:.1f}%")
    print(f"\n💰 Total P&L: ${total_pnl:.2f}")

print("\n" + "="*80)
positions = [p for p in ib.positions() if p.position > 0]
print(f"\nCurrent positions: {len(positions)}")
for p in positions:
    print(f"  {p.contract.symbol}: {int(p.position)} @ ${p.avgCost:.2f}")

ib.disconnect()
