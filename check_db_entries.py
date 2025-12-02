import sqlite3
from datetime import datetime

conn = sqlite3.connect('databases/trading_history.db')
cursor = conn.cursor()

# Check schema
cursor.execute('PRAGMA table_info(active_positions)')
columns = cursor.fetchall()
print("\n=== Active Positions Schema ===")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

# Check Form4 positions
cursor.execute("SELECT symbol, entry_timestamp, entry_price, agent_name FROM active_positions WHERE agent_name='form4_strategy'")
rows = cursor.fetchall()

print(f"\n=== Found {len(rows)} Form4 Positions ===")
for row in rows:
    symbol, entry_ts, entry_price, agent = row
    print(f"{symbol}: {entry_ts} @ ${entry_price:.2f}")
    
    if entry_ts:
        try:
            entry_date = datetime.fromisoformat(entry_ts.replace(' ', 'T'))
            days_held = (datetime.now() - entry_date).days
            print(f"  -> Days held: {days_held}")
        except Exception as e:
            print(f"  -> Parse error: {e}")

conn.close()
