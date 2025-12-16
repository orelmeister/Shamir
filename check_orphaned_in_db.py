"""Check if AUPH and KALV exist in trading_history database"""
import sqlite3
import os

# Get database path
parent_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(parent_dir, "databases", "trading_history.db")

print(f"Checking database: {db_path}\n")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check for AUPH and KALV
cursor.execute('''
    SELECT symbol, action, timestamp, price, quantity, agent_name, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    ORDER BY timestamp
''')

rows = cursor.fetchall()

if rows:
    print(f"Found {len(rows)} trade(s) for AUPH/KALV:\n")
    for row in rows:
        symbol, action, timestamp, price, qty, agent, reason = row
        print(f"{symbol}: {action} {qty} @ ${price} on {timestamp}")
        print(f"  Agent: {agent}, Reason: {reason}\n")
else:
    print("❌ No trades found for AUPH or KALV in database")
    print("These are truly orphaned positions!\n")

conn.close()
