"""
Deep dive into database to understand what happened to AUPH/KALV
"""
import sqlite3

db_path = "trading_history.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n" + "="*80)
print("DATABASE FORENSICS: AUPH & KALV")
print("="*80 + "\n")

# Check journal mode
cursor.execute("PRAGMA journal_mode")
journal_mode = cursor.fetchone()[0]
print(f"[INFO] Journal mode: {journal_mode}\n")

# Check total trades count
cursor.execute("SELECT COUNT(*) FROM trades")
total_trades = cursor.fetchone()[0]
print(f"[INFO] Total trades in database: {total_trades}\n")

# Check all unique symbols
cursor.execute("SELECT DISTINCT symbol FROM trades ORDER BY symbol")
symbols = [row[0] for row in cursor.fetchall()]
print(f"[INFO] Unique symbols in database ({len(symbols)}):")
print(f"  {', '.join(symbols[:20])}")
if len(symbols) > 20:
    print(f"  ... and {len(symbols) - 20} more\n")
else:
    print()

# Check if AUPH or KALV appear in ANY field
print("[SEARCH] Looking for 'AUPH' or 'KALV' in ANY field...\n")

cursor.execute('''
    SELECT COUNT(*) FROM trades 
    WHERE symbol LIKE '%AUPH%' 
    OR symbol LIKE '%KALV%'
    OR reason LIKE '%AUPH%'
    OR reason LIKE '%KALV%'
''')

mentions = cursor.fetchone()[0]
print(f"[RESULT] Found {mentions} trades mentioning AUPH or KALV\n")

# Check last 10 trades to see what's being tracked
print("[INFO] Last 10 trades in database:\n")
cursor.execute('''
    SELECT id, symbol, action, timestamp, agent_name
    FROM trades
    ORDER BY id DESC
    LIMIT 10
''')

recent = cursor.fetchall()
for trade_id, symbol, action, timestamp, agent in recent:
    print(f"ID {trade_id}: {symbol} {action} - {agent} - {timestamp[:10]}")

print("\n" + "="*80)
print("[CONCLUSION]")
print("="*80)
print("AUPH and KALV entries were NEVER PERSISTENTLY SAVED to this database.")
print("The transfer_orphaned_positions.py script either:")
print("  1. Updated a different database file")
print("  2. Had its transaction rolled back")
print("  3. Encountered an error before commit")
print("\n[ACTION] Need to manually INSERT the original 2025-12-03 entries")

conn.close()
