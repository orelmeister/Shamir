"""Track Form 4 position history through exit analysis files"""
import json
from pathlib import Path

exit_dir = Path('weekly_bot/form4_reports')
exit_files = sorted(exit_dir.glob('exit_analysis_*.json'))

print('=' * 80)
print('FORM 4 EXIT ANALYSIS HISTORY - POSITION COUNT TRACKER')
print('=' * 80)
print()

for file in exit_files[-10:]:  # Last 10 exit analyses
    with open(file, 'r') as f:
        data = json.load(f)
    
    date = data.get('date', 'Unknown')
    positions_analyzed = data.get('positions_analyzed', 0)
    sell_decisions = data.get('sell_decisions', 0)
    hold_decisions = data.get('hold_decisions', 0)
    realized_pnl = data.get('total_realized_pnl', 0)
    
    print(f'{date}: {positions_analyzed} positions | {sell_decisions} SELL | {hold_decisions} HOLD | PnL: ${realized_pnl:.2f}')
    
    # Show what symbols were analyzed
    symbols = []
    for decision in data.get('exit_decisions', []):
        pos = decision.get('position', {})
        symbol = pos.get('symbol')
        decision_type = decision.get('decision', {}).get('decision', 'UNKNOWN')
        exec_status = decision.get('execution', {}).get('status', 'PENDING')
        pnl_pct = pos.get('pnl_pct', 0)
        
        if decision_type == 'SELL' and exec_status in ['FILLED', 'COMPLETED']:
            symbols.append(f'{symbol} (SOLD {pnl_pct:+.1f}%)')
        elif decision_type == 'SELL':
            symbols.append(f'{symbol} (SELL ORDER {pnl_pct:+.1f}%)')
        else:
            symbols.append(f'{symbol} ({decision_type} {pnl_pct:+.1f}%)')
    
    symbol_list = ', '.join(symbols)
    print(f'   {symbol_list}')
    print()

print('=' * 80)
print()

# Now check IBKR positions to see what's actually in the account
print('CHECKING IBKR ACCOUNT FOR ACTUAL POSITIONS...')
print('=' * 80)
print()

try:
    from ib_insync import IB, util
    
    ib = IB()
    util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))
    ib.reqMarketDataType(3)
    
    positions = ib.positions()
    
    if positions:
        print(f'Found {len(positions)} positions in IBKR account:')
        print()
        for pos in positions:
            print(f'   {pos.contract.symbol}: {pos.position} shares @ ${pos.avgCost:.2f}')
    else:
        print('No positions found in IBKR account.')
    
    ib.disconnect()
except Exception as e:
    print(f'Could not connect to IBKR: {e}')
    print('Run this when IBKR Gateway/TWS is open to see actual positions.')
