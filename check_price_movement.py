"""Check actual price movement of top picks from open to now"""
from ib_insync import IB, Stock
import ib_insync.util as ib_util
from datetime import datetime, timedelta

ib = IB()
ib_util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))

print("="*80)
print("TOP PICKS PRICE MOVEMENT - Open to Now")
print("="*80)

top_picks = ['WULF', 'RCAT', 'BYND', 'BBAR']

for symbol in top_picks:
    contract = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    
    # Get historical data - 1 day with 1-minute bars
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='1 D',
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=True,  # Regular trading hours only
        formatDate=1
    )
    
    if bars:
        open_price = bars[0].open  # First bar of the day
        current_price = bars[-1].close  # Most recent bar
        high_of_day = max(bar.high for bar in bars)
        low_of_day = min(bar.low for bar in bars)
        
        # Calculate gains
        gain_from_open = ((current_price - open_price) / open_price) * 100
        max_gain_possible = ((high_of_day - open_price) / open_price) * 100
        
        print(f"\n{symbol}:")
        print(f"  Open:    ${open_price:.2f}")
        print(f"  Current: ${current_price:.2f} ({gain_from_open:+.2f}%)")
        print(f"  High:    ${high_of_day:.2f} (max gain: {max_gain_possible:+.2f}%)")
        print(f"  Low:     ${low_of_day:.2f}")
        
        if max_gain_possible >= 1.8:
            print(f"  ✅ HIT +1.8% TARGET! (reached {max_gain_possible:.2f}%)")
        else:
            print(f"  ❌ Never reached +1.8% (max was {max_gain_possible:.2f}%)")
        
        # Check when we actually bought
        fills = [f for f in ib.fills() if f.contract.symbol == symbol and f.execution.side == 'BOT']
        if fills:
            our_entry = sum(f.execution.price for f in fills) / len(fills)
            our_gain = ((high_of_day - our_entry) / our_entry) * 100
            print(f"  Our entry: ${our_entry:.2f}")
            print(f"  Max gain from OUR entry: {our_gain:+.2f}%")
    else:
        print(f"\n{symbol}: No data available")

print("\n" + "="*80)
print("ANALYSIS")
print("="*80)
print("\nIf stocks moved >1.8% from OPEN but we didn't catch it:")
print("1. We entered too late (missed the morning move)")
print("2. Entry timing needs improvement")
print("3. Should enter at/near market open instead of mid-day")

ib.disconnect()
