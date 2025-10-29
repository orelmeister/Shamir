"""
Live monitoring script for day trader bot
Shows latest activity every 60 seconds
"""
import time
import json
import os
from datetime import datetime
from collections import deque

def get_latest_log_file():
    """Find the most recent log file"""
    log_dir = "logs"
    log_files = [f for f in os.listdir(log_dir) if f.startswith("day_trader_run_") and f.endswith(".json")]
    if not log_files:
        return None
    latest = max(log_files, key=lambda f: os.path.getmtime(os.path.join(log_dir, f)))
    return os.path.join(log_dir, latest)

def parse_log_line(line):
    """Parse JSON log line"""
    try:
        return json.loads(line.strip())
    except:
        return None

def monitor_bot():
    """Monitor bot activity every 60 seconds"""
    print("🤖 Day Trader Live Monitor")
    print("=" * 80)
    
    last_position = 0
    
    while True:
        log_file = get_latest_log_file()
        if not log_file:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  No log file found")
            time.sleep(60)
            continue
        
        # Read new log entries
        with open(log_file, 'r') as f:
            f.seek(last_position)
            new_lines = f.readlines()
            last_position = f.tell()
        
        if not new_lines:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 💤 No new activity...")
            time.sleep(60)
            continue
        
        # Parse and display key events
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📊 Activity Update:")
        print("-" * 80)
        
        for line in new_lines[-20:]:  # Last 20 lines
            log = parse_log_line(line)
            if not log:
                continue
            
            msg = log.get('message', '')
            level = log.get('level', 'INFO')
            
            # Highlight important messages
            if 'ENTRY SIGNAL' in msg or 'BUY' in msg.upper():
                print(f"  🟢 {level}: {msg}")
            elif 'SELL' in msg.upper() or 'PROFIT' in msg.upper():
                print(f"  🔴 {level}: {msg}")
            elif 'STOP LOSS' in msg.upper():
                print(f"  🛑 {level}: {msg}")
            elif 'Scanner' in msg or 'watchlist' in msg:
                print(f"  🔍 {level}: {msg}")
            elif 'P&L' in msg:
                print(f"  💰 {level}: {msg}")
            elif 'ERROR' in level:
                print(f"  ❌ {level}: {msg}")
            elif 'ATR' in msg and 'NO ENTRY' in msg:
                # Show a sample of rejections
                pass
            elif 'Processing' in msg:
                print(f"  ⚙️  {msg}")
        
        time.sleep(60)

if __name__ == "__main__":
    try:
        monitor_bot()
    except KeyboardInterrupt:
        print("\n\n👋 Monitor stopped")
