import requests
import os
from dotenv import load_dotenv
from observability import get_database

load_dotenv()

# Get current prices from Polygon
polygon_key = os.getenv('POLYGON_API_KEY')

symbols = {
    'SEMR': {'qty': 57, 'cost': 11.82, 'agent': 'day_trader'},
    'KURA': {'qty': 28, 'cost': 11.87, 'agent': 'day_trader'},
    'KSS': {'qty': 16, 'cost': 19.56, 'agent': 'day_trader'},
    'NESR': {'qty': 23, 'cost': 13.78, 'agent': 'day_trader'},
    'ONDS': {'qty': 48, 'cost': 6.80, 'agent': 'day_trader'},
    'DAO': {'qty': 2, 'cost': 9.43, 'agent': 'day_trader'},
    'SEM': {'qty': 1, 'cost': 15.70, 'agent': 'day_trader'},
    'OPK': {'qty': 195, 'cost': 1.30, 'agent': 'form4'},
    'BLND': {'qty': 100, 'cost': 3.09, 'agent': 'form4'},
    'ONB': {'qty': 49, 'cost': 20.04, 'agent': 'form4'}
}

print('='*80)
print('BOT PERFORMANCE ANALYSIS - WEEK OF NOV 24-26, 2025')
print('='*80)
print()

day_trader_invested = 0
day_trader_current = 0
form4_invested = 0
form4_current = 0

print('CURRENT POSITIONS WITH LIVE PRICES:')
print('='*80)

for symbol, info in symbols.items():
    qty = info['qty']
    cost = info['cost']
    agent = info['agent']
    
    # Get current price from Polygon
    try:
        url = f'https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={polygon_key}'
        resp = requests.get(url)
        data = resp.json()
        
        if 'results' in data and data['results']:
            current_price = data['results'][0]['c']
            invested = qty * cost
            current_value = qty * current_price
            pnl = current_value - invested
            pnl_pct = (pnl / invested) * 100
            
            if agent == 'day_trader':
                day_trader_invested += invested
                day_trader_current += current_value
            else:
                form4_invested += invested
                form4_current += current_value
            
            print(f'{agent.upper():12} | {symbol:6} {qty:4} @ ${cost:6.2f} -> ${current_price:6.2f} | ${pnl:+8.2f} ({pnl_pct:+6.2f}%)')
        else:
            print(f'{agent.upper():12} | {symbol:6} {qty:4} @ ${cost:6.2f} -> NO DATA')
    except Exception as e:
        print(f'{agent.upper():12} | {symbol:6} {qty:4} @ ${cost:6.2f} -> ERROR: {str(e)[:30]}')

print()
print('='*80)
print('TRADE HISTORY THIS WEEK')
print('='*80)

# Get trades from database
db = get_database()
dates = ['2025-11-24', '2025-11-25', '2025-11-26']
day_trader_trades = []
form4_trades = []

for date in dates:
    trades = db.get_trades_by_date(date)
    for trade in trades:
        if trade['agent_name'] in ['day_trader', 'IntradayTraderAgent']:
            day_trader_trades.append(trade)
        elif trade['agent_name'] in ['form4_strategy', 'PreFlightTest']:
            form4_trades.append(trade)

print(f'\nDay Trader: {len(day_trader_trades)} trades')
for t in day_trader_trades:
    print(f"  {t['timestamp'][:16]} | {t['action']:4} {t['quantity']:3.0f} {t['symbol']:6} @ ${t['price']:7.2f}")

print(f'\nForm4 Bot: {len(form4_trades)} trades')
for t in form4_trades:
    print(f"  {t['timestamp'][:16]} | {t['action']:4} {t['quantity']:3.0f} {t['symbol']:6} @ ${t['price']:7.2f}")

print()
print('='*80)
print('FINAL SCORECARD')
print('='*80)

day_trader_pnl = day_trader_current - day_trader_invested
day_trader_roi = (day_trader_pnl / day_trader_invested * 100) if day_trader_invested > 0 else 0

form4_pnl = form4_current - form4_invested  
form4_roi = (form4_pnl / form4_invested * 100) if form4_invested > 0 else 0

print(f'\nDAY TRADER BOT:')
print(f'  Capital Deployed:     ${day_trader_invested:,.2f}')
print(f'  Current Value:        ${day_trader_current:,.2f}')
print(f'  Unrealized P&L:       ${day_trader_pnl:+,.2f}')
print(f'  ROI:                  {day_trader_roi:+.2f}%')
print(f'  Trades Executed:      {len(day_trader_trades)}')

print(f'\nFORM4 BOT:')
print(f'  Capital Deployed:     ${form4_invested:,.2f}')
print(f'  Current Value:        ${form4_current:,.2f}')
print(f'  Unrealized P&L:       ${form4_pnl:+,.2f}')
print(f'  ROI:                  {form4_roi:+.2f}%')
print(f'  Trades Executed:      {len(form4_trades)}')

print()
print('='*80)
print('WINNER ANALYSIS')
print('='*80)

if day_trader_roi > form4_roi:
    winner = 'DAY TRADER'
    margin = day_trader_roi - form4_roi
elif form4_roi > day_trader_roi:
    winner = 'FORM4'
    margin = form4_roi - day_trader_roi
else:
    winner = 'TIE'
    margin = 0

print(f'\n🏆 WINNER: {winner}')
if winner != 'TIE':
    print(f'   Margin: +{margin:.2f}% ROI advantage')
    print(f'   Absolute P&L Difference: ${abs(day_trader_pnl - form4_pnl):.2f}')

print()
