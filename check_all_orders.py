"""Get all actual trades from IBKR for today - the real source of truth""""""

from ib_insync import IBCheck all orders in IBKR - including historical ones from today

import ib_insync.util as ib_util"""

from datetime import datetimefrom ib_insync import IB

from collections import defaultdictfrom datetime import datetime



print("="*80)ib = IB()

print("ACTUAL TRADING ACTIVITY FROM IBKR - October 29, 2025")ib.connect('127.0.0.1', 4001, clientId=97)

print("="*80)

print("\n📊 ALL ORDERS (Today):")

ib = IB()print("=" * 100)

try:

    ib_util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))# Get all orders placed today

    print("\n✓ Connected to IBKR\n")all_trades = ib.trades()

    

    # Get fills for todaysell_orders = [t for t in all_trades if t.order.action == 'SELL']

    today = datetime.now().date()buy_orders = [t for t in all_trades if t.order.action == 'BUY']

    fills = ib.fills()

    print(f"\n📤 SELL Orders: {len(sell_orders)}")

    # Filter for today's fillsprint("-" * 100)

    today_fills = []for trade in sell_orders:

    for fill in fills:    symbol = trade.contract.symbol

        fill_time = fill.time    qty = int(trade.order.totalQuantity)

        if fill_time.date() == today:    price = trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else 0

            today_fills.append(fill)    status = trade.orderStatus.status

        order_id = trade.order.orderId

    if not today_fills:    filled = trade.orderStatus.filled

        print("No fills found for today")    

    else:    print(f"{symbol:8} | SELL {qty:4} @ ${price:7.2f} | {status:12} | OrderID: {order_id:6} | Filled: {filled}")

        print(f"Total fills today: {len(today_fills)}")

        print("\n" + "="*80)print(f"\n📥 BUY Orders (last 10): {len(buy_orders)}")

        print("ALL TRADES TODAY (from IBKR)")print("-" * 100)

        print("="*80)for trade in buy_orders[-10:]:

            symbol = trade.contract.symbol

        # Organize by symbol    qty = int(trade.order.totalQuantity)

        by_symbol = defaultdict(list)    price = trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else 0

        for fill in today_fills:    status = trade.orderStatus.status

            symbol = fill.contract.symbol    order_id = trade.order.orderId

            by_symbol[symbol].append(fill)    filled = trade.orderStatus.filled

            

        # Process each symbol    print(f"{symbol:8} | BUY  {qty:4} @ ${price:7.2f} | {status:12} | OrderID: {order_id:6} | Filled: {filled}")

        total_pnl = 0

        completed_trades = 0print("\n📋 Current Open Orders:")

        winners = 0print("-" * 100)

        losers = 0open_trades = ib.openTrades()

        if open_trades:

        for symbol in sorted(by_symbol.keys()):    for trade in open_trades:

            fills_for_symbol = by_symbol[symbol]        symbol = trade.contract.symbol

                    action = trade.order.action

            print(f"\n{symbol}:")        qty = int(trade.order.totalQuantity)

                    price = trade.order.lmtPrice if hasattr(trade.order, 'lmtPrice') else 0

            buys = []        status = trade.orderStatus.status

            sells = []        order_id = trade.order.orderId

                    

            for fill in fills_for_symbol:        print(f"{symbol:8} | {action:4} {qty:4} @ ${price:7.2f} | {status:12} | OrderID: {order_id:6}")

                action = fill.execution.sideelse:

                qty = fill.execution.shares    print("No open orders")

                price = fill.execution.price

                time = fill.time.strftime("%H:%M:%S")ib.disconnect()

                commission = fill.commissionReport.commission if fill.commissionReport else 0print("\n✅ Done")

                
                if action == 'BOT':  # Bought
                    buys.append((qty, price, time, commission))
                    print(f"  BUY:  {qty} shares @ ${price:.2f} at {time} (commission: ${commission:.2f})")
                elif action == 'SLD':  # Sold
                    sells.append((qty, price, time, commission))
                    print(f"  SELL: {qty} shares @ ${price:.2f} at {time} (commission: ${commission:.2f})")
            
            # Calculate P&L if we have both buys and sells
            if buys and sells:
                total_buy_cost = sum(qty * price + comm for qty, price, _, comm in buys)
                total_buy_shares = sum(qty for qty, _, _, _ in buys)
                total_sell_proceeds = sum(qty * price - comm for qty, price, _, comm in sells)
                total_sell_shares = sum(qty for qty, _, _, _ in sells)
                
                if total_sell_shares > 0:
                    # Calculate realized P&L
                    matched_shares = min(total_buy_shares, total_sell_shares)
                    avg_buy = total_buy_cost / total_buy_shares
                    avg_sell = total_sell_proceeds / total_sell_shares
                    
                    pnl = (avg_sell - avg_buy) * matched_shares
                    pnl_pct = (pnl / (avg_buy * matched_shares)) * 100 if avg_buy > 0 else 0
                    
                    total_pnl += pnl
                    completed_trades += 1
                    
                    if pnl > 0:
                        winners += 1
                        print(f"  ✅ PROFIT: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                    elif pnl < 0:
                        losers += 1
                        print(f"  ❌ LOSS: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                    else:
                        print(f"  ⚪ BREAKEVEN")
                    
                    remaining = total_buy_shares - total_sell_shares
                    if remaining > 0:
                        print(f"  ⚠️  STILL HOLDING: {remaining} shares")
                    elif remaining < 0:
                        print(f"  ⚠️  OVER-SOLD: {abs(remaining)} shares")
            elif buys:
                total_cost = sum(qty * price + comm for qty, price, _, comm in buys)
                total_shares = sum(qty for qty, _, _, _ in buys)
                avg_price = total_cost / total_shares if total_shares > 0 else 0
                print(f"  📊 POSITION STILL OPEN: {total_shares} shares, cost ${total_cost:.2f} (avg ${avg_price:.2f})")
            elif sells:
                total_proceeds = sum(qty * price - comm for qty, price, _, comm in sells)
                total_shares = sum(qty for qty, _, _, _ in sells)
                avg_price = total_proceeds / total_shares if total_shares > 0 else 0
                print(f"  ⚠️  SOLD OLD POSITION: {total_shares} shares @ avg ${avg_price:.2f}")
                print(f"     (No BUY today - this was from before)")
        
        print("\n" + "="*80)
        print("DAILY SUMMARY")
        print("="*80)
        
        print(f"\nCompleted round-trip trades: {completed_trades}")
        if completed_trades > 0:
            print(f"  ✅ Winners: {winners} ({winners/completed_trades*100:.1f}%)")
            print(f"  ❌ Losers: {losers} ({losers/completed_trades*100:.1f}%)")
        
        print(f"\n💰 Total Realized P&L: ${total_pnl:.2f}")
        
        if total_pnl > 0:
            print(f"\n✅ PROFITABLE DAY: +${total_pnl:.2f}")
        elif total_pnl < 0:
            print(f"\n❌ LOSING DAY: ${total_pnl:.2f}")
        else:
            print(f"\n⚪ BREAKEVEN DAY")
    
    print("\n" + "="*80)
    print("CURRENT POSITIONS IN IBKR")
    print("="*80)
    
    positions = ib.positions()
    open_positions = [p for p in positions if p.position > 0]
    
    if open_positions:
        print(f"\nOpen positions: {len(open_positions)}")
        for pos in open_positions:
            print(f"  {pos.contract.symbol}: {int(pos.position)} shares @ ${pos.avgCost:.2f}")
    else:
        print("\n✓ No open positions - account is FLAT")
    
    ib.disconnect()
    print("\n" + "="*80)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
