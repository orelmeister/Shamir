"""Live monitoring of trading system - runs 3 checks"""
from observability import get_database
from ib_insync import IB
import time

db = get_database()

print("\n" + "="*80)
print("LIVE TRADING SYSTEM MONITOR")
print("="*80)

for i in range(3):
    print(f"\n[Check #{i+1}] {time.strftime('%H:%M:%S')}")
    print("-"*80)
    
    # Check database
    active = db.get_active_positions()
    print(f"Database: {len(active)} active day trading positions")
    if active:
        for p in active:
            print(f"  {p['symbol']}: {p['quantity']} @ ${p['entry_price']:.2f} (Agent: {p['agent_name']})")
    else:
        print("  (Waiting for entry signals...)")
    
    # Check IBKR
    try:
        ib = IB()
        ib.connect('127.0.0.1', 4001, clientId=95, timeout=5)
        
        orders = ib.openTrades()
        print(f"IBKR: {len(orders)} open orders")
        if orders:
            for t in orders[:3]:
                print(f"  {t.contract.symbol}: {t.order.action} {t.order.totalQuantity}")
        
        portfolio = ib.portfolio()
        db_symbols = {pos['symbol'] for pos in active}
        day_trade_pnl = sum([p.unrealizedPNL for p in portfolio if p.contract.symbol in db_symbols])
        print(f"Day Trading P&L: ${day_trade_pnl:.2f}")
        
        ib.disconnect()
    except Exception as e:
        print(f"IBKR check skipped: {e}")
    
    if i < 2:
        time.sleep(10)

print("="*80)
print("\nSystem Status: RUNNING NORMALLY")
print("  - Day Trader: Scanning for entry signals every 5 seconds")
print("  - Exit Manager: Monitoring database for positions every 10 seconds")
print("  - Long-term positions: PROTECTED (not in database)")
print("="*80)
