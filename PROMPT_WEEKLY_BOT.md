# Weekly Trading Bot - Master Prompt & Development Guide

This is the comprehensive prompt file for the **Weekly Trading Bot** system (the original bot in `main.py`). Use this document when working on, debugging, or extending the weekly trading functionality.

---

## 🎯 SYSTEM OVERVIEW

**Purpose**: AI-powered weekly stock picker that:
- Runs once per week (typically Sunday evening or Monday pre-market)
- Analyzes fundamental data for longer-term holds (3-7 days)
- Uses LLM reasoning to select best value/growth opportunities
- Focuses on stability and fundamental analysis (not day trading)

**Key Difference from Day Trader**:
- **Weekly Bot**: Fundamental analysis, longer holds, lower frequency
- **Day Trading Bot**: Technical analysis, intraday trades, high frequency

---

## 📁 FILE STRUCTURE

### Core Files
- `main.py` - Main orchestrator for weekly bot
- `agents.py` - Agent classes for weekly analysis
- `requirements.txt` - Python dependencies

### Supporting Files (Shared with Day Trader)
- `utils.py` - Logging, timezone utilities
- `tools.py` - API connections (FMP, Polygon, LLMs)
- `.env` - API keys (NEVER commit)

### Data Files
- `us_tickers.json` - Universe of US stocks
- `full_analysis_results.json` - Weekly analysis output
- `trading_queue.json` - Stocks to buy/hold/sell
- `logs/weekly_bot_run_*.json` - Execution logs

---

## 🚀 HOW TO RUN

### Standard Weekly Run
```powershell
python main.py
```

**Typical Schedule:**
- Sunday 8:00 PM ET (prepare for Monday open)
- Monday 8:00 AM ET (before market open)
- Any time during week for re-analysis

### Command-Line Options
```powershell
# Force fresh data collection
python main.py --force-refresh

# Skip to analysis only
python main.py --analyze-only

# Test mode (no actual orders)
python main.py --dry-run
```

---

## 🏗️ ARCHITECTURE

### Phase 1: Data Collection
**Purpose**: Gather fundamental data for all US stocks

**Data Sources:**
1. **FMP API** (Financial Modeling Prep):
   - Company profiles (sector, industry, description)
   - Income statements (revenue, earnings, margins)
   - Balance sheets (assets, liabilities, equity)
   - Cash flow statements
   - Key ratios (P/E, P/B, ROE, debt ratios)
   - Historical prices (52-week high/low, trends)

2. **Polygon API**:
   - News articles (fundamental catalysts)
   - Earnings reports
   - Corporate actions

**Screening Criteria:**
- All US-listed stocks (NYSE, NASDAQ, AMEX)
- Market cap: Typically > $500M (larger than day trading)
- Price: > $5 (avoid penny stocks)
- Volume: > 100K daily average
- Fundamentally sound: Revenue > $0, positive equity

**Output**: `full_analysis_results.json`

---

### Phase 2: Fundamental Analysis
**Agent**: Uses LLM (DeepSeek/Gemini) for deep analysis

**Analysis Framework:**

1. **Financial Health**
   - Revenue growth trend (YoY, QoQ)
   - Profit margins (gross, operating, net)
   - Balance sheet strength (debt/equity ratio)
   - Cash flow generation (FCF positive?)

2. **Valuation**
   - P/E ratio vs. industry average
   - P/B ratio (book value)
   - PEG ratio (growth-adjusted PE)
   - Price vs. 52-week range

3. **Growth Potential**
   - Revenue CAGR (3-5 years)
   - Earnings growth trajectory
   - Market expansion opportunities
   - Competitive advantages (moat)

4. **Catalysts & Risks**
   - Recent news (positive/negative)
   - Upcoming earnings
   - Industry trends
   - Regulatory risks

**Confidence Score:**
- 0.90-1.0: Strong Buy (high conviction)
- 0.75-0.89: Buy (good opportunity)
- 0.60-0.74: Hold (monitor)
- 0.40-0.59: Weak Hold (consider selling)
- < 0.40: Sell (fundamentals deteriorating)

**Output**: Ranked list with buy/hold/sell recommendations

---

### Phase 3: Portfolio Management
**Purpose**: Execute trades based on analysis

