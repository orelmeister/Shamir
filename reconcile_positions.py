"""
Comprehensive Position Reconciliation
Compares IBKR actual positions vs exit manager tracking vs approved positions
"""
import sys
from ib_insync import IB, util
import json
from pathlib import Path
from datetime import datetime

def get_ibkr_positions():
    """Connect to IBKR and get actual positions"""
    ib = IB()
    try:
        util.run(ib.connectAsync('127.0.0.1', 4001, clientId=98))
        ib.reqMarketDataType(3)
        positions = ib.positions()
        
        result = []
        for pos in positions:
            result.append({
                'symbol': pos.contract.symbol,
                'quantity': pos.position,
                'avg_cost': pos.avgCost,
                'market_value': pos.marketValue,
                'unrealized_pnl': pos.unrealizedPNL
            })
        
        ib.disconnect()
        return result
    except Exception as e:
        print(f"ERROR connecting to IBKR: {e}", file=sys.stderr)
        sys.stderr.flush()
        return []

def get_exit_manager_positions():
    """Read exit manager's view of positions"""
    exit_dir = Path('weekly_bot/form4_reports')
    exit_files = sorted(exit_dir.glob('exit_analysis_*.json'))
    
    if not exit_files:
        return []
    
    latest = exit_files[-1]
    with open(latest) as f:
        data = json.load(f)
    
    return {
        'file': latest.name,
        'timestamp': data.get('timestamp'),
        'positions': data.get('positions', [])
    }

def get_approved_positions():
    """Read approved/executed positions"""
    approved_dir = Path('weekly_bot/form4_reports')
    approved_files = sorted(approved_dir.glob('approved_positions_*.json'))
    
    if not approved_files:
        return []
    
    latest = approved_files[-1]
    with open(latest) as f:
        data = json.load(f)
    
    return {
        'file': latest.name,
        'timestamp': data.get('timestamp'),
        'executed_trades': data.get('executed_trades', [])
    }

def main():
    # Set UTF-8 encoding for Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    print("="*80)
    print("POSITION RECONCILIATION REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    sys.stdout.flush()
    
    # Get IBKR actual positions
    print("\n[1] IBKR ACTUAL POSITIONS (Ground Truth)")
    print("-" * 80)
    ibkr_positions = get_ibkr_positions()
    
    if not ibkr_positions:
        print("[X] NO POSITIONS IN IBKR")
    else:
        for pos in ibkr_positions:
            print(f"[OK] {pos['symbol']:6s}: {pos['quantity']:6.0f} shares @ ${pos['avg_cost']:.2f}")
            print(f"     Market Value: ${pos['market_value']:.2f}")
            print(f"     Unrealized P&L: ${pos['unrealized_pnl']:.2f}")
    sys.stdout.flush()
    
    # Get exit manager positions
    print("\n[2] EXIT MANAGER TRACKED POSITIONS")
    print("-" * 80)
    exit_data = get_exit_manager_positions()
    
    if not exit_data:
        print("[X] NO EXIT ANALYSIS FILES FOUND")
    else:
        print(f"Source: {exit_data['file']}")
        print(f"Time: {exit_data['timestamp']}")
        print()
        
        if not exit_data['positions']:
            print("[X] EXIT MANAGER HAS NO POSITIONS")
        else:
            for pos in exit_data['positions']:
                symbol = pos['symbol']
                shares = pos['quantity']
                entry = pos['entry_price']
                current = pos['current_price']
                pnl_pct = pos['pnl_percentage']
                print(f"[TRACKED] {symbol:6s}: {shares:6.0f} shares @ ${entry:.2f}")
                print(f"          Current: ${current:.2f} ({pnl_pct:+.2f}%)")
    sys.stdout.flush()
    
    # Get approved positions
    print("\n[3] RECENTLY APPROVED/EXECUTED POSITIONS")
    print("-" * 80)
    approved_data = get_approved_positions()
    
    if not approved_data:
        print("[X] NO APPROVED POSITION FILES FOUND")
    else:
        print(f"Source: {approved_data['file']}")
        print(f"Time: {approved_data['timestamp']}")
        print()
        
        if not approved_data['executed_trades']:
            print("[X] NO EXECUTED TRADES")
        else:
            for trade in approved_data['executed_trades']:
                symbol = trade['symbol']
                shares = trade['shares']
                price = trade['executed_price']
                cost = shares * price
                print(f"[NEW] {symbol:6s}: {shares:6.0f} shares @ ${price:.2f} (Cost: ${cost:.2f})")
    sys.stdout.flush()
    
    # DISCREPANCY ANALYSIS
    print("\n[4] DISCREPANCY ANALYSIS")
    print("="*80)
    
    ibkr_symbols = set(pos['symbol'] for pos in ibkr_positions)
    exit_symbols = set(pos['symbol'] for pos in exit_data.get('positions', [])) if exit_data else set()
    approved_symbols = set(t['symbol'] for t in approved_data.get('executed_trades', [])) if approved_data else set()
    
    orphaned = ibkr_symbols - exit_symbols - approved_symbols
    phantom = exit_symbols - ibkr_symbols
    pending = approved_symbols - ibkr_symbols - exit_symbols
    
    if orphaned:
        print(f"\n[ALERT] ORPHANED POSITIONS (In IBKR but NOT tracked):")
        for symbol in orphaned:
            pos = next(p for p in ibkr_positions if p['symbol'] == symbol)
            print(f"   {symbol}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f}")
            print(f"   [WARNING] EXIT MANAGER CANNOT LIQUIDATE - NOT IN TRACKING!")
    
    if phantom:
        print(f"\n[PHANTOM] PHANTOM POSITIONS (Tracked but NOT in IBKR):")
        for symbol in phantom:
            pos = next(p for p in exit_data['positions'] if p['symbol'] == symbol)
            print(f"   {symbol}: {pos['quantity']} shares @ ${pos['entry_price']:.2f}")
            print(f"   [WARNING] ALREADY SOLD OR NEVER BOUGHT?")
    
    if pending:
        print(f"\n[PENDING] PENDING POSITIONS (Approved but not yet in IBKR or tracking):")
        for symbol in pending:
            trade = next(t for t in approved_data['executed_trades'] if t['symbol'] == symbol)
            print(f"   {symbol}: {trade['shares']} shares @ ${trade['executed_price']:.2f}")
            print(f"   [INFO] May take time to settle or sync")
    
    if not orphaned and not phantom and not pending:
        print("\n[OK] ALL POSITIONS MATCH - NO DISCREPANCIES")
    
    print("\n" + "="*80)
    print("SUMMARY:")
    print(f"  IBKR Actual Positions: {len(ibkr_positions)}")
    print(f"  Exit Manager Tracked: {len(exit_data.get('positions', [])) if exit_data else 0}")
    print(f"  Recently Approved: {len(approved_data.get('executed_trades', [])) if approved_data else 0}")
    print(f"  [ALERT] Orphaned: {len(orphaned)}")
    print(f"  [PHANTOM] Phantom: {len(phantom)}")
    print(f"  [PENDING] Pending: {len(pending)}")
    print("="*80)
    sys.stdout.flush()

if __name__ == '__main__':
    main()
