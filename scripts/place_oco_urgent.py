#!/usr/bin/env python3
"""
Emergency OCO bracket placement for all open positions from today.
Places Take Profit (+2.6%) and Stop Loss (-0.9%) orders.
"""
from ib_insync import IB, Stock, LimitOrder, StopOrder
import time

# Today's positions (excluding SKYX which is protected)
TODAY_SYMBOLS = ['SUPV', 'MLTX', 'BCAX', 'CEPU', 'BYND', 'RCAT', 'WULF', 
                 'UDMY', 'CWH', 'RITM', 'BFLY', 'INDI', 'UP']

def place_oco_brackets():
    ib = IB()
    ib.connect('127.0.0.1', 4001, clientId=96)
    
    # Get current positions
    positions = [p for p in ib.positions() if p.contract.symbol in TODAY_SYMBOLS and p.position > 0]
    
    print(f"Found {len(positions)} positions to protect with OCO brackets:")
    
    for pos in positions:
        symbol = pos.contract.symbol
        quantity = int(pos.position)
        avg_cost = pos.avgCost
        
        print(f"\n{symbol}: {quantity} shares @ ${avg_cost:.2f}")
        
        # Calculate prices
        take_profit_price = avg_cost * 1.026  # +2.6%
        stop_loss_price = avg_cost * 0.991    # -0.9%
        
        print(f"  TP: ${take_profit_price:.2f} (+2.6%)")
        print(f"  SL: ${stop_loss_price:.2f} (-0.9%)")
        
        # Create contract
        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        # Create OCA group
        oca_group = f"OCA_{symbol}_{int(time.time())}"
        
        # Take Profit order
        tp_order = LimitOrder('SELL', quantity, take_profit_price)
        tp_order.ocaGroup = oca_group
        tp_order.ocaType = 1  # Cancel all when one fills
        tp_order.tif = 'GTC'
        tp_order.outsideRth = False
        
        # Stop Loss order
        sl_order = StopOrder('SELL', quantity, stop_loss_price)
        sl_order.ocaGroup = oca_group
        sl_order.ocaType = 1
        sl_order.tif = 'GTC'
        sl_order.outsideRth = False
        
        # Place both orders
        tp_trade = ib.placeOrder(contract, tp_order)
        sl_trade = ib.placeOrder(contract, sl_order)
        
        print(f"  ✅ OCO bracket placed (Group: {oca_group})")
        
        ib.sleep(0.5)
    
    print(f"\n✅ All OCO brackets placed!")
    
    # Verify
    print(f"\nOpen orders now: {len(ib.openOrders())}")
    
    ib.disconnect()

if __name__ == '__main__':
    place_oco_brackets()
