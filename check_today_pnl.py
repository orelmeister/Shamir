from ib_insync import IB, util

ib = IB()
util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))
ib.reqMarketDataType(3)  # Use delayed/frozen data (free)

print("=" * 60)
print("TODAY'S NEW POSITIONS P&L (Nov 26)")
print("=" * 60)

new_symbols = ['DAO', 'SEM', 'SEMR']
positions = [p for p in ib.positions() if p.contract.symbol in new_symbols]

total_pnl = 0
for pos in positions:
    symbol = pos.contract.symbol
    qty = pos.position
    avg_cost = pos.avgCost
    
    # Request current market price
    ticker = ib.reqMktData(pos.contract, '', False, False)
    ib.sleep(1)
    
    current_price = ticker.last if ticker.last else ticker.close
    unrealized = (current_price - avg_cost) * qty
    
    print(f"{symbol:6} {qty:3.0f} shares @ ${avg_cost:7.2f} | Current: ${current_price:7.2f} | P&L: ${unrealized:+7.2f}")
    total_pnl += unrealized
    
    ib.cancelMktData(pos.contract)

print("=" * 60)
print(f"TOTAL P&L: ${total_pnl:+.2f}")
print("=" * 60)

ib.disconnect()
