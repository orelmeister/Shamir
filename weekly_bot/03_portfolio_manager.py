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

# Autonomous system imports
from observability import get_database, get_tracer
from self_evaluation import PerformanceAnalyzer
from continuous_improvement import ContinuousImprovementEngine

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


def calculate_expected_return(confidence):
    """
    Convert confidence score to expected return estimate.
    Confidence of 0.85-0.95 maps to ~10-20% expected return.
    """
    # Map confidence (0.0-1.0) to expected return
    # 0.75 confidence = 5% return, 0.95 confidence = 20% return
    base_return = 0.02  # 2% base
    confidence_premium = confidence * 0.20  # Up to 20% from confidence
    return base_return + confidence_premium


def should_rebalance(current_positions, top_picks):
    """
    Determine if rebalancing is warranted based on 5% improvement threshold.
    Returns: (should_rebalance, current_return, optimized_return, improvement_pct)
    """
    if not current_positions:
        logger.info("[INFO] No current positions. Will build portfolio from top picks.")
        return (True, 0.0, 0.0, 0.0)
    
    # Calculate current portfolio expected return
    total_value = sum(pos.marketValue for pos in current_positions)
    current_weighted_return = 0.0
    
    for pos in current_positions:
        symbol = pos.contract.symbol
        weight = pos.marketValue / total_value
        
        # Find confidence from top_picks (or use low default if not in list)
        confidence = next((pick['confidence'] for pick in top_picks if pick['ticker'] == symbol), 0.50)
        expected_return = calculate_expected_return(confidence)
        current_weighted_return += weight * expected_return
        
        logger.info(f"   Current: {symbol} ({weight*100:.1f}% weight, Confidence {confidence:.2f}, Expected {expected_return*100:.1f}%)")
    
    # Calculate optimized portfolio return (top N equal-weighted)
    num_picks = min(len(top_picks), MAX_POSITIONS)
    if num_picks == 0:
        logger.warning("[WARNING] No top picks available. Cannot optimize.")
        return (False, current_weighted_return, 0.0, 0.0)
    
    optimized_return = 0.0
    for pick in top_picks[:num_picks]:
        weight = 1.0 / num_picks
        confidence = pick['confidence']
        expected_return = calculate_expected_return(confidence)
        optimized_return += weight * expected_return
        
        logger.info(f"   Optimized: {pick['ticker']} ({weight*100:.1f}% weight, Confidence {confidence:.2f}, Expected {expected_return*100:.1f}%)")
    
    # Calculate improvement
    improvement = optimized_return - current_weighted_return
    improvement_pct = improvement / current_weighted_return if current_weighted_return > 0 else float('inf')
    
    logger.info(f"[INFO] Portfolio Analysis:")
    logger.info(f"   Current Expected Return: {current_weighted_return*100:.2f}%")
    logger.info(f"   Optimized Expected Return: {optimized_return*100:.2f}%")
    logger.info(f"   Improvement: {improvement*100:.2f}% ({improvement_pct*100:.1f}%)")
    logger.info(f"   Threshold: {REBALANCE_THRESHOLD*100:.1f}%")
    
    should_reb = improvement_pct > REBALANCE_THRESHOLD
    
    if should_reb:
        logger.info(f"[OK] Improvement ({improvement_pct*100:.1f}%) exceeds threshold. REBALANCING.")
    else:
        logger.info(f"🔒 Improvement ({improvement_pct*100:.1f}%) below threshold. HOLDING.")
    
    return (should_reb, current_weighted_return, optimized_return, improvement_pct)


