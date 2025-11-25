#!/usr/bin/env python3
"""
Retroactively add orphaned MOO positions to database
These positions were created by MOO orders but never logged due to connection failure
"""

from observability import get_database
from datetime import datetime

print("=" * 70)
print("ADDING ORPHANED POSITIONS TO DATABASE")
print("=" * 70)

db = get_database()

# Positions from IBKR fills at 2025-11-24 14:30 UTC (6:30 AM PT)
orphaned_positions = [
    {
        'symbol': 'SEMR',
        'quantity': 28,
        'entry_price': 11.82,  # From IBKR position data
        'timestamp': '2025-11-24T14:30:01',  # UTC time from fills
        'reason': 'MOO order - Adobe acquisition catalyst'
    },
    {
        'symbol': 'ONDS',
        'quantity': 48,
        'entry_price': 6.80,  # From IBKR position data
        'timestamp': '2025-11-24T14:30:00',  # UTC time from fills
        'reason': 'MOO order - Senate investigation catalyst'
    },
    {
        'symbol': 'NESR',
        'quantity': 23,
        'entry_price': 13.78,  # From IBKR position data
        'timestamp': '2025-11-24T14:30:01',  # UTC time from fills
        'reason': 'MOO order - Q3 earnings beat catalyst'
    }
]

print("\nPositions to add:")
print("-" * 70)
total_value = 0
for pos in orphaned_positions:
    value = pos['quantity'] * pos['entry_price']
    total_value += value
    print(f"{pos['symbol']:6} {pos['quantity']:3} shares @ ${pos['entry_price']:7.2f} = ${value:8.2f}")
    print(f"  Time: {pos['timestamp']} | Reason: {pos['reason']}")

print(f"\nTotal value: ${total_value:.2f}")
print(f"Within $1,000 budget: {'✅ YES' if total_value <= 1000 else '❌ NO'}")

print("\n" + "-" * 70)
response = input("Add these positions to database as 'day_trader' agent? (yes/no): ")

if response.lower() != 'yes':
    print("Cancelled. Positions NOT added.")
    exit(0)

# Add positions to database
print("\nAdding positions...")
for pos in orphaned_positions:
    try:
        db.log_trade({
            'symbol': pos['symbol'],
            'action': 'BUY',
            'quantity': pos['quantity'],
            'price': pos['entry_price'],
            'timestamp': pos['timestamp'],
            'reason': pos['reason'],
            'agent_name': 'day_trader',
            'metadata': {
                'entry_type': 'MOO',
                'retroactive': True,
                'note': 'Added retroactively after connection failure on 2025-11-24'
            }
        })
        print(f"  ✅ Added {pos['symbol']}")
    except Exception as e:
        print(f"  ❌ Error adding {pos['symbol']}: {e}")

print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

# Verify positions were added
dt_positions = db.get_positions_by_agent('day_trader')
print(f"\nDay trader positions in database: {len(dt_positions)}")
for p in dt_positions:
    print(f"  {p['symbol']}: {p['quantity']} shares @ ${p['entry_price']:.2f}")

print("\n✅ Database updated successfully!")
print("\nNOTE: These positions are now tracked and will be managed by the day trader.")
print("They will be exited at 4:00 PM today or when stop-loss/take-profit triggers.")
