#!/usr/bin/env python3
"""Check position ownership in database and IBKR"""

from observability import get_database
from ib_insync import IB
import sqlite3

print("=" * 60)
print("POSITION OWNERSHIP ANALYSIS")
print("=" * 60)

# Check IBKR positions
print("\n1. CURRENT IBKR POSITIONS:")
print("-" * 60)
ib = IB()
try:
    ib.connect('127.0.0.1', 4001, clientId=99)
    positions = ib.positions()
    
    for p in positions:
        print(f"{p.contract.symbol:6} {p.position:6.0f} shares @ ${p.avgCost:7.2f}")
    
    print(f"\nTotal positions: {len(positions)}")
    ib.disconnect()
except Exception as e:
    print(f"Error connecting to IBKR: {e}")

# Check database
print("\n2. DATABASE TABLES:")
print("-" * 60)
conn = sqlite3.connect('databases/trading_history.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Available tables:", [t[0] for t in tables])

# Check trades table
print("\n3. RECENT TRADES (Last 20):")
print("-" * 60)
cursor.execute("""
    SELECT timestamp, agent_name, symbol, action, quantity, price 
    FROM trades 
    ORDER BY timestamp DESC 
    LIMIT 20
""")
trades = cursor.fetchall()
if trades:
    print(f"{'Timestamp':<25} {'Agent':<15} {'Symbol':<6} {'Action':<6} {'Qty':<8} {'Price':<10}")
    print("-" * 80)
    for t in trades:
        print(f"{t[0]:<25} {t[1]:<15} {t[2]:<6} {t[3]:<6} {t[4]:<8} ${t[5]:<9.2f}")
else:
    print("No trades found")

# Check by agent
print("\n4. TRADES BY AGENT:")
print("-" * 60)
cursor.execute("""
    SELECT agent_name, COUNT(*) as count, SUM(CASE WHEN action='BUY' THEN 1 ELSE 0 END) as buys,
           SUM(CASE WHEN action='SELL' THEN 1 ELSE 0 END) as sells
    FROM trades 
    GROUP BY agent_name
""")
agent_stats = cursor.fetchall()
for stat in agent_stats:
    print(f"{stat[0]:<20} Total: {stat[1]:3} | Buys: {stat[2]:3} | Sells: {stat[3]:3}")

# Check specific symbols in IBKR
print("\n5. SYMBOL TRADE HISTORY:")
print("-" * 60)
ibkr_symbols = ['OPK', 'SEMR', 'NESR', 'BLND', 'ONDS', 'ONB']
for symbol in ibkr_symbols:
    cursor.execute("""
        SELECT agent_name, action, quantity, price, timestamp
        FROM trades 
        WHERE symbol = ?
        ORDER BY timestamp DESC
        LIMIT 3
    """, (symbol,))
    symbol_trades = cursor.fetchall()
    if symbol_trades:
        print(f"\n{symbol}:")
        for st in symbol_trades:
            print(f"  {st[4][:19]} | {st[0]:<15} | {st[1]:<4} {st[2]:3} @ ${st[3]:.2f}")
    else:
        print(f"\n{symbol}: No trades found in database")

conn.close()

print("\n" + "=" * 60)
print("ANALYSIS COMPLETE")
print("=" * 60)
