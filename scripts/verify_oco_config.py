"""
Verify OCO Bracket Order Setup (No Live Orders)
This validates the OCO configuration is correct without placing real orders.
We'll place orders during market hours tomorrow to confirm execution.
"""

from ib_insync import *
import time

def verify_oco_setup():
    """Verify OCO bracket configuration is valid"""
    
    print("=" * 70)
    print("🔍 OCO Bracket Configuration Verification")
    print("=" * 70)
    
    # Connect to IBKR
    ib = IB()
    try:
        ib.connect('127.0.0.1', 4001, clientId=99)
        print("✅ Connected to IBKR (Client ID 99)")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return False
    
    # Test symbol
    test_symbol = "AAPL"
    contract = Stock(test_symbol, 'SMART', 'USD')
    ib.qualifyContracts(contract)
    print(f"✅ Contract qualified: {contract.symbol}")
    
    # Simulate entry fill
    simulated_entry_price = 150.00
    simulated_quantity = 10
    
    print(f"\n📊 Simulated Entry:")
    print(f"   Symbol: {test_symbol}")
    print(f"   Quantity: {simulated_quantity}")
    print(f"   Fill Price: ${simulated_entry_price:.2f}")
    
    # Calculate bracket prices
    take_profit_price = round(simulated_entry_price * 1.026, 2)  # +2.6%
    stop_loss_price = round(simulated_entry_price * 0.991, 2)     # -0.9%
    
    print(f"\n📈 Bracket Prices:")
    print(f"   Take Profit: ${take_profit_price:.2f} (+2.6%)")
    print(f"   Stop Loss: ${stop_loss_price:.2f} (-0.9%)")
    
    # Create OCA group
    oca_group = f"OCA_{test_symbol}_{int(time.time())}"
    print(f"\n🔗 OCA Group: {oca_group}")
    
    # Create Take Profit order
    print("\n1️⃣  Take Profit Order (LIMIT SELL):")
    tp_order = LimitOrder('SELL', simulated_quantity, take_profit_price)
    tp_order.ocaGroup = oca_group
    tp_order.ocaType = 1  # Cancel all on fill
    tp_order.tif = 'DAY'
    tp_order.outsideRth = False
    
    print(f"   ✅ Action: {tp_order.action}")
    print(f"   ✅ Order Type: LIMIT")
    print(f"   ✅ Quantity: {tp_order.totalQuantity}")
    print(f"   ✅ Limit Price: ${tp_order.lmtPrice:.2f}")
    print(f"   ✅ OCA Group: {tp_order.ocaGroup}")
    print(f"   ✅ OCA Type: {tp_order.ocaType} (Cancel all on fill)")
    print(f"   ✅ TIF: {tp_order.tif}")
    
    # Create Stop Loss order
    print("\n2️⃣  Stop Loss Order (STOP SELL):")
    sl_order = StopOrder('SELL', simulated_quantity, stop_loss_price)
    sl_order.ocaGroup = oca_group  # SAME group
    sl_order.ocaType = 1  # Cancel all on fill
    sl_order.tif = 'DAY'
    sl_order.outsideRth = False
    
    print(f"   ✅ Action: {sl_order.action}")
    print(f"   ✅ Order Type: STOP")
    print(f"   ✅ Quantity: {sl_order.totalQuantity}")
    print(f"   ✅ Stop Price: ${sl_order.auxPrice:.2f}")
    print(f"   ✅ OCA Group: {sl_order.ocaGroup}")
    print(f"   ✅ OCA Type: {sl_order.ocaType} (Cancel all on fill)")
    print(f"   ✅ TIF: {sl_order.tif}")
    
    # Verify OCA groups match
    print("\n🔍 Verification Checks:")
    
    checks = [
        ("OCA groups match", tp_order.ocaGroup == sl_order.ocaGroup),
        ("OCA types match", tp_order.ocaType == sl_order.ocaType),
        ("Both are SELL orders", tp_order.action == 'SELL' and sl_order.action == 'SELL'),
        ("Quantities match", tp_order.totalQuantity == sl_order.totalQuantity),
        ("TP price > entry", tp_order.lmtPrice > simulated_entry_price),
        ("SL price < entry", sl_order.auxPrice < simulated_entry_price),
        ("TIF is DAY", tp_order.tif == 'DAY' and sl_order.tif == 'DAY'),
    ]
    
    all_passed = True
    for check_name, check_result in checks:
        status = "✅" if check_result else "❌"
        print(f"   {status} {check_name}")
        if not check_result:
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ OCO BRACKET CONFIGURATION VALID")
        print("\n📝 Implementation Notes:")
        print("   1. Place these orders AFTER entry fills")
        print("   2. Both orders MUST use same ocaGroup ID")
        print("   3. ocaType=1 means 'Cancel all others when one fills'")
        print("   4. IBKR will auto-cancel remaining order when one executes")
        print("\n🚀 Ready to integrate into day trading bot!")
    else:
        print("❌ OCO BRACKET CONFIGURATION INVALID")
        print("   Fix errors above before integrating")
    print("=" * 70)
    
    ib.disconnect()
    return all_passed

if __name__ == "__main__":
    verify_oco_setup()
