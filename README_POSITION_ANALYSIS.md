# Position Analysis Tool

## Overview
This tool provides a comprehensive analysis of your current IBKR positions compared to when you first entered them. It shows:

- Current position details (quantity, current price, market value)
- Entry data from database (entry price, entry date, quantity)
- Profit/Loss calculations (both from database entry and IBKR average cost)
- Performance metrics (price change %, unrealized P&L)
- Account summary (net liquidation, available funds)

## Usage

### Quick Start
```bash
python3 analyze_positions.py
```

### What It Does
1. **Connects to IBKR** - Uses port 4001 with client ID 50 (won't conflict with other bots)
2. **Retrieves current positions** - Gets all active positions from your IBKR account
3. **Compares with entry data** - Looks up entry prices and dates from the trading database
4. **Calculates P&L** - Shows both database-tracked P&L and IBKR-reported P&L
5. **Provides summary** - Total unrealized P&L and account status

### Requirements
- IBKR Gateway or TWS must be running on port 4001
- Trading database (`trading_history.db`) must exist in the same directory
- Python packages: `ib-insync` (already installed per requirements.txt)

### Output Example
```
================================================================================
POSITION ANALYSIS - Current Status vs Entry
================================================================================

[POSITIONS] Found 1 active position(s)

────────────────────────────────────────────────────────────────────────────────
Symbol: ADEA
────────────────────────────────────────────────────────────────────────────────

📊 CURRENT POSITION:
  Quantity:        10 shares
  Current Price:   $13.25
  Market Value:    $132.50
  Avg Cost (IBKR): $13.08

📝 ENTRY DATA (from database):
  Entry Price:     $13.08
  Entry Date:      2025-11-03T14:45:38
  Entry Quantity:  10 shares
  Profit Target:   $13.32
  Stop Loss:       $12.96

💰 PERFORMANCE (vs DB entry $13.08):
  Price Change:    +$0.17 (+1.30%)
  P&L (database):  +$1.70

💵 IBKR P&L:
  Unrealized P&L:  +$1.70
  Return (IBKR):   +1.30%

════════════════════════════════════════════════════════════════════════════════
SUMMARY
════════════════════════════════════════════════════════════════════════════════

Total Positions:     1
Total Unrealized PnL: +$1.70

Net Liquidation:  $10,523.45
Excess Liquidity: $10,391.95
Available Funds:  $10,391.95

================================================================================
```

## Features

### 1. Multi-Source Entry Data
The tool checks multiple sources for entry data:
- **Active positions table** - Current open positions with profit targets and stop losses
- **Trades table** - Historical first entry and latest entry for each symbol
- Falls back gracefully if data is missing

### 2. Accurate P&L Calculations
- **Database P&L** - Based on tracked entry price from when position was opened
- **IBKR P&L** - Based on average cost (accounts for multiple entries/exits)
- Shows both percentage and dollar P&L

### 3. Target/Stop Information
If the position has been tracked by the exit manager, shows:
- Profit target price
- Stop loss price
- Helps you understand your risk/reward setup

### 4. Account Summary
Displays key account metrics:
- Net Liquidation Value
- Excess Liquidity (available for trading)
- Available Funds

## Troubleshooting

### "Connection failed"
- Make sure IBKR Gateway or TWS is running
- Check that port 4001 is configured in IBKR settings
- Verify no firewall is blocking the connection

### "No positions currently held"
- This is normal if you've closed all positions
- The tool will show historical entries from the database

### "No entry data found in database"
- Position may be from the weekly bot (not tracked in day trading database)
- Position may have been entered before database tracking was enabled
- IBKR P&L will still be shown

## Integration with Trading System

This tool complements the autonomous trading system:
- **Day Trader** (`day_trader.py`) - Opens intraday positions
- **Exit Manager** (`exit_manager.py`) - Manages profit targets and stop losses
- **Position Analysis** (`analyze_positions.py`) - Analyzes current status

Run this tool anytime to check on your positions without interfering with the automated bots.

## Notes
- Uses delayed/frozen market data (free, no subscription required)
- Read-only tool - will not place any orders or modify positions
- Client ID 50 avoids conflicts with other bots (day_trader=2, exit_manager=10, etc.)
