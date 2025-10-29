"""
Emergency liquidation script - Sells all positions from today's watchlist
"""
import json
from ib_insync import IB, Stock, MarketOrder, util
import time

def liquidate_today_positions():
    # Load today's watchlist
    try:
        with open('ranked_tickers.json', 'r') as f:
            watchlist = json.load(f)
        today_tickers = [item['ticker'] for item in watchlist]
        print(f"Today's watchlist: {today_tickers}\n")
    except:
        print("❌ Could not load watchlist")
        return
    
    # Connect to IBKR
    ib = IB()
    try:
        util.run(ib.connectAsync('127.0.0.1', 4001, clientId=98))
        print("✅ Connected to IBKR\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    # Get all positions
    positions = ib.positions()
    portfolio = ib.portfolio()
    
    if not positions:
        print("📭 No positions in account")
        ib.disconnect()
        return
    
    # Find today's positions
    today_positions = []
    for pos in positions:
        symbol = pos.contract.symbol
        if symbol in today_tickers:
            quantity = pos.position
            avg_cost = pos.avgCost
            
            # Get current price from portfolio
            portfolio_item = next((p for p in portfolio if p.contract.symbol == symbol), None)
            if portfolio_item:
                current_price = portfolio_item.marketPrice
            else:
                current_price = avg_cost
            
            pnl = (current_price - avg_cost) * quantity
            pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
            
            today_positions.append({
                'symbol': symbol,
                'quantity': quantity,
                'avg_cost': avg_cost,
                'current_price': current_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'contract': pos.contract
            })
    
    if not today_positions:
        print("📭 No positions from today's watchlist to liquidate")
        ib.disconnect()
        return
    
    print(f"🎯 Found {len(today_positions)} position(s) from today's watchlist:")
    print("=" * 80)
    
    total_pnl = 0
    for p in today_positions:
        profit_emoji = "🟢" if p['pnl'] > 0 else "🔴" if p['pnl'] < 0 else "⚪"
        print(f"{profit_emoji} {p['symbol']:6} | {p['quantity']:>5} shares @ ${p['avg_cost']:>7.2f} | "
              f"Now: ${p['current_price']:>7.2f} | P&L: {p['pnl']:>+8.2f} ({p['pnl_pct']:>+6.2f}%)")
        total_pnl += p['pnl']
    
    print("=" * 80)
    print(f"📊 Total P&L if liquidated now: ${total_pnl:+.2f}\n")
    
    # Confirm liquidation
    print("⚠️  Are you sure you want to liquidate ALL these positions?")
    print("   This will submit MARKET SELL orders immediately.")
    confirm = input("   Type 'YES' to confirm: ")
    
    if confirm.strip().upper() != 'YES':
        print("\n❌ Liquidation cancelled")
        ib.disconnect()
        return
    
    print("\n🚀 Starting liquidation...\n")
    
    # Sell each position
    trades = []
    for p in today_positions:
        symbol = p['symbol']
        quantity = p['quantity']
        
        print(f"📤 Selling {quantity} shares of {symbol}...")
        
        try:
            # Create contract and order
            contract = Stock(symbol, 'SMART', 'USD')
            ib.qualifyContracts(contract)
            order = MarketOrder('SELL', quantity)
            
            # Place order
            trade = ib.placeOrder(contract, order)
            trades.append({'symbol': symbol, 'trade': trade})
            
            # Wait for fill
            for i in range(10):  # Wait up to 5 seconds
                time.sleep(0.5)
                if trade.orderStatus.status == 'Filled':
                    break
            
            if trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                filled_qty = trade.orderStatus.filled
                actual_pnl = (fill_price - p['avg_cost']) * filled_qty
                actual_pnl_pct = ((fill_price - p['avg_cost']) / p['avg_cost'] * 100)
                
                profit_emoji = "✅" if actual_pnl > 0 else "❌" if actual_pnl < 0 else "⚪"
                print(f"   {profit_emoji} FILLED: {filled_qty} shares @ ${fill_price:.2f} | "
                      f"P&L: ${actual_pnl:+.2f} ({actual_pnl_pct:+.2f}%)\n")
            else:
                print(f"   ⏳ Order status: {trade.orderStatus.status} (may fill shortly)\n")
        
        except Exception as e:
            print(f"   ❌ Error selling {symbol}: {e}\n")
    
    print("=" * 80)
    print("🏁 Liquidation complete!")
    print("\nℹ️  Check TWS to verify all orders filled")
    print("ℹ️  You can now restart the bot with fresh capital\n")
    
    ib.disconnect()

if __name__ == '__main__':
    liquidate_today_positions()
