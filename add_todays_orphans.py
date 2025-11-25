#!/usr/bin/env python3
"""Add today's orphaned MOO positions (KURA, KSS) to database"""

from observability import get_database
from datetime import datetime, timezone

db = get_database()

# Today's orphaned MOO orders from logs
orphaned_positions = [
    {
        'symbol': 'KURA',
        'quantity': 28,
        'price': 11.87,  # From IBKR actual fill
        'timestamp': '2025-11-25T14:30:00',  # 9:30 AM ET = 6:30 AM PT
    },
    {
        'symbol': 'KSS',
        'quantity': 16,
        'price': 19.56,  # From IBKR actual fill
        'timestamp': '2025-11-25T14:30:00',
    },
    {
        'symbol': 'SEMR',
        'quantity': 28,  # Additional shares from today (already had 28 from yesterday)
        'price': 11.82,
        'timestamp': '2025-11-25T14:30:00',
    }
]

print("=" * 70)
print("ADDING ORPHANED MOO POSITIONS TO DATABASE")
print("=" * 70)

for pos in orphaned_positions:
    print(f"\n✅ Adding {pos['symbol']} ({pos['quantity']} shares @ ${pos['price']})")
    
    db.log_trade({
        'symbol': pos['symbol'],
        'action': 'BUY',
        'quantity': pos['quantity'],
        'price': pos['price'],
        'timestamp': pos['timestamp'],
        'agent_name': 'day_trader',
        'reason': 'MOO order executed (retroactive logging)',
        'metadata': {
            'retroactive': True,
            'date': '2025-11-25',
            'entry_type': 'MOO',
            'note': 'Added retroactively - Phase 2 connection failed'
        }
    })

print("\n" + "=" * 70)
print("DATABASE UPDATED SUCCESSFULLY!")
print("=" * 70)

# Verify
print("\nDay trader positions in database:")
trades = db.get_trades_by_agent('day_trader')
print(f"Total trades: {len(trades)}")
print(f"Total buys: {len([t for t in trades if t[3] == 'BUY'])}")
print(f"Total sells: {len([t for t in trades if t[3] == 'SELL'])}")
