"""Check all historical trades in database"""
from observability import get_database

db = get_database()

print("="*80)
print("📊 DATABASE TRADE HISTORY")
print("="*80)
print()

with db._get_connection() as conn:
    # Get total count
    cursor = conn.execute("SELECT COUNT(*) FROM trades")
    total = cursor.fetchone()[0]
    print(f"Total trades in database: {total}")
    print()
    
    # Get last 30 trades
    cursor = conn.execute("""
        SELECT timestamp, agent_name, action, symbol, quantity, price, 
               profit_loss, profit_loss_pct, reason
        FROM trades 
        ORDER BY timestamp DESC 
        LIMIT 30
    """)
    trades = cursor.fetchall()
    
    print("Last 30 trades:")
    print("-" * 80)
    for t in trades:
        timestamp = t[0][:19] if t[0] else "N/A"
        agent = t[1][:20] if t[1] else "N/A"
        action = t[2]
        symbol = t[3]
        qty = t[4]
        price = t[5]
        pnl = t[6] if t[6] else 0
        pnl_pct = t[7] if t[7] else 0
        reason = t[8][:40] if t[8] else "N/A"
        
        pnl_str = f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)" if pnl != 0 else ""
        print(f"{timestamp} | {agent:20} | {action:4} {symbol:6} x{qty:3} @ ${price:6.2f} {pnl_str}")
    
    print()
    print("="*80)
    print("TRADES BY AGENT:")
    print("="*80)
    
    cursor = conn.execute("""
        SELECT agent_name, COUNT(*) as count
        FROM trades
        GROUP BY agent_name
        ORDER BY count DESC
    """)
    
    for row in cursor.fetchall():
        print(f"{row[0]:30} : {row[1]:3} trades")
