"""Comprehensive P&L analysis of all trades today"""
from observability import get_database
from collections import defaultdict

db = get_database()
trades = db.get_trades_by_date('2025-10-29')

print("="*80)
print("TRADING SUMMARY - October 29, 2025")
print("="*80)
print(f"\nTotal trades: {len(trades)}\n")

by_symbol = defaultdict(list)
for t in trades:
    by_symbol[t.get('symbol', 'UNKNOWN')].append(t)

print("="*80)
print("PROFIT/LOSS BY SYMBOL")
print("="*80)

total_pnl = 0
winners = 0
losers = 0

for symbol in sorted(by_symbol.keys()):
    symbol_trades = by_symbol[symbol]
    buys = [t for t in symbol_trades if t.get('action') == 'BUY']
    sells = [t for t in symbol_trades if t.get('action') == 'SELL']
    
    print(f"\n{symbol}: {len(buys)} BUY, {len(sells)} SELL")
    
    buy_cost = 0
    buy_shares = 0
    for buy in buys:
        qty = buy.get('quantity', 0)
        price = buy.get('price', 0)
        buy_shares += qty
        buy_cost += qty * price
        time = buy.get('timestamp', '')[:19]
        print(f"  BUY:  {qty} @ ${price:.2f} = ${qty*price:.2f} at {time}")
    
    sell_proceeds = 0
    sell_shares = 0
    for sell in sells:
        qty = sell.get('quantity', 0)
        price = sell.get('price', 0)
        sell_shares += qty
        sell_proceeds += qty * price
        time = sell.get('timestamp', '')[:19]
        print(f"  SELL: {qty} @ ${price:.2f} = ${qty*price:.2f} at {time}")
    
    if sell_shares > 0:
        pnl = sell_proceeds - (buy_cost * sell_shares / buy_shares if buy_shares > 0 else 0)
        pnl_pct = (pnl / (buy_cost * sell_shares / buy_shares)) * 100 if buy_cost > 0 else 0
        total_pnl += pnl
        
        if pnl > 0:
            winners += 1
            print(f"  ✅ PROFIT: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        elif pnl < 0:
            losers += 1
            print(f"  ❌ LOSS: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        
        if buy_shares > sell_shares:
            print(f"  ⚠️  STILL HOLDING: {buy_shares - sell_shares} shares")
    else:
        print(f"  📊 OPEN: {buy_shares} shares, cost ${buy_cost:.2f}")

print("\n" + "="*80)
print("DAILY SUMMARY")
print("="*80)
print(f"\nWinners: {winners}")
print(f"Losers: {losers}")
print(f"Win Rate: {winners/(winners+losers)*100:.1f}%" if (winners+losers) > 0 else "N/A")
print(f"\n💰 Total P&L: ${total_pnl:.2f}")

if total_pnl > 0:
    print(f"\n✅ PROFITABLE DAY: +${total_pnl:.2f}")
elif total_pnl < 0:
    print(f"\n❌ LOSING DAY: ${total_pnl:.2f}")

print("\n" + "="*80)
active = db.get_active_positions()
print(f"\nOpen positions: {len(active)}")
for p in active:
    print(f"  {p['symbol']}: {p['quantity']} @ ${p['entry_price']:.2f}")

print("="*80)
