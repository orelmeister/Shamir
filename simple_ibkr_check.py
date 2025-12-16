"""Simple IBKR Position Check"""
print("Starting position check...")

try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from ib_insync import IB, util
    print("✅ ib_insync imported")
    
    ib = IB()
    print("Connecting to IBKR...")
    util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))
    print("✅ Connected!")
    
    ib.reqMarketDataType(3)
    
    positions = ib.positions()
    print(f"\n📊 Found {len(positions)} positions in IBKR account:\n")
    
    for pos in positions:
        print(f"   {pos.contract.symbol}: {pos.position} shares @ ${pos.avgCost:.2f}")
    
    ib.disconnect()
    print("\n✅ Done!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("   Try: pip install ib_insync")
except Exception as e:
    print(f"❌ Error: {e}")
    print("   Make sure IBKR Gateway/TWS is running!")
