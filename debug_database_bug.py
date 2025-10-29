"""Debug why trades aren't being added to active_positions"""
import sqlite3
from datetime import datetime

conn = sqlite3.connect('trading_history.db')
cursor = conn.cursor()

print("=== DATABASE SCHEMA ===")
cursor.execute("PRAGMA table_info(active_positions)")
print("\nactive_positions columns:")
for col in cursor.fetchall():
    print(f"  {col[1]}: {col[2]}")

print("\n=== CURRENT DATA ===")
cursor.execute("SELECT COUNT(*) FROM active_positions")
print(f"Active positions: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM trades WHERE DATE(timestamp) = DATE('now')")
print(f"Trades today: {cursor.fetchone()[0]}")

print("\n=== TODAY'S TRADES ===")
cursor.execute("""
    SELECT timestamp, action, symbol, quantity, price 
    FROM trades 
    WHERE DATE(timestamp) = DATE('now')
    ORDER BY timestamp
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} {row[2]} - {row[3]} shares @ ${row[4]:.2f}")

print("\n=== CHECKING IF add_active_position WAS CALLED ===")
# Check if there were any INSERT attempts that might have failed
cursor.execute("""
    SELECT symbol, action, timestamp 
    FROM trades 
    WHERE action = 'BUY' AND DATE(timestamp) = DATE('now')
""")
buy_trades = cursor.fetchall()
print(f"\nFound {len(buy_trades)} BUY trades today")
print("These should have triggered add_active_position() calls")

print("\n=== ACTIVE POSITIONS TABLE ===")
cursor.execute("SELECT * FROM active_positions")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f"  {row}")
else:
    print("  (Empty - only VMD was just added)")

conn.close()

print("\n=== ANALYSIS ===")
print("BUG: 11 BUY trades logged but positions not added to active_positions")
print("Possible causes:")
print("1. add_active_position() not being called (code path issue)")
print("2. add_active_position() failing silently (exception handling)")
print("3. Database transaction not committing")
print("4. Old version of code was running (before database integration)")
