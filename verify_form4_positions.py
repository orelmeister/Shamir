"""Quick verification that AUPH and KALV are now tracked correctly"""
import sqlite3
import os
from datetime import datetime, timezone

parent_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(parent_dir, "databases", "trading_history.db")

print("\n" + "="*80)
print("VERIFICATION: FORM 4 STRATEGY POSITIONS")
print("="*80 + "\n")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all form4_strategy positions
cursor.execute('''
    SELECT symbol, action, timestamp, price, quantity, reason
    FROM trades 
    WHERE agent_name = 'form4_strategy'
    AND action = 'BUY'
    ORDER BY timestamp
''')

rows = cursor.fetchall()

print(f"Found {len(rows)} positions tracked by form4_strategy:\n")

now = datetime.now(timezone.utc)

for row in rows:
    symbol, action, timestamp, price, qty, reason = row
    
    # Parse timestamp
    entry_date = datetime.fromisoformat(timestamp.replace(' ', 'T'))
    if entry_date.tzinfo is None:
        entry_date = entry_date.replace(tzinfo=timezone.utc)
    
    days_held = (now - entry_date).days
    
    print(f"{symbol}: {qty} shares @ ${price:.2f}")
    print(f"  Entry: {entry_date.strftime('%Y-%m-%d')}")
    print(f"  Days held: {days_held}")
    print(f"  Reason: {reason[:60]}...")
    print()

conn.close()

print("="*80)
print(f"[RESULT] {len(rows)} positions ready for Form 4 exit manager")
print("="*80)
