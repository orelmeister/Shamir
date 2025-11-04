from ib_insync import *
from datetime import datetime, timedelta

ib = IB()
ib.connect('127.0.0.1', 4001, clientId=99)

fills = ib.fills()
print("\n=== RECENT TRADES (Last 10) ===")
for f in sorted(fills, key=lambda x: x.time, reverse=True)[:10]:
    trade_date = f.time.strftime('%Y-%m-%d %H:%M')
    # Settlement is T+2 for stocks
    settlement_date = (f.time + timedelta(days=2)).strftime('%Y-%m-%d')
    print(f"{trade_date} - {f.execution.side:4} {f.execution.shares:3.0f} {f.contract.symbol:6} @ ${f.execution.price:7.2f} | Settles: {settlement_date}")

print("\n=== CASH STATUS ===")
acct = ib.accountSummary()
for v in acct:
    if v.tag == 'SettledCash' and v.currency == 'USD':
        print(f"SettledCash: ${float(v.value):,.2f}")
    elif v.tag == 'ExcessLiquidity' and v.currency == 'USD':
        print(f"ExcessLiquidity: ${float(v.value):,.2f}")

print("\n📅 Today: November 4, 2025 (Monday)")
print("   Recent sells should settle by: November 6, 2025 (Wednesday)")

ib.disconnect()
