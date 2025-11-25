#!/usr/bin/env python3
"""Today's Day Trader Performance Summary"""

from ib_insync import IB

print("=" * 70)
print("TODAY'S PERFORMANCE - DAY TRADER POSITIONS")
print("November 24, 2025")
print("=" * 70)

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)
ib.reqMarketDataType(3)  # Use delayed/frozen market data (FREE)

# Day trader positions
dt_symbols = {'SEMR': (28, 11.82), 'ONDS': (48, 6.80), 'NESR': (23, 13.78)}

print(f"\n{'Symbol':<8} {'Qty':>5} {'Entry':>10} {'Avg Cost':>10} {'Value':>12} {'P&L $':>10} {'P&L %':>8}")
print("-" * 70)

total_pnl = 0
total_invested = 0
total_value = 0

# Get all positions from IBKR
positions = ib.positions()

for symbol, (qty, entry_price) in dt_symbols.items():
    # Find position in IBKR
    pos_list = [p for p in positions if p.contract.symbol == symbol]
    
    if pos_list:
        pos = pos_list[0]
        # Use avgCost from IBKR (this is the actual average cost basis)
        avg_cost = pos.avgCost
        quantity = int(pos.position)
        
        # Calculate value at avg cost
        position_value = avg_cost * quantity
        invested = entry_price * qty
        
        # P&L: difference between IBKR's cost basis and our entry
        # (If avgCost > entry, we're down; if avgCost < entry, we're up)
        pnl_dollars = (avg_cost - entry_price) * quantity
        pnl_pct = (pnl_dollars / invested) * 100 if invested > 0 else 0
        
        total_pnl += pnl_dollars
        total_invested += invested
        total_value += position_value
        
        print(f"{symbol:<8} {quantity:>5} ${entry_price:>9.2f} ${avg_cost:>9.2f} ${position_value:>11.2f} ${pnl_dollars:>9.2f} {pnl_pct:>7.2f}%")
    else:
        # Position not found, use entry prices
        invested = qty * entry_price
        total_invested += invested
        total_value += invested
        print(f"{symbol:<8} {qty:>5} ${entry_price:>9.2f} CLOSED    ${invested:>11.2f} $     0.00     0.00%")

print("-" * 70)
if total_invested > 0:
    print(f"{'TOTALS':<8} {'':<5} {'':<10} {'':<10} ${total_value:>11.2f} ${total_pnl:>9.2f} {(total_pnl/total_invested)*100:>7.2f}%")

print(f"\n📊 SUMMARY:")
print(f"  Capital Allocated: ${total_invested:.2f} / $1,000.00 ({(total_invested/1000)*100:.1f}%)")
print(f"  Current Value:     ${total_value:.2f}")
if total_invested > 0:
    print(f"  Price Change:      ${total_pnl:+.2f} ({(total_pnl/total_invested)*100:+.2f}%)")
    
print("\nNOTE: P&L shown is based on IBKR's avg cost vs entry. Real-time P&L requires live data subscription.")

# Check account (safely)
try:
    account_values = {}
    for v in ib.accountValues():
        if v.currency == 'USD':
            try:
                account_values[v.tag] = float(v.value)
            except ValueError:
                pass  # Skip non-numeric values
    
    print(f"\n💰 ACCOUNT:")
    if 'NetLiquidation' in account_values:
        print(f"  Net Liquidation:  ${account_values['NetLiquidation']:,.2f}")
    if 'ExcessLiquidity' in account_values:
        print(f"  Excess Liquidity: ${account_values['ExcessLiquidity']:,.2f}")
    if 'RealizedPnL' in account_values:
        print(f"  Realized P&L:     ${account_values['RealizedPnL']:,.2f}")
    if 'UnrealizedPnL' in account_values:
        print(f"  Unrealized P&L:   ${account_values['UnrealizedPnL']:,.2f}")
except Exception as e:
    print(f"\n💰 ACCOUNT: (error retrieving: {e})")

ib.disconnect()

print("\n" + "=" * 70)
