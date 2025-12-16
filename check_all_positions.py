import sys
from ib_insync import IB, util
import json
from pathlib import Path

# IBKR Connection
ib = IB()
util.run(ib.connectAsync('127.0.0.1', 4001, clientId=98))
ib.reqMarketDataType(3)

print("IBKR ACTUAL POSITIONS:")
positions = ib.positions()
for pos in positions:
    print(f"  {pos.contract.symbol}: {pos.position} shares @ ${pos.avgCost:.2f}")
    sys.stdout.flush()

ib.disconnect()

# Exit Manager Tracking
print("\nEXIT MANAGER TRACKED:")
exit_files = sorted(Path('weekly_bot/form4_reports').glob('exit_analysis_*.json'))
if exit_files:
    with open(exit_files[-1]) as f:
        data = json.load(f)
    print(f"  File: {exit_files[-1].name}")
    for pos in data.get('positions', []):
        print(f"  {pos['symbol']}: {pos['quantity']} shares @ ${pos['entry_price']:.2f}")
        sys.stdout.flush()

# Approved Positions
print("\nAPPROVED TODAY:")
approved_files = sorted(Path('weekly_bot/form4_reports').glob('approved_positions_*.json'))
if approved_files:
    with open(approved_files[-1]) as f:
        data = json.load(f)
    print(f"  File: {approved_files[-1].name}")
    for trade in data.get('executed_trades', []):
        print(f"  {trade['symbol']}: {trade['shares']} shares @ ${trade['executed_price']:.2f}")
        sys.stdout.flush()
