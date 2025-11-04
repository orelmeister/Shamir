from ib_insync import *

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)

print("\n=== CASH AND LIQUIDITY VALUES ===")
acct = ib.accountSummary()
for v in acct:
    if 'Cash' in v.tag or 'Liquidity' in v.tag:
        if v.currency == 'USD':
            print(f"{v.tag}: ${float(v.value):,.2f}")

ib.disconnect()
