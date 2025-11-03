"""
sync_positions_from_ibkr.py

Utility script to sync current IBKR positions into shared_state/positions_state.json.
Tags each position as "WEEKLY" or "DAY_TRADER" based on day_trading_watchlist.json.

Usage:
    python sync_positions_from_ibkr.py
    
Can be run standalone or called by either bot before trading begins.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
import filelock
from ib_insync import IB, Stock, util
from dotenv import load_dotenv

# Load environment
load_dotenv()
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", 4001))

# File paths
POSITIONS_STATE_FILE = "shared_state/positions_state.json"
LOCK_FILE = "shared_state/.positions_state.lock"
DAY_TRADER_WATCHLIST = "day_trading_watchlist.json"


def load_day_trader_watchlist():
    """Load day trading watchlist to identify DAY_TRADER positions."""
    if not os.path.exists(DAY_TRADER_WATCHLIST):
        print(f"⚠️  Day trader watchlist not found: {DAY_TRADER_WATCHLIST}")
        return []
    
    with open(DAY_TRADER_WATCHLIST, "r") as f:
        data = json.load(f)
    
    # Extract just the symbols
    return [item["symbol"] for item in data] if isinstance(data, list) else []


def tag_position_source(symbol, day_trader_symbols):
    """Determine if position belongs to WEEKLY bot or DAY_TRADER."""
    if symbol in day_trader_symbols:
        return "DAY_TRADER"
    return "WEEKLY"


def sync_positions():
    """Fetch positions from IBKR and update shared state JSON."""
    print("=" * 60)
    print("IBKR Position Sync Utility")
    print("=" * 60)
    
    # Load day trader watchlist
    day_trader_symbols = load_day_trader_watchlist()
    print(f"📋 Day trader watchlist loaded: {len(day_trader_symbols)} symbols")
    
    # Connect to IBKR
    ib = IB()
    try:
        print(f"🔌 Connecting to IBKR at {IB_HOST}:{IB_PORT} (ClientID: 99 - Sync Utility)...")
        util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=99))
        ib.reqMarketDataType(3)  # Delayed data (free)
        print("✅ Connected to IBKR")
    except Exception as e:
        print(f"❌ Failed to connect to IBKR: {e}")
        sys.exit(1)
    
    # Fetch current positions
    try:
        portfolio = ib.portfolio()
        print(f"📊 Fetched {len(portfolio)} positions from IBKR")
    except Exception as e:
        print(f"❌ Failed to fetch portfolio: {e}")
        ib.disconnect()
        sys.exit(1)
    
    # Build positions list
    positions = []
    for item in portfolio:
        if item.position == 0:
            continue  # Skip closed positions
        
        symbol = item.contract.symbol
        source = tag_position_source(symbol, day_trader_symbols)
        
        position_data = {
            "symbol": symbol,
            "quantity": int(item.position),
            "entry_price": float(item.averageCost),
            "entry_date": datetime.now().isoformat(),  # Approximate (IBKR doesn't provide exact entry date)
            "stop_loss": None,  # Will be calculated by monitoring agent
            "trailing_stop": None,
            "trailing_stop_trigger": None,
            "source": source,
            "metadata": {
                "market_value": float(item.marketValue),
                "unrealized_pnl": float(item.unrealizedPNL),
                "last_sync": datetime.now().isoformat()
            }
        }
        positions.append(position_data)
        
        print(f"  {symbol:6s} | {item.position:>6.0f} shares | ${item.averageCost:>8.2f} avg | {source}")
    
    ib.disconnect()
    print("🔌 Disconnected from IBKR")
    
    # Write to shared state with file locking
    lock = filelock.FileLock(LOCK_FILE, timeout=10)
    try:
        with lock:
            # Read existing state
            if os.path.exists(POSITIONS_STATE_FILE):
                with open(POSITIONS_STATE_FILE, "r") as f:
                    existing_data = json.load(f)
            else:
                existing_data = {"positions": [], "last_updated": None}
            
            # Update positions
            state_data = {
                "positions": positions,
                "last_updated": datetime.now().isoformat()
            }
            
            # Write back
            with open(POSITIONS_STATE_FILE, "w") as f:
                json.dump(state_data, f, indent=2)
            
            print(f"\n✅ Updated {POSITIONS_STATE_FILE}")
            print(f"   Total positions: {len(positions)}")
            print(f"   WEEKLY: {sum(1 for p in positions if p['source'] == 'WEEKLY')}")
            print(f"   DAY_TRADER: {sum(1 for p in positions if p['source'] == 'DAY_TRADER')}")
    
    except filelock.Timeout:
        print(f"❌ Failed to acquire lock on {LOCK_FILE} (timeout)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to write positions state: {e}")
        sys.exit(1)
    
    print("=" * 60)
    print("✅ Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    sync_positions()
