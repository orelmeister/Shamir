# Form 4 Insider Cluster Strategy

**Dedicated Capital:** $1,000  
**Rebalancing:** Weekly (Sundays)  
**Strategy Type:** Insider trading signal-based swing trading

---

## Overview

This is a **separate, specialized strategy** that focuses exclusively on detecting and trading insider buying clusters through SEC Form 4 filings. Unlike your main weekly bot (microcaps $1-18) and day trader, this strategy targets mid-cap stocks where insider activity is most prevalent.

### Why a Separate Strategy?

**The Analysis Showed:**
- Your microcap strategy ($1-18 price) only captures **16.7%** of Form 4 clusters
- Most insider activity happens in **mid-caps** ($500M-20B) with **higher prices** ($5-50)
- Better to run as dedicated strategy than force-fit into existing system

---

## Strategy Parameters

### Market Criteria
```python
MIN_MARKET_CAP = $500M     # Higher than microcap to catch insiders
MAX_MARKET_CAP = $20B      # Large-caps have different dynamics
MIN_PRICE = $5.00          # Avoid penny stocks
MAX_PRICE = $50.00         # Capture mid-cap range (vs $18 in main bot)
```

### Insider Signal Criteria
```python
MIN_FILINGS_FOR_CLUSTER = 3  # 3+ Form 4s in 7 days = cluster
LOOKBACK_DAYS = 7            # Fresh signals only
```

### Portfolio Rules
```python
CAPITAL = $1,000             # Dedicated allocation
MAX_POSITIONS = 4            # Equal weight (2-4 positions)
MIN_CONFIDENCE_SCORE = 0.65  # Lower than main bot (Form 4 is strong signal)
```

---

## 🔒 Safety & Protection Mechanism

### Critical: No Automatic Trading

**This strategy has the SAME protection as your weekly bot:**

✅ **NEVER places orders automatically**  
✅ **ALWAYS requires manual approval before any trade**  
✅ **Generates reports only - you execute manually**  
✅ **Complete control over which positions to trade**

### How Protection Works

**Step 1: Analysis Phase (Automated)**
- Fetches Form 4 filings from SEC
- Filters by market cap and price criteria
- Analyzes with LLM (or rule-based fallback)
- Generates PDF and JSON reports

**Step 2: Approval Phase (Manual - YOU CONTROL THIS)**
```
⚠️  APPROVAL REQUIRED

[1/3] AAPL - Apple Inc.
  Price: $150.00 | Position: 6 shares ($900.00)
  Insider Activity: 5 Form 4 filings (cluster)
  Confidence: 85.0%
  
  Approve AAPL? (y/n/all/none): _  <-- YOU TYPE HERE
```

**You must explicitly approve EACH position:**
- Type `y` = Approve this position
- Type `n` = Reject this position  
- Type `all` = Approve all remaining
- Type `none` = Reject all remaining

**Step 3: Manual Trading (You Execute)**
- Review `approved_positions_YYYYMMDD_HHMMSS.json`
- Open IBKR manually
- Place orders yourself
- Control timing, price, execution

### What Bot Does NOT Do

❌ **Never connects to IBKR**  
❌ **Never places orders**  
❌ **Never modifies your account**  
❌ **Never executes trades automatically**  
❌ **Never sends API commands to brokers**

### What Bot DOES Do

✅ **Fetches public Form 4 data from SEC**  
✅ **Analyzes insider buying patterns**  
✅ **Generates PDF reports for your review**  
✅ **Saves approved positions to JSON**  
✅ **Provides trading recommendations**  
✅ **Calculates position sizes**

### Comparison to Day Trader

| Feature | Form 4 Strategy | Day Trader |
|---------|-----------------|------------|
| **IBKR Connection** | ❌ None | ✅ Required |
| **Order Placement** | ❌ Manual only | ✅ Automatic |
| **Protection** | 🔒 Approval required | ⚠️ Auto-executes |
| **Risk Level** | 🟢 Low (you control) | 🟡 Medium (algo trades) |
| **Timeframe** | Weekly review | Intraday real-time |
| **Capital** | $1000 dedicated | Variable (25-30%) |

