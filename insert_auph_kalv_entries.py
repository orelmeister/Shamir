"""
Manually insert AUPH and KALV entries with original 2025-12-03 purchase data
"""
import sqlite3
from datetime import datetime, timezone

db_path = "trading_history.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n" + "="*80)
print("MANUAL INSERT: AUPH & KALV ORIGINAL ENTRIES")
print("="*80 + "\n")

# Original purchase data from IBKR (from earlier in conversation)
# AUPH: 8 shares @ $14.99 on 2025-12-03T14:49:37
# KALV: 9 shares @ $14.84 on 2025-12-03T14:51:39

auph_entry = {
    'symbol': 'AUPH',
    'action': 'BUY',
    'quantity': 8,
    'price': 14.99,
    'timestamp': '2025-12-03T14:49:37+00:00',
    'reason': 'Day trader purchase - Transferred to Form 4 exit management',
    'agent_name': 'form4_strategy',
    'metadata': '{}'
}

kalv_entry = {
    'symbol': 'KALV',
    'action': 'BUY',
    'quantity': 9,
    'price': 14.84,
    'timestamp': '2025-12-03T14:51:39+00:00',
    'reason': 'Day trader purchase - Transferred to Form 4 exit management',
    'agent_name': 'form4_strategy',
    'metadata': '{}'
}

# Insert AUPH
print("[INSERT] AUPH: 8 shares @ $14.99 on 2025-12-03...")
cursor.execute('''
    INSERT INTO trades (symbol, action, quantity, price, timestamp, reason, agent_name, metadata)
    VALUES (:symbol, :action, :quantity, :price, :timestamp, :reason, :agent_name, :metadata)
''', auph_entry)

# Insert KALV  
print("[INSERT] KALV: 9 shares @ $14.84 on 2025-12-03...")
cursor.execute('''
    INSERT INTO trades (symbol, action, quantity, price, timestamp, reason, agent_name, metadata)
    VALUES (:symbol, :action, :quantity, :price, :timestamp, :reason, :agent_name, :metadata)
''', kalv_entry)

conn.commit()

print("[OK] Entries inserted successfully\n")

# Verify
print("[VERIFY] Checking database...\n")
cursor.execute('''
    SELECT symbol, quantity, price, timestamp, agent_name
    FROM trades
    WHERE symbol IN ('AUPH', 'KALV')
    ORDER BY timestamp
''')

results = cursor.fetchall()
for symbol, qty, price, timestamp, agent in results:
    # Calculate days held
    entry_dt = datetime.fromisoformat(timestamp)
    days_held = (datetime.now(timezone.utc) - entry_dt).days
    
    print(f"✅ {symbol}: {qty} shares @ ${price}")
    print(f"   Entry: {timestamp}")
    print(f"   Days held: {days_held}")
    print(f"   Agent: {agent}\n")

print("="*80)
print("[SUCCESS] AUPH and KALV now in database for Form 4 exit management")
print("="*80)

conn.close()
