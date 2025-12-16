"""
Check ALL AUPH and KALV trades (including SELLs) to understand what happened
"""
import sqlite3

db_path = "trading_history.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n" + "="*80)
print("ALL AUPH & KALV TRADES IN DATABASE")
print("="*80 + "\n")

cursor.execute('''
    SELECT id, symbol, action, quantity, price, timestamp, agent_name, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    ORDER BY id ASC
''')

all_trades = cursor.fetchall()

print(f"[TOTAL] {len(all_trades)} total trades for AUPH/KALV\n")

if len(all_trades) == 0:
    print("❌ NO TRADES FOUND IN DATABASE!")
    print("\n[DIAGNOSIS]:")
    print("  - The transfer_orphaned_positions.py script may have:")
    print("    1. Worked but changes were later deleted")
    print("    2. Not actually committed the changes")
    print("    3. Updated different database file")
    print("\n[SOLUTION NEEDED]:")
    print("  - Re-run transfer script with explicit commit()")
    print("  - Or manually INSERT the original 2025-12-03 entries")
else:
    for row in all_trades:
        trade_id, symbol, action, qty, price, timestamp, agent_name, reason = row
        print(f"ID {trade_id}: {symbol} {action} {qty}@${price:.2f}")
        print(f"  Agent: {agent_name}")
        print(f"  Date: {timestamp}")
        print(f"  Reason: {reason}")
        print()

conn.close()
