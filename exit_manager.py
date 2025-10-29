"""
Exit Manager Bot - Persistent Connection for Managing Open Positions

This bot maintains a persistent IBKR connection to:
1. Place and maintain profit target orders (+1.8%)
2. Monitor stop losses (-0.9%) using portfolio data (no subscription)
3. Automatically exit positions when targets hit

CRITICAL SAFETY: Only monitors positions in the database (day trading positions).
Long-term holdings and positions from other bots are PROTECTED.
"""

import time
import logging
from datetime import datetime
from ib_insync import *

# Configuration
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001
CLIENT_ID = 10  # Unique ID for Exit Manager
PROFIT_TARGET_PCT = 0.018  # +1.8%
STOP_LOSS_PCT = 0.009      # -0.9%
CHECK_INTERVAL = 10         # seconds
RESYNC_INTERVAL = 100       # seconds

# Database import
from observability import get_database

class ExitManagerBot:
    
    def __init__(self):
        self.ib = IB()
        self.positions = {}  # {symbol: {quantity, entry_price, tp_trade, sl_price}}
        self.last_resync = 0
        self.failed_sells = set()  # Track symbols that can't be sold (short restrictions)
        self.db = get_database()  # Shared database for coordination
        
    def connect(self):
        """Connect to IBKR"""
        try:
            print(f"[CONNECT] Connecting to IBKR (port {IBKR_PORT}, clientId {CLIENT_ID})...")
            self.ib.connect(IBKR_HOST, IBKR_PORT, clientId=CLIENT_ID, timeout=20)
            self.ib.reqMarketDataType(3)  # Delayed/frozen data
            print("[OK] Connected to IBKR")
            return True
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            return False
    
    def sync_positions(self):
        """
        Sync positions from IBKR and place profit targets.
        
        CRITICAL SAFETY: Only monitors positions that are in the database.
        This prevents Exit Manager from selling long-term holdings or positions
        from the weekly bot. Only day trading positions (in active_positions table)
        will be monitored and managed.
        """
        print(f"\n[STATUS] Syncing day trading positions...")
        
        try:
            # STEP 1: Get day trading positions from database (single source of truth)
            db_positions = self.db.get_active_positions()
            db_symbols = {pos['symbol'] for pos in db_positions}
            
            if not db_symbols:
                print("   No day trading positions in database to monitor")
                return True
            
            print(f"   Database: {len(db_symbols)} day trading position(s) -> {', '.join(sorted(db_symbols))}")
            
            # STEP 2: Get ALL positions from IBKR
            ibkr_positions = self.ib.positions()
            ibkr_dict = {p.contract.symbol: p for p in ibkr_positions if p.position > 0}
            
            print(f"   IBKR Account: {len(ibkr_dict)} total position(s)")
            
            # STEP 3: Report long-term positions that will be PROTECTED
            protected_positions = set(ibkr_dict.keys()) - db_symbols
            if protected_positions:
                print(f"\n   [PROTECTED] {len(protected_positions)} long-term position(s):")
                for symbol in sorted(protected_positions):
                    pos = ibkr_dict[symbol]
                    print(f"      - {symbol}: {int(pos.position)} shares @ ${pos.avgCost:.2f} (NOT monitored)")
                print(f"   [INFO] These positions will NOT be sold by Exit Manager\n")
            
            # STEP 4: Only sync positions that are BOTH in database AND in IBKR
            synced = 0
            for symbol in db_symbols:
                # Skip if already tracking
                if symbol in self.positions:
                    continue
                
                # Check if this day trading position exists in IBKR
                if symbol not in ibkr_dict:
                    print(f"   [WARN] {symbol}: In database but not in IBKR (may have been closed)")
                    continue
                
                pos = ibkr_dict[symbol]
                quantity = pos.position
                entry_price = pos.avgCost
                
                # Calculate targets
                take_profit = entry_price * (1 + PROFIT_TARGET_PCT)
                stop_loss_price = entry_price * (1 - STOP_LOSS_PCT)
                
                # Create contract
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                
                # Check if profit target already exists
                existing_trades = [t for t in self.ib.trades() 
                                   if t.contract.symbol == symbol and t.order.action == 'SELL']
                
                if existing_trades:
                    print(f"   [WARN] {symbol}: Existing SELL order found, using it")
                    tp_trade = existing_trades[0]
                else:
                    # Place profit target order
                    tp_order = LimitOrder('SELL', abs(int(quantity)), round(take_profit, 2))
                    tp_order.tif = 'DAY'
                    tp_order.outsideRth = True
                    tp_order.transmit = True
                    
                    print(f"   [TARGET] {symbol}: Placing profit target at ${take_profit:.2f}")
                    tp_trade = self.ib.placeOrder(contract, tp_order)
                    self.ib.sleep(0.5)
                
                # Track position
                self.positions[symbol] = {
                    'quantity': quantity,
                    'entry_price': entry_price,
                    'take_profit': take_profit,
                    'stop_loss_price': stop_loss_price,
                    'contract': contract,
                    'tp_trade': tp_trade
                }
                
                # Add to shared database
                self.db.add_active_position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=entry_price,
                    agent_name='exit_manager',
                    profit_target=take_profit,
                    stop_loss=stop_loss_price
                )
                
                synced += 1
                print(f"   [OK] {symbol}: Entry ${entry_price:.2f}, Target ${take_profit:.2f}, Stop ${stop_loss_price:.2f}")
            
            print(f"[OK] Synced {synced} positions")
            self.last_resync = time.time()
            return True
            
        except Exception as e:
            print(f"[ERROR] Position sync error: {e}")
            return False
    
    def check_stop_losses(self):
        """Monitor positions for stop loss conditions using portfolio data (no subscription needed)"""
        for symbol, pos in list(self.positions.items()):
            # Skip symbols that previously failed to sell
            if symbol in self.failed_sells:
                continue
                
            try:
                # Get current position data from portfolio (includes market value)
                portfolio_items = self.ib.portfolio()
                
                # Find this symbol in portfolio
                current_position = None
                for item in portfolio_items:
                    if item.contract.symbol == symbol:
                        current_position = item
                        break
                
                if not current_position:
                    # Position no longer exists in portfolio (may have been closed)
                    continue
                
                # Calculate current price from portfolio data
                if current_position.position != 0:
                    current_price = current_position.marketValue / current_position.position
                else:
                    continue
                
                # Calculate P&L percentage
                position_value = abs(current_position.position * current_position.averageCost)
                if position_value > 0:
                    pnl_pct = (current_position.unrealizedPNL / position_value) * 100
                else:
                    continue
                
                # Check stop loss
                stop_loss_price = pos['stop_loss_price']
                if pnl_pct <= -STOP_LOSS_PCT * 100:  # -0.9%
                    print(f"\n[CRITICAL] STOP LOSS: {symbol} at ${current_price:.2f} (PnL: {pnl_pct:.2f}%)")
                    
                    # Cancel profit target first
                    try:
                        tp_trade = pos['tp_trade']
                        self.ib.cancelOrder(tp_trade.order)
                        self.ib.sleep(2)  # Wait for cancel confirmation
                        print(f"   [OK] Profit target cancelled")
                    except Exception as e:
                        print(f"   [WARN] Failed to cancel profit target: {e}")
                    
                    # Place stop loss market order
                    try:
                        quantity = abs(int(pos['quantity']))
                        sl_order = MarketOrder('SELL', quantity)
                        sl_order.tif = 'IOC'
                        sl_order.outsideRth = True
                        
                        sl_trade = self.ib.placeOrder(pos['contract'], sl_order)
                        
                        # Wait for fill
                        for _ in range(10):
                            self.ib.sleep(1)
                            if sl_trade.orderStatus.status == 'Filled':
                                fill_price = sl_trade.orderStatus.avgFillPrice
                                actual_pnl = ((fill_price / pos['entry_price']) - 1) * 100
                                
                                # Remove from database
                                self.db.remove_active_position(
                                    symbol=symbol,
                                    exit_price=fill_price,
                                    exit_reason='STOP_LOSS',
                                    agent_name='exit_manager'
                                )
                                
                                # Log trade
                                self.db.log_trade({
                                    'symbol': symbol,
                                    'action': 'SELL',
                                    'quantity': quantity,
                                    'price': fill_price,
                                    'agent_name': 'exit_manager',
                                    'reason': 'STOP_LOSS',
                                    'profit_loss': (fill_price - pos['entry_price']) * quantity,
                                    'profit_loss_pct': actual_pnl
                                })
                                
                                print(f"   [OK] Stop loss filled at ${fill_price:.2f} ({actual_pnl:+.2f}%)")
                                del self.positions[symbol]
                                break
                            
                            # Check for errors
                            if 'CANNOT SHORT' in sl_trade.orderStatus.whyHeld:
                                print(f"   [WARN] Cannot sell {symbol} - short sale restriction (manual action needed)")
                                self.failed_sells.add(symbol)
                                del self.positions[symbol]
                                break
                            elif sl_trade.orderStatus.status == 'Cancelled':
                                print(f"   [WARN] Stop loss order cancelled: {sl_trade.orderStatus.status}")
                                break
                        else:
                            print(f"   [WARN] Stop loss order status: {sl_trade.orderStatus.status}")
                    except Exception as e:
                        print(f"   [ERROR] Stop loss execution error: {e}")
                        
            except Exception as e:
                print(f"[ERROR] Error checking stop loss for {symbol}: {e}")
    
    def check_profit_targets(self):
        """Monitor profit target fills"""
        for symbol, pos in list(self.positions.items()):
            try:
                tp_trade = pos['tp_trade']
                
                if tp_trade.orderStatus.status == 'Filled':
                    fill_price = tp_trade.orderStatus.avgFillPrice
                    entry_price = pos['entry_price']
                    pnl = ((fill_price / entry_price) - 1) * 100
                    
                    print(f"\n[PROFIT] PROFIT TARGET FILLED: {symbol} at ${fill_price:.2f} (+{pnl:.2f}%)")
                    
                    # Remove from database
                    self.db.remove_active_position(
                        symbol=symbol,
                        exit_price=fill_price,
                        exit_reason='PROFIT_TARGET',
                        agent_name='exit_manager'
                    )
                    
                    # Log trade
                    self.db.log_trade({
                        'symbol': symbol,
                        'action': 'SELL',
                        'quantity': abs(int(pos['quantity'])),
                        'price': fill_price,
                        'agent_name': 'exit_manager',
                        'reason': 'PROFIT_TARGET',
                        'profit_loss': (fill_price - entry_price) * abs(int(pos['quantity'])),
                        'profit_loss_pct': pnl
                    })
                    
                    del self.positions[symbol]
                    
            except Exception as e:
                print(f"[ERROR] Error checking profit target for {symbol}: {e}")
    
    def status(self):
        """Print status"""
        now = datetime.now().strftime('%H:%M:%S')
        print(f"\n[{now}] [STATUS] Monitoring {len(self.positions)} positions")
        for symbol, pos in self.positions.items():
            print(f"   {symbol}: Entry ${pos['entry_price']:.2f}, TP ${pos['take_profit']:.2f}, SL ${pos['stop_loss_price']:.2f}")
    
    def run(self):
        """Main loop"""
        print("=" * 80)
        print("Exit Manager Bot - Position Exit Management")
        print("=" * 80)
        
        # Connect
        if not self.connect():
            print("[ERROR] Failed to connect to IBKR")
            return
        
        # Sync positions
        if not self.sync_positions():
            print("[ERROR] Failed to sync positions")
            return
        
        # Main monitoring loop
        print(f"[OK] Monitoring {len(self.positions)} positions")
        print(f"Check interval: {CHECK_INTERVAL}s")
        print("Press Ctrl+C to stop")
        print("=" * 80)
        
        try:
            while True:
                # Resync periodically
                if time.time() - self.last_resync > RESYNC_INTERVAL:
                    self.sync_positions()
                
                # Check exits
                self.check_stop_losses()
                self.check_profit_targets()
                
                # Status every 5 checks
                if int(time.time()) % (CHECK_INTERVAL * 5) < CHECK_INTERVAL:
                    self.status()
                
                # Sleep
                self.ib.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\n[INFO] Exit Manager stopped by user")
        except Exception as e:
            print(f"\n[ERROR] Error in main loop: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.ib.disconnect()
            print("[OK] Disconnected")

if __name__ == "__main__":
    manager = ExitManagerBot()
    manager.run()
