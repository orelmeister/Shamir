"""Investigate VMD trades"""
import sqlite3

conn = sqlite3.connect('trading_history.db')
cursor = conn.cursor()

print("=== ALL VMD TRADES IN DATABASE ===\n")
cursor.execute("SELECT timestamp, action, quantity, price, agent_name, reason FROM trades WHERE symbol='VMD' ORDER BY timestamp")
rows = cursor.fetchall()

if rows:
    for row in rows:
        print(f"{row[0]}: {row[1]} {row[2]} shares @ ${row[3]:.2f}")
        print(f"  Agent: {row[4]}, Reason: {row[5]}\n")
else:
    print("No VMD BUY trades found in database!")

print("\n=== VMD IN CLOSED_POSITIONS_TODAY ===\n")
cursor.execute("SELECT * FROM closed_positions_today WHERE symbol='VMD'")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(row)
else:
    print("Not in closed_positions_today table")

print("\n=== INVESTIGATION ===")
print("VMD shows SELL but no BUY in trades table")
print("This means:")
print("1. VMD was manually added to database (we did this)")
print("2. Exit Manager sold it")
print("3. But the original BUY was never logged (old position)")
print("\nVMD was a LONG-TERM position that should have been PROTECTED!")

conn.close()
