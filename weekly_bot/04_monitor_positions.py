"""
Phase 4: Position Monitor
Continuous monitoring of positions with stop-loss and trailing stop checks.
Runs in a loop during market hours.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_insync import IB, Order
import ib_insync.util as ib_util

# Import shared utilities
from shared_state.state_manager import read_state, write_state
from market_hours import is_market_open

# Import position tracker from Phase 3
sys.path.append(os.path.join(os.path.dirname(__file__)))
from weekly_bot import portfolio_manager_03 as pm

# Configuration
IB_HOST = '127.0.0.1'
IB_PORT = 4001
CHECK_INTERVAL = 300  # 5 minutes

# Generate run ID
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'monitor_{RUN_ID}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Monitor] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def monitor_positions(position_tracker, duration_minutes=None):
    """
    Monitor positions continuously during market hours.
    
    Args:
        position_tracker: PositionTracker instance
        duration_minutes: Optional limit on monitoring duration (for testing)
    """
    logger.info("Starting position monitoring...")
    start_time = time.time()
    check_count = 0
    
    while True:
        # Check if we should stop (duration limit or market closed)
        if duration_minutes:
            elapsed = (time.time() - start_time) / 60
            if elapsed >= duration_minutes:
                logger.info(f"Monitoring duration limit reached ({duration_minutes} min). Stopping.")
                break
        
        if not is_market_open():
            logger.info("Market closed. Stopping monitoring.")
            break
        
        check_count += 1
        logger.info(f"=== Position Check #{check_count} ===")
        
        ib = IB()
        try:
            ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
            ib.reqMarketDataType(3)
            
            current_positions = ib.portfolio()
            
            if not current_positions:
                logger.info("No positions to monitor.")
            
            positions_to_sell = []
            
            for pos in current_positions:
                symbol = pos.contract.symbol
                current_price = pos.marketPrice
                
                if current_price <= 0:
                    logger.warning(f"Invalid price for {symbol}: {current_price}")
                    continue
                
                # Update position and check for stops
                action = position_tracker.update_position(symbol, current_price)
                
                if action == 'STOP_OUT':
                    pos_data = position_tracker.get_position(symbol)
                    logger.critical(f"🛑 STOP LOSS HIT: {symbol} @ ${current_price:.2f} (entry ${pos_data['entry_price']:.2f}, -10%)")
                    positions_to_sell.append((symbol, pos.contract, pos.position, "STOP_LOSS"))
                
                elif action == 'TRAILING_STOP_HIT':
                    pos_data = position_tracker.get_position(symbol)
                    logger.info(f"📉 TRAILING STOP HIT: {symbol} @ ${current_price:.2f} (highest ${pos_data['highest_price']:.2f}, +{pos_data['current_return_pct']*100:.1f}%)")
                    positions_to_sell.append((symbol, pos.contract, pos.position, "TRAILING_STOP"))
                
                elif action == 'HOLD':
                    pos_data = position_tracker.get_position(symbol)
                    if pos_data:
                        gain_pct = pos_data['current_return_pct'] * 100
                        trailing_status = "ACTIVE" if pos_data['trailing_stop_active'] else "NOT ACTIVE"
                        logger.info(f"[OK] {symbol}: ${current_price:.2f} ({gain_pct:+.1f}%, trailing: {trailing_status})")
            
            # Execute sell orders for stopped positions
            for symbol, contract, quantity, reason in positions_to_sell:
                logger.info(f"Selling {abs(quantity)} shares of {symbol} ({reason})...")
                order = Order(action="SELL", totalQuantity=abs(quantity), orderType='MKT', outsideRth=True)
                trade = ib.placeOrder(contract, order)
                ib.sleep(2)
                logger.info(f"[OK] Sell order placed for {symbol}")
                
                # Remove from tracking
                position_tracker.remove_position(symbol)
                
                # Update shared state
                positions_data = read_state('positions_state')
                if symbol in positions_data.get('weekly_positions', []):
                    positions_data['weekly_positions'].remove(symbol)
                    write_state('positions_state', positions_data)
            
            if positions_to_sell:
                logger.info(f"[WARNING] Sold {len(positions_to_sell)} position(s) due to stops.")
            
        except Exception as e:
            logger.error(f"Error during monitoring check: {e}", exc_info=True)
        finally:
            if ib.isConnected():
                ib.disconnect()
        
        # Wait before next check
        logger.info(f"Next check in {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)
    
    logger.info(f"Monitoring complete. Performed {check_count} checks.")


def main():
    """Main execution for Phase 4: Position Monitoring"""
    logger.info("=" * 80)
    logger.info("PHASE 4: POSITION MONITOR - Starting")
    logger.info("=" * 80)
    
    # Check if market is open
    if not is_market_open():
        logger.info("Market is closed. No monitoring needed.")
        sys.exit(0)
    
    # Initialize position tracker
    position_tracker = pm.PositionTracker()
    
    # Check phase state
    phase_state = read_state('phase_state')
    current_phase = phase_state.get('current_phase', 'unknown')
    
    if current_phase != 'execution_complete':
        logger.warning(f"Phase is '{current_phase}', not 'execution_complete'. Monitoring anyway...")
    
    # Start monitoring (runs until market close)
    try:
        monitor_positions(position_tracker)
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user.")
    
    logger.info("=" * 80)
    logger.info("PHASE 4: POSITION MONITOR - Complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error in Position Monitor: {e}", exc_info=True)
        sys.exit(1)
