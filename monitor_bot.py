"""
Real-time Bot Monitoring Script
Shows current status, database activity, and system health
"""

import sqlite3
import os
from datetime import datetime
import pytz
import time

def get_latest_trades(limit=5):
    """Get the most recent trades from the database."""
    if not os.path.exists('trading_history.db'):
        return []
    
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, symbol, action, quantity, price, profit_loss, profit_loss_pct, reason
        FROM trades
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    
    trades = cursor.fetchall()
    conn.close()
    return trades

def get_today_metrics():
    """Get today's performance metrics."""
    if not os.path.exists('trading_history.db'):
        return None
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT total_trades, winning_trades, losing_trades, total_profit_loss, 
               total_profit_loss_pct, max_drawdown, positions_held_eod
        FROM daily_metrics
        WHERE date = ?
    """, (today,))
    
    metrics = cursor.fetchone()
    conn.close()
    return metrics

def get_latest_health():
    """Get the most recent health check."""
    if not os.path.exists('trading_history.db'):
        return None
    
    conn = sqlite3.connect('trading_history.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, cpu_percent, memory_mb, ibkr_connected, health_status
        FROM agent_health
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    
    health = cursor.fetchone()
    conn.close()
    return health

def monitor():
    """Display current bot status."""
    print("\n" + "="*70)
    print("🤖 DAY TRADING BOT - REAL-TIME MONITOR")
    print("="*70)
    
    # Current time
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)
    print(f"\n⏰ Current Time (ET): {now_et.strftime('%I:%M:%S %p')}")
    print(f"📅 Date: {now_et.strftime('%B %d, %Y')}")
    
    # Bot status
    print("\n" + "-"*70)
    print("📊 BOT STATUS")
    print("-"*70)
    
    # Check if database exists
    if not os.path.exists('trading_history.db'):
        print("⚠️  Database not yet created - bot hasn't started trading")
        print("\n💡 Bot is currently waiting for market hours:")
        print("   • 7:00 AM - Data aggregation begins")
        print("   • 9:30 AM - Intraday trading starts")
        return
    
    # Latest health check
    health = get_latest_health()
    if health:
        timestamp, cpu, memory, ibkr, status = health
        print(f"Latest Health Check: {timestamp}")
        print(f"  CPU Usage: {cpu:.1f}%")
        print(f"  Memory: {memory:.0f} MB")
        print(f"  IBKR Connected: {'✅ YES' if ibkr else '❌ NO'}")
        print(f"  Status: {status.upper()}")
    else:
        print("⏳ No health checks yet - bot starting soon")
    
    # Today's metrics
    print("\n" + "-"*70)
    print("📈 TODAY'S PERFORMANCE")
    print("-"*70)
    
    metrics = get_today_metrics()
    if metrics:
        total, winning, losing, pnl, pnl_pct, drawdown, positions = metrics
        print(f"Total Trades: {total}")
        print(f"Winning: {winning} | Losing: {losing}")
        print(f"Win Rate: {(winning/total*100) if total > 0 else 0:.1f}%")
        print(f"Total P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
        print(f"Max Drawdown: {drawdown:.2f}%")
        print(f"Positions Held EOD: {positions}")
    else:
        print("⏳ No trades yet today")
    
    # Latest trades
    print("\n" + "-"*70)
    print("📝 RECENT TRADES (Last 5)")
    print("-"*70)
    
    trades = get_latest_trades(5)
    if trades:
        print(f"{'Time':<12} {'Symbol':<8} {'Action':<6} {'Qty':<6} {'Price':<10} {'P&L':<12} {'Reason':<30}")
        print("-"*70)
        for trade in trades:
            timestamp, symbol, action, qty, price, pnl, pnl_pct, reason = trade
            time_parts = timestamp.split()
            time_str = time_parts[1][:8] if len(time_parts) > 1 else timestamp[:8]  # HH:MM:SS
            pnl_str = f"${pnl:.2f}" if pnl else "---"
            pnl_pct_str = f"({pnl_pct:.2f}%)" if pnl_pct else ""
            reason_short = reason[:28] if reason else "---"
            print(f"{time_str:<12} {symbol:<8} {action:<6} {qty:<6} ${price:<9.2f} {pnl_str:<6} {pnl_pct_str:<5} {reason_short}")
    else:
        print("⏳ No trades yet")
    
    # Next milestones
    print("\n" + "-"*70)
    print("🎯 UPCOMING MILESTONES")
    print("-"*70)
    
    current_hour = now_et.hour
    current_minute = now_et.minute
    
    milestones = [
        (7, 0, "Data Aggregation (Market data collection)"),
        (7, 15, "ATR Prediction (LLM volatility analysis)"),
        (7, 30, "Pre-Market Analysis (LLM watchlist generation)"),
        (8, 15, "Ticker Validation (IBKR compatibility check)"),
        (9, 0, "Pre-Market Momentum (Movement analysis)"),
        (9, 30, "🚀 INTRADAY TRADING STARTS"),
        (15, 55, "End-of-Day Liquidation"),
        (16, 0, "Improvement Cycle (Performance analysis)")
    ]
    
    for hour, minute, description in milestones:
        if current_hour < hour or (current_hour == hour and current_minute < minute):
            milestone_time = now_et.replace(hour=hour, minute=minute, second=0)
            time_until = milestone_time - now_et
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            print(f"⏰ {hour:02d}:{minute:02d} - {description} (in {hours}h {minutes}m)")
            break
    
    print("\n" + "="*70)
    print("💡 Tip: Run this script periodically to see updates!")
    print("   Command: python monitor_bot.py")
    print("="*70 + "\n")

if __name__ == "__main__":
    try:
        monitor()
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
