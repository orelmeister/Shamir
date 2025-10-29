# Trading Strategy Changes - Daily Profit Target Bot

## Old Strategy (Rapid Day Trading)
- Bought and sold stocks continuously all day
- 86 trades in one session!
- Re-entered same stocks multiple times
- Result: -$45 loss from multiple small stop losses

## New Strategy (Daily Profit Target)

### Core Principle
**Make 1.8% daily profit and STOP trading for the day**

### Key Changes

1. **Daily Profit Target Tracking**
   - Bot tracks starting capital at market open
   - Calculates total daily P&L (realized + unrealized)
   - Once portfolio reaches +1.8%, liquidates all positions and STOPS

2. **One Position Per Stock**
   - Don't keep buying more if already holding
   - Prevents over-trading same stock

3. **Profit Exit = No Re-Entry**
   - When stock hits +1.8% profit target and sells
   - Mark stock as "done for the day"
   - No re-entry on profitable exits

4. **Stop Loss = Can Re-Enter**
   - When stock hits -0.9% stop loss and sells
   - Mark stock as "can re-enter"
   - Watch for momentum recovery
   - Re-enter when conditions improve

5. **Recovery Trades**
   - Stocks bought after stop loss = "recovery trades"
   - Use LOWER profit target: **1.1%** instead of 1.8%
   - Faster exit to recover losses

### Trading Flow

**Morning:**
1. Buy stocks with strong momentum
2. Hold patiently for profit targets

**If Profit Target Hit (+1.8%):**
1. Sell position
2. Don't re-enter that stock
3. Check if daily target reached (+1.8% portfolio)
4. If yes → liquidate everything and STOP

**If Stop Loss Hit (-0.9%):**
1. Sell position
2. Wait for momentum recovery
3. Re-enter when signals improve
4. Use 1.1% profit target for quick recovery

**End Goal:**
- End day with +1.8% portfolio gain
- Stop trading once target reached
- Don't over-trade trying to squeeze more profit

## Benefits

✅ Less trading = lower commissions
✅ Patient holding = better fills
✅ Clear daily goal = disciplined trading
✅ Recovery logic = adapt to losses
✅ Auto-stop at target = lock in profits
