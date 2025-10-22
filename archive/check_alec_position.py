from ib_insync import *
import time

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=5)
time.sleep(2)

# Get positions
positions = ib.positions()
alec_positions = [p for p in positions if p.contract.symbol == 'ALEC']

if alec_positions:
    alec = alec_positions[0]
    print(f"\n{'='*60}")
    print(f"ALEC POSITION DETAILS")
    print(f"{'='*60}")
    print(f"  Shares Held:        {alec.position}")
    print(f"  Avg Cost per Share: ${alec.avgCost:.4f}")
    
    # Calculate total cost
    total_cost = alec.avgCost * abs(alec.position)
    print(f"  Total Cost Basis:   ${total_cost:.2f}")
    
    # Try to get current ticker price
    try:
        contract = Stock('ALEC', 'SMART', 'USD')
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=True
        )
        if bars:
            current_price = bars[-1].close
            current_value = current_price * abs(alec.position)
            unrealized_pnl = current_value - total_cost
            pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0
            
            print(f"  Current Price:      ${current_price:.4f}")
            print(f"  Current Value:      ${current_value:.2f}")
            print(f"  Unrealized P&L:     ${unrealized_pnl:.2f}")
            print(f"  P&L Percentage:     {pnl_pct:+.2f}%")
    except Exception as e:
        print(f"  Could not fetch current price: {e}")
else:
    print("\nNo ALEC position found.")

# Get account summary
print(f"\n{'='*60}")
print(f"ACCOUNT SUMMARY")
print(f"{'='*60}")
account_summary = ib.accountSummary()
for item in account_summary:
    if item.tag in ['AvailableFunds', 'NetLiquidation', 'TotalCashValue', 'BuyingPower']:
        print(f"  {item.tag:20s}: ${float(item.value):.2f}")

# Get all open positions summary
print(f"\n{'='*60}")
print(f"ALL OPEN POSITIONS")
print(f"{'='*60}")
for p in positions:
    total_cost = p.avgCost * abs(p.position)
    print(f"  {p.contract.symbol:6s}: {p.position:6.0f} shares @ ${p.avgCost:.4f}, Cost: ${total_cost:.2f}")

ib.disconnect()