def check_stops_and_exits(position_tracker):
    """
    Check all positions for stop loss hits.
    Returns list of symbols to sell.
    """
    logger.info("Checking stop losses and trailing stops...")
    
    # Initialize autonomous system components
    agent_name = "weekly_portfolio_manager"
    db = get_database()
    tracer = get_tracer()
    
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
                    logger.info(f"[OK] HOLD: {symbol} @ ${current_price:.2f} ({gain_pct:+.1f}%, trailing: {trailing})")
        
        # Execute sell orders
        for symbol, contract, quantity, reason in positions_to_sell:
            logger.info(f"Selling {abs(quantity)} shares of {symbol} ({reason})...")
            order = Order(action="SELL", totalQuantity=abs(quantity), orderType='MKT', outsideRth=True)
            trade = ib.placeOrder(contract, order)
            ib.sleep(2)
            logger.info(f"Sell order placed for {symbol}")
            
            # Log trade to database for observability
            try:
                pos_data = position_tracker.get_position(symbol)
                fill_price = trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice > 0 else pos_data['current_price']
                pnl = (fill_price - pos_data['entry_price']) * abs(quantity)
                pnl_pct = ((fill_price - pos_data['entry_price']) / pos_data['entry_price']) * 100
                
                db.log_trade({
                    'timestamp': datetime.now().isoformat(),
                    'symbol': symbol,
                    'action': 'SELL',
                    'quantity': abs(quantity),
                    'price': fill_price,
                    'agent_name': agent_name,
                    'reason': reason,
                    'profit_loss': pnl,
                    'profit_loss_pct': pnl_pct,
                    'metadata': {
                        'entry_price': pos_data['entry_price'],
                        'exit_trigger': reason,
                        'highest_price': pos_data.get('highest_price', fill_price),
                        'stop_loss_price': pos_data.get('stop_loss_price', 0)
                    }
                })
                
                db.remove_active_position(
                    symbol=symbol,
                    exit_price=fill_price,
                    exit_reason=reason,
                    agent_name=agent_name
                )
            except Exception as e:
                logger.warning(f"Failed to log SELL trade for {symbol}: {e}")
            
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
                    logger.info(f"[OK] {symbol} within tolerance")
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
                logger.info(f"[INFO] Tracking {ticker}: Entry=${entry_price:.2f}, Stop=${pos_data['stop_loss_price']:.2f}")
            
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


def load_approved_trades():
    """Load user-approved trades from reviewer."""
    approved_file = "shared_state/approved_trades.json"
    
    if not os.path.exists(approved_file):
        logger.error(f"No approved trades file found at {approved_file}")
        logger.info("[ERROR] Please run portfolio_reviewer.py first to review and approve trades")
        return None
    
    with open(approved_file, 'r') as f:
        data = json.load(f)
    
    logger.info(f"Loaded {data['total_approved']} approved trades (from {data['total_proposed']} proposed)")
    return data['approved_trades']


