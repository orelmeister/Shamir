# A/B Testing Quick Reference Card

## ✅ Status: IMPLEMENTED & TESTED - Ready for Production

---

## Quick Start

### Run Strategy with A/B Testing (Default Mode)
```powershell
& .\.venv\Scripts\python.exe weekly_bot\05_form4_strategy.py
```
- Uses V1 weights (safe)
- Logs V2 scores in parallel (no risk)
- Both scores saved to database

### Check Results After 10+ Trades
```powershell
& .\.venv\Scripts\python.exe weekly_bot\analyze_ab_testing.py
```

### Activate V2 (After Validation)
```powershell
$env:USE_NEW_WEIGHTS = 'true'
& .\.venv\Scripts\python.exe weekly_bot\05_form4_strategy.py
```

---

## What Changed

| Insider Type | V1 Weight | V2 Weight | Change | Reason |
|-------------|-----------|-----------|--------|--------|
| **Director** | 2.0 | 2.5 | +25% | 69.6% win rate (n=23) ✅ |
| **Officer** | 0.5 | 0.2 | -60% | -2.17% ROI (n=7) ❌ |
| **Politician** | 3.0 | 3.0 | 0% | Need more data (n=2) ⏳ |

---

## Expected Impact

**Director-heavy signals:** V2 scores ~8-12% higher  
**Officer-heavy signals:** V2 scores ~14-21% lower (risk reduction)  
**Overall improvement:** +11.9% in signal quality scores

---

## Environment Variables

```powershell
# Enable A/B testing (default: true)
$env:ENABLE_AB_TESTING = 'true'

# Use new weights (default: false)
$env:USE_NEW_WEIGHTS = 'false'  # Safe: V1
$env:USE_NEW_WEIGHTS = 'true'   # Activate: V2
```

---

## Test Commands

```powershell
# Test 1: Infrastructure
& .\.venv\Scripts\python.exe test_ab_testing.py

# Test 2: Calculations
& .\.venv\Scripts\python.exe test_ab_integration.py

# Test 3: Full Simulation
& .\.venv\Scripts\python.exe test_ab_comprehensive.py
```

---

## Files Created/Modified

### New Files
- `test_ab_testing.py` - Basic test
- `test_ab_integration.py` - Integration test
- `test_ab_comprehensive.py` - Full simulation
- `weekly_bot/analyze_ab_testing.py` - Analysis script
- `weekly_bot/SIGNAL_WEIGHT_OPTIMIZATION.md` - Documentation
- `TEST_RESULTS.md` - Test results
- `AB_TESTING_QUICK_REFERENCE.md` - This file

### Modified Files
- `weekly_bot/05_form4_strategy.py` - A/B testing integration
- `observability.py` - Added `execute_query()` method

### Database
- New table: `ab_test_log` (17 columns)
- New index: `idx_ab_test_symbol_timestamp`

---

## Console Output Example

```
[🧪] A/B TESTING MODE: Logging decisions with both weight sets
[⚙️] Active weights: V1 (CURRENT)

[TOP STOCKS] BY SIGNAL QUALITY:

   AAPL: Score 2.04/3.0 **
      [A/B] V1: 2.04 | V2: 2.29 | Delta: +0.25
      Signals: 12 directors, 3 officers

   JPM: Score 1.71/3.0 *
      [A/B] V1: 1.71 | V2: 1.89 | Delta: +0.18
      Signals: 8 directors, 5 officers
```

---

## Decision Flow

```
1. Strategy runs → Analyzes signals
2. For each stock:
   ├─ Calculate V1 score (current weights)
   ├─ Calculate V2 score (optimized weights)
   ├─ Log both scores to database
   └─ Use V1 score for actual decision (safe)
3. After 10+ trades → Run analysis
4. If V2 improvement > 0.2 → Activate V2
5. Continue monitoring → Quarterly re-evaluation
```

---

## Success Metrics

**Minimum Requirements for V2 Activation:**
- ✅ 10+ BUY decisions logged
- ✅ V2 average score 5%+ higher
- ✅ 5+ closed positions (P&L validation)
- ✅ V2 win rate ≥ V1 win rate
- ✅ No unexpected degradation

---

## Rollback Procedure

If V2 underperforms:
```powershell
# Instant rollback to V1
$env:USE_NEW_WEIGHTS = 'false'

# Or just remove the variable
Remove-Item Env:\USE_NEW_WEIGHTS

# Run strategy
& .\.venv\Scripts\python.exe weekly_bot\05_form4_strategy.py
```

---

## Support

**Documentation:**
- [SIGNAL_WEIGHT_OPTIMIZATION.md](weekly_bot/SIGNAL_WEIGHT_OPTIMIZATION.md) - Full guide
- [TEST_RESULTS.md](TEST_RESULTS.md) - Test results

**Database Queries:**
```powershell
# Check how many logs collected
& .\.venv\Scripts\python.exe -c "from observability import get_database; db = get_database('databases/trading_history.db'); logs = db.execute_query('SELECT COUNT(*) FROM ab_test_log'); print(f'Total logs: {logs[0][0]}')"

# Clean database (if needed)
& .\.venv\Scripts\python.exe -c "from observability import get_database; db = get_database('databases/trading_history.db'); db.execute_query('DELETE FROM ab_test_log'); print('Cleaned')"
```

---

**Status:** ✅ All systems tested and operational  
**Last Updated:** December 16, 2025
