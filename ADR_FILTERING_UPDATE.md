# ADR Filtering Update

## Date: October 29, 2025

## Problem Identified
BBAR (Banco BBVA Argentina) and other foreign ADRs were causing repeated failures:
- No valid price data from IBKR
- Orders rejected or not submitted
- Wasted computational resources

## Root Cause
Although ADRs are listed on NYSE/NASDAQ, they often have trading restrictions that make them unsuitable for automated trading.

## Solution Implemented

### 1. ticker_screener_fmp.py (Lines 93-120)
**Enhanced filtering at the source** - prevents problematic stocks from entering the pipeline

```python
# Blacklist: Known problematic ADRs
BLACKLIST = {'BBAR', 'YPF', 'VALE', 'PAM', 'TX', 'BBD', 'ITUB', 'PBR', 'SID'}

# ADR detection keywords
adr_keywords = ['ADR', 'ADS', 'DEPOSITARY', 'SA DE CV', 'NV', 'PLC', 'LTD', 'BANCO']

# Filter logic:
# 1. Check blacklist
# 2. Check company name for ADR indicators
# 3. Check ticker suffix (.A, .B, .C)
```

**Effect**: Runs daily at 6:55 AM, creates `us_tickers.json` with only US common stocks

### 2. intraday_scanner_polygon.py (Lines 146-200)
**Added ADR filtering to _is_common_stock() method**

```python
# Blacklist check
BLACKLIST = {'BBAR', 'YPF', 'VALE', 'PAM', 'TX', 'BBD', 'ITUB', 'PBR', 'SID'}
if ticker in BLACKLIST:
    return False

# ADR suffix patterns
if ticker.endswith('.A') or ticker.endswith('.B') or ticker.endswith('.C'):
    return False
```

**Effect**: Runs every 15 minutes during market hours, ensures intraday scanner doesn't pick up ADRs

### 3. day_trading_agents.py (Lines 1301-1316)
**Removed $10 fallback pricing workaround**

**Before:**
```python
if not valid_prices:
    self.log(logging.WARNING, f"Using $10 fallback estimate")
    estimated_price = 10.0
```

**After:**
```python
if not valid_prices:
    self.log(logging.WARNING, f"No valid price data, skipping (stock may have restrictions)")
    continue
```

**Rationale**: Let IBKR's protection mechanisms work - if a stock has no price data, it's likely restricted. Skip it entirely rather than trying to work around it.

## What This Fixes

### Immediate Benefits
✅ No more BBAR failures  
✅ No more wasted API calls for restricted stocks  
✅ Cleaner logs without repeated price data errors  
✅ More reliable order placement  

### Long-term Protection
✅ Prevents future ADRs from entering watchlists  
✅ Respects IBKR's trading restrictions  
✅ Focuses bot on truly tradeable US stocks  
✅ Reduces false positives in momentum scanning  

## Testing Checklist

- [ ] Tomorrow's 6:55 AM ticker screener run excludes BBAR
- [ ] `us_tickers.json` contains no blacklisted tickers
- [ ] Intraday scanner (9:30+ every 15 min) produces clean watchlist
- [ ] No "No valid price data" errors for filtered stocks
- [ ] MOO orders (8:22 AM) only attempt NASDAQ/NYSE common stocks
- [ ] Scanner updates (9:30-4:00 PM) maintain quality stocks

## Files Modified

1. **ticker_screener_fmp.py** - Primary filtering at source
2. **intraday_scanner_polygon.py** - Secondary filtering for intraday scans
3. **day_trading_agents.py** - Removed fallback workaround, now skips bad stocks

## Known Blacklisted Tickers

- BBAR (Banco BBVA Argentina)
- YPF (YPF Sociedad Anónima)
- VALE (Vale S.A.)
- PAM (Pampa Energía)
- TX (Ternium S.A.)
- BBD (Banco Bradesco)
- ITUB (Itaú Unibanco)
- PBR (Petróleo Brasileiro)
- SID (Companhia Siderúrgica Nacional)

## Detection Keywords

Company names containing these are filtered:
- ADR / ADS
- DEPOSITARY
- SA DE CV (Mexican corporations)
- NV (Dutch corporations)
- PLC (UK public limited companies)
- LTD (Foreign limited companies)
- BANCO (Spanish/Portuguese banks)

## Next Steps

**No bot restart needed** - filters take effect at next scheduled runs:
1. Tomorrow 6:55 AM: Ticker screener creates clean `us_tickers.json`
2. Tomorrow 8:22+ AM: MOO strategy uses filtered tickers
3. Tomorrow 9:30+ AM: Intraday scanner uses double-filtered tickers

**Monitor tomorrow:**
- Check `us_tickers.json` doesn't contain BBAR or other ADRs
- Verify logs show ADR filtering messages
- Confirm no "No valid price data" errors for filtered stocks