def execute_approved_trades_only(approved_trades, position_tracker):
    """Execute only user-approved trades."""
    
    # Initialize autonomous system components
    agent_name = "weekly_portfolio_manager"
    db = get_database()
    tracer = get_tracer()
    
    if not approved_trades:
        logger.info("No approved trades to execute")
        return {"status": "SUCCESS", "reason": "No approved trades", "executed_trades": []}
    
    ib = IB()
    
    try:
        logger.info("Connecting to IBKR for execution...")
        ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
        ib.reqMarketDataType(3)
        
        # FIXED CAPITAL ALLOCATION: Weekly bot uses ONLY $2000 budget
        WEEKLY_BOT_BUDGET = 2000.00
        
        account_summary = ib.accountSummary()
        
        # Check both SettledCash (actual cash) and ExcessLiquidity (margin power)
        settled_cash_data = next((v for v in account_summary if v.tag == 'SettledCash' and v.currency == 'USD'), None)
        excess_liquidity_data = next((v for v in account_summary if v.tag == 'ExcessLiquidity' and v.currency == 'USD'), None)
        
        if not settled_cash_data or not excess_liquidity_data:
            logger.error("Could not determine SettledCash or ExcessLiquidity.")
            return {"status": "FAILURE", "reason": "Cash values not found"}
        
        settled_cash = float(settled_cash_data.value)
        excess_liquidity = float(excess_liquidity_data.value)
        
        logger.info(f"SettledCash: ${settled_cash:,.2f}, ExcessLiquidity: ${excess_liquidity:,.2f}")
        
        # Use MINIMUM of: $2000 budget, settled cash, and excess liquidity
        # This prevents order rejections due to insufficient settled cash
        available_cash = min(WEEKLY_BOT_BUDGET, settled_cash, excess_liquidity)
        logger.info(f"Weekly bot budget (capped at $2000, limited by SettledCash): ${available_cash:,.2f}")
        
        current_positions = ib.portfolio()
        executed_trades = []
        total_spent = 0.0
        
        # Calculate capital per buy (split available cash evenly across approved buys)
        approved_buys = [t for t in approved_trades if t['action'] == 'BUY']
        capital_per_buy = available_cash / len(approved_buys) if approved_buys else 0
        
        logger.info(f"Capital per buy (${available_cash:,.2f} / {len(approved_buys)} positions): ${capital_per_buy:,.2f}")
        
        # Helper function to check remaining cash
        def get_remaining_cash():
            """Get current settled cash available."""
            ib.reqAccountSummary()
            ib.sleep(0.5)
            acct = ib.accountSummary()
            cash_item = next((v for v in acct if v.tag == 'SettledCash' and v.currency == 'USD'), None)
            return float(cash_item.value) if cash_item else 0.0
        
        # Process each approved trade
        for approved in approved_trades:
            action = approved['action']
            symbol = approved['symbol']
            
            if action == "SELL":
                # Find position
                pos = next((p for p in current_positions if p.contract.symbol == symbol), None)
                if not pos:
                    logger.warning(f"Cannot sell {symbol} - no position found")
                    continue
                
                quantity = int(abs(pos.position))
                contract = pos.contract
                
                logger.info(f"Selling {quantity} {symbol}...")
                order = Order(action="SELL", totalQuantity=quantity, orderType='MKT', outsideRth=True)
                trade = ib.placeOrder(contract, order)
                ib.sleep(2)
                
                position_tracker.remove_position(symbol)
                executed_trades.append(f"SELL {quantity} {symbol}")
                logger.info(f"[OK] Sold {quantity} {symbol}")
                
                # Log trade to database for observability
                try:
                    fill_price = trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice > 0 else ticker_data.marketPrice()
                    entry_price = pos.avgCost
                    pnl = (fill_price - entry_price) * quantity
                    pnl_pct = ((fill_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                    
                    db.log_trade({
                        'timestamp': datetime.now().isoformat(),
                        'symbol': symbol,
                        'action': 'SELL',
                        'quantity': quantity,
                        'price': fill_price,
                        'agent_name': agent_name,
                        'reason': 'Rebalancing SELL (approved trade)',
                        'profit_loss': pnl,
                        'profit_loss_pct': pnl_pct,
                        'metadata': {
                            'entry_price': entry_price,
                            'rebalance_action': 'approved_trade',
                            'order_type': 'MKT'
                        }
                    })
                    
                    db.remove_active_position(
                        symbol=symbol,
                        exit_price=fill_price,
                        exit_reason='Rebalancing SELL',
                        agent_name=agent_name
                    )
                except Exception as e:
                    logger.warning(f"Failed to log SELL trade for {symbol}: {e}")
            
            elif action == "BUY":
                logger.info(f"Fetching price for {symbol}...")
                contract = Stock(symbol, 'SMART', 'USD')
                
                # Try to get market price with multiple fallbacks
                ticker_data = ib.reqMktData(contract, '', True, False, [])
                ib.sleep(2)
                
                price = ticker_data.marketPrice()
                
                # Fallback 1: Try last price if market price unavailable
                if not (pd.notna(price) and price > 0):
                    price = ticker_data.last
                    if pd.notna(price) and price > 0:
                        logger.info(f"Using last price for {symbol}: ${price:.2f}")
                
                # Fallback 2: Try close price
                if not (pd.notna(price) and price > 0):
                    price = ticker_data.close
                    if pd.notna(price) and price > 0:
                        logger.info(f"Using close price for {symbol}: ${price:.2f}")
                
                # Fallback 3: Use historical data
                if not (pd.notna(price) and price > 0):
                    logger.warning(f"Live price unavailable for {symbol}, trying historical data...")
                    try:
                        bars = ib.reqHistoricalData(
                            contract,
                            endDateTime='',
                            durationStr='1 D',
                            barSizeSetting='1 day',
                            whatToShow='TRADES',
                            useRTH=True
                        )
                        if bars:
                            price = bars[-1].close
                            logger.info(f"Using historical close price for {symbol}: ${price:.2f}")
                    except Exception as e:
                        logger.error(f"Failed to get historical data for {symbol}: {e}")
                
                # Execute if we have a valid price
                if pd.notna(price) and price > 0:
                    # Check remaining cash before attempting purchase
                    remaining_cash = get_remaining_cash()
                    estimated_cost = price * (capital_per_buy / price)  # Cost for this trade
                    
                    logger.info(f"Remaining SettledCash: ${remaining_cash:.2f}, Estimated cost: ${estimated_cost:.2f}")
                    
                    if remaining_cash < estimated_cost * 0.9:  # 10% buffer for slippage
                        logger.warning(f"[SKIPPED] Insufficient SettledCash for {symbol} (${remaining_cash:.2f} < ${estimated_cost:.2f})")
                        logger.info(f"   Cash will settle on Nov 6. Re-run portfolio manager then.")
                        continue
                    
                    quantity = int(capital_per_buy / price)
                    
                    if quantity > 0:
                        logger.info(f"Attempting to buy {quantity} {symbol} @ ${price:.2f} (${quantity * price:.2f} total)...")
                        order = Order(action="BUY", totalQuantity=quantity, orderType='MKT', outsideRth=True)
                        trade = ib.placeOrder(contract, order)
                        ib.sleep(4)  # Wait longer for order status
                        
                        # Check if order was actually filled or rejected
                        if trade.orderStatus.status in ['Filled']:
                            fill_price = trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice > 0 else price
                            pos_data = position_tracker.add_position(symbol, fill_price, quantity)
                            executed_trades.append(f"BUY {quantity} {symbol}")
                            total_spent += quantity * fill_price
                            logger.info(f"[OK] ✓ Bought {quantity} {symbol} @ ${fill_price:.2f} (Total spent: ${total_spent:.2f})")
                            logger.info(f"   Tracking: Entry=${fill_price:.2f}, Stop=${pos_data['stop_loss_price']:.2f}")
                            
                            # Log trade to database for observability
                            try:
                                db.log_trade({
                                    'timestamp': datetime.now().isoformat(),
                                    'symbol': symbol,
                                    'action': 'BUY',
                                    'quantity': quantity,
                                    'price': fill_price,
                                    'agent_name': agent_name,
                                    'reason': 'Rebalancing BUY (approved trade)',
                                    'metadata': {
                                        'analyst_score': approved.get('analyst_score', 'N/A'),
                                        'expected_return': approved.get('expected_return', 'N/A'),
                                        'rebalance_action': 'approved_trade',
                                        'order_type': 'MKT',
                                        'capital_allocated': quantity * fill_price
                                    }
                                })
                                
                                db.add_active_position(
                                    symbol=symbol,
                                    quantity=quantity,
                                    entry_price=fill_price,
                                    agent_name=agent_name,
                                    profit_target=fill_price * 1.20,  # 20% target
                                    stop_loss=pos_data['stop_loss_price'],
                                    metadata={
                                        'analyst_score': approved.get('analyst_score', 'N/A'),
                                        'expected_return': approved.get('expected_return', 'N/A'),
                                        'entry_reason': 'Weekly rebalancing',
                                        'trailing_stop_active': False
                                    }
                                )
                            except Exception as e:
                                logger.warning(f"Failed to log BUY trade for {symbol}: {e}")
                        elif trade.orderStatus.status in ['PreSubmitted', 'Submitted']:
                            # Order pending, assume it will fill
                            logger.info(f"[PENDING] Order for {symbol} submitted, waiting for fill...")
                            ib.sleep(2)
                            if trade.orderStatus.status == 'Filled':
                                fill_price = trade.orderStatus.avgFillPrice
                                pos_data = position_tracker.add_position(symbol, fill_price, quantity)
                                executed_trades.append(f"BUY {quantity} {symbol}")
                                total_spent += quantity * fill_price
                                logger.info(f"[OK] ✓ Bought {quantity} {symbol} @ ${fill_price:.2f} (Total spent: ${total_spent:.2f})")
                            else:
                                logger.warning(f"Order still pending for {symbol}: {trade.orderStatus.status}")
                        elif trade.orderStatus.status in ['Cancelled', 'Inactive']:
                            error_msg = trade.log[-1].message if trade.log else 'Unknown reason'
                            logger.error(f"[FAILED] ✗ Order for {symbol} rejected: {error_msg}")
                            if 'settled cash' in error_msg.lower():
                                logger.info(f"   → Wait for cash settlement (Nov 6) and re-run")
                        else:
                            logger.warning(f"[UNKNOWN] Order status for {symbol}: {trade.orderStatus.status}")
                    else:
                        logger.warning(f"Quantity 0 for {symbol} - insufficient capital (${capital_per_buy:.2f} / ${price:.2f})")
                else:
                    logger.error(f"[SKIPPED] ✗ Cannot get valid price for {symbol} - all price sources failed")
                    logger.info(f"   → Price may require live market data subscription")
            
            elif action == "HOLD":
                logger.info(f"[OK] Holding {symbol} (user approved)")
        
        logger.info("Waiting for trades to settle...")
        ib.sleep(10)
        
        return {"status": "SUCCESS", "executed_trades": executed_trades}
    
    except Exception as e:
        logger.critical(f"Failed to execute trades: {e}", exc_info=True)
        return {"status": "FAILURE", "reason": str(e), "executed_trades": []}
    finally:
        if ib.isConnected():
            ib.disconnect()


def main():
    """Main execution for Phase 3: Portfolio Management (Approval-Based)"""
    logger.info("=" * 80)
    logger.info("PHASE 3: PORTFOLIO MANAGER - Starting (Approval-Based Mode)")
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
    
    # STEP 2: Load approved trades from reviewer
    approved_trades = load_approved_trades()
    
    if approved_trades is None:
        logger.error("Cannot proceed without approved trades")
        logger.info("[ERROR] Run portfolio_reviewer.py first to review and approve trades")
        sys.exit(1)
    
    if not approved_trades:
        logger.info("[OK] No trades approved. Maintaining current portfolio.")
        write_state('phase_state', {
            'current_phase': 'execution_complete',
            'executed_trades': [],
            'reason': 'No trades approved by user',
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(0)
    
    logger.info(f"Processing {len(approved_trades)} approved trades...")
    
    # STEP 3: Check if market is open
    if not is_market_open():
        logger.warning("Market is closed. Cannot execute trades now.")
        write_state('phase_state', {
            'current_phase': 'execution_pending',
            'reason': 'Market closed - trades deferred',
            'approved_trades_pending': approved_trades,
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(0)
    
    # STEP 4: Execute approved trades
    logger.info("Market is open. Executing approved trades...")
    trade_result = execute_approved_trades_only(approved_trades, position_tracker)
    
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
    
    # STEP 5: Run weekly improvement cycle (autonomous system)
    if datetime.now().weekday() == 6:  # Sunday (after weekly rebalancing)
        try:
            logger.info("📊 Running weekly autonomous improvement cycle...")
            improvement_engine = ContinuousImprovementEngine("weekly_portfolio_manager")
            improvement_report = improvement_engine.daily_improvement_cycle()
            
            if improvement_report.get('parameter_changes'):
                logger.info(f"✅ Parameters autonomously updated:")
                for param, change in improvement_report['parameter_changes'].items():
                    logger.info(f"   • {param}: {change['old']} → {change['new']}")
            else:
                logger.info("⏸  No parameter changes this week (monitoring)")
            
            if improvement_report.get('llm_insights'):
                insights = improvement_report['llm_insights']
                if isinstance(insights, dict) and 'assessment' in insights:
                    logger.info(f"💡 LLM Assessment: {insights['assessment'][:200]}...")
            
            logger.info(f"📁 Improvement report saved: reports/improvement/improvement_report_{datetime.now().strftime('%Y-%m-%d')}.json")
        except Exception as e:
            logger.warning(f"Failed to run improvement cycle: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error in Portfolio Manager: {e}", exc_info=True)
        sys.exit(1)
