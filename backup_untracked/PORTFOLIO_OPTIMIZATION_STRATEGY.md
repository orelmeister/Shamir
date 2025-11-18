# Portfolio Optimization Strategy

## Overview

The weekly trading bot now implements a **sophisticated portfolio optimization algorithm** that maximizes expected returns while minimizing unnecessary trading. The bot holds up to **5 equal-weighted positions** and only rebalances when the optimized portfolio improves expected returns by **more than 5%**.

## Key Configuration

```python
MAX_POSITIONS = 5               # Hold top 5 stocks for diversification
POSITION_SIZE_PCT = 0.20        # 20% per position (equal weight)
REBALANCE_THRESHOLD = 0.05      # Only rebalance if expected return improves by >5%
```

## Strategy Philosophy

**Hold Winners, But Optimize When Materially Better**

- ✅ Hold positions indefinitely (no forced weekly selling)
- ✅ Diversify across top 5 Monte Carlo picks
- ✅ Equal weight positions (20% each = $400/stock)
- ✅ Only rebalance when significantly better opportunities emerge
- ✅ Stop losses (-10%) and trailing stops (+20% activation) protect capital

## Decision Algorithm

### Step 1: Monte Carlo Analysis
Every Sunday, the bot:
1. Analyzes all BUY recommendations (confidence ≥ 0.80)
2. Runs Monte Carlo simulation across 3 horizons (weekly, monthly, yearly)
3. Ranks stocks by Sharpe ratio across all horizons
4. Validates top 5 tickers exist in IBKR
5. Returns top 5 picks with Sharpe ratios

### Step 2: Portfolio Optimization
The bot calculates expected returns for:

**Current Portfolio:**
```python
current_expected_return = Σ (weight_i × expected_return_i)

where:
- weight_i = market value / total portfolio value
- expected_return_i = risk_free_rate + (sharpe_i × volatility)
- risk_free_rate = 4% (current T-bill rate)
- volatility = 15% (market assumption)
```

**Optimized Portfolio (Top 5 Equal-Weighted):**
```python
optimized_expected_return = (1/5) × Σ expected_return_i  (i = 1 to 5)

where:
- Each position = 20% of portfolio
- Top 5 picks from Monte Carlo rankings
```

### Step 3: Rebalance Decision
```python
improvement = optimized_expected_return - current_expected_return
improvement_pct = improvement / current_expected_return

if improvement_pct > 0.05:  # 5% threshold
    REBALANCE to top 5 equal-weighted
else:
    HOLD current positions
```

## Example Scenarios

### Scenario 1: 100% Single Position → Top 5 Diversified
**Situation:** Monday morning, bot has $2,000 invested 100% in SKYX (Sharpe 1.45)

**Monte Carlo Rankings:**
1. ACRS (Sharpe 10.00)
2. CVRX (Sharpe 6.82)
3. TYGO (Sharpe 3.50)
4. EB (Sharpe 2.20)
5. SKYX (Sharpe 1.45)

**Analysis:**
- Current Expected Return: 25.75% (100% SKYX)
- Optimized Expected Return: 75.91% (20% each × 5 stocks)
- Improvement: 50.16% (194.8% better!)

**Decision:** ✅ **REBALANCE**
- SELL 100% SKYX ($2,000)
- BUY $400 ACRS, $400 CVRX, $400 TYGO, $400 EB, $400 SKYX
- Result: 5 positions at 20% each

### Scenario 2: Already Holding Top 5 (Minor Sharpe Changes)
**Situation:** Portfolio already has top 5 equal-weighted, Sharpe ratios change slightly

**Current Portfolio:**
- ACRS (20%, Sharpe 9.80)
- CVRX (20%, Sharpe 6.75)
- TYGO (20%, Sharpe 3.45)
- EB (20%, Sharpe 2.15)
- SKYX (20%, Sharpe 1.40)

**New Rankings:** (Same stocks, slightly different Sharpes: 9.90, 6.85, 3.55, 2.25, 1.50)

**Analysis:**
- Current Expected Return: 74.65%
- Optimized Expected Return: 76.15%
- Improvement: 1.50% (2.0%)

**Decision:** 🔒 **HOLD**
- 2% improvement < 5% threshold
- Avoids unnecessary trading costs
- Current portfolio already optimized

### Scenario 3: Partial Overlap (3 of 5 Still in Top Picks)
**Situation:** Bot holds 5 stocks, but 2 have fallen out of top 5