### Why This Protection Matters

**Form 4 clusters are SIGNALS, not guarantees:**
- Insiders can be wrong about timing
- Market conditions change rapidly
- News can invalidate thesis between analysis and trading
- You may want to research further before committing capital

**Manual approval lets you:**
1. Double-check fundamentals before trading
2. Verify insider activity is genuine (not option exercises)
3. Check latest news for red flags
4. Adjust position sizes if needed
5. Skip weeks when market conditions are poor
6. Sleep well knowing you control every trade

---

## How It Works

### Weekly Cycle (Run Sundays)

**Step 1: Scan Form 4 Filings**
- Fetch last 7 days of Form 4 filings from FMP API
- Identify "clusters" (3+ filings for same ticker)
- Example: If 5 insiders at SentinelOne file Form 4s in one week = strong cluster

**Step 2: Filter by Fundamentals**
- Check market cap ($500M-$20B)
- Check price ($5-$50)
- Reject stocks outside range

**Step 3: LLM Analysis** (or rule-based if LLM unavailable)
- Analyze company fundamentals
- Review recent news
- Assess insider cluster strength
- Generate confidence score (0.65-1.0)

**Step 4: Position Sizing**
- Select top 2-4 candidates (max 4 positions)
- Equal weight allocation
- Calculate exact shares to buy

**Step 5: Generate Trading Report**
- Save to `form4_strategy/form4_positions_YYYYMMDD_HHMMSS.json`
- Print human-readable summary
- Provide trading instructions

---

## Running the Strategy

### Manual Execution
```powershell
# From repository root
& .\.venv-weekly\Scripts\python.exe weekly_bot\05_form4_strategy.py
```

### Batch File
```cmd
run_form4_strategy.bat
```

**⚠️ IMPORTANT: Manual Approval Required**

This strategy **NEVER executes trades automatically**. After analysis completes:

1. **PDF Report Generated**: Review `weekly_bot/form4_reports/form4_report_YYYYMMDD_HHMMSS.pdf`
2. **Terminal Prompt**: You'll be asked to approve/reject each position:
   ```
   [1/3] S - SentinelOne, Inc.
     Price: $16.92 | Position: 59 shares ($998.28)
     Insider Activity: 3 Form 4 filings (cluster)
     Confidence: 70.0%
     
   Approve S? (y/n/all/none): _
   ```
3. **Responses**:
   - `y` or `yes` = Approve this position
   - `n` or `no` = Reject this position
   - `all` = Approve all remaining positions
   - `none` = Reject all remaining positions

4. **Approved Positions Saved**: Check `weekly_bot/form4_reports/approved_positions_YYYYMMDD_HHMMSS.json` for what to trade
5. **Manual Trading**: You place orders yourself in IBKR

### Task Scheduler (Recommended)
**Schedule:** Every Sunday at 8:00 PM

1. Open Task Scheduler
2. Create Basic Task: "Form 4 Strategy"
3. Trigger: Weekly, Sundays, 8:00 PM
4. Action: Start a program
5. Program: `C:\Users\orelm\OneDrive\Documents\GitHub\trade\run_form4_strategy.bat`

**Note:** Even when scheduled, you must approve positions manually. The script will wait for your input.

---

## Example Output

### Terminal Output
```
================================================================================
FORM 4 INSIDER CLUSTER STRATEGY - ANALYSIS COMPLETE
================================================================================

Generated: November 8, 2025 at 01:36 PM
Capital: $1000.00
Positions Found: 1
Total Allocation: $998.28
Cash Remaining: $1.72

────────────────────────────────────────────────────────────────────────────────
POSITIONS PENDING APPROVAL
────────────────────────────────────────────────────────────────────────────────

#1. S - SentinelOne, Inc.
    Sector: Technology
    Market Cap: $5432M
    Price: $16.92
    📊 Insider Activity: 3 Form 4 filings (CLUSTER)
    🎯 Confidence: 70.0%
    💰 Position: 59 shares = $998.28
    📅 Hold Period: 14 days

================================================================================
```

