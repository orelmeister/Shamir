"""
System Status Checker
Quick overview of current trading system state
"""

from observability import get_database
from datetime import datetime
import os

def check_system_status():
    """Display current system status"""
    
    print("\n" + "="*80)
    print(f"📊 Trading System Status - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    db = get_database()
    
    # Active Positions
    print("\n🟢 ACTIVE POSITIONS:")
    active = db.get_active_positions()
    if active:
        print(f"   Total: {len(active)} position(s)")
        for pos in active:
            symbol = pos['symbol']
            qty = pos['quantity']
            entry = pos['entry_price']
            tp = pos.get('profit_target_price', 0)
            sl = pos.get('stop_loss_price', 0)
            agent = pos.get('agent_name', 'unknown')
            
            print(f"   • {symbol}: {qty} shares @ ${entry:.2f}")
            print(f"     Entry: ${entry:.2f} | TP: ${tp:.2f} (+{((tp/entry - 1)*100):.1f}%) | SL: ${sl:.2f} ({((sl/entry - 1)*100):.1f}%)")
            print(f"     Managed by: {agent}")
    else:
        print("   No active positions")
    
    # Closed Today
    print("\n🔴 CLOSED TODAY:")
    closed = db.get_closed_today()
    if closed:
        print(f"   Total: {len(closed)} position(s)")
        total_pnl = 0
        for pos in closed:
            symbol = pos['symbol']
            reason = pos.get('exit_reason', 'UNKNOWN')
            pnl_pct = pos.get('profit_loss_pct', 0)
            agent = pos.get('agent_name', 'unknown')
            total_pnl += pnl_pct if pnl_pct else 0
            
            emoji = "✅" if pnl_pct and pnl_pct > 0 else "❌"
            print(f"   {emoji} {symbol}: {reason} - {pnl_pct:+.2f}% (by {agent})")
        
        print(f"\n   💰 Total P&L Today: {total_pnl:+.2f}%")
    else:
        print("   No positions closed today")
    
    # Recent Trades
    print("\n📈 RECENT TRADES (Last 10):")
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        trades = db.get_trades_by_date(today)
        
        if trades:
            # Show last 10
            recent = trades[-10:]
            for trade in recent:
                symbol = trade.get('symbol', 'N/A')
                action = trade.get('action', 'N/A')
                qty = trade.get('quantity', 0)
                price = trade.get('price', 0)
                reason = trade.get('reason', 'N/A')
                pnl_pct = trade.get('profit_loss_pct', 0)
                
                if action == 'BUY':
                    print(f"   🟢 {symbol}: {action} {qty} @ ${price:.2f} - {reason}")
                else:
                    emoji = "✅" if pnl_pct and pnl_pct > 0 else "❌"
                    print(f"   {emoji} {symbol}: {action} {qty} @ ${price:.2f} - {reason} ({pnl_pct:+.2f}%)")
        else:
            print("   No trades today")
    except Exception as e:
        print(f"   ⚠️  Error retrieving trades: {e}")
    
    # File Status
    print("\n📁 WATCHLIST FILES:")
    files = {
        'day_trading_watchlist.json': 'Intraday scanner output',
        'ranked_tickers.json': 'Pre-market analysis',
        'validated_tickers.json': 'IBKR validated tickers',
        'full_market_data.json': 'Market data aggregation'
    }
    
    for file, desc in files.items():
        if os.path.exists(file):
            size = os.path.getsize(file)
            mod_time = datetime.fromtimestamp(os.path.getmtime(file))
            age = datetime.now() - mod_time
            age_str = f"{age.seconds // 3600}h {(age.seconds % 3600) // 60}m ago"
            print(f"   ✅ {file} ({size} bytes, updated {age_str})")
        else:
            print(f"   ❌ {file} (missing)")
    
    # Database Stats
    print("\n💾 DATABASE:")
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trades")
        total_trades = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM active_positions")
        active_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM closed_positions_today")
        closed_count = cursor.fetchone()[0]
        
        print(f"   Total trades: {total_trades}")
        print(f"   Active positions: {active_count}")
        print(f"   Closed today: {closed_count}")
        print(f"   Database: trading_history.db (WAL mode)")
    except Exception as e:
        print(f"   ⚠️  Error querying database: {e}")
    
    print("\n" + "="*80)
    print("✅ System status check complete")
    print("="*80 + "\n")
    
    # Recommendations
    if len(active) > 0 and len(closed) == 0:
        print("💡 TIP: Positions are open. Make sure Exit Manager is running!")
    
    if len(closed) > len(active) * 2 and total_pnl < 0:
        print("⚠️  WARNING: More exits than active positions with negative P&L. Consider reviewing strategy.")
    
    if not os.path.exists('day_trading_watchlist.json'):
        print("⚠️  WARNING: Intraday watchlist missing. Run scanner or pre-market analysis.")
    

if __name__ == "__main__":
    check_system_status()