**Current Portfolio:**
- ACRS (20%, Sharpe 10.00) ← Still in top 5
- CVRX (20%, Sharpe 6.82) ← Still in top 5
- TYGO (20%, Sharpe 3.50) ← Still in top 5
- OLDSTOCK1 (20%, Sharpe 1.00) ← Dropped out
- OLDSTOCK2 (20%, Sharpe 0.50) ← Dropped out

**New Top 5:** ACRS, CVRX, TYGO, EB (2.20), SKYX (1.45)

**Analysis:**
- Current Expected Return: 69.46%
- Optimized Expected Return: 75.91%
- Improvement: 6.45% (9.3%)

**Decision:** ✅ **REBALANCE**
- SELL OLDSTOCK1 and OLDSTOCK2
- BUY EB and SKYX
- Keep ACRS, CVRX, TYGO (rebalance to 20% each)

## Risk Management Integration

### Stop Loss Protection (-10%)
- Every position tracked with entry price
- Automatic sell if price drops 10% below entry
- Cuts losers fast to preserve capital

### Trailing Stop Protection (+20% activation, -10% trail)
- Activates when position gains 20%
- Trails 10% below highest price reached
- Locks in profits while letting winners run

### Position Limits
- Maximum 5 positions (diversification)
- Equal weighting prevents over-concentration
- Cannot exceed MAX_POSITIONS limit

## Pre-Market Execution (9:00-9:27 AM ET)

If bot runs before market open (9:30 AM), it places **Market-On-Open (MOO) orders**:
- Safe time window: 9:00-9:27 AM ET (3-minute buffer)
- Uses MKT orders (not MOO type) for flexibility
- Orders execute at 9:30 AM market open price
- Position tracking starts with estimated price, updated with actual fill

## Logging and Transparency

Every rebalancing decision logs:
```
📊 Portfolio Analysis:
   Current: SKYX (100.0% weight, Sharpe 1.45, Expected Return 25.8%)
   Optimized: ACRS (20.0% weight, Sharpe 10.00, Expected Return 154.0%)
   Optimized: CVRX (20.0% weight, Sharpe 6.82, Expected Return 106.3%)
   ...
   Current Expected Return: 25.75%
   Optimized Expected Return: 75.91%
   Improvement: 50.16% (194.8%)
   Threshold: 5.0%
✅ Improvement (194.8%) exceeds threshold. REBALANCING.
```

If holding:
```
🔒 HOLDING current positions - insufficient improvement to justify rebalancing.
   (improvement 2.0% < threshold 5.0%)
```

## Benefits

1. **Maximizes Returns:** Diversifies across top 5 highest Sharpe ratio stocks
2. **Minimizes Trading Costs:** Only rebalances when improvement > 5%
3. **Avoids Whipsaw:** Ignores minor Monte Carlo noise (< 5% changes)
4. **Lets Winners Run:** No forced selling, positions held indefinitely until stopped out
5. **Risk-Adjusted:** Uses Sharpe ratios (return per unit of risk) for optimization
6. **Transparent:** Detailed logging shows exact reasoning for every decision

## When Bot Rebalances

The bot will rebalance when:
- ✅ Starting from 0 positions (builds full portfolio)
- ✅ Current portfolio expected return < optimized return by >5%
- ✅ Positions fall out of top 5 and replacement improves return by >5%
- ✅ Stop losses or trailing stops trigger (force sells)

The bot will NOT rebalance when:
- ❌ Already holding top 5 with minor Sharpe changes (<5% improvement)
- ❌ Current portfolio "good enough" (optimized only 2-4% better)
- ❌ New picks exist but improvement < 5% threshold

## Configuration Tuning

**To make bot more aggressive (rebalance more often):**
```python
REBALANCE_THRESHOLD = 0.03  # 3% threshold instead of 5%
```

**To make bot more conservative (hold longer):**
```python
REBALANCE_THRESHOLD = 0.10  # 10% threshold (rarely rebalances)
```

**Current setting (5%) balances:**
- Captures significant opportunities (9%+ improvements)
- Avoids micro-optimization (2-4% noise)
- Reasonable for $2,000 portfolio with ~$7-10 trading costs per rebalance

## Next Steps

1. Monitor Monday's rebalancing decision in logs
2. Track improvement percentage over multiple weeks
3. Adjust threshold if too many/too few rebalances occur
4. Consider increasing capital for better diversification
5. Review stop loss/trailing stop effectiveness

## Testing

Run test scenarios:
```bash
python test_portfolio_optimization.py
```

This validates:
- ✅ 100% single stock → diversified (194% improvement)
- ✅ Already optimized portfolio (2% improvement = HOLD)
- ✅ Partial overlap (9% improvement = REBALANCE)
- ✅ Marginal improvement (5.3% = REBALANCE at threshold)
