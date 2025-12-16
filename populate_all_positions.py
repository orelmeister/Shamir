"""
Populate database with ALL current Form 4 positions from the script output
Based on the 05_form4_strategy.py output showing these positions:

Ready for Exit Analysis (10):
- AL: 3 @ $64.35, entry $64.02 on 2025-12-10 (5 days)
- BBIO: 3 @ $71.87, entry $71.53 on 2025-12-09 (6 days)
- BLND: 100 @ $3.09, entry $3.09 on 2025-11-15 (30 days)
- HSY: 2 @ $179.09, entry $178.71 on 2025-12-09 (6 days)
- III: 41 @ $6.10, entry $6.08 on 2025-12-10 (5 days)
- NATH: 2 @ $93.60, entry $93.10 on 2025-12-10 (5 days)
- NESR: 23 @ $13.78, entry $13.78 on 2025-11-15 (30 days)
- OPK: 195 @ $1.30, entry $1.30 on 2025-11-15 (30 days)
- SRPT: 11 @ $22.19, entry $22.09 on 2025-12-10 (5 days)
- TEAM: 1 @ $163.67, entry $160.99 on 2025-12-09 (6 days)

Today's purchases (4):
- AMR: 1 @ $184.95 on 2025-12-15
- CASS: 5 @ $44.68 on 2025-12-15
- KYMR: 2 @ $86.04 on 2025-12-15
- SYM: 4 @ $61.05 on 2025-12-15

Plus AUPH and KALV (already inserted)
"""
import sqlite3
from datetime import datetime

db_path = "trading_history.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n" + "="*80)
print("BULK INSERT: ALL FORM 4 POSITIONS")
print("="*80 + "\n")

# Position data from script output
positions = [
    # Symbol, Qty, Entry Price, Entry Date (YYYY-MM-DD HH:MM:SS)
    ('AL', 3, 64.02, '2025-12-10 16:30:00'),
    ('BBIO', 3, 71.53, '2025-12-09 20:25:00'),
    ('BLND', 100, 3.09, '2025-11-15 09:30:00'),
    ('HSY', 2, 178.71, '2025-12-09 20:25:00'),
    ('III', 41, 6.08, '2025-12-10 16:30:00'),
    ('NATH', 2, 93.10, '2025-12-10 16:30:00'),
    ('NESR', 23, 13.78, '2025-11-15 09:30:00'),
    ('OPK', 195, 1.30, '2025-11-15 09:30:00'),
    ('SRPT', 11, 22.09, '2025-12-10 16:30:00'),
    ('TEAM', 1, 160.99, '2025-12-09 20:25:00'),
    # Today's purchases
    ('AMR', 1, 184.95, '2025-12-15 16:55:36'),
    ('CASS', 5, 44.68, '2025-12-15 16:55:42'),
    ('KYMR', 2, 86.04, '2025-12-15 16:55:39'),
    ('SYM', 4, 61.05, '2025-12-15 16:55:38'),
]

inserted_count = 0

for symbol, qty, entry_price, entry_date in positions:
    # Convert to ISO format with timezone
    dt = datetime.strptime(entry_date, '%Y-%m-%d %H:%M:%S')
    timestamp = dt.isoformat() + '+00:00'
    
    print(f"[INSERT] {symbol}: {qty}@${entry_price} on {entry_date}")
    
    cursor.execute('''
        INSERT INTO trades (symbol, action, quantity, price, timestamp, reason, agent_name, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, 'BUY', qty, entry_price, timestamp, 
          'Form 4 insider trading signal', 'form4_strategy', '{}'))
    
    inserted_count += 1

conn.commit()

print(f"\n[OK] Inserted {inserted_count} positions\n")

# Verify
print("[VERIFY] All Form 4 positions in database:\n")
cursor.execute('''
    SELECT symbol, quantity, price, timestamp
    FROM trades
    WHERE agent_name = 'form4_strategy'
    ORDER BY timestamp ASC
''')

results = cursor.fetchall()
print(f"Total positions: {len(results)}\n")

for symbol, qty, price, timestamp in results:
    entry_dt = datetime.fromisoformat(timestamp)
    days_held = (datetime.now() - entry_dt.replace(tzinfo=None)).days
    print(f"  {symbol}: {qty}@${price:.2f} - {days_held} days held")

print("\n" + "="*80)
print(f"[SUCCESS] {len(results)} positions now tracked by form4_strategy")
print("="*80)

conn.close()