### Approval Prompt
```
================================================================================
⚠️  FORM 4 STRATEGY - MANUAL APPROVAL REQUIRED
================================================================================

� PROTECTION: This strategy NEVER executes trades automatically
You must review and approve each position before trading.

Review each position and approve/reject:
  - Type 'y' or 'yes' to APPROVE
  - Type 'n' or 'no' to REJECT
  - Type 'all' to approve ALL positions
  - Type 'none' to reject ALL positions
================================================================================

[1/1] S - SentinelOne, Inc.
  Price: $16.92 | Position: 59 shares ($998.28)
  Insider Activity: 3 Form 4 filings (cluster)
  Confidence: 70.0%
  Reasoning: 3 insider filings detected. Rule-based score: 0.70...
  
  Approve S? (y/n/all/none): y
  ✅ Approved: S

================================================================================
✅ APPROVAL SUMMARY
================================================================================
Total positions proposed: 1
Approved: 1
Rejected: 0

📋 APPROVED POSITIONS FOR MANUAL TRADING:
  ✅ S: BUY 59 shares @ $16.92 = $998.28

💰 Total capital to deploy: $998.28
================================================================================
```

### Generated Files

**PDF Report:** `weekly_bot/form4_reports/form4_report_20251108_133617.pdf`
- Executive summary with capital allocation
- Detailed position cards with fundamentals
- Insider activity analysis
- Bull/bear cases for each position
- Trading instructions

**JSON Position File:** `weekly_bot/form4_reports/form4_positions_20251108_133617.json`
- Machine-readable format
- All position details and analysis
- Confidence scores and reasoning

**Approval Decisions:** `weekly_bot/form4_reports/approved_positions_20251108_133617.json`
- Which positions you approved
- Which positions you rejected
- Capital to deploy
- Ready for manual trading execution

---

## Trading Workflow

### Sunday Evening (8:00 PM) - Analysis Phase
1. **Run Strategy:** Execute `run_form4_strategy.bat` or manually run script
2. **Wait for Analysis:** Script fetches Form 4 clusters, filters, and analyzes
3. **Review PDF Report:** Open `weekly_bot/form4_reports/form4_report_YYYYMMDD_HHMMSS.pdf`
   - Check each position's fundamentals
   - Read insider activity details
   - Review confidence scores and reasoning
   - Validate bull/bear cases

### Approval Phase (CRITICAL)
1. **Terminal Prompt Appears:** Script asks for approval of each position
2. **For Each Position:**
   - Read displayed summary (symbol, price, shares, confidence)
   - Type `y` to approve OR `n` to reject
   - Or use `all` to approve all, `none` to reject all
3. **Approval Summary:** Script shows what you approved/rejected
4. **Files Saved:**
   - `approved_positions_YYYYMMDD_HHMMSS.json` = Your approved trades
   - This is your manual trading checklist

### Monday Morning (Pre-Market) - Execution Phase
1. **Open Approved Positions File:** `weekly_bot/form4_reports/approved_positions_YYYYMMDD_HHMMSS.json`
2. **For Each Approved Position:**
   - Open IBKR Trader Workstation
   - Create LIMIT order at listed price (or better)
   - Quantity: Exact shares from approved file
   - Place order manually
3. **Set Reminders:** Calendar alerts for hold period (typically 14 days)
4. **Document Entry:** Note actual fill prices and dates

### During Hold Period
1. **Monitor Weekly:** Check for new Form 4 filings on approved positions
   - More insider buying = bullish confirmation (hold)
   - Insider selling = warning sign (consider exit)
