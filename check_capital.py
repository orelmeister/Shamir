#!/usr/bin/env python3
"""Check available capital for day trader"""

from ib_insync import IB

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)

print("=" * 70)
print("CAPITAL ALLOCATION ANALYSIS")
print("=" * 70)

# Get positions
positions = ib.positions()

# Separate by agent
day_trader_symbols = {'SEMR', 'ONDS', 'NESR'}
form4_symbols = {'OPK', 'BLND', 'ONB'}

day_trader_value = 0
form4_value = 0
other_value = 0
kura_value = 0
kss_value = 0

print("\nCURRENT POSITIONS:")
print("-" * 70)

for p in positions:
    symbol = p.contract.symbol
    qty = int(p.position)
    price = p.avgCost
    value = price * qty
    
    if symbol in day_trader_symbols:
        day_trader_value += value
        agent = "day_trader"
    elif symbol in form4_symbols:
        form4_value += value
        agent = "form4"
    elif symbol == 'KURA':
        kura_value += value
        agent = "UNKNOWN"
    elif symbol == 'KSS':
        kss_value += value
        agent = "UNKNOWN"
    else:
        other_value += value
        agent = "other"
    
    print(f"{symbol:6} {qty:>4} @ ${price:>7.2f} = ${value:>9.2f}  ({agent})")

print("-" * 70)
print(f"Day Trader Total:  ${day_trader_value:>9.2f}")
print(f"Form4 Total:       ${form4_value:>9.2f}")
print(f"KURA (unknown):    ${kura_value:>9.2f}")
print(f"KSS (unknown):     ${kss_value:>9.2f}")
print(f"Other:             ${other_value:>9.2f}")
print(f"GRAND TOTAL:       ${day_trader_value + form4_value + kura_value + kss_value + other_value:>9.2f}")

# Get account values
print("\nACCOUNT STATUS:")
print("-" * 70)

account_values = {}
for v in ib.accountValues():
    if v.currency == 'USD':
        try:
            account_values[v.tag] = float(v.value)
        except ValueError:
            pass

net_liq = account_values.get('NetLiquidation', 0)
excess_liq = account_values.get('ExcessLiquidity', 0)
settled_cash = account_values.get('SettledCash', 0)

print(f"Net Liquidation:   ${net_liq:>9,.2f}")
print(f"Excess Liquidity:  ${excess_liq:>9,.2f}")
print(f"Settled Cash:      ${settled_cash:>9,.2f}")

# Calculate available for day trader
print("\nDAY TRADER CAPITAL CALCULATION:")
print("-" * 70)

# Method from day_trading_agents.py: available = ExcessLiquidity - form4_value
available_for_day_trader = excess_liq - form4_value
print(f"Excess Liquidity:         ${excess_liq:>9,.2f}")
print(f"Form4 Position Value:     ${form4_value:>9,.2f}")
print(f"Available for Day Trader: ${available_for_day_trader:>9,.2f}")

# Current day trader usage
print(f"\nCurrent Day Trader Usage: ${day_trader_value:>9,.2f}")
print(f"Remaining Budget:         ${available_for_day_trader - day_trader_value:>9,.2f}")

# What about KURA and KSS?
if kura_value > 0 or kss_value > 0:
    print("\n⚠️  WARNING: Unknown positions found!")
    print(f"KURA: ${kura_value:.2f}")
    print(f"KSS:  ${kss_value:.2f}")
    print("These are not tracked in database. Might be orphaned day_trader positions?")

ib.disconnect()

print("\n" + "=" * 70)
