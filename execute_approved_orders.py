#!/usr/bin/env python3
"""
Execute approved Form 4 positions from the latest approval file.
Run this after manual approval to place orders via IBKR.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ib_insync import IB, Stock, MarketOrder, LimitOrder, util

# IBKR Connection Parameters
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001
IBKR_CLIENT_ID = 10  # Same as Form 4 strategy


def find_latest_approval_file():
    """Find the most recent approved_positions file"""
    reports_dir = Path("weekly_bot/form4_reports")
    files = list(reports_dir.glob("approved_positions_*.json"))
    if not files:
        print("❌ No approved positions files found!")
        return None
    
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return latest


def load_approved_positions(filepath):
    """Load approved positions from JSON file"""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Filter only positions that weren't already executed
    pending = [
        pos for pos in data.get('approved_positions', [])
        if pos.get('status') != 'EXECUTED'
    ]
    
    return pending, data


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Execute approved Form 4 positions")
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    args = parser.parse_args()
    
    # Find latest approval file
    approval_file = find_latest_approval_file()
    if not approval_file:
        return
    
    print(f"\n📄 Loading approvals from: {approval_file.name}")
    
    positions, full_data = load_approved_positions(approval_file)
    
    if not positions:
        print("✅ All positions already executed or no approved positions found!")
        return
    
    print(f"\n📋 Found {len(positions)} pending positions:")
    total_cost = 0
    for pos in positions:
        cost = pos['cost']
        total_cost += cost
        print(f"   {pos['symbol']}: {pos['shares']} shares @ ${pos['price']:.2f} = ${cost:.2f}")
    print(f"\n💰 Total to deploy: ${total_cost:.2f}")
    
    # Confirm execution
    if not args.yes:
        confirm = input("\n⚠️  Execute these orders now? (y/n): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("❌ Cancelled - no orders placed.")
            return
    else:
        print("\n✅ Auto-confirm enabled (--yes flag)")

    
    # Connect to IBKR
    print("\n🔌 Connecting to IBKR...")
    ib = IB()
    try:
        util.run(ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID))
        ib.reqMarketDataType(3)  # Delayed data (free)
        print("✅ Connected to IBKR!")
    except Exception as e:
        print(f"❌ Failed to connect to IBKR: {e}")
        print("   Make sure TWS or IB Gateway is running and API is enabled.")
        return
    
    # Check BOTH buying power AND settled cash
    # ExcessLiquidity = total buying power (includes unsettled funds)
    # SettledCash = actual cash available for NEW stock purchases (T+1 settled)
    buying_power = 0
    settled_cash = 0
    
    for av in ib.accountValues():
        if av.currency == 'USD':
            if av.tag == 'ExcessLiquidity':
                buying_power = float(av.value)
            elif av.tag == 'SettledCash':
                settled_cash = float(av.value)
    
    # The ACTUAL available cash for NEW purchases is the SETTLED cash
    # ExcessLiquidity can be higher due to unsettled sales (T+1 for stocks)
    actual_available = settled_cash
    
    print(f"\n💰 ACCOUNT CASH STATUS:")
    print(f"   Buying Power (ExcessLiquidity): ${buying_power:.2f}")
    print(f"   Settled Cash (Available Now):   ${settled_cash:.2f}")
    
    if buying_power > settled_cash + 10:  # More than $10 difference
        unsettled = buying_power - settled_cash
        print(f"   ⏳ Unsettled Funds (T+1):        ${unsettled:.2f}")
        print(f"\n   ℹ️  You have ${unsettled:.2f} from recent sales waiting to settle.")
        print(f"   ℹ️  These funds will be available tomorrow (T+1 for stocks).")
    
    print(f"\n   ✓ Can use for NEW purchases: ${actual_available:.2f}")
    
    if actual_available < total_cost:
        print(f"\n⚠️  Warning: Settled cash (${actual_available:.2f}) is less than needed (${total_cost:.2f})")
        
        # Calculate which positions we CAN afford with SETTLED cash
        affordable = []
        running_cost = 0
        for pos in sorted(positions, key=lambda x: x['cost']):  # Start with cheapest
            if running_cost + pos['cost'] <= actual_available:
                affordable.append(pos)
                running_cost += pos['cost']
        
        if affordable:
            print(f"\n💡 Can afford {len(affordable)} of {len(positions)} positions (${running_cost:.2f}):")
            for pos in affordable:
                print(f"   ✓ {pos['symbol']}: ${pos['cost']:.2f}")
            
            # Show what we're skipping
            skipped = [p for p in positions if p not in affordable]
            if skipped:
                print(f"\n   ⏭️  Skipping (insufficient settled cash):")
                for pos in skipped:
                    print(f"      • {pos['symbol']}: ${pos['cost']:.2f}")
            
            if not args.yes:
                proceed = input("\n   Execute affordable positions? (y/n): ").strip().lower()
                if proceed not in ['y', 'yes']:
                    ib.disconnect()
                    print("❌ Cancelled.")
                    return
            else:
                print("\n   ✅ Auto-confirm: Executing affordable positions only")
            
            # Replace positions with affordable subset
            positions = affordable
        else:
            print(f"\n❌ Cannot afford ANY positions with settled cash (${actual_available:.2f}).")
            if buying_power > actual_available + 50:
                print(f"\n💡 TIP: You have ${buying_power - actual_available:.2f} in unsettled funds.")
                print(f"   Wait until tomorrow for these funds to settle, then run this script again.")
            else:
                print(f"   Add more capital to your account.")
            ib.disconnect()
            return
    
    # Execute orders
    print("\n" + "="*60)
    print("📊 EXECUTING ORDERS")
    print("="*60)
    
    executions = {}
    for pos in positions:
        symbol = pos['symbol']
        shares = int(pos['shares'])
        
        # Create contract
        contract = Stock(symbol, 'SMART', 'USD')
        try:
            ib.qualifyContracts(contract)
        except Exception as e:
            print(f"❌ {symbol}: Failed to qualify contract - {e}")
            continue
        
        # Use Market order (will execute at market open if placed outside hours)
        order = MarketOrder('BUY', shares)
        # Don't use IOC outside market hours - use DAY or GTC
        order.tif = 'DAY'  # Good for the day (will execute at market open)
        order.outsideRth = False  # Regular trading hours only
        
        print(f"\n📤 {symbol}: Placing BUY order for {shares} shares...")
        
        try:
            trade = ib.placeOrder(contract, order)
            ib.sleep(2)  # Wait for order status
            
            status = trade.orderStatus.status
            if status in ['Filled', 'Submitted', 'PreSubmitted']:
                fill_price = trade.orderStatus.avgFillPrice or pos['price']
                filled_qty = trade.orderStatus.filled or 0
                
                if status == 'Filled':
                    print(f"   ✅ FILLED: {filled_qty} shares @ ${fill_price:.2f}")
                    executions[symbol] = {
                        'status': 'FILLED',
                        'filled_qty': filled_qty,
                        'fill_price': fill_price,
                        'total_cost': filled_qty * fill_price
                    }
                else:
                    print(f"   ⏳ {status}: Order submitted (will fill at market open)")
                    executions[symbol] = {
                        'status': status,
                        'filled_qty': filled_qty,
                        'fill_price': fill_price,
                        'order_id': trade.order.orderId
                    }
            else:
                print(f"   ⚠️  Status: {status}")
                if status == 'Cancelled':
                    print(f"      Order was cancelled (market may be closed for IOC orders)")
        
        except Exception as e:
            print(f"   ❌ Error placing order: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("📊 EXECUTION SUMMARY")
    print("="*60)
    print(f"Orders Placed: {len(executions)}/{len(positions)}")
    
    filled = [e for e in executions.values() if e.get('status') == 'FILLED']
    pending = [e for e in executions.values() if e.get('status') in ['Submitted', 'PreSubmitted']]
    
    if filled:
        total_filled = sum(e['total_cost'] for e in filled)
        print(f"Filled: {len(filled)} orders = ${total_filled:.2f}")
    
    if pending:
        print(f"Pending (will fill at market open): {len(pending)} orders")
    
    # Update the approval file with execution results
    if executions:
        for pos in full_data['approved_positions']:
            if pos['symbol'] in executions:
                pos['execution'] = executions[pos['symbol']]
                pos['status'] = 'EXECUTED' if executions[pos['symbol']].get('status') == 'FILLED' else 'PENDING'
        
        full_data['total_executed'] = len([e for e in executions.values() if e.get('status') == 'FILLED'])
        full_data['executions'] = executions
        full_data['execution_timestamp'] = datetime.now().isoformat()
        
        with open(approval_file, 'w') as f:
            json.dump(full_data, f, indent=2)
        
        print(f"\n✅ Updated {approval_file.name} with execution results")
    
    # Disconnect
    ib.disconnect()
    print("\n🔌 Disconnected from IBKR")
    print("="*60)


if __name__ == "__main__":
    main()
