from ib_insync import IB, util
from observability import get_database
import pandas as pd
from datetime import datetime, timedelta

# Connect to IBKR
ib = IB()
util.run(ib.connectAsync('127.0.0.1', 4001, clientId=98))

# Get account summary
account_summary = ib.accountSummary()
net_liquidation = 0
for item in account_summary:
    if item.tag == 'NetLiquidation':
        try:
            net_liquidation = float(item.value)
        except:
            pass
print(f'Current Account Net Liquidation: ${net_liquidation:,.2f}')
print()

# Get all current positions
positions = ib.positions()
print('='*80)
print('CURRENT POSITIONS BY BOT')
print('='*80)

# Get database
db = get_database()

form4_value = 0
form4_unrealized = 0
day_trader_value = 0
day_trader_unrealized = 0
unknown_value = 0

form4_positions = []
day_trader_positions = []
unknown_positions = []

for pos in positions:
    symbol = pos.contract.symbol
    qty = pos.position
    avg_cost = pos.avgCost
    position_value = qty * avg_cost
    
    # Get current market price
    ticker = ib.reqMktData(pos.contract, '', False, False)
    ib.sleep(0.5)
    current_price = ticker.last if ticker.last else ticker.close if ticker.close else avg_cost
    ib.cancelMktData(pos.contract)
    
    unrealized_pnl = (current_price - avg_cost) * qty
    
    # Check trades table for agent ownership
    # Get recent trades (last 1000 should cover all positions)
    all_trades = db.get_recent_trades(limit=1000)
    symbol_trades = [t for t in all_trades if t['symbol'] == symbol]
    
    if any(t['agent_name'] in ['form4_strategy', 'PreFlightTest'] for t in symbol_trades):
        agent = 'FORM4'
        form4_value += position_value
        form4_unrealized += unrealized_pnl
        form4_positions.append((symbol, qty, avg_cost, current_price, unrealized_pnl))
    elif any(t['agent_name'] in ['day_trader', 'IntradayTraderAgent'] for t in symbol_trades):
        agent = 'DAY_TRADER'
        day_trader_value += position_value
        day_trader_unrealized += unrealized_pnl
        day_trader_positions.append((symbol, qty, avg_cost, current_price, unrealized_pnl))
    else:
        agent = 'UNKNOWN'
        unknown_value += position_value
        unknown_positions.append((symbol, qty, avg_cost, current_price, unrealized_pnl))

print(f'\n{"="*80}')
print(f'FORM4 BOT - ${form4_value:,.2f} invested')
print(f'{"="*80}')
for symbol, qty, cost, current, pnl in form4_positions:
    pnl_pct = (pnl / (cost * qty)) * 100
    print(f'  {symbol:6} {qty:4.0f} @ ${cost:6.2f} -> ${current:6.2f} | P&L: ${pnl:+8.2f} ({pnl_pct:+6.2f}%)')
print(f'\nForm4 Unrealized P&L: ${form4_unrealized:+,.2f}')

print(f'\n{"="*80}')
print(f'DAY TRADER BOT - ${day_trader_value:,.2f} invested')
print(f'{"="*80}')
for symbol, qty, cost, current, pnl in day_trader_positions:
    pnl_pct = (pnl / (cost * qty)) * 100
    print(f'  {symbol:6} {qty:4.0f} @ ${cost:6.2f} -> ${current:6.2f} | P&L: ${pnl:+8.2f} ({pnl_pct:+6.2f}%)')
print(f'\nDay Trader Unrealized P&L: ${day_trader_unrealized:+,.2f}')

if unknown_positions:
    print(f'\n{"="*80}')
    print(f'UNKNOWN - ${unknown_value:,.2f} invested')
    print(f'{"="*80}')
    for symbol, qty, cost, current, pnl in unknown_positions:
        pnl_pct = (pnl / (cost * qty)) * 100
        print(f'  {symbol:6} {qty:4.0f} @ ${cost:6.2f} -> ${current:6.2f} | P&L: ${pnl:+8.2f} ({pnl_pct:+6.2f}%)')

print(f'\n{"="*80}')
print('TRADES THIS WEEK (Nov 24-26)')
print(f'{"="*80}')

# Get trades from Nov 24, 25, 26
dates = ['2025-11-24', '2025-11-25', '2025-11-26']
form4_trades = []
day_trader_trades = []

for date in dates:
    day_trades = db.get_trades_by_date(date)
    for trade in day_trades:
        if trade['agent_name'] in ['form4_strategy', 'PreFlightTest']:
            form4_trades.append(trade)
        elif trade['agent_name'] in ['day_trader', 'IntradayTraderAgent']:
            day_trader_trades.append(trade)

print(f'\nForm4 Bot Trades: {len(form4_trades)}')
for trade in form4_trades[:20]:  # Show first 20
    print(f"  {trade['timestamp'][:16]} | {trade['action']:4} {trade['quantity']:3.0f} {trade['symbol']:6} @ ${trade['price']:7.2f}")

print(f'\nDay Trader Trades: {len(day_trader_trades)}')
for trade in day_trader_trades[:20]:  # Show first 20
    print(f"  {trade['timestamp'][:16]} | {trade['action']:4} {trade['quantity']:3.0f} {trade['symbol']:6} @ ${trade['price']:7.2f}")

print(f'\n{"="*80}')
print('SUMMARY')
print(f'{"="*80}')
print(f'Form4 Bot:')
print(f'  Capital Deployed: ${form4_value:,.2f}')
print(f'  Unrealized P&L:   ${form4_unrealized:+,.2f}')
print(f'  ROI:              {(form4_unrealized/form4_value)*100:+.2f}%' if form4_value > 0 else '  ROI: N/A')
print(f'\nDay Trader Bot:')
print(f'  Capital Deployed: ${day_trader_value:,.2f}')
print(f'  Unrealized P&L:   ${day_trader_unrealized:+,.2f}')
print(f'  ROI:              {(day_trader_unrealized/day_trader_value)*100:+.2f}%' if day_trader_value > 0 else '  ROI: N/A')

ib.disconnect()
