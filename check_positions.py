from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)

print("\n=== CURRENT POSITIONS ===")
positions = ib.portfolio()
for p in positions:
    if p.position != 0:
        print(f"{p.contract.symbol}: {p.position} shares @ ${p.averageCost:.2f} avg")
        print(f"  Current: ${p.marketPrice:.2f} | P&L: ${p.unrealizedPNL:.2f}")

print("\n=== ACCOUNT CASH ===")
acct = ib.accountSummary()
for v in acct:
    if v.tag == 'SettledCash' and v.currency == 'USD':
        print(f"SettledCash: ${float(v.value):,.2f}")
    elif v.tag == 'ExcessLiquidity' and v.currency == 'USD':
        print(f"ExcessLiquidity: ${float(v.value):,.2f}")

ib.disconnect()
