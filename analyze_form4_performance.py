"""Analyze Form 4 strategy performance since inception"""
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Get all approved positions files
form4_dir = Path('weekly_bot/form4_reports')
approved_files = sorted(form4_dir.glob('approved_positions_*.json'))

print('=' * 80)
print('FORM 4 STRATEGY - COMPLETE TRADING HISTORY')
print('=' * 80)
print()

all_trades = []
total_invested = 0
unique_symbols = set()

for file in approved_files:
    try:
        with open(file, 'r') as f:
            data = json.load(f)
        
        approved_at = data.get('approved_at', '')[:10]  # Date only
        
        if 'approved_positions' in data:
            for pos in data['approved_positions']:
                if pos.get('status') == 'EXECUTED' and 'execution' in pos:
                    exec_data = pos['execution']
                    symbol = pos['symbol']
                    shares = exec_data.get('shares', 0)
                    fill_price = exec_data.get('fill_price', 0)
                    total_cost = exec_data.get('total_cost', 0)
                    
                    all_trades.append({
                        'date': approved_at,
                        'symbol': symbol,
                        'shares': shares,
                        'price': fill_price,
                        'cost': total_cost
                    })
                    
                    total_invested += total_cost
                    unique_symbols.add(symbol)
    except Exception as e:
        print(f"Error reading {file}: {e}")

print(f'Total Execution Dates: {len(approved_files)}')
print(f'Total Trades Executed: {len(all_trades)}')
print(f'Unique Symbols Traded: {len(unique_symbols)}')
print(f'Total Capital Deployed: ${total_invested:.2f}')
print()
print('TRADE HISTORY (Buys):')
print('-' * 80)

# Group by date
trades_by_date = defaultdict(list)
for trade in all_trades:
    trades_by_date[trade['date']].append(trade)

for date in sorted(trades_by_date.keys()):
    print(f"\n{date}:")
    for trade in trades_by_date[date]:
        print(f"  BUY {trade['shares']:6.0f} {trade['symbol']:6s} @ ${trade['price']:8.2f} = ${trade['cost']:9.2f}")

print()
print('=' * 80)

# Now get current positions from exit analysis
exit_files = sorted(form4_dir.glob('exit_analysis_*.json'))
if exit_files:
    latest_exit = exit_files[-1]
    print(f'\nLATEST POSITION STATUS ({latest_exit.name}):')
    print('=' * 80)
    
    with open(latest_exit, 'r') as f:
        exit_data = json.load(f)
    
    total_current_value = 0
    total_cost_basis = 0
    total_unrealized_pnl = 0
    
    if 'exit_decisions' in exit_data:
        print(f"\nCurrent Positions: {exit_data.get('positions_analyzed', 0)}")
        print('-' * 80)
        
        for decision in exit_data['exit_decisions']:
            pos = decision['position']
            symbol = pos['symbol']
            qty = pos['quantity']
            entry_price = pos['entry_price']
            current_price = pos['current_price']
            pnl_dollars = pos['pnl_dollars']
            pnl_pct = pos['pnl_pct']
            days_held = pos['days_held']
            market_value = pos['market_value']
            cost_basis = pos['cost_basis']
            
            total_current_value += market_value
            total_cost_basis += cost_basis
            total_unrealized_pnl += pnl_dollars
            
            print(f"\n{symbol}:")
            print(f"  Quantity: {qty}")
            print(f"  Entry: ${entry_price:.2f} -> Current: ${current_price:.2f}")
            print(f"  P&L: ${pnl_dollars:.2f} ({pnl_pct:+.2f}%)")
            print(f"  Days Held: {days_held}")
            print(f"  Market Value: ${market_value:.2f}")
            print(f"  Decision: {decision['decision']['decision']}")
    
    print()
    print('=' * 80)
    print('CURRENT PORTFOLIO SUMMARY:')
    print('=' * 80)
    print(f"Total Cost Basis: ${total_cost_basis:.2f}")
    print(f"Current Market Value: ${total_current_value:.2f}")
    print(f"Unrealized P&L: ${total_unrealized_pnl:.2f} ({(total_unrealized_pnl/total_cost_basis*100) if total_cost_basis > 0 else 0:.2f}%)")
    print()
    print(f"Total Capital Ever Deployed: ${total_invested:.2f}")
    print(f"Current Active Capital: ${total_cost_basis:.2f}")
    print(f"Cash Available: ${1000 - total_cost_basis:.2f}")
    print('=' * 80)
