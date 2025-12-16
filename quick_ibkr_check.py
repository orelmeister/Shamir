import sys
from ib_insync import IB, util

print("Connecting to IBKR...")
sys.stdout.flush()

ib = IB()
util.run(ib.connectAsync('127.0.0.1', 4001, clientId=11))
ib.reqMarketDataType(3)

print(f"\nPositions in IBKR:")
sys.stdout.flush()

positions = ib.portfolio()
for p in positions:
    if p.position != 0:
        print(f"  {p.contract.symbol}: {p.position} @ ${p.averageCost:.2f}")
        sys.stdout.flush()

print(f"\nTotal: {len([p for p in positions if p.position != 0])} positions")
sys.stdout.flush()

ib.disconnect()
