"""
Verify database state for AUPH and KALV after full run
"""
import sqlite3
from datetime import datetime, timezone

db_path = "trading_history.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n" + "="*80)
print("DATABASE STATE CHECK: AUPH & KALV")
print("="*80)

# Get all AUPH and KALV entries
cursor.execute('''
    SELECT id, symbol, action, quantity, price, timestamp, agent_name, reason
    FROM trades 
    WHERE symbol IN ('AUPH', 'KALV')
    ORDER BY timestamp DESC
''')

results = cursor.fetchall()

print(f"\n[TOTAL] {len(results)} entries for AUPH/KALV in database\n")

for row in results:
    trade_id, symbol, action, qty, price, timestamp, agent_name, reason = row
    # Parse timestamp
    try:
        dt = datetime.fromisoformat(timestamp)
        days_ago = (datetime.now(timezone.utc) - dt).days
        date_str = f"{dt.strftime('%Y-%m-%d %H:%M:%S')} ({days_ago} days ago)"
    except:
        date_str = timestamp
    
    print(f"ID {trade_id}: {symbol} {action} {qty}@${price:.2f}")
    print(f"  Date: {date_str}")
    print(f"  Agent: {agent_name}")
    print(f"  Reason: {reason}")
    print()

print("="*80)
print("[CHECKING] Which agent_name does exit manager query for?")
print("="*80)

cursor.execute('''
    SELECT symbol, COUNT(*) as count, agent_name
    FROM trades
    WHERE symbol IN ('AUPH', 'KALV')
    GROUP BY symbol, agent_name
''')

summary = cursor.fetchall()
for symbol, count, agent in summary:
    print(f"{symbol}: {count} entries with agent_name='{agent}'")

print("\n" + "="*80)
print("[ACTION NEEDED?]")
print("="*80)

cursor.execute('''
    SELECT symbol, quantity, price, timestamp, agent_name
    FROM trades
    WHERE symbol IN ('AUPH', 'KALV')
    AND action = 'BUY'
    AND agent_name = 'form4_strategy'
    ORDER BY timestamp ASC
''')

form4_positions = cursor.fetchall()

if len(form4_positions) == 2:
    print("✅ Both AUPH and KALV are in database with agent_name='form4_strategy'")
    for symbol, qty, price, timestamp, agent in form4_positions:
        print(f"   {symbol}: {qty}@${price} - {timestamp}")
else:
    print(f"❌ Expected 2 positions with agent_name='form4_strategy', found {len(form4_positions)}")
    if len(form4_positions) == 0:
        print("   [PROBLEM] Positions not visible to form4_strategy exit manager!")

conn.close()
