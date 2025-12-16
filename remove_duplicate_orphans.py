"""Remove duplicate AUPH and KALV entries created by orphaned sync

The sync created duplicate entries on 2025-12-15 with reason 'ORPHANED_POSITION_SYNC'.
We need to keep the original 2025-12-03 entries (transferred from day_trader) and
delete the duplicate 2025-12-15 entries.
"""
import sqlite3
import os

parent_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(parent_dir, "databases", "trading_history.db")

print("\n" + "="*80)
print("REMOVING DUPLICATE AUPH/KALV ENTRIES")
print("="*80 + "\n")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Show all AUPH/KALV entries
print("[BEFORE] All AUPH/KALV entries:\n")
cursor.execute('''
    SELECT id, symbol, timestamp, price, quantity, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    AND agent_name = 'form4_strategy'
    ORDER BY timestamp
''')

rows = cursor.fetchall()
for row in rows:
    trade_id, symbol, timestamp, price, qty, reason = row
    print(f"ID {trade_id}: {symbol} {qty}@${price:.2f} on {timestamp[:10]}")
    print(f"  Reason: {reason[:70]}...\n")

# Delete the duplicate entries from 2025-12-15 with ORPHANED_POSITION_SYNC
print("[DELETING] Removing duplicate entries from 2025-12-15...\n")

cursor.execute('''
    DELETE FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    AND agent_name = 'form4_strategy'
    AND reason LIKE '%ORPHANED_POSITION_SYNC%'
    AND timestamp LIKE '2025-12-15%'
''')

deleted_count = cursor.rowcount
conn.commit()

print(f"[OK] Deleted {deleted_count} duplicate entry(ies)\n")

# Verify only original entries remain
print("[AFTER] Remaining AUPH/KALV entries:\n")
cursor.execute('''
    SELECT id, symbol, timestamp, price, quantity, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    AND agent_name = 'form4_strategy'
    ORDER BY timestamp
''')

rows = cursor.fetchall()
for row in rows:
    trade_id, symbol, timestamp, price, qty, reason = row
    print(f"ID {trade_id}: {symbol} {qty}@${price:.2f} on {timestamp[:10]}")
    print(f"  Reason: {reason[:70]}...\n")

conn.close()

print("="*80)
print("[SUCCESS] Duplicates removed - only original entries remain")
print("="*80)