2. **Watch News:** Major negative catalysts = early exit regardless of hold period
3. **Track Performance:** Document gains/losses for strategy evaluation

### Exit Strategy
1. **Hold Period End:** Sell positions after 14 days (or as specified in approved file)
2. **Early Exit Triggers:**
   - Major negative news or earnings miss
   - Insider selling detected (new Form 4s)
   - Technical breakdown (close below key support)
   - Position hits -10% stop loss (discretionary)
3. **Execution:** Place LIMIT orders to exit (same manual process as entry)
4. **Roll Forward:** Freed capital goes into next Sunday's approved positions

**🔒 PROTECTION GUARANTEE:** This bot NEVER places orders automatically. You have complete control over:
- Which positions to trade (approval phase)
- When to enter (you place orders)
- When to exit (you decide timing)
- Position sizes (pre-calculated, you confirm)

---

## Understanding Form 4 Signals

### What is a Form 4?
- SEC filing required within **2 business days** of insider transaction
- Filed by: Directors, officers, 10%+ shareholders
- Shows: Buy/sell, quantity, price, date

### Why Clusters Matter
**Single Filing:** Could be routine stock option exercise  
**Cluster (3+ filings):** Multiple insiders buying simultaneously = **strong bullish signal**

**Example:**
- Nov 5: CEO buys 10,000 shares
- Nov 6: CFO buys 5,000 shares  
- Nov 7: Director buys 8,000 shares
- **Signal:** Three insiders coordinating = they know something positive

### False Positives to Watch
- **Option exercises:** Check if shares were bought or just exercised
- **Restricted stock vesting:** Automatic, not discretionary buying
- **Selling:** Ignore clusters of insider selling (this strategy focuses on buying)

---

## Performance Tracking

### Metrics to Monitor
- **Win Rate:** % of positions that close positive
- **Average Return:** Mean gain/loss per position
- **Hold Period Accuracy:** Do positions hit target before exit?
- **Cluster Strength Correlation:** Do 5+ filings outperform 3 filings?

### Expected Performance
**Realistic Targets:**
- Win Rate: 60-70% (insider buying is bullish but not guaranteed)
- Average Return: +5-10% per position over 14 days
- Annual Return: 20-30% on $1000 capital (if above targets met)

**Best Case:** One 30%+ winner quarterly = 2x annual capital  
**Worst Case:** 50% win rate, 5% average = modest gains but beats market

---

## Advantages Over Main Strategies

### vs. Microcap Weekly Bot
- **Different universe:** Mid-caps vs microcaps (no overlap)
- **Stronger signal:** Insider clusters > news sentiment
- **Higher prices:** $5-50 range captures more actionable stocks
- **Less crowded:** Fewer retail traders watching Form 4s

### vs. Day Trader
- **Swing timeframe:** Hold 14 days vs intraday
- **Fundamental edge:** Insider knowledge vs technical signals
- **Lower stress:** Weekly rebalance vs constant monitoring
- **Uncorrelated:** Different market segment and strategy

---

## Capital Allocation Summary

| Strategy | Capital | Timeframe | Signal Type | Price Range |
|----------|---------|-----------|-------------|-------------|
| **Day Trader** | Variable (25-30% of account) | Intraday | VWAP momentum | Any liquid stocks |
| **Weekly Microcaps** | Variable (~$5K typical) | 1-3 weeks | News + fundamentals | $1-18 |
| **Form 4 Insider** | **$1,000 dedicated** | 2-3 weeks | Insider clusters | $5-50 |

**Total diversification:** 3 uncorrelated strategies running in parallel

---

## Troubleshooting

### "No insider clusters found"
- **Normal:** Some weeks have low Form 4 activity
- **Action:** Skip week, keep cash, run again next Sunday
- **Frequency:** Expect 1-3 weeks per quarter with no signals

