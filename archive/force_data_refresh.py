"""
Emergency fix: Delete old data files and force complete refresh with CURRENT news only.
This will ensure the system fetches fresh data from scratch.
"""
import os
import json
from datetime import datetime, timedelta

print("="*60)
print("EMERGENCY DATA REFRESH - Deleting stale data files")
print("="*60)

files_to_delete = [
    'full_market_data.json',
    'day_trading_watchlist.json'
]

for filename in files_to_delete:
    if os.path.exists(filename):
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(filename))
        print(f"\n✗ Deleting {filename}")
        print(f"  Last Modified: {file_mod_time}")
        print(f"  Size: {os.path.getsize(filename):,} bytes")
        os.remove(filename)
        print(f"  ✓ Deleted successfully")
    else:
        print(f"\n⚠ {filename} not found (already deleted or doesn't exist)")

print("\n" + "="*60)
print("DATA FILES CLEARED")
print("="*60)
print("\nNext steps:")
print("1. The system will now fetch FRESH data on next run")
print("2. Phase 0 will run and collect current market data")
print("3. Phase 1 will analyze with fresh data and generate new watchlist")
print("\nRun: .\.venv-daytrader\Scripts\python.exe day_trader.py --allocation 0.25")
print("="*60)
