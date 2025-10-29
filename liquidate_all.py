"""
Quick script to liquidate ALL positions in IBKR paper account.
"""
from ib_insync import IB, Stock, LimitOrder
import time

def liquidate_all():
    ib = IB()
    try:
        print("Connecting to IBKR...")
        ib.connect('127.0.0.1', 4001, clientId=999)
        print("✅ Connected to IBKR\n")
        
        positions = ib.positions()
        
        if not positions:
            print("📭 No positions to liquidate")
            return
        
        print(f"Found {len(positions)} positions to liquidate:\n")
        
        for pos in positions:
            symbol = pos.contract.symbol
            quantity = int(abs(pos.position))
            avg_cost = pos.avgCost
            
            print(f"📤 Liquidating {symbol}: {quantity} shares @ ${avg_cost:.4f}")
            
            try:
                # Get current price
                contract = Stock(symbol, 'SMART', 'USD')
                bars = ib.reqHistoricalData(
                    contract, endDateTime='', durationStr='1 D',
                    barSizeSetting='1 min', whatToShow='TRADES', useRTH=True
                )
                
                if bars:
                    current_price = bars[-1].close
                    limit_price = round(current_price * 0.99, 2)  # -1% to ensure fill
                else:
                    limit_price = avg_cost * 0.99
                
                order = LimitOrder('SELL', quantity, limit_price)
                trade = ib.placeOrder(contract, order)
                
                # Wait for fill
                for _ in range(10):  # Wait up to 5 seconds
                    ib.sleep(0.5)
                    if trade.orderStatus.status == 'Filled':
                        break
                
                if trade.orderStatus.status == 'Filled':
                    exit_price = trade.orderStatus.avgFillPrice
                    pnl = (exit_price - avg_cost) * quantity
                    pnl_pct = ((exit_price - avg_cost) / avg_cost) * 100
                    print(f"   ✅ FILLED @ ${exit_price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                else:
                    print(f"   ⚠️  Order status: {trade.orderStatus.status}")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print("\n✅ Liquidation complete")
        
        # Show final account balance
        account_values = {v.tag: v.value for v in ib.accountSummary()}
        total_cash = float(account_values.get('TotalCashValue', 0))
        net_liq = float(account_values.get('NetLiquidation', 0))
        print(f"\n💰 Final Account: Cash=${total_cash:.2f}, Net Liquidation=${net_liq:.2f}")
        
    finally:
        ib.disconnect()
        print("\n🔌 Disconnected from IBKR")

if __name__ == "__main__":
    liquidate_all()
