"""
Position Analysis Tool - Compare IBKR Current Positions with Entry Data

This script provides a simple analysis of:
1. Current positions in IBKR
2. Entry prices and dates from database
3. Profit/Loss calculations
4. Position performance summary
"""

from ib_insync import *
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json

# IBKR Connection Settings
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001
CLIENT_ID = 50  # Unique ID for analysis tool


class PositionAnalyzer:
    """Analyze current IBKR positions against database entry data"""
    
    def __init__(self, db_path: str = "trading_history.db"):
        self.db_path = db_path
        self.ib = IB()
        
    def connect_ibkr(self) -> bool:
        """Connect to IBKR"""
        try:
            print(f"[CONNECT] Connecting to IBKR (port {IBKR_PORT}, clientId {CLIENT_ID})...")
            self.ib.connect(IBKR_HOST, IBKR_PORT, clientId=CLIENT_ID, timeout=20)
            self.ib.reqMarketDataType(3)  # Delayed/frozen data (free)
            print("[OK] Connected to IBKR\n")
            return True
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            return False
    
    def get_database_entry_data(self) -> Dict[str, Dict]:
        """Get entry data for all positions from database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        entry_data = {}
        
        # Get entry data from trades table (first BUY for each symbol)
        cursor.execute("""
            SELECT symbol, MIN(timestamp) as first_entry, price as entry_price, quantity, agent_name
            FROM trades
            WHERE action = 'BUY'
            GROUP BY symbol
        """)
        
        for row in cursor.fetchall():
            symbol = row['symbol']
            entry_data[symbol] = {
                'first_entry_date': row['first_entry'],
                'first_entry_price': row['entry_price'],
                'quantity': row['quantity'],
                'agent_name': row['agent_name']
            }
        
        # Get most recent entry price for each symbol (in case of multiple entries)
        cursor.execute("""
            SELECT symbol, timestamp, price, quantity
            FROM trades
            WHERE action = 'BUY'
            AND (symbol, timestamp) IN (
                SELECT symbol, MAX(timestamp)
                FROM trades
                WHERE action = 'BUY'
                GROUP BY symbol
            )
        """)
        
        for row in cursor.fetchall():
            symbol = row['symbol']
            if symbol in entry_data:
                entry_data[symbol]['latest_entry_date'] = row['timestamp']
                entry_data[symbol]['latest_entry_price'] = row['price']
                entry_data[symbol]['latest_quantity'] = row['quantity']
        
        # Get active position data from active_positions table (if exists)
        cursor.execute("""
            SELECT symbol, entry_price, entry_timestamp, quantity, profit_target_price, stop_loss_price
            FROM active_positions
            WHERE status = 'OPEN'
        """)
        
        for row in cursor.fetchall():
            symbol = row['symbol']
            if symbol not in entry_data:
                entry_data[symbol] = {}
            entry_data[symbol].update({
                'active_entry_price': row['entry_price'],
                'active_entry_date': row['entry_timestamp'],
                'active_quantity': row['quantity'],
                'profit_target': row['profit_target_price'],
                'stop_loss': row['stop_loss_price']
            })
        
        conn.close()
        return entry_data
    
    def get_ibkr_positions(self) -> List[Dict]:
        """Get current positions from IBKR"""
        positions = []
        portfolio_items = self.ib.portfolio()
        
        for item in portfolio_items:
            if item.position != 0:  # Only active positions
                current_price = item.marketPrice if item.marketPrice > 0 else (
                    item.marketValue / item.position if item.position != 0 else 0
                )
                
                positions.append({
                    'symbol': item.contract.symbol,
                    'quantity': item.position,
                    'avg_cost': item.averageCost,
                    'market_price': current_price,
                    'market_value': item.marketValue,
                    'unrealized_pnl': item.unrealizedPNL,
                    'realized_pnl': item.realizedPNL,
                })
        
        return positions
    
    def analyze_positions(self):
        """Main analysis function"""
        print("=" * 80)
        print("POSITION ANALYSIS - Current Status vs Entry")
        print("=" * 80)
        print()
        
        # Get data
        db_entry_data = self.get_database_entry_data()
        ibkr_positions = self.get_ibkr_positions()
        
        if not ibkr_positions:
            print("[INFO] No positions currently held in IBKR")
            print()
            if db_entry_data:
                print("[INFO] Historical positions found in database (all closed):")
                for symbol, data in db_entry_data.items():
                    print(f"  - {symbol}: First entry at ${data.get('first_entry_price', 0):.2f} "
                          f"on {data.get('first_entry_date', 'N/A')[:10]}")
            return
        
        # Analyze each position
        total_unrealized_pnl = 0
        positions_analyzed = 0
        
        print(f"[POSITIONS] Found {len(ibkr_positions)} active position(s)\n")
        
        for pos in ibkr_positions:
            symbol = pos['symbol']
            positions_analyzed += 1
            
            print(f"{'─' * 80}")
            print(f"Symbol: {symbol}")
            print(f"{'─' * 80}")
            
            # Current position details
            print(f"\n📊 CURRENT POSITION:")
            print(f"  Quantity:        {int(pos['quantity'])} shares")
            print(f"  Current Price:   ${pos['market_price']:.2f}")
            print(f"  Market Value:    ${pos['market_value']:.2f}")
            print(f"  Avg Cost (IBKR): ${pos['avg_cost']:.2f}")
            
            # Entry data from database
            entry_info = db_entry_data.get(symbol)
            if entry_info:
                print(f"\n📝 ENTRY DATA (from database):")
                
                # Show active position entry if available
                if 'active_entry_price' in entry_info:
                    print(f"  Entry Price:     ${entry_info['active_entry_price']:.2f}")
                    print(f"  Entry Date:      {entry_info.get('active_entry_date', 'N/A')[:19]}")
                    print(f"  Entry Quantity:  {int(entry_info.get('active_quantity', 0))} shares")
                    
                    if 'profit_target' in entry_info and entry_info['profit_target']:
                        print(f"  Profit Target:   ${entry_info['profit_target']:.2f}")
                    if 'stop_loss' in entry_info and entry_info['stop_loss']:
                        print(f"  Stop Loss:       ${entry_info['stop_loss']:.2f}")
                    
                    entry_price = entry_info['active_entry_price']
                else:
                    # Fall back to latest entry from trades
                    print(f"  First Entry:     ${entry_info.get('first_entry_price', 0):.2f} "
                          f"on {entry_info.get('first_entry_date', 'N/A')[:10]}")
                    if 'latest_entry_price' in entry_info:
                        print(f"  Latest Entry:    ${entry_info.get('latest_entry_price', 0):.2f} "
                              f"on {entry_info.get('latest_entry_date', 'N/A')[:10]}")
                        entry_price = entry_info['latest_entry_price']
                    else:
                        entry_price = entry_info.get('first_entry_price', pos['avg_cost'])
                
                # Calculate P&L based on database entry
                db_pnl = (pos['market_price'] - entry_price) * pos['quantity']
                db_pnl_pct = ((pos['market_price'] / entry_price) - 1) * 100
                
                print(f"\n💰 PERFORMANCE (vs DB entry ${entry_price:.2f}):")
                print(f"  Price Change:    ${pos['market_price'] - entry_price:+.2f} "
                      f"({db_pnl_pct:+.2f}%)")
                print(f"  P&L (database):  ${db_pnl:+.2f}")
            else:
                print(f"\n⚠️  No entry data found in database")
                print(f"  (Position may be from weekly bot or entered before database tracking)")
            
            # IBKR P&L
            print(f"\n💵 IBKR P&L:")
            print(f"  Unrealized P&L:  ${pos['unrealized_pnl']:+.2f}")
            if pos['realized_pnl'] != 0:
                print(f"  Realized P&L:    ${pos['realized_pnl']:+.2f}")
            
            # P&L percentage
            if pos['avg_cost'] > 0:
                ibkr_pnl_pct = ((pos['market_price'] / pos['avg_cost']) - 1) * 100
                print(f"  Return (IBKR):   {ibkr_pnl_pct:+.2f}%")
            
            total_unrealized_pnl += pos['unrealized_pnl']
            print()
        
        # Summary
        print(f"{'═' * 80}")
        print(f"SUMMARY")
        print(f"{'═' * 80}")
        print(f"\nTotal Positions:     {positions_analyzed}")
        print(f"Total Unrealized PnL: ${total_unrealized_pnl:+.2f}")
        print()
        
        # Account info
        account_values = self.ib.accountValues()
        for val in account_values:
            if val.tag == 'NetLiquidation' and val.currency == 'USD':
                print(f"Net Liquidation:  ${float(val.value):,.2f}")
            elif val.tag == 'ExcessLiquidity' and val.currency == 'USD':
                print(f"Excess Liquidity: ${float(val.value):,.2f}")
            elif val.tag == 'AvailableFunds' and val.currency == 'USD':
                print(f"Available Funds:  ${float(val.value):,.2f}")
        
        print()
        print("=" * 80)
    
    def run(self):
        """Main execution"""
        try:
            if not self.connect_ibkr():
                return
            
            self.analyze_positions()
            
        except Exception as e:
            print(f"\n[ERROR] Analysis error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.ib.isConnected():
                self.ib.disconnect()
                print("[OK] Disconnected from IBKR")


if __name__ == "__main__":
    analyzer = PositionAnalyzer()
    analyzer.run()