### "Candidates filtered out"
- **Cause:** Clusters outside $500M-20B or $5-50 price range
- **Action:** Accept - strategy is intentionally selective
- **Don't:** Lower filters just to force trades

### "LLM analysis failed"
- **Fallback:** Script uses rule-based scoring automatically
- **Impact:** Lower confidence but still functional
- **Fix:** Set DEEPSEEK_API_KEY or GOOGLE_API_KEY in environment

### "Position only $250"
- **By design:** Equal weight across 2-4 positions
- **Math:** $1000 / 4 positions = $250 per position
- **If only 1 position:** Uses full $1000 (like SentinelOne example)

---

## Future Enhancements

### Potential Improvements
1. **Parse XML:** Extract exact buy/sell direction and share counts
2. **Insider Roles:** Weight CEO/CFO buys higher than board members
3. **Historical Backtest:** Test strategy on past Form 4 clusters
4. **Portfolio Tracker:** Auto-track open positions and P&L
5. **IBKR Integration:** Auto-place orders (currently manual)

### Data Enhancements
1. **SEC Edgar API:** Direct parsing instead of FMP proxy
2. **13F Filings:** Add institutional buying clusters
3. **Schedule 13D:** Detect activist investors
4. **Insider Selling:** Add inverse signals (short candidates)

---

## Risk Warnings

⚠️ **Insider Trading ≠ Guaranteed Profits**
- Insiders can be wrong about timing
- Market conditions override insider confidence
- Regulations allow insiders to file late (up to 2 days)

⚠️ **Small Sample Size**
- $1000 capital = 2-4 positions only
- One bad trade = 25-50% of capital
- Results will be lumpy (high variance)

⚠️ **Correlation Risk**
- Mid-cap tech clusters may all move together
- Sector rotation can hurt multiple positions
- Diversify by holding period offset if possible

---

## Files and Locations

### Core Files
- **Strategy:** `weekly_bot/05_form4_strategy.py` (Phase 5 in weekly bot folder)
- **Runner:** `run_form4_strategy.bat` (Windows batch)
- **Output Folder:** `weekly_bot/form4_reports/`

### Generated Reports (per run)
- **PDF Report:** `form4_report_YYYYMMDD_HHMMSS.pdf` (visual analysis)
- **JSON Positions:** `form4_positions_YYYYMMDD_HHMMSS.json` (machine-readable)
- **Approved Trades:** `approved_positions_YYYYMMDD_HHMMSS.json` (your manual checklist)

### Test Scripts (for development)
- **FMP API Test:** `scripts/test_form4_fmp.py`
- **Microcap Analysis:** `scripts/analyze_form4_microcaps.py`

### Documentation
- **This file:** `docs/FORM4_STRATEGY.md`
- **Main README:** `docs/README.md`
- **Weekly Bot Guide:** `docs/WEEKLY_BOT_DOCS.md`

---

## Quick Start Checklist

- [ ] Review strategy parameters in `weekly_bot/05_form4_strategy.py`
- [ ] Set FMP_API_KEY in environment (or use default)
- [ ] Test run: `python weekly_bot\05_form4_strategy.py`
- [ ] Review PDF output in `weekly_bot/form4_reports/` folder
- [ ] Practice approval workflow (type `y`/`n`/`all`/`none`)
- [ ] Check approved positions JSON file
- [ ] Set up Task Scheduler for Sunday 8:00 PM
- [ ] **IMPORTANT:** Understand this bot NEVER auto-trades
- [ ] Create calendar template for 14-day hold periods
- [ ] Set up spreadsheet for performance tracking

---

## Contact & Support

For questions about this strategy, refer to:
- **Repository README:** `docs/README.md`
- **Weekly Bot Docs:** `docs/WEEKLY_BOT_DOCS.md`
- **Production Guide:** `docs/PRODUCTION_GUIDE.md`

**Last Updated:** November 8, 2025
