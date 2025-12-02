#!/usr/bin/env python3
"""Add Form4 orphaned positions to database - Dec 1, 2025"""

from observability import get_database
from datetime import datetime, timezone
import json

db = get_database()

# Form4 positions from IBKR - entry dates ESTIMATED
orphaned_positions = [
    {
        'symbol': 'KSS',
        'quantity': 16,
        'price': 19.562525,
        'timestamp': '2025-11-08T09:30:00',  # Estimated from approved_positions
    },
    {
        'symbol': 'ONB',
        'quantity': 49,
        'price': 20.0404306,
        'timestamp': '2025-11-08T09:30:00',  # Estimated
    },
    {
        'symbol': 'ONDS',
        'quantity': 48,
        'price': 6.80085625,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'BLND',
        'quantity': 100,
        'price': 3.089322,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'DAO',
        'quantity': 2,
        'price': 9.4344,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'NESR',
        'quantity': 23,
        'price': 13.7835,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'OPK',
        'quantity': 195,
        'price': 1.30015025,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'SEMR',
        'quantity': 57,
        'price': 11.8226386,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'KURA',
        'quantity': 28,
        'price': 11.8657357,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
    {
        'symbol': 'SEM',
        'quantity': 1,
        'price': 15.6964,
        'timestamp': '2025-11-15T09:30:00',  # Estimated
    },
]

print("=" * 80)
print("ADDING FORM4 ORPHANED POSITIONS TO DATABASE")
print("=" * 80)

added_count = 0
for pos in orphaned_positions:
    entry_dt = datetime.fromisoformat(pos['timestamp'])
    days_held = (datetime.now() - entry_dt).days
    
    print(f"\n✅ Adding {pos['symbol']} ({pos['quantity']} shares @ ${pos['price']:.4f}) - {days_held} days ago")
    
    # Log to trades table
    db.log_trade({
        'symbol': pos['symbol'],
        'action': 'BUY',
        'quantity': pos['quantity'],
        'price': pos['price'],
        'timestamp': pos['timestamp'],
        'agent_name': 'form4_strategy',
        'reason': 'Form4 insider trading signal (retroactive logging)',
        'metadata': {
            'retroactive': True,
            'note': 'Added retroactively - predates autonomous tracking',
            'entry_date_estimated': True
        }
    })
    
    # Also add to active_positions table for tracking
    try:
        import sqlite3
        conn = sqlite3.connect('databases/trading_history.db')
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO active_positions 
            (symbol, quantity, entry_price, entry_timestamp, agent_name, status, last_updated, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pos['symbol'],
            pos['quantity'],
            pos['price'],
            pos['timestamp'],
            'form4_strategy',
            'OPEN',
            datetime.now().isoformat(),
            json.dumps({'retroactive': True, 'entry_date_estimated': True})
        ))
        conn.commit()
        conn.close()
        added_count += 1
    except Exception as e:
        print(f"  ⚠️  Warning: {e}")

print("\n" + "=" * 80)
print("DATABASE UPDATED SUCCESSFULLY!")
print("=" * 80)

# Verify
print("\nForm4 active positions in database:")
form4_positions = db.get_active_positions(agent_name='form4_strategy')
print(f"Active positions: {len(form4_positions)}")
for p in form4_positions:
    entry_dt = datetime.fromisoformat(p['entry_timestamp'])
    days_held = (datetime.now() - entry_dt).days
    print(f"  {p['symbol']}: {p['quantity']} shares @ ${p['entry_price']:.2f} ({days_held} days held)")

print(f"\n✅ Successfully added {added_count}/{len(orphaned_positions)} positions!")
print("\n✅ Run exit manager now to see accurate 'Days Held' values!")