**Strategy:**
1. **Buy New Positions**:
   - Top-ranked stocks not in portfolio
   - Allocate capital equally or by conviction score
   - Maximum 10-20 positions (diversification)

2. **Hold Existing Positions**:
   - Stocks still ranking well (score > 0.60)
   - No fundamental deterioration
   - Keep until sell signal or target reached

3. **Sell Positions**:
   - Score drops below 0.40 (fundamentals weak)
   - Better opportunities available
   - Technical stop loss hit (-20% typical)
   - Time-based exit (held > 30 days, no progress)

**Position Sizing:**
- Equal weight: 100% / N positions
- Conviction-based: Higher allocation to higher scores
- Risk limit: Max 10% per position

---

## 🔧 CONFIGURATION

### Environment Variables (.env)
```bash
# Required for Weekly Bot
FMP_API_KEY=your_fmp_key
POLYGON_API_KEY=your_polygon_key
DEEPSEEK_API_KEY=your_deepseek_key
GEMINI_API_KEY=your_gemini_key

# IBKR Connection (if auto-trading enabled)
IBKR_HOST=127.0.0.1
IBKR_PORT=7497  # Live trading port
IBKR_CLIENT_ID=1  # Different from day trader (clientId=2)

# Portfolio Settings
MAX_POSITIONS=15
POSITION_SIZE_PCT=0.067  # 6.7% per position (15 positions)
STOP_LOSS_PCT=0.20  # -20% stop loss
```

### Key Parameters (in `main.py` or `agents.py`)
```python
# Analysis settings
MIN_MARKET_CAP = 500_000_000  # $500M minimum
MIN_REVENUE = 10_000_000  # $10M minimum annual revenue
MIN_VOLUME = 100_000  # 100K daily volume

# Scoring thresholds
BUY_THRESHOLD = 0.75  # Score needed to buy
HOLD_THRESHOLD = 0.60  # Score needed to hold
SELL_THRESHOLD = 0.40  # Score below = sell

# Time-based rules
MAX_HOLD_DAYS = 90  # Sell after 90 days if no movement
MIN_HOLD_DAYS = 3  # Avoid frequent flipping
```

---

## 🐛 COMMON ISSUES & FIXES

### Issue 1: API Rate Limits
**Symptom**: `429 Too Many Requests` errors

**Cause**: FMP/Polygon free tier limits

**Fix**:
1. Add delays between requests: `time.sleep(0.5)`
2. Batch requests when possible
3. Cache results to avoid re-fetching
4. Upgrade to paid API tier if needed

---

### Issue 2: Stale Data
**Symptom**: Analysis using old financial reports

**Cause**: Cached `full_analysis_results.json` not refreshed

**Fix**:
```powershell
# Delete cache and force refresh
Remove-Item -Path "full_analysis_results.json" -Force
python main.py --force-refresh
```

---

### Issue 3: LLM Analysis Timeout
**Symptom**: Analysis hangs or times out

**Cause**: Too many stocks analyzed in parallel

**Fix**: Reduce batch size in `agents.py`:
```python
# Current
batch_size = 50  # Analyze 50 stocks at once

# Reduce if timeouts
batch_size = 20  # Smaller batches
```

---

### Issue 4: Conflicting with Day Trader
**Symptom**: IBKR connection fails "clientId already in use"

**Cause**: Both bots trying to use same clientId

**Fix**: Use different clientIds:
- Weekly Bot: `clientId=1`
- Day Trader: `clientId=2`

---

## 📊 MONITORING & LOGS

### Log Files
- Location: `logs/weekly_bot_run_YYYYMMDD_HHMMSS.json`
- Format: JSON-structured logging
- Retention: Keep last 30 days

### Key Metrics to Track
- Total stocks analyzed
- Buy recommendations count
- Sell recommendations count
- Portfolio value change (week-over-week)
- Win rate (% profitable trades)
- Average holding period
- Best/worst performers

---

## 🚨 CRITICAL RULES

### DO NOT:
1. ❌ Modify while day trader is running
2. ❌ Use same clientId as day trader
3. ❌ Ignore stop losses (protect capital)
4. ❌ Over-concentrate (max 10% per position)
5. ❌ Chase momentum (stick to fundamentals)
6. ❌ Panic sell on short-term drops
7. ❌ Commit sensitive data files

