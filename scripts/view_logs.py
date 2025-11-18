"""
Day Trader Log Viewer - Real-time monitoring tool
Usage: python view_logs.py [--live] [--errors-only] [--trades-only]
"""
import json
import sys
import time
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def get_latest_log():
    """Get the most recent day trader log file"""
    logs_dir = Path("logs")
    log_files = list(logs_dir.glob("day_trader_run_*.json"))
    if not log_files:
        return None
    return max(log_files, key=lambda p: p.stat().st_mtime)

def load_log(log_file):
    """Load and parse JSON log file"""
    try:
        with open(log_file, 'r') as f:
            return [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        print(f"Error loading log: {e}")
        return []

def format_log_entry(entry, colorize=True):
    """Format a single log entry for display"""
    timestamp = entry.get('timestamp', 'N/A')
    level = entry.get('level', 'INFO')
    agent = entry.get('agent', 'Unknown')
    message = entry.get('message', '')
    
    # Color codes (ANSI)
    colors = {
        'ERROR': '\033[91m',    # Red
        'WARNING': '\033[93m',  # Yellow
        'INFO': '\033[92m',     # Green
        'RESET': '\033[0m'      # Reset
    }
    
    if colorize and sys.stdout.isatty():
        color = colors.get(level, colors['RESET'])
        reset = colors['RESET']
    else:
        color = reset = ''
    
    return f"{color}[{timestamp}] [{level}] [{agent}]{reset} {message}"

def print_summary(entries):
    """Print summary statistics"""
    total = len(entries)
    by_level = defaultdict(int)
    by_agent = defaultdict(int)
    trades = 0
    
    for entry in entries:
        by_level[entry.get('level', 'INFO')] += 1
        by_agent[entry.get('agent', 'Unknown')] += 1
        if 'ENTRY SIGNAL' in entry.get('message', '') or 'EXIT SIGNAL' in entry.get('message', ''):
            trades += 1
    
    print("\n" + "="*70)
    print("LOG SUMMARY")
    print("="*70)
    print(f"Total entries: {total}")
    print(f"\nBy Level:")
    for level, count in sorted(by_level.items()):
        print(f"  {level}: {count}")
    
    print(f"\nTrades: {trades // 2}")  # Entry + Exit = 1 trade
    
    print(f"\nMost Active Agents:")
    for agent, count in sorted(by_agent.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {agent}: {count}")
    print("="*70 + "\n")

def watch_log(log_file, errors_only=False, trades_only=False):
    """Watch log file for new entries (tail -f style)"""
    print(f"Watching: {log_file}")
    print("Press Ctrl+C to stop\n")
    
    # Read existing content
    entries = load_log(log_file)
    last_size = len(entries)
    
    # Print existing entries
    for entry in entries:
        if should_print(entry, errors_only, trades_only):
            print(format_log_entry(entry))
    
    # Watch for new entries
    try:
        while True:
            time.sleep(1)
            current_entries = load_log(log_file)
            
            if len(current_entries) > last_size:
                # New entries added
                new_entries = current_entries[last_size:]
                for entry in new_entries:
                    if should_print(entry, errors_only, trades_only):
                        print(format_log_entry(entry))
                last_size = len(current_entries)
    except KeyboardInterrupt:
        print("\n\nStopped watching.")

def should_print(entry, errors_only, trades_only):
    """Determine if entry should be printed based on filters"""
    if errors_only and entry.get('level') != 'ERROR':
        return False
    
    if trades_only:
        message = entry.get('message', '')
        if not any(keyword in message for keyword in ['ENTRY SIGNAL', 'EXIT SIGNAL', 'BUY', 'SELL']):
            return False
    
    return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Day Trader Log Viewer')
    parser.add_argument('--live', action='store_true', help='Watch log file in real-time')
    parser.add_argument('--errors-only', action='store_true', help='Show only errors')
    parser.add_argument('--trades-only', action='store_true', help='Show only trade-related entries')
    parser.add_argument('--summary', action='store_true', help='Show summary statistics')
    parser.add_argument('--last', type=int, help='Show last N entries', metavar='N')
    
    args = parser.parse_args()
    
    log_file = get_latest_log()
    if not log_file:
        print("No log files found in logs/ directory")
        return
    
    print(f"Latest log: {log_file.name}")
    print(f"Modified: {datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if args.live:
        watch_log(log_file, args.errors_only, args.trades_only)
    else:
        entries = load_log(log_file)
        
        if args.summary:
            print_summary(entries)
        
        # Apply filters
        if args.last:
            entries = entries[-args.last:]
        
        # Print entries
        for entry in entries:
            if should_print(entry, args.errors_only, args.trades_only):
                print(format_log_entry(entry))
        
        if not args.summary:
            print(f"\nTotal entries shown: {len([e for e in entries if should_print(e, args.errors_only, args.trades_only)])}")

if __name__ == "__main__":
    main()
