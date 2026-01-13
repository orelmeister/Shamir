#!/usr/bin/env python3
import sqlite3

db_path = "databases/trading_history.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all unique symbols
cursor.execute("SELECT DISTINCT symbol FROM trades ORDER BY symbol")
all_syms = [row[0] for row in cursor.fetchall()]

missing = ['CPRT', 'FCX', 'GEO', 'IEP', 'K', 'LHCG', 'NRG', 'PCAR', 'REXR', 'RLY', 'UMC']

print("="*80)
print("CHECKING FOR MISSING POSITIONS IN DATABASE")
print("="*80)
print(f"\nTotal symbols in database: {len(all_syms)}")
print(f"All symbols: {', '.join(sorted(all_syms))}\n")

print("Status of the 11 missing positions:\n")
found_count = 0
for sym in sorted(missing):
    if sym in all_syms:
        print(f"  ✓ {sym}: FOUND IN DATABASE")
        found_count += 1
    else:
        print(f"  ✗ {sym}: NOT IN DATABASE")

print(f"\nResult: {found_count}/{len(missing)} positions found in database")
conn.close()