### ALWAYS:
1. ✅ Run fundamental analysis before buying
2. ✅ Set stop losses on every position
3. ✅ Diversify across sectors
4. ✅ Review portfolio weekly
5. ✅ Keep position sizing disciplined
6. ✅ Log all trades for analysis
7. ✅ Test changes in paper trading first

---

## 🔄 WEEKLY WORKFLOW

### Sunday Evening or Monday Pre-Market
1. Run `python main.py`
2. Data collection (30-60 min)
3. LLM analysis (30-60 min)
4. Review recommendations
5. Execute trades (Monday 9:30 AM open)

### Mid-Week Check (Wednesday)
1. Review portfolio performance
2. Check for news on holdings
3. Adjust stop losses if needed
4. No trading (patience)

### Weekend Review
1. Calculate weekly P&L
2. Analyze what worked / didn't work
3. Adjust parameters if needed
4. Prepare for next week's run

---

## 🆘 GETTING HELP

### Debugging Checklist
1. Check logs: `logs/weekly_bot_run_*.json`
2. Verify API keys in `.env`
3. Test API connections: `python tools.py test`
4. Check data freshness: Look at timestamps
5. Review LLM responses: Are they reasonable?

### Common Error Messages
| Error | Meaning | Fix |
|-------|---------|-----|
| `API key invalid` | Wrong or missing key | Check `.env` file |
| `Rate limit exceeded` | Too many requests | Add delays, upgrade plan |
| `No data for ticker` | Stock delisted/invalid | Update ticker list |
| `Analysis timeout` | LLM taking too long | Reduce batch size |
| `clientId in use` | IBKR conflict | Change clientId |

---

## 📈 PERFORMANCE OPTIMIZATION

### Speed Improvements
1. **Parallel API Calls**: Use `concurrent.futures`
2. **Cache Aggressively**: Store FMP data locally
3. **Selective Analysis**: Only analyze changed stocks
4. **Batch LLM Requests**: Multiple stocks per prompt

### Cost Reduction
1. **Use DeepSeek First**: Cheaper than GPT/Claude
2. **Cache LLM Results**: Don't re-analyze unchanged stocks
3. **Limit Polygon News**: Only fetch if score close to threshold
4. **Free Tier APIs**: yfinance for basic data

---

## 🎓 KEY CONCEPTS

### Fundamental Analysis Terms
- **P/E Ratio**: Price-to-Earnings (valuation)
- **P/B Ratio**: Price-to-Book (asset value)
- **ROE**: Return on Equity (profitability)
- **Debt/Equity**: Financial leverage
- **FCF**: Free Cash Flow (cash generation)
- **CAGR**: Compound Annual Growth Rate

### Portfolio Management
- **Diversification**: Spread risk across stocks
- **Rebalancing**: Adjust position sizes periodically
- **Stop Loss**: Automatic sell to limit losses
- **Position Sizing**: How much to invest per stock
- **Conviction Weighting**: More $ in high-confidence picks

---

## 📝 VERSION HISTORY

**October 21, 2025** - Separation from Day Trader
- ✅ Isolated from day trading bot
- ✅ Maintained stability during day trader development
- ✅ No breaking changes
- ✅ Shared utilities only (utils.py, tools.py)

**Next Planned Features:**
- Sector rotation strategy
- Options integration (covered calls)
- Dividend capture strategy
- ESG screening filters
- Automated portfolio rebalancing

---

## 🔗 INTEGRATION WITH DAY TRADER

### How They Coexist
- **Separate Files**: No code overlap (except utils/tools)
- **Separate clientIds**: Weekly=1, DayTrader=2
- **Separate Data**: Different JSON files
- **Separate Schedules**: Weekly runs off-hours
- **Separate Portfolios**: No position conflicts

### Shared Resources
- `utils.py`: Logging, timezone functions
- `tools.py`: API clients (FMP, Polygon, LLMs)
- `.env`: API keys (used by both)
- IBKR Account: Same account, different clientIds

---

**Last Updated**: October 21, 2025
**Status**: Stable & Production Ready
**Maintainer**: See `main.py` for latest changes
