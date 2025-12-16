"""Transfer orphaned positions from day_trader to form4_strategy

AUPH and KALV were purchased by day_trader on 2025-12-03 but need to be managed
by the Form 4 exit manager. This script transfers ownership in the database.
"""
import sqlite3
import os
from datetime import datetime, timezone

# Get database path
parent_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(parent_dir, "databases", "trading_history.db")

print("="*80)
print("TRANSFERRING ORPHANED POSITIONS TO FORM 4 STRATEGY")
print("="*80 + "\n")

print(f"Database: {db_path}\n")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check current state
print("[BEFORE] Checking current ownership:\n")
cursor.execute('''
    SELECT symbol, action, timestamp, price, quantity, agent_name, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    ORDER BY timestamp
''')

rows = cursor.fetchall()
for row in rows:
    symbol, action, timestamp, price, qty, agent, reason = row
    print(f"{symbol}: {action} {qty} @ ${price}")
    print(f"  Agent: {agent}")
    print(f"  Date: {timestamp}")
    print(f"  Reason: {reason}\n")

# Update agent_name from day_trader to form4_strategy
print("[TRANSFERRING] Updating agent_name to 'form4_strategy'...\n")

cursor.execute('''
    UPDATE trades 
    SET agent_name = 'form4_strategy',
        reason = reason || ' [TRANSFERRED from day_trader for Form 4 exit management]'
    WHERE symbol IN ('AUPH', 'KALV')
    AND agent_name = 'day_trader'
''')

updated_count = cursor.rowcount
conn.commit()

print(f"[OK] Updated {updated_count} trade(s)\n")

# Verify after update
print("[AFTER] Verifying transfer:\n")
cursor.execute('''
    SELECT symbol, action, timestamp, price, quantity, agent_name, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    ORDER BY timestamp
''')

rows = cursor.fetchall()
for row in rows:
    symbol, action, timestamp, price, qty, agent, reason = row
    print(f"{symbol}: {action} {qty} @ ${price}")
    print(f"  Agent: {agent}")
    print(f"  Date: {timestamp}")
    print(f"  Reason: {reason}\n")

conn.close()

print("="*80)
print("[SUCCESS] Orphaned positions transferred!")
print("="*80)
print("\nAUPH and KALV are now managed by form4_strategy")
print("Run the Form 4 exit manager to confirm they're tracked correctly.")
