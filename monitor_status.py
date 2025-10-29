"""Quick status monitor for trading bots"""
from observability import get_database
from ib_insync import IB

print("\n" + "="*80)
print("TRADING BOT STATUS MONITOR")
print("="*80)

# Check database
db = get_database()
active_positions = db.get_active_positions()

print(f"\nDatabase Status:")
print(f"  Active day trading positions: {len(active_positions)}")
if active_positions:
    for pos in active_positions:
        print(f"    {pos['symbol']}: {pos['quantity']} shares @ ${pos['entry_price']:.2f}")
        print(f"      TP: ${pos.get('profit_target', 'N/A')}, SL: ${pos.get('stop_loss', 'N/A')}")
        print(f"      Agent: {pos['agent_name']}")
else:
    print("    No day trading positions")

# Check IBKR positions
try:
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=98, timeout=5)
    
    ibkr_positions = ib.positions()
    long_positions = [p for p in ibkr_positions if p.position > 0]
    
    print(f"\nIBKR Account Status:")
    print(f"  Total positions: {len(long_positions)}")
    
    # Separate day trading from long-term
    db_symbols = {pos['symbol'] for pos in active_positions}
    long_term = [p for p in long_positions if p.contract.symbol not in db_symbols]
    day_trade = [p for p in long_positions if p.contract.symbol in db_symbols]
    
    if long_term:
        print(f"\n  PROTECTED Long-term positions ({len(long_term)}):")
        for p in long_term:
            print(f"    {p.contract.symbol}: {int(p.position)} shares @ ${p.avgCost:.2f}")
    
    if day_trade:
        print(f"\n  Day trading positions ({len(day_trade)}):")
        for p in day_trade:
            print(f"    {p.contract.symbol}: {int(p.position)} shares @ ${p.avgCost:.2f}")
    
    # Check open orders
    open_orders = ib.openTrades()
    if open_orders:
        print(f"\n  Open orders: {len(open_orders)}")
        for trade in open_orders[:5]:
            print(f"    {trade.contract.symbol}: {trade.order.action} {trade.order.totalQuantity} @ {trade.order.lmtPrice}")
    
    ib.disconnect()
    
except Exception as e:
    print(f"\nIBKR Connection Error: {e}")

print("\n" + "="*80)
