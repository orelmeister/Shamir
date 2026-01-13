"""
Execute politician-first exits for positions that lost politician backing.
This script properly waits for order fills instead of the 2-second timeout in the main strategy.

Usage:
    python execute_politician_exits.py           # Execute exits
    python execute_politician_exits.py --dry-run # Preview only, no execution
"""

import sys
import os
import argparse
import time
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_insync import IB, Stock, MarketOrder, util
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Positions that need to exit based on politician-first hard gate violation
# These are positions with NO politician signals remaining
POSITIONS_TO_EXIT = [
    'AMR', 'ASPI', 'AUPH', 'BBIO', 'CASS', 'IEP', 'III', 
    'KALV', 'NATH', 'NESR', 'OPK', 'PGEN', 'SYM', 'TEM'
]

# Only CBRL has politician backing and should be kept
POSITIONS_TO_KEEP = ['CBRL']


def connect_ibkr(client_id: int = 20) -> IB:
    """Connect to IBKR"""
    ib = IB()
    try:
        util.run(ib.connectAsync('127.0.0.1', 4001, clientId=client_id))
        ib.reqMarketDataType(3)  # Delayed data
        logger.info("✅ Connected to IBKR")
        return ib
    except Exception as e:
        logger.error(f"❌ Failed to connect to IBKR: {e}")
        sys.exit(1)


def get_current_positions(ib: IB) -> dict:
    """Get current positions from IBKR"""
    positions = {}
    for pos in ib.positions():
        symbol = pos.contract.symbol
        if pos.position != 0:
            positions[symbol] = {
                'quantity': abs(pos.position),
                'avg_cost': pos.avgCost,
                'contract': pos.contract
            }
    return positions


def execute_exit(ib: IB, symbol: str, quantity: float, contract, dry_run: bool = False) -> dict:
    """
    Execute a single exit order with proper fill waiting
    
    Returns:
        Dict with status, fill_price, pnl
    """
    result = {
        'symbol': symbol,
        'quantity': quantity,
        'status': 'PENDING',
        'fill_price': None,
        'error': None
    }
    
    if dry_run:
        print(f"   [DRY RUN] Would sell {quantity} shares of {symbol}")
        result['status'] = 'DRY_RUN'
        return result
    
    try:
        # Create market order
        order = MarketOrder('SELL', quantity)
        order.tif = 'DAY'  # Good for day (not IOC!)
        order.outsideRth = False  # Regular trading hours only
        
        # Place order
        trade = ib.placeOrder(contract, order)
        print(f"   📤 Order placed for {symbol}...")
        
        # Wait for fill with timeout (max 30 seconds)
        max_wait = 30
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            ib.sleep(1)  # Let ib_insync process events
            
            status = trade.orderStatus.status
            
            if status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                print(f"   ✅ FILLED at ${fill_price:.2f}")
                result['status'] = 'FILLED'
                result['fill_price'] = fill_price
                return result
            
            elif status in ['Cancelled', 'ApiCancelled']:
                print(f"   ❌ Order CANCELLED")
                result['status'] = 'CANCELLED'
                # Check for error message
                if trade.log:
                    for entry in trade.log:
                        if entry.message:
                            result['error'] = entry.message
                            print(f"   Reason: {entry.message}")
                return result
            
            elif status == 'Inactive':
                print(f"   ⚠️  Order INACTIVE - may need manual intervention")
                result['status'] = 'INACTIVE'
                return result
            
            # Still pending
            print(f"   ⏳ Status: {status}...", end='\r')
        
        # Timeout - order still pending
        print(f"   ⚠️  Timeout - order status: {trade.orderStatus.status}")
        result['status'] = trade.orderStatus.status
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        result['status'] = 'ERROR'
        result['error'] = str(e)
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Execute politician-first exits')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no execution')
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("POLITICIAN-FIRST EXIT EXECUTION")
    print("="*80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE EXECUTION'}")
    print("="*80 + "\n")
    
    # Connect to IBKR
    ib = connect_ibkr()
    
    # Get current positions
    positions = get_current_positions(ib)
    print(f"\n📊 Current positions: {len(positions)}")
    
    # Find positions to exit
    exits_needed = []
    for symbol in POSITIONS_TO_EXIT:
        if symbol in positions:
            pos = positions[symbol]
            exits_needed.append({
                'symbol': symbol,
                'quantity': pos['quantity'],
                'contract': pos['contract'],
                'avg_cost': pos['avg_cost']
            })
            print(f"   ❌ {symbol}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f} - NEEDS EXIT")
        else:
            print(f"   ✓ {symbol}: Not held (already exited or never owned)")
    
    # Check positions to keep
    print(f"\n📊 Positions to KEEP (politician-backed):")
    for symbol in POSITIONS_TO_KEEP:
        if symbol in positions:
            pos = positions[symbol]
            print(f"   ✅ {symbol}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f} - KEEPING")
    
    if not exits_needed:
        print("\n✅ No exits needed - all positions already exited!")
        ib.disconnect()
        return
    
    print(f"\n{'='*80}")
    print(f"EXECUTING {len(exits_needed)} EXITS")
    print(f"{'='*80}\n")
    
    if not args.dry_run:
        confirm = input("⚠️  Confirm execution? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("❌ Aborted by user")
            ib.disconnect()
            return
    
    # Execute exits
    results = []
    total_proceeds = 0.0
    
    for pos in exits_needed:
        symbol = pos['symbol']
        quantity = pos['quantity']
        print(f"\n[EXIT] {symbol} ({quantity} shares):")
        
        result = execute_exit(ib, symbol, quantity, pos['contract'], dry_run=args.dry_run)
        results.append(result)
        
        if result['fill_price']:
            proceeds = result['fill_price'] * quantity
            total_proceeds += proceeds
            print(f"   💰 Proceeds: ${proceeds:.2f}")
    
    # Summary
    print("\n" + "="*80)
    print("EXIT SUMMARY")
    print("="*80)
    
    filled = [r for r in results if r['status'] == 'FILLED']
    cancelled = [r for r in results if r['status'] == 'CANCELLED']
    errors = [r for r in results if r['status'] == 'ERROR']
    
    print(f"   ✅ Filled: {len(filled)}")
    print(f"   ❌ Cancelled: {len(cancelled)}")
    print(f"   ⚠️  Errors: {len(errors)}")
    print(f"   💰 Total Proceeds: ${total_proceeds:.2f}")
    
    if cancelled:
        print("\n⚠️  CANCELLED ORDERS:")
        for r in cancelled:
            print(f"   {r['symbol']}: {r.get('error', 'Unknown reason')}")
    
    if errors:
        print("\n❌ ERRORS:")
        for r in errors:
            print(f"   {r['symbol']}: {r['error']}")
    
    print("="*80 + "\n")
    
    # Disconnect
    ib.disconnect()
    logger.info("🔌 Disconnected from IBKR")


if __name__ == '__main__':
    main()
