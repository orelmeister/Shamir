"""Comprehensive P&L analysis of all trades today with detailed breakdown"""
from observability import get_database
from collections import defaultdict
from datetime import datetime

db = get_database()

# Get all trades for today
trades = db.get_trades_by_date('2025-10-29')

print("="*80)
print("COMPLETE TRADING SUMMARY - October 29, 2025")
print("="*80)

if not trades:
    print("No trades found for today")
    exit()

print(f"\nTotal trades logged: {len(trades)}")

# Organize trades by symbol
by_symbol = defaultdict(list)
for trade in trades:
    symbol = trade.get('symbol', 'UNKNOWN')
    by_symbol[symbol].append(trade)

# Calculate P&L for each symbol
print("\n" + "="*80)
print("PROFIT/LOSS BY SYMBOL")
print("="*80)

total_pnl = 0
total_trades = 0
winners = 0
losers = 0
breakeven = 0

for symbol in sorted(by_symbol.keys()):
    symbol_trades = by_symbol[symbol]
    
    # Separate buys and sells
    buys = [t for t in symbol_trades if t.get('action') == 'BUY']
    sells = [t for t in symbol_trades if t.get('action') == 'SELL']
    
    print(f"\n{symbol}:")
    print(f"  Buys: {len(buys)}, Sells: {len(sells)}")
    
    # Calculate P&L
    total_buy_cost = 0
    total_buy_shares = 0
                entries.append(entry)
            except:
                continue
    
    print(f"📝 Total log entries: {len(entries)}")
    print()
    
    # === SESSION TIMELINE ===
    print("⏰ SESSION TIMELINE")
    print("-" * 80)
    
    if entries:
        start_time = entries[0]['timestamp_obj']
        end_time = entries[-1]['timestamp_obj']
        duration = end_time - start_time if start_time and end_time else None
        
        print(f"Session Start: {start_time.strftime('%H:%M:%S') if start_time else 'Unknown'}")
        print(f"Session End:   {end_time.strftime('%H:%M:%S') if end_time else 'Unknown'}")
        print(f"Duration:      {duration if duration else 'Unknown'}")
    print()
    
    # === SCANNER ACTIVITY ===
    print("🔍 SCANNER ACTIVITY")
    print("-" * 80)
    
    scanner_runs = [e for e in entries if 'scanner' in e.get('message', '').lower() and 'completed' in e.get('message', '').lower()]
    watchlist_updates = [e for e in entries if 'Active watchlist' in e.get('message', '')]
    
    print(f"Scanner runs: {len(scanner_runs)}")
    
    for i, update in enumerate(watchlist_updates, 1):
        msg = update.get('message', '')
        ts = update.get('timestamp_obj')
        # Extract watchlist from message
        match = re.search(r"Active watchlist: \[(.*?)\]", msg)
        if match and ts:
            stocks = match.group(1).replace("'", "").split(', ')
            print(f"  {i}. {ts.strftime('%H:%M')} - {len(stocks)} stocks: {', '.join(stocks[:5])}{'...' if len(stocks) > 5 else ''}")
    print()
    
    # === TRADE ACTIVITY ===
    print("💰 TRADE ACTIVITY")
    print("-" * 80)
    
    buy_orders = [e for e in entries if 'BUY' in e.get('message', '') and 'Placing' in e.get('message', '')]
    buy_filled = [e for e in entries if 'BUY FILLED' in e.get('message', '')]
    sell_orders = [e for e in entries if 'SELL' in e.get('message', '') and ('Placing' in e.get('message', '') or 'MarketOrder' in e.get('message', ''))]
    sell_filled = [e for e in entries if 'SOLD' in e.get('message', '') and 'shares' in e.get('message', '')]
    
    print(f"BUY Orders Placed:  {len(buy_orders)}")
    print(f"BUY Orders Filled:  {len(buy_filled)}")
    print(f"SELL Orders Placed: {len(sell_orders)}")
    print(f"SELL Orders Filled: {len(sell_filled)}")
    print()
    
    if buy_filled:
        print("Recent BUY fills:")
        for trade in buy_filled[-5:]:
            print(f"  • {trade.get('timestamp', 'N/A')}: {trade.get('message', '')}")
        print()
    
    if sell_filled:
        print("Recent SELL fills:")
        for trade in sell_filled[-5:]:
            print(f"  • {trade.get('timestamp', 'N/A')}: {trade.get('message', '')}")
        print()
    
    # === ENTRY REJECTIONS ===
    print("🚫 ENTRY REJECTIONS (Last 20)")
    print("-" * 80)
    
    no_entry = [e for e in entries if 'NO ENTRY' in e.get('message', '')]
    
    # Count rejection reasons
    rejection_reasons = Counter()
    for entry in no_entry:
        msg = entry.get('message', '')
        if 'ATR' in msg and 'low volatility' in msg:
            rejection_reasons['ATR too low (< 0.3%)'] += 1
        elif 'RSI' in msg and '>=' in msg:
            rejection_reasons['RSI too high (overbought)'] += 1
        elif 'Price' in msg and '<=' in msg and 'VWAP' in msg:
            rejection_reasons['Price <= VWAP'] += 1
        else:
            rejection_reasons['Other'] += 1
    
    print("Rejection Summary:")
    for reason, count in rejection_reasons.most_common():
        print(f"  • {reason}: {count}")
    print()
    
    print("Last 20 rejections:")
    for entry in no_entry[-20:]:
        ts = entry.get('timestamp_obj')
        msg = entry.get('message', '').replace('NO ENTRY for ', '')
        if ts:
            print(f"  {ts.strftime('%H:%M:%S')} - {msg[:80]}")
    print()
    
    # === P&L TRACKING ===
    print("💵 P&L PROGRESSION")
    print("-" * 80)
    
    pnl_entries = [e for e in entries if 'Whole Account P&L' in e.get('message', '')]
    
    if pnl_entries:
        print(f"Total P&L checks: {len(pnl_entries)}")
        print()
        print("Sample progression (every 30 min):")
        
        # Sample every ~30 entries (approximately 30 minutes apart)
        step = max(1, len(pnl_entries) // 10)
        for entry in pnl_entries[::step]:
            ts = entry.get('timestamp_obj')
            msg = entry.get('message', '')
            if ts:
                print(f"  {ts.strftime('%H:%M')} - {msg}")
        
        # Show last entry
        last_pnl = pnl_entries[-1]
        print()
        print(f"FINAL: {last_pnl.get('timestamp', 'N/A')} - {last_pnl.get('message', '')}")
    print()
    
    # === EOD LIQUIDATION INVESTIGATION ===
    print("🔴 END-OF-DAY LIQUIDATION INVESTIGATION")
    print("=" * 80)
    
    # Check for market close detection
    market_close = [e for e in entries if 'market.*close' in e.get('message', '').lower() or '3:45' in e.get('message', '')]
    
    print(f"Market close detections: {len(market_close)}")
    if market_close:
        for entry in market_close:
            print(f"  • {entry.get('timestamp', 'N/A')}: {entry.get('message', '')}")
    else:
        print("  ⚠️  NO market close detection found!")
    print()
    
    # Check for liquidation attempts
    liquidation = [e for e in entries if 'liquidat' in e.get('message', '').lower()]
    
    print(f"Liquidation attempts: {len(liquidation)}")
    if liquidation:
        for entry in liquidation:
            print(f"  • {entry.get('timestamp', 'N/A')}: {entry.get('message', '')}")
    else:
        print("  ⚠️  NO liquidation attempts found!")
    print()
    
    # Check for positions at end of day
    position_checks = [e for e in entries if 'Processing' in e.get('message', '') and 'contracts' in e.get('message', '')]
    
    if position_checks:
        last_check = position_checks[-1]
        msg = last_check.get('message', '')
        match = re.search(r'Processing (\d+) contracts', msg)
        if match:
            num_contracts = int(match.group(1))
            print(f"Last position check: {num_contracts} contracts")
            print(f"Time: {last_check.get('timestamp', 'N/A')}")
            
            if num_contracts > 0:
                print()
                print("⚠️  WARNING: Bot had open positions at last check!")
                print("   These should have been liquidated by 3:45 PM ET")
    print()
    
    # Check what time the bot last ran
    if entries:
        last_entry = entries[-1]
        last_time = last_entry.get('timestamp_obj')
        
        if last_time:
            # Convert to ET (assuming system time is PT, add 3 hours)
            last_time_et = last_time + timedelta(hours=3)
            
            print(f"Bot last activity: {last_time.strftime('%H:%M:%S')} PT / {last_time_et.strftime('%H:%M:%S')} ET")
            
            # Check if it ran past 3:45 PM ET
            eod_liquidation_time = last_time_et.replace(hour=15, minute=45, second=0)
            
            if last_time_et < eod_liquidation_time:
                print("⚠️  Bot stopped BEFORE EOD liquidation time (3:45 PM ET)")
                print("   This explains why positions weren't liquidated!")
            elif last_time_et > eod_liquidation_time:
                print("✅ Bot ran AFTER EOD liquidation time")
                print("   Should have triggered liquidation - need to investigate code logic")
    print()
    
    # === CODE ANALYSIS ===
    print("🔍 CODE LIQUIDATION LOGIC CHECK")
    print("-" * 80)
    
    # Check if EOD liquidation code exists
    agent_file = "day_trading_agents.py"
    if os.path.exists(agent_file):
        with open(agent_file, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        
        # Search for EOD liquidation patterns
        patterns = {
            'Market close check': r'market.*close|15.*45|3.*45.*PM',
            'Liquidation function': r'def.*liquidate|liquidate_all',
            'Time-based exit': r'if.*hour.*>=.*15|if.*time.*>.*345',
            'Position closing': r'close.*all.*position|sell.*all'
        }
        
        found = {}
        for name, pattern in patterns.items():
            matches = re.findall(pattern, code, re.IGNORECASE)
            found[name] = len(matches) > 0
            print(f"  {'✅' if found[name] else '❌'} {name}: {'Found' if found[name] else 'NOT FOUND'}")
        
        print()
        
        if not any(found.values()):
            print("🚨 CRITICAL: No EOD liquidation logic found in code!")
            print("   The bot is missing automatic position closing at market close")
            print("   Recommendation: Add market close detection and liquidation")
    print()
    
    # === RECOMMENDATIONS ===
    print("💡 RECOMMENDATIONS")
    print("=" * 80)
    
    recommendations = []
    
    if not market_close:
        recommendations.append("1. Add market close time detection (3:45 PM ET)")
    
    if not liquidation:
        recommendations.append("2. Add automatic liquidation of all positions at EOD")
    
    if rejection_reasons.get('ATR too low (< 0.3%)', 0) > 50:
        recommendations.append("3. Consider lowering ATR threshold to 0.2% for more entries")
    
    if len(buy_filled) < 3:
        recommendations.append("4. Very few trades executed - market may be too quiet or criteria too strict")
    
    # Check if bot ran past market close
    if entries:
        last_time = entries[-1].get('timestamp_obj')
        if last_time:
            last_time_et = last_time + timedelta(hours=3)
            if last_time_et.hour >= 13:  # 1 PM PT = 4 PM ET (market close)
                if not liquidation:
                    recommendations.append("5. URGENT: Bot ran during/after market close but didn't liquidate positions")
    
    if recommendations:
        for rec in recommendations:
            print(f"  {rec}")
    else:
        print("  ✅ No major issues detected")
    print()
    
    print("=" * 80)
    print("Analysis complete!")
    print("=" * 80)

if __name__ == "__main__":
    analyze_trading_session()
