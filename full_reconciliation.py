import sys
from ib_insync import IB, util
import json
from pathlib import Path
from datetime import datetime

# Get IBKR positions
ib = IB()
util.run(ib.connectAsync('127.0.0.1', 4001, clientId=98))
ib.reqMarketDataType(3)
ibkr_positions = {}
for pos in ib.positions():
    market_value = pos.position * pos.avgCost  # Approximate - need current price for exact
    ibkr_positions[pos.contract.symbol] = {
        'quantity': pos.position,
        'avg_cost': pos.avgCost,
        'market_value': market_value,
        'unrealized_pnl': 0  # Not available from basic position object
    }
ib.disconnect()

# Get exit manager positions
with open('weekly_bot/form4_reports/exit_analysis_20251215_080325.json') as f:
    exit_data = json.load(f)
exit_positions = {}
for decision in exit_data.get('exit_decisions', []):
    pos = decision['position']
    exit_positions[pos['symbol']] = {
        'quantity': pos['quantity'],
        'entry_price': pos['entry_price'],
        'entry_date': pos['entry_date'],
        'pnl_pct': pos['pnl_pct']
    }

# Get approved positions
with open('weekly_bot/form4_reports/approved_positions_20251215_080210.json') as f:
    approved_data = json.load(f)
approved_positions = {}
for trade in approved_data.get('executed_trades', []):
    approved_positions[trade['symbol']] = {
        'shares': trade['shares'],
        'price': trade['executed_price'],
        'timestamp': approved_data.get('timestamp')
    }

# Generate report
print("="*80)
print("FORM 4 STRATEGY POSITION RECONCILIATION")
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

print(f"\nIBKR ACTUAL: {len(ibkr_positions)} positions")
print(f"EXIT MANAGER: {len(exit_positions)} positions tracked")
print(f"APPROVED TODAY: {len(approved_positions)} new positions")

# Find discrepancies
ibkr_symbols = set(ibkr_positions.keys())
exit_symbols = set(exit_positions.keys())
approved_symbols = set(approved_positions.keys())

orphaned = ibkr_symbols - exit_symbols - approved_symbols
phantom = exit_symbols - ibkr_symbols
approved_in_ibkr = approved_symbols & ibkr_symbols
approved_not_in_ibkr = approved_symbols - ibkr_symbols

print("\n" + "="*80)
print("DISCREPANCY ANALYSIS:")
print("="*80)

if orphaned:
    print(f"\n[ALERT] {len(orphaned)} ORPHANED POSITIONS (in IBKR but NOT tracked):")
    for symbol in sorted(orphaned):
        pos = ibkr_positions[symbol]
        cost = pos['quantity'] * pos['avg_cost']
        print(f"  {symbol:6s}: {pos['quantity']:6.0f} shares @ ${pos['avg_cost']:7.2f} = ${cost:8.2f}")
    print(f"\n  [WARNING] Exit manager CANNOT liquidate these - not in tracking!")

if phantom:
    print(f"\n[PHANTOM] {len(phantom)} positions tracked but NOT in IBKR:")
    for symbol in sorted(phantom):
        pos = exit_positions[symbol]
        print(f"  {symbol:6s}: {pos['quantity']:6.0f} shares @ ${pos['entry_price']:7.2f}")
        print(f"           Entry: {pos['entry_date']}, P&L: {pos['pnl_pct']:+.2f}%")
    print(f"\n  [INFO] These may have been sold manually or never bought")

if approved_in_ibkr:
    print(f"\n[OK] {len(approved_in_ibkr)} approved positions CONFIRMED in IBKR:")
    for symbol in sorted(approved_in_ibkr):
        appr = approved_positions[symbol]
        ibkr = ibkr_positions[symbol]
        print(f"  {symbol:6s}: Approved {appr['shares']:3.0f} @ ${appr['price']:7.2f}, IBKR has {ibkr['quantity']:3.0f} @ ${ibkr['avg_cost']:7.2f}")

if approved_not_in_ibkr:
    print(f"\n[PENDING] {len(approved_not_in_ibkr)} approved but NOT yet in IBKR:")
    for symbol in sorted(approved_not_in_ibkr):
        appr = approved_positions[symbol]
        print(f"  {symbol:6s}: {appr['shares']:6.0f} shares @ ${appr['price']:7.2f}")
    print(f"\n  [INFO] May be settling or order not filled")

print("\n" + "="*80)
print("SUMMARY:")
print(f"  Total capital deployed in IBKR: ${sum(p['market_value'] for p in ibkr_positions.values()):.2f}")
print(f"  Exit Manager can liquidate: {len(exit_symbols)} positions")
print(f"  Exit Manager BLIND to: {len(orphaned)} positions")
if orphaned:
    orphaned_value = sum(ibkr_positions[s]['market_value'] for s in orphaned)
    print(f"  Value stuck (orphaned): ${orphaned_value:.2f}")
print("="*80)
