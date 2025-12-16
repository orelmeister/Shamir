"""
Execute Form4 Orders - Manual Execution Script
Executes sell orders FIRST (exit manager), then buy orders (approved positions)

Usage:
    python execute_form4_orders.py             # Live execution
    python execute_form4_orders.py --dry-run   # Test mode (no orders)
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_insync import IB, Stock, MarketOrder, util
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/execute_form4_orders_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# IBKR Connection
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001
IBKR_CLIENT_ID = 12  # Unique client ID for manual executor


class Form4OrderExecutor:
    """Execute Form4 orders: SELL first, then BUY"""
    
    def __init__(self):
        self.ib = None
        self.ibkr_connected = False
        self.output_dir = Path("weekly_bot/form4_reports")
    
    def connect_to_ibkr(self) -> bool:
        """Connect to IBKR"""
        try:
            self.ib = IB()
            print(f"\n[CONNECT] Connecting to IBKR at {IBKR_HOST}:{IBKR_PORT}...")
            logger.info(f"Connecting to IBKR at {IBKR_HOST}:{IBKR_PORT}")
            
            util.run(self.ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID))
            self.ib.reqMarketDataType(3)  # Delayed data
            
            self.ibkr_connected = True
            print("✅ Connected to IBKR\n")
            logger.info("Connected to IBKR successfully")
            return True
            
        except Exception as e:
            logger.error(f"IBKR connection failed: {e}")
            print(f"\n❌ IBKR CONNECTION FAILED: {e}")
            print("   Make sure TWS/Gateway is running on port 4001")
            return False
    
    def disconnect_from_ibkr(self):
        """Disconnect from IBKR"""
        if self.ib and self.ibkr_connected:
            try:
                self.ib.disconnect()
                logger.info("Disconnected from IBKR")
                print("\n[DISCONNECT] Disconnected from IBKR")
            except Exception as e:
                logger.warning(f"Error disconnecting: {e}")
    
    def get_buying_power(self) -> float:
        """Get available buying power"""
        if not self.ibkr_connected:
            return 0.0
        
        try:
            account_values = self.ib.accountValues()
            for av in account_values:
                if av.tag == 'ExcessLiquidity' and av.currency == 'USD':
                    buying_power = float(av.value)
                    logger.info(f"Buying Power: ${buying_power:.2f}")
                    return buying_power
            
            logger.warning("ExcessLiquidity not found")
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching buying power: {e}")
            return 0.0
    
    def get_current_positions(self) -> List[Dict]:
        """Get all current portfolio positions"""
        if not self.ibkr_connected:
            return []
        
        try:
            portfolio = self.ib.portfolio()
            positions = []
            
            for pos in portfolio:
                if pos.position == 0:
                    continue
                
                positions.append({
                    'symbol': pos.contract.symbol,
                    'quantity': pos.position,
                    'avg_cost': pos.averageCost,
                    'current_price': pos.marketPrice,
                    'market_value': pos.marketValue,
                    'unrealized_pnl': pos.unrealizedPNL,
                    'pnl_pct': (pos.unrealizedPNL / abs(pos.averageCost * pos.position)) * 100 if pos.position != 0 else 0
                })
            
            return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def execute_sell_order(self, symbol: str, quantity: int, reason: str, dry_run: bool = False) -> Dict:
        """Execute a sell order"""
        if dry_run:
            print(f"   [DRY RUN] Would sell {quantity} shares of {symbol}")
            logger.info(f"DRY RUN: Would sell {quantity} {symbol} - {reason}")
            return {'status': 'dry_run', 'symbol': symbol, 'quantity': quantity}
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            print(f"   📉 Placing SELL order: {quantity} shares of {symbol}")
            logger.info(f"Placing SELL order: {quantity} {symbol} - {reason}")
            
            order = MarketOrder('SELL', quantity)
            order.tif = 'DAY'
            order.outsideRth = False
            
            trade = self.ib.placeOrder(contract, order)
            
            # Wait for fill (up to 30 seconds)
            for i in range(30):
                self.ib.sleep(1)
                if trade.orderStatus.status in ['Filled', 'Cancelled', 'Inactive']:
                    break
            
            if trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                total_proceeds = fill_price * quantity
                
                print(f"   ✅ SOLD: {quantity} shares @ ${fill_price:.2f} = ${total_proceeds:.2f}")
                logger.info(f"SOLD: {quantity} {symbol} @ ${fill_price:.2f}")
                
                return {
                    'status': 'filled',
                    'symbol': symbol,
                    'quantity': quantity,
                    'fill_price': fill_price,
                    'total_proceeds': total_proceeds,
                    'order_id': trade.order.orderId
                }
            else:
                print(f"   ⚠️  Order not filled: {trade.orderStatus.status}")
                logger.warning(f"SELL order not filled: {symbol} - {trade.orderStatus.status}")
                return {'status': 'not_filled', 'symbol': symbol, 'reason': trade.orderStatus.status}
                
        except Exception as e:
            logger.error(f"Error selling {symbol}: {e}")
            print(f"   ❌ Error: {e}")
            return {'status': 'error', 'symbol': symbol, 'error': str(e)}
    
    def execute_buy_order(self, symbol: str, quantity: int, cost: float, dry_run: bool = False) -> Dict:
        """Execute a buy order"""
        if dry_run:
            print(f"   [DRY RUN] Would buy {quantity} shares of {symbol} (~${cost:.2f})")
            logger.info(f"DRY RUN: Would buy {quantity} {symbol}")
            return {'status': 'dry_run', 'symbol': symbol, 'quantity': quantity}
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Check if complex ETF
            complex_etfs = {'BITB', 'BITO', 'BTF', 'SQQQ', 'TQQQ', 'UPRO', 'SPXU', 'UVXY', 'SVXY'}
            if symbol in complex_etfs:
                print(f"   ⚠️  {symbol}: Complex/Leveraged ETF - requires special IBKR permissions")
                logger.warning(f"Skipping {symbol}: Complex ETF requires permissions")
                return {'status': 'skipped', 'symbol': symbol, 'reason': 'complex_etf'}
            
            print(f"   📈 Placing BUY order: {quantity} shares of {symbol}")
            logger.info(f"Placing BUY order: {quantity} {symbol}")
            
            order = MarketOrder('BUY', quantity)
            order.tif = 'DAY'
            order.outsideRth = False
            
            trade = self.ib.placeOrder(contract, order)
            
            # Wait for fill (up to 30 seconds)
            for i in range(30):
                self.ib.sleep(1)
                if trade.orderStatus.status in ['Filled', 'Cancelled', 'Inactive']:
                    break
            
            if trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                total_cost = fill_price * quantity
                
                print(f"   ✅ BOUGHT: {quantity} shares @ ${fill_price:.2f} = ${total_cost:.2f}")
                logger.info(f"BOUGHT: {quantity} {symbol} @ ${fill_price:.2f}")
                
                return {
                    'status': 'filled',
                    'symbol': symbol,
                    'quantity': quantity,
                    'fill_price': fill_price,
                    'total_cost': total_cost,
                    'order_id': trade.order.orderId
                }
            else:
                print(f"   ⚠️  Order not filled: {trade.orderStatus.status}")
                logger.warning(f"BUY order not filled: {symbol} - {trade.orderStatus.status}")
                return {'status': 'not_filled', 'symbol': symbol, 'reason': trade.orderStatus.status}
                
        except Exception as e:
            logger.error(f"Error buying {symbol}: {e}")
            print(f"   ❌ Error: {e}")
            return {'status': 'error', 'symbol': symbol, 'error': str(e)}
    
    def load_latest_approved_positions(self) -> Dict:
        """Load most recent approved positions file"""
        try:
            position_files = sorted(
                self.output_dir.glob("approved_positions_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not position_files:
                logger.warning("No approved positions file found")
                return {}
            
            latest_file = position_files[0]
            print(f"\n[LOAD] Loading approved positions from {latest_file.name}")
            logger.info(f"Loading positions from {latest_file.name}")
            
            with open(latest_file, 'r') as f:
                return json.load(f)
        
        except Exception as e:
            logger.error(f"Failed to load approved positions: {e}")
            return {}
    
    def run_sell_phase(self, dry_run: bool = False) -> Dict:
        """
        PHASE 1: SELL - Run exit manager logic manually
        Evaluates all positions and sells those that meet exit criteria
        """
        print("\n" + "="*80)
        print("PHASE 1: SELL ORDERS (Exit Analysis)")
        print("="*80)
        
        # Import exit manager
        try:
            from form4_exit_manager import Form4ExitManager
            print("\n[+] Initializing exit manager...")
            exit_manager = Form4ExitManager()
            
            print("[+] Running exit analysis...\n")
            exit_results = exit_manager.run(dry_run=dry_run)
            
            print("\n✅ Exit phase complete")
            logger.info(f"Exit phase complete: {exit_results}")
            
            return exit_results if exit_results else {'status': 'completed', 'positions_analyzed': 0}
            
        except Exception as e:
            logger.error(f"Exit manager failed: {e}", exc_info=True)
            print(f"\n❌ Exit manager error: {e}")
            print("⚠️  Continuing to buy phase despite exit failure...")
            return {'status': 'error', 'error': str(e)}
    
    def run_buy_phase(self, dry_run: bool = False) -> Dict:
        """
        PHASE 2: BUY - Execute approved positions from latest JSON
        Scales down orders if insufficient capital
        """
        print("\n" + "="*80)
        print("PHASE 2: BUY ORDERS (Approved Positions)")
        print("="*80)
        
        # Load approved positions
        approved_data = self.load_latest_approved_positions()
        
        if not approved_data or not approved_data.get('approved_positions'):
            print("\n⚠️  No approved positions to execute")
            logger.info("No approved positions found")
            return {'status': 'no_positions'}
        
        approved_positions = approved_data['approved_positions']
        print(f"\n[FOUND] {len(approved_positions)} approved position(s)")
        
        # Check buying power
        buying_power = self.get_buying_power()
        total_needed = sum(pos['cost'] for pos in approved_positions)
        
        print(f"\n💰 CAPITAL CHECK:")
        print(f"   Available: ${buying_power:.2f}")
        print(f"   Needed: ${total_needed:.2f}")
        
        # Apply scaling if needed
        scale_factor = 1.0
        if buying_power < total_needed:
            if buying_power < total_needed * 0.40:
                print(f"\n❌ INSUFFICIENT CAPITAL (need at least 40%)")
                print(f"   Required minimum: ${total_needed * 0.40:.2f}")
                logger.error(f"Insufficient capital: ${buying_power:.2f} < ${total_needed * 0.40:.2f}")
                return {'status': 'insufficient_capital', 'buying_power': buying_power, 'needed': total_needed}
            else:
                scale_factor = buying_power / total_needed
                print(f"\n⚠️  SCALING DOWN ORDERS: {scale_factor:.1%}")
                logger.info(f"Scaling orders by {scale_factor:.1%}")
        else:
            print(f"   ✅ Sufficient capital\n")
        
        # Execute buy orders
        print("\n" + "="*80)
        print("EXECUTING BUY ORDERS")
        print("="*80 + "\n")
        
        buy_results = []
        
        for pos in approved_positions:
            symbol = pos['symbol']
            original_shares = pos['shares']
            shares = max(1, int(original_shares * scale_factor))
            cost = shares * pos['price']
            
            if scale_factor < 1.0:
                print(f"\n[{symbol}] Scaled: {original_shares} → {shares} shares (${cost:.2f})")
            else:
                print(f"\n[{symbol}] {shares} shares (${cost:.2f})")
            
            result = self.execute_buy_order(symbol, shares, cost, dry_run)
            buy_results.append(result)
            
            self.ib.sleep(1)  # Pace orders
        
        # Summary
        filled = [r for r in buy_results if r['status'] == 'filled']
        skipped = [r for r in buy_results if r['status'] == 'skipped']
        failed = [r for r in buy_results if r['status'] in ['not_filled', 'error']]
        
        print("\n" + "="*80)
        print("BUY PHASE SUMMARY")
        print("="*80)
        print(f"✅ Filled: {len(filled)}")
        print(f"⏭️  Skipped: {len(skipped)}")
        print(f"❌ Failed: {len(failed)}")
        
        if filled:
            total_deployed = sum(r['total_cost'] for r in filled)
            print(f"\n💰 Total Capital Deployed: ${total_deployed:.2f}")
        
        return {
            'status': 'completed',
            'filled': filled,
            'skipped': skipped,
            'failed': failed,
            'scale_factor': scale_factor
        }
    
    def run(self, dry_run: bool = False):
        """
        Main execution: SELL FIRST, then BUY
        """
        print("\n" + "="*80)
        print("FORM 4 ORDER EXECUTOR")
        print("="*80)
        print(f"Mode: {'DRY RUN (No Execution)' if dry_run else 'LIVE TRADING'}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Market Hours: 9:30 AM - 4:00 PM ET")
        print("="*80)
        
        # Connect to IBKR
        if not self.connect_to_ibkr():
            print("\n❌ Cannot proceed without IBKR connection")
            return
        
        try:
            # PHASE 1: SELL (Exit Manager)
            sell_results = self.run_sell_phase(dry_run)
            
            # PHASE 2: BUY (Approved Positions)
            buy_results = self.run_buy_phase(dry_run)
            
            # Final Summary
            print("\n" + "="*80)
            print("EXECUTION COMPLETE")
            print("="*80)
            print(f"\n📊 SELL PHASE: {sell_results.get('status', 'unknown')}")
            print(f"📊 BUY PHASE: {buy_results.get('status', 'unknown')}")
            print("\n" + "="*80 + "\n")
            
            logger.info("Execution complete")
            logger.info(f"Sell results: {sell_results}")
            logger.info(f"Buy results: {buy_results}")
            
        finally:
            self.disconnect_from_ibkr()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Execute Form4 Orders: SELL then BUY")
    parser.add_argument('--dry-run', action='store_true', help="Test mode (no actual orders)")
    
    args = parser.parse_args()
    
    executor = Form4OrderExecutor()
    executor.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
