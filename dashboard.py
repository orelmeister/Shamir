"""
Real-time Trading Dashboard Monitor
Displays live updates from the day trading bot
"""

import json
import os
import time
from datetime import datetime
from collections import defaultdict

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_time(timestamp_str):
    """Extract time from ISO timestamp"""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%H:%M:%S')
    except:
        return timestamp_str

def monitor_dashboard(log_file):
    """Display live trading dashboard"""
    
    trades = []
    positions = {}
    stats = {
        'total_trades': 0,
        'wins': 0,
        'losses': 0,
        'total_pnl': 0.0
    }
    last_messages = []
    
    print("🚀 Starting Day Trading Dashboard...")
    print(f"📊 Monitoring: {log_file}")
    print("Press Ctrl+C to exit\n")
    time.sleep(2)
    
    with open(log_file, 'r') as f:
        # Read existing content
        for line in f:
            process_log_line(line, trades, positions, stats, last_messages)
        
        # Monitor new lines
        while True:
            line = f.readline()
            if line:
                process_log_line(line, trades, positions, stats, last_messages)
                display_dashboard(trades, positions, stats, last_messages)
            else:
                time.sleep(1)

def process_log_line(line, trades, positions, stats, last_messages):
    """Process a single log line"""
    try:
        log = json.loads(line.strip())
        message = log.get('message', '')
        timestamp = format_time(log.get('timestamp', ''))
        
        # Track trades
        if 'BOUGHT' in message:
            parts = message.split()
            if len(parts) >= 5:
                ticker = parts[4]
                qty = int(parts[1])
                price = float(parts[6].replace('$', ''))
                trades.append({
                    'time': timestamp,
                    'action': 'BUY',
                    'ticker': ticker,
                    'qty': qty,
                    'price': price
                })
                positions[ticker] = {'qty': qty, 'entry_price': price}
                stats['total_trades'] += 1
        
        elif 'SOLD' in message:
            parts = message.split()
            if len(parts) >= 5:
                ticker = parts[4]
                qty = int(parts[1])
                price = float(parts[6].replace('$', ''))
                trades.append({
                    'time': timestamp,
                    'action': 'SELL',
                    'ticker': ticker,
                    'qty': qty,
                    'price': price
                })
                
                # Calculate P&L
                if ticker in positions:
                    entry = positions[ticker]['entry_price']
                    pnl = (price - entry) * qty
                    stats['total_pnl'] += pnl
                    if pnl > 0:
                        stats['wins'] += 1
                    else:
                        stats['losses'] += 1
                    del positions[ticker]
        
        # Keep last 10 messages
        last_messages.append(f"[{timestamp}] {log.get('agent', 'BOT')}: {message}")
        if len(last_messages) > 10:
            last_messages.pop(0)
    
    except json.JSONDecodeError:
        pass

def display_dashboard(trades, positions, stats, last_messages):
    """Display the dashboard"""
    clear_screen()
    
    # Header
    print("═" * 80)
    print("🤖  DAY TRADING BOT - LIVE DASHBOARD".center(80))
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(80))
    print("═" * 80)
    print()
    
    # Statistics
    print("📊 TRADING STATISTICS")
    print("─" * 80)
    win_rate = (stats['wins'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
    print(f"Total Trades: {stats['total_trades']}  |  Wins: {stats['wins']}  |  Losses: {stats['losses']}  |  Win Rate: {win_rate:.1f}%")
    pnl_color = '🟢' if stats['total_pnl'] >= 0 else '🔴'
    print(f"Total P&L: {pnl_color} ${stats['total_pnl']:.2f}")
    print()
    
    # Open Positions
    print("📈 OPEN POSITIONS")
    print("─" * 80)
    if positions:
        for ticker, pos in positions.items():
            print(f"  {ticker}: {pos['qty']} shares @ ${pos['entry_price']:.2f}")
    else:
        print("  No open positions")
    print()
    
    # Recent Trades
    print("💰 RECENT TRADES (Last 5)")
    print("─" * 80)
    recent_trades = trades[-5:] if trades else []
    if recent_trades:
        for trade in reversed(recent_trades):
            action_emoji = '🟢' if trade['action'] == 'BUY' else '🔴'
            print(f"  {action_emoji} [{trade['time']}] {trade['action']} {trade['qty']} {trade['ticker']} @ ${trade['price']:.2f}")
    else:
        print("  No trades yet")
    print()
    
    # Recent Log Messages
    print("📝 RECENT ACTIVITY")
    print("─" * 80)
    for msg in last_messages[-5:]:
        print(f"  {msg}")
    print()
    print("═" * 80)
    print("Press Ctrl+C to exit | Auto-refreshing...")

if __name__ == "__main__":
    # Find latest log file
    log_dir = "logs"
    log_files = [f for f in os.listdir(log_dir) if f.startswith('day_trader_run_')]
    
    if not log_files:
        print("❌ No log files found. Start the bot first!")
        exit(1)
    
    latest_log = max([os.path.join(log_dir, f) for f in log_files], key=os.path.getmtime)
    
    try:
        monitor_dashboard(latest_log)
    except KeyboardInterrupt:
        print("\n\n✓ Dashboard stopped. Bot is still running.")
