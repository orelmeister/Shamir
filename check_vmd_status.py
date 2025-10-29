"""Check if VMD is in the database and IBKR positions"""
from observability import get_database
from ib_insync import IB
import ib_insync.util as ib_util

# Check database
print("\n" + "="*80)
print("DATABASE CHECK")
print("="*80)

db = get_database()

print("\n=== ACTIVE POSITIONS IN DATABASE ===")
active = db.get_active_positions()
print(f"Count: {len(active)}")
if active:
    for pos in active:
        print(f"  {pos['symbol']}: {pos['quantity']} shares @ ${pos['entry_price']:.2f}")
else:
    print("  (None)")

print("\n=== CLOSED POSITIONS TODAY ===")
closed = db.get_closed_today()
print(f"Count: {len(closed)}")
if closed:
    for pos in closed:
        print(f"  {pos['symbol']}: closed at {pos.get('timestamp', 'unknown')} ({pos.get('exit_reason', 'unknown')})")
else:
    print("  (None)")

print("\n=== ALL TRADES TODAY (2025-10-29) ===")
trades = db.get_trades_by_date('2025-10-29')
print(f"Total trades: {len(trades)}")
if trades:
    for t in trades[-20:]:  # Last 20 trades
        action = t.get('action', 'UNKNOWN')
        symbol = t.get('symbol', 'UNKNOWN')
        quantity = t.get('quantity', 0)
        price = t.get('price', 0)
        timestamp = t.get('timestamp', 'unknown')
        print(f"  {timestamp}: {action} {symbol} - {quantity} shares @ ${price:.2f}")
else:
    print("  (No trades found)")

# Check IBKR
print("\n" + "="*80)
print("IBKR POSITIONS CHECK")
print("="*80)

ib = IB()
try:
    ib_util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))
    positions = ib.positions()
    print(f"\nTotal IBKR positions: {len(positions)}")
    for pos in positions:
        if pos.position > 0:
            print(f"  {pos.contract.symbol}: {int(pos.position)} shares @ ${pos.avgCost:.2f}")
    
    # Check specifically for VMD
    vmd_positions = [p for p in positions if p.contract.symbol == 'VMD' and p.position > 0]
    if vmd_positions:
        print(f"\n✓ VMD FOUND IN IBKR:")
        for p in vmd_positions:
            print(f"  Quantity: {int(p.position)}")
            print(f"  Avg Cost: ${p.avgCost:.2f}")
    else:
        print("\n✗ VMD NOT FOUND IN IBKR")
    
    ib.disconnect()
except Exception as e:
    print(f"Error connecting to IBKR: {e}")

print("\n" + "="*80)
