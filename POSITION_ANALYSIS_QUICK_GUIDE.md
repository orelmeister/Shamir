# Position Analysis - Quick Reference Guide

## What is this?
A tool that compares your **current IBKR positions** with **when you first entered them**, showing profit/loss and performance.

## Quick Commands

### Option 1: Full Analysis (with IBKR)
```bash
python analyze_positions.py
```
**Requires**: IBKR Gateway/TWS running on port 4001

### Option 2: Database-Only Check
```bash
python verify_position_database.py
```
**Requires**: Only the `trading_history.db` file

### Option 3: Windows Launcher
```bash
analyze_positions.bat
```
Double-click the file or run from command line

## What You'll See

### Current Position Details
- How many shares you own
- Current market price
- Total market value

### Entry Information
- When you first bought (date & time)
- Entry price from database
- Original quantity

### Performance Metrics
- **Price Change**: How much the stock moved since entry
- **P&L**: Profit or loss in dollars and percentage
- **Targets**: Profit target and stop loss levels (if tracked)

### Account Summary
- Net liquidation value
- Available funds for trading
- Excess liquidity

## Example Output

```
════════════════════════════════════════════════════════════════════════
Symbol: ADEA
────────────────────────────────────────────────────────────────────────

📊 CURRENT POSITION:
  Quantity:        10 shares
  Current Price:   $13.25
  Market Value:    $132.50
  Avg Cost (IBKR): $13.08

📝 ENTRY DATA (from database):
  Entry Price:     $13.08
  Entry Date:      2025-11-03T14:45:38
  Profit Target:   $13.32
  Stop Loss:       $12.96

💰 PERFORMANCE (vs DB entry $13.08):
  Price Change:    +$0.17 (+1.30%)
  P&L (database):  +$1.70

💵 IBKR P&L:
  Unrealized P&L:  +$1.70
  Return (IBKR):   +1.30%
```

## Use Cases

### 1. Daily Position Check
Run this every morning to see where you stand:
```bash
python analyze_positions.py
```

### 2. Quick Database Verification
Check what's in your trading history without connecting to IBKR:
```bash
python verify_position_database.py
```

### 3. Performance Review
Compare current price vs entry to evaluate your trading decisions

### 4. Risk Assessment
See how close you are to profit targets or stop losses

## Troubleshooting

### "Connection failed"
**Problem**: Can't connect to IBKR  
**Solution**: 
1. Make sure IBKR Gateway or TWS is running
2. Check port 4001 is configured
3. Verify no firewall blocking

### "No positions currently held"
**Explanation**: This is normal if all positions are closed  
**Note**: Tool will still show historical entries from database

### "No entry data found in database"
**Possible Reasons**:
- Position from weekly bot (different database)
- Position entered before tracking started
- Database not synced yet

**What to do**: IBKR P&L will still be shown (uses IBKR average cost)

## Key Features

✅ **Multi-source data**: Checks both active positions table and trades history  
✅ **Accurate P&L**: Shows both database-tracked and IBKR-calculated P&L  
✅ **Safe to run**: Read-only tool, won't place any orders  
✅ **No conflicts**: Uses unique client ID (50) to avoid interfering with bots  
✅ **Free data**: Uses delayed/frozen market data (no subscription needed)

## Files Created

- `analyze_positions.py` - Main analysis script
- `verify_position_database.py` - Database-only verification
- `analyze_positions.bat` - Windows launcher
- `README_POSITION_ANALYSIS.md` - Detailed documentation
- `POSITION_ANALYSIS_QUICK_GUIDE.md` - This file

## Integration with Trading System

This tool works alongside:
- **Day Trader** (`day_trader.py`) - Opens positions
- **Exit Manager** (`exit_manager.py`) - Manages exits
- **Position Analysis** (this tool) - Reviews status

Run anytime without interfering with automated bots!

---

**Need more details?** See `README_POSITION_ANALYSIS.md`  
**Having issues?** Check the troubleshooting section above  
**Want to verify?** Run `verify_position_database.py` first
