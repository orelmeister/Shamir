"""
Phase 3: Portfolio Manager
Executes rebalancing based on analyst recommendations with 5% improvement threshold.
Manages stop losses, trailing stops, and position limits.
"""
import json
import logging
import os
import sys
from datetime import datetime
import pytz

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_insync import IB, Stock, Order
import ib_insync.util as ib_util
import pandas as pd

# Import shared utilities
from shared_state.state_manager import read_state, write_state
from market_hours import is_market_open

# Configuration
IB_HOST = '127.0.0.1'
IB_PORT = 4001
MAX_POSITIONS = 5
REBALANCE_THRESHOLD = 0.05  # 5% improvement required
STOP_LOSS_PCT = 0.10  # -10% stop loss
TRAILING_STOP_TRIGGER = 0.20  # Activate at +20% gain
TRAILING_STOP_PCT = 0.10  # 10% trailing stop

# Position tracking file
POSITION_TRACKING_FILE = "shared_state/position_tracking.json"

# Generate run ID
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'portfolio_manager_{RUN_ID}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [PortfolioMgr] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PositionTracker:
    """Manages position metadata including entry prices, stops, and trailing stops."""
    
    def __init__(self, tracking_file=POSITION_TRACKING_FILE):
        self.tracking_file = tracking_file
        self.positions = self._load_positions()
    
    def _load_positions(self):
        """Load position data from JSON file."""
        if os.path.exists(self.tracking_file):
            with open(self.tracking_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_positions(self):
        """Save position data to JSON file."""
        os.makedirs(os.path.dirname(self.tracking_file), exist_ok=True)
        with open(self.tracking_file, 'w') as f:
            json.dump(self.positions, f, indent=2)
    
    def add_position(self, symbol, entry_price, quantity, entry_date=None):
        """Record a new position with stop loss tracking."""
        if entry_date is None:
            entry_date = datetime.now().isoformat()
        
        stop_loss_price = entry_price * (1 - STOP_LOSS_PCT)
        
        self.positions[symbol] = {
            "entry_price": entry_price,
            "entry_date": entry_date,
            "quantity": quantity,
            "stop_loss_price": stop_loss_price,
            "trailing_stop_active": False,
            "trailing_stop_price": None,
            "highest_price": entry_price,
            "current_return_pct": 0.0,
            "days_held": 0
        }
        self._save_positions()
        return self.positions[symbol]
    
    def update_position(self, symbol, current_price):
        """
        Update position tracking with current price.
        Returns: 'HOLD', 'STOP_OUT', or 'TRAILING_STOP_HIT'
        """
        if symbol not in self.positions:
            return 'HOLD'
        
        pos = self.positions[symbol]
        entry_price = pos["entry_price"]
        current_return_pct = (current_price - entry_price) / entry_price
        pos["current_return_pct"] = current_return_pct
        
        # Update highest price
        if current_price > pos["highest_price"]:
            pos["highest_price"] = current_price
        
        # Check -10% stop loss
        if current_price <= pos["stop_loss_price"]:
            self._save_positions()
            return 'STOP_OUT'
        
        # Activate trailing stop at +20% gain
        if not pos["trailing_stop_active"] and current_return_pct >= TRAILING_STOP_TRIGGER:
            pos["trailing_stop_active"] = True
            pos["trailing_stop_price"] = current_price * (1 - TRAILING_STOP_PCT)
            self._save_positions()
            return 'HOLD'
        
        # Update trailing stop (10% below highest price)
        if pos["trailing_stop_active"]:
            new_trailing_stop = pos["highest_price"] * (1 - TRAILING_STOP_PCT)
            pos["trailing_stop_price"] = max(pos["trailing_stop_price"], new_trailing_stop)
            
            # Check if trailing stop hit
            if current_price <= pos["trailing_stop_price"]:
                self._save_positions()
                return 'TRAILING_STOP_HIT'
        
        self._save_positions()
        return 'HOLD'
    
    def remove_position(self, symbol):
        """Remove position from tracking."""
        if symbol in self.positions:
            del self.positions[symbol]
            self._save_positions()
    
    def get_position(self, symbol):
        """Get position tracking data."""
        return self.positions.get(symbol, None)
    
    def get_all_positions(self):
        """Get all tracked positions."""
        return self.positions


def calculate_expected_return(sharpe_ratio):
    """Convert Sharpe ratio to expected return estimate."""
    risk_free_rate = 0.04
    assumed_volatility = 0.15
    return risk_free_rate + (sharpe_ratio * assumed_volatility)


def should_rebalance(current_positions, top_picks):
    """
    Determine if rebalancing is warranted based on 5% improvement threshold.
    Returns: (should_rebalance, current_return, optimized_return, improvement_pct)
    """
    if not current_positions:
        logger.info("📊 No current positions. Will build portfolio from top picks.")
        return (True, 0.0, 0.0, 0.0)
    
    # Calculate current portfolio expected return
    total_value = sum(pos.marketValue for pos in current_positions)
    current_weighted_return = 0.0
    
    for pos in current_positions:
        symbol = pos.contract.symbol
        weight = pos.marketValue / total_value
        
        # Find Sharpe ratio from top_picks
        sharpe = next((pick['sharpe_ratio'] for pick in top_picks if pick['ticker'] == symbol), 0.0)
        expected_return = calculate_expected_return(sharpe)
        current_weighted_return += weight * expected_return
        
        logger.info(f"   Current: {symbol} ({weight*100:.1f}% weight, Sharpe {sharpe:.2f}, Expected {expected_return*100:.1f}%)")
    
    # Calculate optimized portfolio return (top N equal-weighted)
    num_picks = min(len(top_picks), MAX_POSITIONS)
    if num_picks == 0:
        logger.warning("⚠️ No top picks available. Cannot optimize.")
        return (False, current_weighted_return, 0.0, 0.0)
    
    optimized_return = 0.0
    for pick in top_picks[:num_picks]:
        weight = 1.0 / num_picks
        sharpe = pick['sharpe_ratio']
        expected_return = calculate_expected_return(sharpe)
        optimized_return += weight * expected_return
        
        logger.info(f"   Optimized: {pick['ticker']} ({weight*100:.1f}% weight, Sharpe {sharpe:.2f}, Expected {expected_return*100:.1f}%)")
    
    # Calculate improvement
    improvement = optimized_return - current_weighted_return
    improvement_pct = improvement / current_weighted_return if current_weighted_return > 0 else float('inf')
    
    logger.info(f"📊 Portfolio Analysis:")
    logger.info(f"   Current Expected Return: {current_weighted_return*100:.2f}%")
    logger.info(f"   Optimized Expected Return: {optimized_return*100:.2f}%")
    logger.info(f"   Improvement: {improvement*100:.2f}% ({improvement_pct*100:.1f}%)")
    logger.info(f"   Threshold: {REBALANCE_THRESHOLD*100:.1f}%")
    
    should_reb = improvement_pct > REBALANCE_THRESHOLD
    
    if should_reb:
        logger.info(f"✅ Improvement ({improvement_pct*100:.1f}%) exceeds threshold. REBALANCING.")
    else:
        logger.info(f"🔒 Improvement ({improvement_pct*100:.1f}%) below threshold. HOLDING.")
    
    return (should_reb, current_weighted_return, optimized_return, improvement_pct)


def check_stops_and_exits(position_tracker):
    """
    Check all positions for stop loss hits.
    Returns list of symbols to sell.
    """
    logger.info("Checking stop losses and trailing stops...")
    
    ib = IB()
    positions_to_sell = []
    
    try:
        ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
        ib.reqMarketDataType(3)
        
        current_positions = ib.portfolio()
        
        for pos in current_positions:
            symbol = pos.contract.symbol
            current_price = pos.marketPrice
            
            if current_price <= 0:
                logger.warning(f"Invalid price for {symbol}: {current_price}")
                continue
            
            action = position_tracker.update_position(symbol, current_price)
            
            if action == 'STOP_OUT':
                pos_data = position_tracker.get_position(symbol)
                logger.critical(f"🛑 STOP LOSS: {symbol} @ ${current_price:.2f} (entry ${pos_data['entry_price']:.2f})")
                positions_to_sell.append((symbol, pos.contract, pos.position, "STOP_LOSS"))
            
            elif action == 'TRAILING_STOP_HIT':
                pos_data = position_tracker.get_position(symbol)
                logger.info(f"📉 TRAILING STOP: {symbol} @ ${current_price:.2f} (peak ${pos_data['highest_price']:.2f}, +{pos_data['current_return_pct']*100:.1f}%)")
                positions_to_sell.append((symbol, pos.contract, pos.position, "TRAILING_STOP"))
            
            elif action == 'HOLD':
                pos_data = position_tracker.get_position(symbol)
                if pos_data:
                    gain_pct = pos_data['current_return_pct'] * 100
                    trailing = "ACTIVE" if pos_data['trailing_stop_active'] else "NOT ACTIVE"
                    logger.info(f"✅ HOLD: {symbol} @ ${current_price:.2f} ({gain_pct:+.1f}%, trailing: {trailing})")
        
        # Execute sell orders
        for symbol, contract, quantity, reason in positions_to_sell:
            logger.info(f"Selling {abs(quantity)} shares of {symbol} ({reason})...")
            order = Order(action="SELL", totalQuantity=abs(quantity), orderType='MKT', outsideRth=True)
            trade = ib.placeOrder(contract, order)
            ib.sleep(2)
            logger.info(f"Sell order placed for {symbol}")
            position_tracker.remove_position(symbol)
        
        if positions_to_sell:
            logger.info(f"Sold {len(positions_to_sell)} positions due to stops.")
        else:
            logger.info("No stops triggered.")
    
    except Exception as e:
        logger.error(f"Error checking stops: {e}", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
    
    return [sym for sym, _, _, _ in positions_to_sell]


def execute_rebalance(top_picks, position_tracker):
    """
    Rebalance portfolio to equal weight across top N picks.
    Returns dict with status and executed trades.
    """
    ib = IB()
    
    try:
        logger.info("Connecting to IBKR for rebalancing...")
        ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
        ib.reqMarketDataType(3)
        
        account_summary = ib.accountSummary()
        portfolio_value_data = next((v for v in account_summary if v.tag == 'NetLiquidation' and v.currency == 'USD'), None)
        
        if not portfolio_value_data:
            logger.error("Could not determine Net Liquidation.")
            return {"status": "FAILURE", "reason": "NetLiquidation not found"}
        
        total_portfolio_value = float(portfolio_value_data.value)
        current_positions = ib.portfolio()
        
        logger.info(f"Portfolio Value: ${total_portfolio_value:,.2f}")
        logger.info(f"Current positions: {len(current_positions)}")
        
        # Target portfolio
        target_tickers = [pick['ticker'] for pick in top_picks[:MAX_POSITIONS]]
        num_target = len(target_tickers)
        target_value_per_position = total_portfolio_value / num_target
        
        logger.info(f"Target: {num_target} stocks @ ${target_value_per_position:,.2f} each")
        logger.info(f"Target tickers: {target_tickers}")
        
        trades_to_make = []
        
        # STEP 1: Sell positions not in target
        for pos in current_positions:
            symbol = pos.contract.symbol
            if symbol not in target_tickers:
                quantity = int(abs(pos.position))
                logger.info(f"🔻 Selling {quantity} {symbol} (not in top {MAX_POSITIONS})")
                trades_to_make.append({"action": "SELL", "ticker": symbol, "quantity": quantity})
                position_tracker.remove_position(symbol)
        
        # STEP 2: Adjust positions in target portfolio
        for pos in current_positions:
            symbol = pos.contract.symbol
            if symbol in target_tickers:
                current_value = pos.marketValue
                current_price = pos.marketPrice
                
                if current_price <= 0:
                    continue
                
                value_diff = target_value_per_position - current_value
                if abs(value_diff) / target_value_per_position < 0.10:  # 10% tolerance
                    logger.info(f"✅ {symbol} within tolerance")
                    continue
                
                num_shares = int(abs(value_diff) / current_price)
                action = "BUY" if value_diff > 0 else "SELL"
                
                if num_shares > 0:
                    logger.info(f"{'📈' if action=='BUY' else '📉'} {action} {num_shares} {symbol}")
                    trades_to_make.append({
                        "action": action,
                        "ticker": symbol,
                        "quantity": num_shares,
                        "price": current_price if action == "BUY" else None
                    })
        
        # STEP 3: Buy new positions
        current_symbols = {pos.contract.symbol for pos in current_positions}
        for ticker in target_tickers:
            if ticker not in current_symbols:
                logger.info(f"Fetching price for new stock: {ticker}")
                contract = Stock(ticker, 'SMART', 'USD')
                ticker_data = ib.reqMktData(contract, '', True, False, [])
                ib.sleep(2)
                
                price = ticker_data.marketPrice()
                if pd.notna(price) and price > 0:
                    quantity = int(target_value_per_position / price)
                    if quantity > 0:
                        logger.info(f"🆕 BUY {quantity} {ticker} @ ${price:.2f}")
                        trades_to_make.append({
                            "action": "BUY",
                            "ticker": ticker,
                            "quantity": quantity,
                            "price": price
                        })
                else:
                    logger.error(f"Invalid price for {ticker}: {price}")
        
        if not trades_to_make:
            logger.info("Portfolio already matches target. No trades needed.")
            return {"status": "SUCCESS", "reason": "Already optimized", "executed_trades": []}
        
        # STEP 4: Execute trades
        logger.info(f"Executing {len(trades_to_make)} trades...")
        executed_trades = []
        
        for trade_order in trades_to_make:
            contract = Stock(trade_order['ticker'], 'SMART', 'USD')
            order = Order(
                action=trade_order['action'],
                totalQuantity=trade_order['quantity'],
                orderType='MKT',
                outsideRth=True
            )
            trade = ib.placeOrder(contract, order)
            logger.info(f"Placed {trade_order['action']} order: {trade_order['quantity']} {trade_order['ticker']}")
            
            # Add position tracking for buys
            if trade_order['action'] == 'BUY' and 'price' in trade_order:
                entry_price = trade_order['price']
                quantity = trade_order['quantity']
                ticker = trade_order['ticker']
                
                pos_data = position_tracker.add_position(ticker, entry_price, quantity)
                logger.info(f"📊 Tracking {ticker}: Entry=${entry_price:.2f}, Stop=${pos_data['stop_loss_price']:.2f}")
            
            executed_trades.append(f"{trade_order['action']} {trade_order['quantity']} {trade_order['ticker']}")
        
        logger.info("Waiting for trades to settle...")
        ib.sleep(15)
        
        return {"status": "SUCCESS", "executed_trades": executed_trades}
    
    except Exception as e:
        logger.critical(f"Failed to rebalance: {e}", exc_info=True)
        return {"status": "FAILURE", "reason": str(e), "executed_trades": []}
    finally:
        if ib.isConnected():
            ib.disconnect()


def main():
    """Main execution for Phase 3: Portfolio Management"""
    logger.info("=" * 80)
    logger.info("PHASE 3: PORTFOLIO MANAGER - Starting")
    logger.info("=" * 80)
    
    position_tracker = PositionTracker()
    
    # STEP 1: Check stops if market is open
    if is_market_open():
        logger.info("Market is open. Checking stops first...")
        stopped_symbols = check_stops_and_exits(position_tracker)
        if stopped_symbols:
            logger.info(f"Stopped out of: {stopped_symbols}")
    else:
        logger.info("Market closed - skipping stop checks.")
    
    # STEP 2: Read analysis results
    phase_state = read_state('phase_state')
    current_phase = phase_state.get('current_phase', 'unknown')
    
    if current_phase != 'analysis_complete':
        logger.error(f"Expected 'analysis_complete', got '{current_phase}'. Cannot proceed.")
        sys.exit(1)
    
    top_picks = phase_state.get('top_picks', [])
    
    if not top_picks:
        logger.info("No top picks to evaluate. Ending cycle.")
        write_state('phase_state', {
            'current_phase': 'execution_complete',
            'executed_trades': [],
            'reason': 'No top picks from analysis',
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(0)
    
    logger.info(f"Received {len(top_picks)} top picks: {[p['ticker'] for p in top_picks]}")
    
    # STEP 3: Portfolio optimization check
    ib = IB()
    try:
        logger.info("Evaluating portfolio optimization...")
        ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
        ib.reqMarketDataType(3)
        
        current_positions = ib.portfolio()
        logger.info(f"Current portfolio: {len(current_positions)} positions")
        
        should_reb, current_ret, optimized_ret, improvement = should_rebalance(current_positions, top_picks)
        
        if not should_reb:
            logger.info("🔒 HOLDING - insufficient improvement to justify rebalancing.")
            write_state('phase_state', {
                'current_phase': 'execution_complete',
                'executed_trades': [],
                'reason': f'Held positions (improvement {improvement*100:.1f}% < threshold {REBALANCE_THRESHOLD*100:.1f}%)',
                'timestamp': datetime.now().isoformat()
            })
            sys.exit(0)
        
        logger.info("✅ REBALANCING warranted - proceeding...")
    
    except Exception as e:
        logger.error(f"Error during portfolio evaluation: {e}", exc_info=True)
        write_state('phase_state', {
            'current_phase': 'execution_complete',
            'executed_trades': [],
            'reason': f'Evaluation error: {str(e)}',
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(1)
    finally:
        if ib.isConnected():
            ib.disconnect()
    
    # STEP 4: Execute rebalancing
    if not is_market_open():
        logger.warning("Market is closed. Cannot execute trades now.")
        logger.info("TODO: Implement pre-market MOO order placement here")
        write_state('phase_state', {
            'current_phase': 'execution_complete',
            'executed_trades': [],
            'reason': 'Market closed - trades deferred',
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(0)
    
    logger.info("Market is open. Executing rebalance...")
    trade_result = execute_rebalance(top_picks, position_tracker)
    
    logger.info(f"Rebalancing result: {trade_result.get('status')}")
    
    # Update phase state
    write_state('phase_state', {
        'current_phase': 'execution_complete',
        'executed_trades': trade_result.get('executed_trades', []),
        'rebalance_status': trade_result.get('status'),
        'timestamp': datetime.now().isoformat()
    })
    
    # Update positions state with current holdings
    positions_data = read_state('positions_state')
    positions_data['weekly_positions'] = list(position_tracker.get_all_positions().keys())
    positions_data['last_updated'] = datetime.now().isoformat()
    write_state('positions_state', positions_data)
    
    logger.info("=" * 80)
    logger.info(f"PHASE 3: PORTFOLIO MANAGER - Complete")
    logger.info(f"Executed {len(trade_result.get('executed_trades', []))} trades")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error in Portfolio Manager: {e}", exc_info=True)
        sys.exit(1)
