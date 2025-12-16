"""Quick Form4 Strategy Status Check"""
from ib_insync import IB, util

# Connect to IBKR
ib = IB()
util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))
ib.reqMarketDataType(3)  # Delayed data

# Get all positions
portfolio = ib.portfolio()

print("\n" + "="*80)
print("FORM4 STRATEGY STATUS - December 8, 2025")
print("="*80 + "\n")

if not portfolio:
    print("❌ NO POSITIONS FOUND")
    print("\nLast run: December 2, 2025")
    print("Result: 0 positions executed (all 4 proposals rejected)")
    print("  - BITB: Complex ETF (permission required)")
    print("  - GH, HSY, ARLP: Rejected by exit manager\n")
else:
    total_pnl = 0
    total_value = 0
    total_cost = 0
    
    print("📊 CURRENT POSITIONS:\n")
    
    for item in portfolio:
        cost_basis = abs(item.averageCost * item.position)
        pnl = item.unrealizedPNL
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        
        print(f"  {item.contract.symbol}:")
        print(f"    Quantity: {item.position} shares")
        print(f"    Entry: ${item.averageCost:.2f}")
        print(f"    Current: ${item.marketPrice:.2f}")
        print(f"    P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)\n")
        
        total_pnl += pnl
        total_value += item.marketValue
        total_cost += cost_basis
    
    print("-" * 80)
    print(f"\n💰 SUMMARY:")
    print(f"  Total Invested: ${total_cost:.2f}")
    print(f"  Current Value: ${total_value:.2f}")
    print(f"  Total P&L: ${total_pnl:.2f} ({total_pnl/total_cost*100:+.2f}%)\n")
    
    if total_pnl > 0:
        print("✅ PROFITABLE")
    elif total_pnl < 0:
        print("❌ LOSING")
    else:
        print("➖ FLAT")

print("="*80 + "\n")

ib.disconnect()
