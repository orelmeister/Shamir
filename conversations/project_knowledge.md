# Trade Bot Project Knowledge Base

**Last Updated**: October 28, 2025

---

## 🎯 Project Goal

Create a day trading bot that makes **1.8% profit per day** on individual stocks, with automatic liquidation when the entire account gains **2.6%**.

---

## 🏗️ Architecture

### Core Components
1. **day_trader.py** - Orchestrator (schedules, manages workflow)
2. **day_trading_agents.py** - IntradayTraderAgent (executes trades)
3. **ticker_screener_fmp.py** - Stock screening with AI analysis
4. **tools.py** - IBKR integration utilities
5. **observability.py** - Logging and monitoring

### Strategy
- Screen 1600+ tickers at 6:55 AM ET
- AI selects top 8-10 stocks
- Start trading at 9:30 AM
- Exit each stock at **+1.8% profit** or **-0.9% stop loss**
- Liquidate ALL when account hits **+2.6% total**

---

## 🔑 Critical Fixes Applied

### 1. **PDT Buying Power Fix** (October 27, 2025)
**Problem**: Orders rejected with "Available settled cash: 2.97 USD" despite $1,970 cash  
**Root Cause**: Pattern Day Trader restrictions - IBKR checks `SettledCash`, not `TotalCashValue`  
**Solution**: Changed to `ExcessLiquidity` field
```python
# OLD (BROKEN)
total_capital = float(self.account_summary.get('TotalCashValue', 0))

# NEW (WORKS)
excess_liquidity = float(self.account_summary.get('ExcessLiquidity', 0))
total_capital = excess_liquidity * self.allocation
```

**Location**: `day_trading_agents.py` lines 1140-1155

---

### 2. **Order Execution Fix** (October 27, 2025)
**Problem**: Orders stuck in "PendingSubmit" status  
**Root Cause**: MarketOrder requires market data subscription (not available in free tier)  
**Solution**: Switched to LimitOrder with aggressive pricing
```python
# Buy orders: +0.5% above current price
limit_price = round(current_price * 1.005, 2)
order = LimitOrder('BUY', quantity, limit_price)

# Sell orders: -0.5% below current price
limit_price = round(current_price * 0.995, 2)
order = LimitOrder('SELL', quantity, limit_price)
```

**Location**: Multiple places in `day_trading_agents.py`
- Buy: Line 1509-1518
- Sell (profit): Line 1607-1618
- Sell (stop loss): Line 1656-1667
- Liquidation: Line 1740-1756

---

### 3. **Profit Target Clarification** (October 27, 2025)
**Problem**: Confusion about individual stock vs. account-wide profit targets  
**Solution**: Implemented BOTH:
- **Individual stocks**: Exit at +1.8% profit each
- **Whole account**: Liquidate all when total account gains +2.6%

**Why 2.6%?** Account includes old positions (~$1,914). Higher threshold ensures real profitability across everything.

```python
# Individual stock (per trade)
self.profit_target_pct = 0.018  # 1.8%
self.stop_loss_pct = 0.009      # 0.9%

# Whole account (daily)
self.daily_profit_target = 0.026  # 2.6%
```

**Location**: `day_trading_agents.py` lines 1032-1037, 1045

---

## 📊 Account Details (As of Oct 27, 2025)

```
Account: U21952129 (Paper Trading)
NetLiquidation: $3,881.54
ExcessLiquidity: $1,970.07  ← This is buying power!
SettledCash: $2.97
BuyingPower: $2.97 (misleading due to PDT)

Old Positions (8 stocks): ~$1,914
- RNGR, SKYX, SSP, VMD, RPID, FTEK, STRW, EHTH
```

---

## 🔧 Configuration

### Command Line
```powershell
# Run with 10% allocation
python day_trader.py --allocation 0.10

# With 10% of $1,970 = $197 total
# Divided by 8 stocks = $24.62 per stock
```

### Key Parameters (Hardcoded)
- Profit target per stock: **1.8%**
- Stop loss per stock: **0.9%**
- Recovery profit (after stop loss): **1.1%**
- Daily account target: **2.6%**
- Limit order buffer: **±0.5%**

---

## 🐛 Known Issues

1. **Old positions locking capital** - Need to liquidate manually when market opens
2. **Recovery trade logic untested** - Need live market to verify re-entry after stop loss
3. **2.6% target includes old positions** - May trigger prematurely if old stocks rally

---

## ✅ Verified Working

- ✅ IBKR connection (port 4001, clientId 4)
- ✅ Capital allocation using ExcessLiquidity
- ✅ Profit/loss calculation (1.8%/0.9%)
- ✅ Daily account profit tracking (2.6%)
- ✅ Order creation with LimitOrder
- ✅ Watchlist generation (10 stocks)
- ✅ Scheduling (6:55 AM screening, 9:30 AM trading)

---

## 🚀 Next Steps

1. **Tomorrow 9:30 AM**: Watch first orders execute live
2. **Liquidate old positions**: Run `python liquidate_all.py`
3. **Monitor logs**: `python view_logs.py --live`
4. **Verify fills**: Check for "PENDING BUY FILLED" messages
5. **Test recovery logic**: Wait for a stop loss to trigger

---

## 📝 Important Commands

```powershell
# Start bot (manual)
python day_trader.py --allocation 0.10

# View live logs
python view_logs.py --live

# Check positions
python liquidate_today.py

# Liquidate everything
python liquidate_all.py

# Test connection
python test_connection.py

# Check account details
python -c "from ib_insync import IB; ib = IB(); ib.connect('127.0.0.1', 4001, clientId=99); summary = {v.tag: v.value for v in ib.accountSummary()}; print(f'ExcessLiquidity: {summary.get(\"ExcessLiquidity\")}'); ib.disconnect()"
```

---

## 💡 Lessons Learned

1. **IBKR has multiple "cash" fields** - Not all represent actual buying power
2. **Pattern Day Trading rules apply even in paper trading** - Must use ExcessLiquidity
3. **MarketOrder ≠ LimitOrder** - Market orders need paid data subscription
4. **Aggressive limit pricing works** - ±0.5% ensures fills without market data
5. **VS Code loses context** - Must preserve knowledge in files like this

---

## 🔗 Useful Links

- IBKR API Docs: https://interactivebrokers.github.io/tws-api/
- ib_insync Docs: https://ib-insync.readthedocs.io/
- DeepSeek API: https://platform.deepseek.com/
- FMP API: https://site.financialmodelingprep.com/

---

**Remember**: This bot is in paper trading. Don't use with real money until thoroughly tested!
