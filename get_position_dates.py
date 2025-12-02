"""
Query IBKR for position entry dates and details
"""
from ib_insync import *
from datetime import datetime

def get_position_details():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 4001, clientId=99)
        
        # Get portfolio items (includes more detail than positions())
        portfolio = ib.portfolio()
        
        print(f"\n{'='*80}")
        print(f"Found {len(portfolio)} positions in portfolio")
        print(f"{'='*80}\n")
        
        for item in portfolio:
            print(f"\n{item.contract.symbol}:")
            print(f"  Full PortfolioItem: {item}")
            print(f"  Available attributes: {dir(item)}")
            print()
        
        # Try to get execution history
        print(f"\n{'='*80}")
        print("Checking execution history...")
        print(f"{'='*80}\n")
        
        fills = ib.reqExecutions()
        if fills:
            print(f"Found {len(fills)} executions:")
            for fill in sorted(fills, key=lambda x: x.time, reverse=True)[:20]:
                print(f"{fill.contract.symbol}: {fill.execution.side} {fill.execution.shares} @ ${fill.execution.avgPrice:.2f} on {fill.time}")
        else:
            print("No execution history available from IBKR API")
            print("\nNote: IBKR API does not retain long-term execution history.")
            print("Entry dates must be obtained from:")
            print("  1. IBKR Account Management portal (Flex Queries)")
            print("  2. Your own tracking records")
            print("  3. Manual entry based on broker statements")
        
    finally:
        ib.disconnect()

if __name__ == "__main__":
    get_position_details()
