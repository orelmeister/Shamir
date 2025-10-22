# AI-Powered Dynamic Portfolio Manager - Implementation Plan

**Date Created**: October 22, 2025  
**Current Status**: Day trader bot running (let it finish today's session)  
**Goal**: Transform from "25% day trader" to "100% AI-driven portfolio manager"

---

## 📊 CURRENT STATE ANALYSIS

### Existing Bot Architecture
```
Phase 0 (7:00 AM): Data Collection
├── Screen 26 stocks from FMP
├── Collect news, fundamentals, historical data
└── Output: full_market_data.json

Phase 0.5 (7:15 AM): ATR Prediction
├── ML model predicts volatility
└── Output: atr_predictions.json

Phase 1 (7:30 AM): LLM Watchlist Analysis
├── DeepSeek Reasoner analyzes 26 stocks
├── Narrows to 9 "GOOD" candidates
└── Output: day_trading_watchlist.json

Phase 1.5 (8:15 AM): Ticker Validation
├── IBKR validates tickers exist
└── Output: validated_tickers.json

Phase 1.75 (9:00 AM): Pre-Market Momentum
├── Checks pre-market price action
└── Output: momentum ranking

Phase 2 (9:30 AM - 4:00 PM): Intraday Trading
├── Monitor 9 watchlist stocks
├── Entry: Price > VWAP, 40 < RSI < 60, ATR > 1.5%
├── Exit: Price < VWAP or RSI extreme
└── Uses 25% of capital ($479 requested, $4.43 available)
```

### Current Limitations
- ❌ **99.8% capital idle** ($1,914 / $1,918 not being actively managed)
- ❌ **Ignores existing positions** (bot doesn't know what it already owns)
- ❌ **Artificial day trading restriction** (forces same-day exits)
- ❌ **No portfolio review** (existing holdings never re-evaluated)
- ❌ **PDT risk** (current strategy could trigger pattern day trader violations)

### Current Account Status
- **Net Liquidation**: $1,918.80
- **Available Cash**: $4.43 (after ALEC purchases)
- **Existing Positions**: Unknown (need to query IBKR)
- **Paper Trading**: Yes (IBKR account U21952129)

---

## 🎯 PROJECT 1: MONITORING DASHBOARD

### Objective
Build a web-based monitoring interface accessible from phone/remote to track bot activity without being at the PC.

### Solution Architecture: Flask Dashboard + Telegram Bot Combo

#### **A. Flask Web Dashboard** (Primary Interface)

**Tech Stack:**
- **Backend**: Flask + Flask-SocketIO (real-time updates)
- **Frontend**: HTML5 + CSS3 + JavaScript (responsive design)
- **Data Storage**: JSON files + SQLite for trade history
- **Charts**: Chart.js or Plotly for visualizations

**Features:**

1. **Live Terminal Output View**
   - Real-time scrolling log (last 500 lines)
   - Color-coded by log level (INFO=white, WARNING=yellow, ERROR=red)
   - Auto-scroll toggle
   - Search/filter functionality

2. **Portfolio Overview Dashboard**
   ```
   ┌─────────────────────────────────────────┐
   │ ACCOUNT SUMMARY                         │
   │ Net Liquidation: $1,918.80 (+2.3%)     │
   │ Cash Available: $4.43                   │
   │ Day's P&L: +$45.20 (+2.4%)             │
   │ Total Positions: 5                      │
   └─────────────────────────────────────────┘
   ```

3. **Active Positions Table**
   ```
   Ticker | Qty | Entry Price | Current | P&L  | P&L% | Status
   ─────────────────────────────────────────────────────────────
   ALEC   | 3   | $1.565      | $1.60   | +$0.11| +2.2%| HOLD
   HOND   | 1   | $16.80      | $16.90  | +$0.10| +0.6%| HOLD
   ```

4. **Trade History Log**
   - Chronological list of all trades (BUY/SELL)
   - Timestamps, prices, P&L per trade
   - Exportable to CSV

5. **Performance Charts**
   - Intraday P&L chart (line graph)
   - Position allocation (pie chart)
   - Daily win rate (bar chart)

6. **System Status**
   - Bot state: RUNNING / STOPPED / ERROR
   - IBKR connection: CONNECTED / DISCONNECTED
   - Market status: OPEN / CLOSED / PRE-MARKET
   - Last update timestamp

**File Structure:**
```
/monitoring_dashboard/
├── app.py                 # Flask app main
├── static/
│   ├── css/
│   │   └── dashboard.css  # Styling
│   ├── js/
│   │   └── dashboard.js   # WebSocket client, chart updates
│   └── favicon.ico
├── templates/
│   ├── index.html         # Main dashboard
│   └── login.html         # Optional: simple password protection
├── data/
│   ├── logs/              # Symlink to bot logs
│   └── trades.db          # SQLite for trade history
└── requirements_dashboard.txt
```

**API Endpoints:**
```python
GET  /                      # Dashboard HTML
GET  /api/status            # System status JSON
GET  /api/positions         # Current positions JSON
GET  /api/account           # Account summary JSON
GET  /api/trades            # Trade history JSON
GET  /api/logs              # Latest log lines JSON
WebSocket /ws               # Real-time updates
```

**Access Methods:**
1. **Local Network**: `http://192.168.x.x:5000` (find IP with `ipconfig`)
2. **Remote (via ngrok)**: `ngrok http 5000` → `https://abc123.ngrok.io`
3. **Port Forwarding**: Configure router to expose port 5000 (less secure)

---

#### **B. Telegram Bot** (Mobile Notifications)

**Tech Stack:**
- **Library**: python-telegram-bot
- **Hosting**: Runs alongside main bot (same process or separate)

**Features:**

1. **Automatic Notifications**
   - 🟢 `[BUY] ALEC: 3 shares @ $1.565 (Entry signal: VWAP momentum)`
   - 🔴 `[SELL] HOND: 1 share @ $17.05 (Exit: Price < VWAP)`
   - ⚠️ `[ALERT] PDT limit approaching: 2/3 day trades used`
   - 📊 `[DAILY] Day end summary: 3 trades, +$45.20 (+2.4%)`

2. **Commands**
   - `/start` - Subscribe to notifications
   - `/status` - Current bot status & positions
   - `/positions` - Detailed position breakdown
   - `/pnl` - Today's P&L summary
   - `/trades` - Last 5 trades
   - `/stop` - Emergency shutdown (stops bot)
   - `/restart` - Restart bot
   - `/logs` - Get last 50 log lines

3. **Interactive Buttons**
   ```
   Current Status: 🟢 RUNNING
   [📊 Positions] [💰 P&L] [📜 Logs] [🛑 Stop]
   ```

**Setup Process:**
1. Create bot via BotFather on Telegram → get API token
2. Store token in `.env` file (keep secure)
3. User sends `/start` to bot → bot saves chat_id
4. Bot sends notifications to saved chat_id

**Security:**
- Only authorized chat_id can control bot
- `.env` file in `.gitignore` (never commit API token)
- Optional: password verification before executing commands

---

#### **C. Implementation Checklist**

**Dashboard Setup (2-3 hours):**
- [ ] Install Flask, Flask-SocketIO, python-socketio
- [ ] Create basic HTML template with responsive CSS
- [ ] Implement WebSocket for real-time log streaming
- [ ] Add API endpoints for positions/account data
- [ ] Create Chart.js visualizations
- [ ] Test on phone browser (local network)
- [ ] Optional: Set up ngrok for remote access

**Telegram Bot Setup (1 hour):**
- [ ] Install python-telegram-bot
- [ ] Create bot via BotFather
- [ ] Implement notification system in trading bot
- [ ] Add command handlers (/status, /positions, etc.)
- [ ] Test notifications and commands
- [ ] Document setup process for future reference

**Bot Integration (30 minutes):**
- [ ] Modify day_trading_agents.py to log trades to SQLite
- [ ] Add Telegram notification calls on trade execution
- [ ] Add dashboard data endpoints to read bot state
- [ ] Test end-to-end: trade execution → dashboard update → Telegram ping

---

## 🤖 PROJECT 2: AI-POWERED DYNAMIC PORTFOLIO MANAGER

### Objective
Transform the bot from a "25% day trader" into a "100% AI-driven portfolio manager" that actively manages ALL positions using LLM analysis and technical indicators.

### Core Philosophy
**"Unified Portfolio Management"** - No distinction between "day trades" and "long-term holds". Every position is evaluated daily on its merit. Capital is dynamically allocated to the strongest opportunities. Weak positions are rotated out into better setups.

---

### Architecture Changes

#### **NEW PHASE 1.8: Portfolio Review & Liquidation**
**Time**: 7:45 AM (after watchlist analysis, before market open)

**Purpose**: 
- Fetch current positions from IBKR
- LLM analyzes each holding with latest market data
- Decide: HOLD (strong momentum) vs SELL (momentum dying)
- Execute liquidations before market open or at 9:30 AM

**Agent**: `PortfolioReviewAgent`

**Inputs**:
1. Current positions from IBKR API (`ib.positions()`)
2. Latest market data for each holding (from Phase 0)
3. Historical price action (last 5 days)
4. Recent news for each ticker

**LLM Prompt** (DeepSeek Reasoner):
```
You are a portfolio manager analyzing existing holdings to decide if they should be kept or sold.

CURRENT PORTFOLIO:
{positions_json}

LATEST MARKET DATA:
{market_data_for_holdings}

For each position, analyze:
1. Price momentum: Is it still trending upward or weakening?
2. News sentiment: Any negative developments since purchase?
3. Technical setup: Still above VWAP? RSI still healthy (30-70)?
4. Relative strength: Better opportunities available in watchlist?

OUTPUT (JSON):
{
  "positions": [
    {
      "ticker": "AAPL",
      "action": "HOLD",
      "reasoning": "Strong uptrend intact, above VWAP, RSI 55 (neutral), no negative news",
      "confidence": 8
    },
    {
      "ticker": "TSLA", 
      "action": "SELL",
      "reasoning": "Momentum dying, price breaking below VWAP, negative news on production delays",
      "confidence": 9,
      "suggested_replacement": "ALEC" // from watchlist
    }
  ]
}

Be decisive. We want to rotate capital from weak positions to strong ones.
```

**Execution**:
- SELL orders placed at market open (9:30 AM)
- Freed capital immediately available for new positions
- Log all decisions with reasoning

**Output**: `portfolio_review_decisions.json`

---

#### **MODIFIED PHASE 2: Unified Trading Agent**

**Previous**: Monitor 9 watchlist stocks only  
**New**: Monitor existing positions + watchlist stocks (unified approach)

**Changes**:

1. **Capital Allocation Strategy**
```python
# OLD: Fixed 25% allocation
capital_per_stock = (net_liquidation * 0.25) / num_watchlist_stocks

# NEW: Dynamic 100% allocation with position sizing
max_positions = 7  # Diversification limit
capital_per_position = available_cash / (max_positions - current_positions)
# Example: $1,918 / 7 = ~$274 per position
```

2. **Monitoring Scope**
```python
# OLD: Only new watchlist stocks
stocks_to_monitor = watchlist_stocks  # 9 stocks

# NEW: Existing positions + watchlist stocks
current_positions = [p.contract.symbol for p in ib.positions()]
stocks_to_monitor = list(set(current_positions + watchlist_stocks))
# Could be 5 holdings + 9 watchlist = 14 stocks total
```

3. **Entry Logic** (Unchanged)
- Price > VWAP
- 40 < RSI < 60
- ATR > 1.5% (volatile enough to day trade)

4. **Exit Logic** (MODIFIED - Allow Overnight Holds)
```python
# OLD: Always exit same day
if price < vwap or rsi < 30 or rsi > 70:
    sell_immediately()

# NEW: Exit only when momentum dies (can hold overnight)
if price < vwap and rsi < 40:  # Confirmed weakness
    sell_immediately()
elif rsi > 75:  # Extremely overbought
    sell_immediately()
elif holding_period > 3 days:  # Max hold duration
    sell_immediately()
else:
    hold_position()  # Keep if momentum intact
```

**Benefits**:
- Allows holding winners overnight (not a "day trade" per PDT rules)
- Only exits when technical breakdown occurs
- Maximizes gains from strong momentum moves

5. **PDT Tracking** (NEW)
```python
class PDTTracker:
    def __init__(self):
        self.trades = []  # Rolling 5-day window
    
    def is_day_trade(self, ticker, buy_date, sell_date):
        return buy_date == sell_date
    
    def count_recent_day_trades(self):
        # Count day trades in last 5 trading days
        return len([t for t in self.trades if t.is_day_trade and t.age_days < 5])
    
    def can_day_trade(self):
        return self.count_recent_day_trades() < 3
    
    def log_trade(self, ticker, buy_date, sell_date, pnl):
        is_dt = self.is_day_trade(ticker, buy_date, sell_date)
        self.trades.append(Trade(ticker, buy_date, sell_date, pnl, is_dt))
        if is_dt:
            count = self.count_recent_day_trades()
            logger.warning(f"Day trade executed: {ticker}. Count: {count}/3")
```

**Logic**:
```python
# Before executing same-day sell:
if pdt_tracker.can_day_trade():
    execute_sell()
else:
    logger.warning(f"Cannot sell {ticker} today - would violate PDT rule (3/3 trades). Holding overnight.")
    # Sell tomorrow morning instead
```

---

#### **RENAMED PHASES**

To reflect the new "dynamic portfolio manager" paradigm:

```
Phase 0:     Data Collection              [UNCHANGED]
Phase 0.5:   ATR Prediction               [UNCHANGED]
Phase 1:     Market Opportunity Screening [RENAMED: was "Watchlist Analysis"]
Phase 1.5:   Ticker Validation            [UNCHANGED]
Phase 1.8:   Portfolio Review & Rotation  [NEW]
Phase 1.75:  Pre-Market Momentum          [UNCHANGED]
Phase 2:     Unified Portfolio Trading    [RENAMED: was "Intraday Trading"]
```

---

### Position Sizing & Risk Management

#### **Rules**:
1. **Max Positions**: 5-7 stocks at once (diversification without over-spreading)
2. **Position Size**: ~$250-350 per stock (with $1,918 account)
3. **Max Per Stock**: 20% of portfolio ($383 max)
4. **Stop Loss**: Exit if position drops 8% from entry (protect capital)
5. **Profit Target**: Consider taking profits at +15% (lock in gains)
6. **Sector Limit**: Max 2 stocks from same sector (reduce correlation risk)

#### **Example Portfolio** (after Phase 1.8):
```
Available Capital: $1,918
Max Positions: 7
Target per Position: $274

Current Holdings (after review):
1. ALEC - $156 (3 shares @ $1.56) - HOLD - 8% of portfolio
2. NAVI - $252 (20 shares @ $12.60) - HOLD - 13% of portfolio
3. [Freed up from TSLA liquidation: $450] 

Open Slots: 5 positions available
Capital for New Positions: $1,918 - $156 - $252 = $1,510
Per Position: $1,510 / 5 = $302 each

Watchlist Opportunities:
- HOND: Strong setup, ATR 1.7%, above VWAP → BUY $300
- REPL: Improving RSI, ATR 0.8% (too low) → SKIP
- PUBM: Overbought RSI 72 → SKIP
```

---

### LLM Integration Points

#### **1. Phase 1: Market Opportunity Screening**
**Model**: DeepSeek Reasoner (deep analysis, 60s thinking)
**Input**: 26 stocks with news, fundamentals, technical data
**Output**: Top opportunities ranked by potential
**Caching**: Daily (skip if already analyzed today)

#### **2. Phase 1.8: Portfolio Review** (NEW)
**Model**: Gemini 2.0 Flash (fast decisions, 5s)
**Input**: Current holdings + latest market data
**Output**: HOLD/SELL decisions with reasoning
**Caching**: None (must run daily)

#### **3. Phase 2: Trade Validation** (Optional Enhancement)
**Model**: Gemini 2.0 Flash (sanity check, 2s)
**Input**: Proposed trade (BUY ALEC @ $1.565)
**Output**: Approve/Reject with reasoning
**Purpose**: Second opinion before execution (avoid obvious mistakes)

**Prompt**:
```
Quick sanity check before executing trade:

PROPOSED TRADE: BUY 3 shares of ALEC @ $1.565
ENTRY REASON: Price > VWAP ($1.56), RSI 43 (neutral), ATR 1.66% (volatile)
ACCOUNT: $1,918 total, 2 existing positions, this would be position #3

VALIDATE:
1. Does this trade make sense given market conditions?
2. Any red flags (news, technical warnings)?
3. Position size appropriate ($4.70 for 3 shares)?

OUTPUT (JSON):
{"decision": "APPROVE/REJECT", "reasoning": "...", "confidence": 8}

Be quick but thorough.
```

---

### Daily Workflow (Revised)

```
7:00 AM - Phase 0: Data Collection
├── Scrape 26 stocks from FMP
├── Collect news, fundamentals, prices
└── ✅ full_market_data.json

7:15 AM - Phase 0.5: ATR Prediction  
├── ML model predicts volatility
└── ✅ atr_predictions.json

7:30 AM - Phase 1: Market Opportunity Screening
├── DeepSeek analyzes 26 stocks
├── Ranks top opportunities
└── ✅ market_opportunities.json (9 stocks)

7:45 AM - Phase 1.8: Portfolio Review (NEW)
├── Fetch current positions from IBKR
├── Gemini analyzes each holding
├── Decide HOLD vs SELL
└── ✅ portfolio_review_decisions.json

8:15 AM - Phase 1.5: Ticker Validation
├── Validate all tickers (holdings + opportunities)
└── ✅ validated_tickers.json

9:00 AM - Phase 1.75: Pre-Market Momentum
├── Check pre-market price action
└── ✅ Momentum ranking

9:30 AM - Phase 2: Unified Portfolio Trading
├── Execute SELL orders (from Phase 1.8)
├── Monitor: existing positions + opportunities (unified)
├── Execute BUY when signals trigger
├── Exit positions when momentum dies
├── Track PDT status (max 3 day trades / 5 days)
└── Run until 4:00 PM market close

4:00 PM - End of Day Summary
├── Generate performance report
├── Log all trades to database
├── Send Telegram summary
└── ✅ daily_performance_report.json
```

---

### Code Architecture Changes

#### **New Files to Create**:

1. **`portfolio_review_agent.py`**
```python
class PortfolioReviewAgent(BaseAgent):
    """
    Reviews existing positions each morning and decides HOLD vs SELL.
    Uses LLM to analyze momentum, news, and technical indicators.
    """
    def __init__(self, ib, llm_client):
        self.ib = ib
        self.llm = llm_client
    
    def fetch_current_positions(self):
        """Get positions from IBKR API"""
        return self.ib.positions()
    
    def analyze_position(self, position, market_data):
        """LLM analyzes single position"""
        prompt = self._build_analysis_prompt(position, market_data)
        response = self.llm.generate(prompt)
        return self._parse_decision(response)
    
    def execute_liquidations(self, sell_decisions):
        """Place market sell orders for positions to liquidate"""
        for decision in sell_decisions:
            if decision['action'] == 'SELL':
                self.place_sell_order(decision['ticker'])
    
    def run(self):
        """Main execution: review all positions, make decisions"""
        positions = self.fetch_current_positions()
        decisions = []
        for pos in positions:
            decision = self.analyze_position(pos, market_data)
            decisions.append(decision)
        
        # Execute sells
        sell_list = [d for d in decisions if d['action'] == 'SELL']
        self.execute_liquidations(sell_list)
        
        # Save decisions
        self.save_decisions(decisions)
```

2. **`pdt_tracker.py`**
```python
class PDTTracker:
    """
    Tracks day trades in rolling 5-day window to avoid PDT violations.
    """
    def __init__(self, db_path='trades.db'):
        self.db = sqlite3.connect(db_path)
        self._create_table()
    
    def log_trade(self, ticker, buy_date, sell_date, pnl):
        """Record trade in database"""
        is_day_trade = (buy_date == sell_date)
        self.db.execute("""
            INSERT INTO trades (ticker, buy_date, sell_date, pnl, is_day_trade)
            VALUES (?, ?, ?, ?, ?)
        """, (ticker, buy_date, sell_date, pnl, is_day_trade))
        
    def count_recent_day_trades(self):
        """Count day trades in last 5 trading days"""
        five_days_ago = (datetime.now() - timedelta(days=7)).date()
        cursor = self.db.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE is_day_trade = 1 AND buy_date >= ?
        """, (five_days_ago,))
        return cursor.fetchone()[0]
    
    def can_day_trade(self):
        """Check if we can execute another day trade"""
        count = self.count_recent_day_trades()
        return count < 3
```

3. **`unified_trader_agent.py`** (refactored from `IntradayTraderAgent`)
```python
class UnifiedTraderAgent(BaseAgent):
    """
    Manages entire portfolio: existing positions + new opportunities.
    No distinction between "day trades" and "holds" - unified strategy.
    """
    def __init__(self, ib, allocation=1.0):  # Default 100%
        self.allocation = allocation  # 1.0 = use full account
        self.pdt_tracker = PDTTracker()
        self.max_positions = 7
    
    def get_stocks_to_monitor(self):
        """Combine existing positions + watchlist"""
        holdings = [p.contract.symbol for p in self.ib.positions()]
        watchlist = load_watchlist('market_opportunities.json')
        return list(set(holdings + watchlist))
    
    def calculate_position_size(self):
        """Dynamic position sizing based on available capital"""
        available = self.get_available_cash()
        current_positions = len(self.ib.positions())
        open_slots = self.max_positions - current_positions
        return available / max(open_slots, 1)
    
    def should_exit_position(self, ticker, price, vwap, rsi, holding_days):
        """Unified exit logic (not forced same-day exit)"""
        # Exit conditions
        if price < vwap and rsi < 40:  # Confirmed weakness
            return True, "Price below VWAP with weak RSI"
        if rsi > 75:  # Extreme overbought
            return True, "Extremely overbought"
        if holding_days > 3:  # Max hold period
            return True, "Max 3-day hold reached"
        
        # Otherwise, keep holding
        return False, "Momentum still intact"
    
    def execute_exit(self, ticker):
        """Exit position with PDT awareness"""
        position = self.get_position(ticker)
        buy_date = position.entry_date
        sell_date = datetime.now().date()
        
        # Check if selling today would be a day trade
        if buy_date == sell_date:
            if not self.pdt_tracker.can_day_trade():
                logger.warning(f"Cannot sell {ticker} today - PDT limit reached. Holding overnight.")
                return False
        
        # Execute sell
        self.place_sell_order(ticker)
        self.pdt_tracker.log_trade(ticker, buy_date, sell_date, position.pnl)
        return True
```

#### **Modified Files**:

1. **`day_trader.py`** (orchestrator)
```python
# Add Phase 1.8
def _run_portfolio_review(self):
    """Phase 1.8: Review existing positions and liquidate weak ones"""
    if not is_market_open() and datetime.now().hour < 9:
        self.log("Running Portfolio Review (Phase 1.8)...")
        review_agent = PortfolioReviewAgent(self.ib, self.llm_client)
        review_agent.run()
        self.log("Portfolio review complete.")

# Modify start() to include new phase
def start(self):
    self.run_data_aggregation()        # Phase 0
    self.run_atr_prediction()           # Phase 0.5
    self.run_premarket_analysis()       # Phase 1
    self.run_ticker_validation()        # Phase 1.5
    self._run_portfolio_review()        # Phase 1.8 (NEW)
    self.run_premarket_momentum()       # Phase 1.75
    self.run_unified_trading()          # Phase 2 (RENAMED)
```

2. **`day_trading_agents.py`**
   - Rename `IntradayTraderAgent` → `UnifiedTraderAgent`
   - Modify monitoring scope (existing + watchlist)
   - Update exit logic (allow overnight holds)
   - Add PDT tracking

---

### Testing Strategy

#### **Phase 1: Portfolio Review Testing**
```bash
# Test portfolio review agent standalone
python test_portfolio_review.py

# Expected output:
# - Fetch current positions from IBKR
# - Analyze each with LLM
# - Output decisions (HOLD/SELL)
# - Log reasoning
```

#### **Phase 2: Unified Trading Testing**
```bash
# Test unified trader with paper account
python day_trader.py --allocation 1.0 --duration 60

# Validate:
# - Monitors existing positions + watchlist
# - Calculates position size correctly
# - PDT tracking works
# - Overnight holds allowed
# - Exits only on technical breakdown
```

#### **Phase 3: End-to-End Testing**
```bash
# Full day simulation
python day_trader.py --allocation 1.0

# Monitor:
# - Phase 1.8 reviews portfolio at 7:45 AM
# - Liquidates weak positions at 9:30 AM
# - Allocates freed capital to strong opportunities
# - Manages positions throughout day
# - Holds winners overnight if momentum intact
# - Generates end-of-day report
```

---

### Risk Mitigation

#### **Safeguards**:
1. **Max Drawdown Limit**: Stop trading if daily loss exceeds 5% ($96)
2. **Position Size Cap**: Never more than 20% in single stock ($383)
3. **Stop Losses**: Auto-exit if position drops 8% from entry
4. **PDT Protection**: Track and prevent violations (built-in)
5. **Human Override**: Telegram `/stop` command for emergency shutdown

#### **Monitoring**:
- Dashboard shows real-time P&L
- Telegram alerts on every trade
- Daily email summary (optional)
- Weekly performance review

---

### Success Metrics

**After 1 Week:**
- [ ] No PDT violations
- [ ] Average 2-3 positions held daily
- [ ] Capital utilization > 80% (vs current 0.2%)
- [ ] Dashboard accessible from phone
- [ ] Telegram notifications working

**After 1 Month:**
- [ ] Positive total return (any amount = success for paper trading)
- [ ] Win rate > 50%
- [ ] Avg trade duration 1-2 days (swing trading, not day trading)
- [ ] Portfolio Review correctly identifies weak positions
- [ ] Max drawdown < 10%

---

### Implementation Timeline

#### **Day 1 (End of Today's Trading Session)**
- [ ] Let current bot finish (4:00 PM)
- [ ] Query IBKR for current positions
- [ ] Analyze what we're holding and why
- [ ] Plan liquidation strategy if needed

#### **Day 2 (Implementation)**
- **Morning (3 hours)**:
  - [ ] Create `PortfolioReviewAgent` class
  - [ ] Implement LLM prompt for position analysis
  - [ ] Add Phase 1.8 to orchestrator
  - [ ] Test portfolio review logic

- **Afternoon (3 hours)**:
  - [ ] Create `PDTTracker` class with SQLite
  - [ ] Refactor `IntradayTraderAgent` → `UnifiedTraderAgent`
  - [ ] Modify monitoring scope (existing + watchlist)
  - [ ] Update exit logic (allow overnight)
  - [ ] Test unified trading logic

- **Evening (2 hours)**:
  - [ ] End-to-end testing with paper account
  - [ ] Validate all phases work together
  - [ ] Fix any bugs discovered

#### **Day 3 (Monitoring Dashboard)**
- **Morning (2 hours)**:
  - [ ] Set up Flask app structure
  - [ ] Create basic HTML dashboard
  - [ ] Implement WebSocket for real-time logs
  - [ ] Test on local network

- **Afternoon (2 hours)**:
  - [ ] Add API endpoints (positions, account, trades)
  - [ ] Create Chart.js visualizations
  - [ ] Make responsive for mobile
  - [ ] Test from phone browser

- **Evening (1 hour)**:
  - [ ] Set up Telegram bot
  - [ ] Implement notification system
  - [ ] Test commands (/status, /positions, etc.)
  - [ ] Document setup process

#### **Day 4 (Production Launch)**
- [ ] Final testing: full workflow from Phase 0 → Phase 2
- [ ] Deploy dashboard (keep running in background)
- [ ] Start Telegram bot
- [ ] Launch unified portfolio manager (paper trading)
- [ ] Monitor throughout day

---

## 📋 PROMPTS FOR IMPLEMENTATION

### **Prompt 1: Portfolio Review Agent**

```
I need you to implement a new agent called PortfolioReviewAgent that reviews existing IBKR positions each morning and decides whether to HOLD or SELL each one.

CONTEXT:
- We're building a "Dynamic Portfolio Manager" that actively manages 100% of capital
- Every morning at 7:45 AM (Phase 1.8), the bot should review existing positions
- Use Gemini 2.0 Flash (fast model) to analyze each position
- Output decisions with reasoning to portfolio_review_decisions.json

REQUIREMENTS:
1. Fetch current positions from IBKR API (ib.positions())
2. For each position, gather:
   - Current price, entry price, P&L
   - Latest market data from full_market_data.json
   - Technical indicators: VWAP, RSI, ATR
   - Recent news (if available)
3. Send to LLM for analysis with this prompt structure:
   "You are analyzing position [TICKER] bought at [ENTRY_PRICE].
    Current price: [CURRENT_PRICE], P&L: [PNL]%.
    Technical: Price vs VWAP [ABOVE/BELOW], RSI [VALUE], ATR [VALUE]%
    Recent news: [NEWS_SUMMARY]
    
    Decision: HOLD or SELL?
    Reasoning: Why?
    Confidence: 1-10
    Suggested_replacement: If SELL, what from watchlist should replace it?"
4. Parse LLM response (expect JSON)
5. Execute SELL orders for positions marked SELL
6. Log all decisions with reasoning

INTEGRATION:
- Add to day_trader.py as Phase 1.8 (after Phase 1.5, before Phase 1.75)
- Should run at 7:45 AM before market opens
- Output saved to portfolio_review_decisions.json

TESTING:
- Create test_portfolio_review.py to test standalone
- Mock IBKR positions if needed
- Validate LLM prompt works correctly
- Ensure sells execute properly

Please implement this following the existing agent pattern (inherit from BaseAgent).
```

---

### **Prompt 2: PDT Tracker**

```
I need you to implement a PDT (Pattern Day Trader) tracking system to prevent violations of the 3-day-trades-per-5-days rule.

CONTEXT:
- Account is under $25k, so limited to 3 day trades per rolling 5 trading days
- A "day trade" = buying and selling the same stock on the same day
- If we exceed 3 day trades, account gets flagged and restricted

REQUIREMENTS:
1. Create PDTTracker class that:
   - Stores all trades in SQLite database (trades.db)
   - Tracks: ticker, buy_date, sell_date, pnl, is_day_trade (boolean)
   - Counts day trades in last 5 trading days
   - Has method: can_day_trade() → returns True/False

2. Database schema:
   ```sql
   CREATE TABLE trades (
       id INTEGER PRIMARY KEY,
       ticker TEXT,
       buy_date DATE,
       sell_date DATE,
       pnl REAL,
       is_day_trade BOOLEAN,
       timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
   );
   ```

3. Methods needed:
   - log_trade(ticker, buy_date, sell_date, pnl)
   - count_recent_day_trades() → int
   - can_day_trade() → bool
   - get_trade_history(days=30) → list

4. Usage in UnifiedTraderAgent:
   ```python
   # Before selling same-day position:
   if self.pdt_tracker.can_day_trade():
       self.execute_sell(ticker)
   else:
       logger.warning("Cannot sell today - would violate PDT. Holding overnight.")
   ```

5. Logging:
   - Log warning when day trade count reaches 2/3
   - Log error if attempting 4th day trade (should never happen)
   - Daily summary: "Day trades used: X/3 (resets in Y days)"

Please implement this as a standalone class in pdt_tracker.py.
Create test_pdt_tracker.py to validate the counting logic works correctly.
```

---

### **Prompt 3: Unified Trader Agent**

```
I need you to refactor IntradayTraderAgent into UnifiedTraderAgent that manages the ENTIRE portfolio (existing positions + new opportunities) instead of just day trading with 25% capital.

CONTEXT:
- Current bot only monitors 9 watchlist stocks with 25% capital
- New bot should monitor existing positions + watchlist stocks (unified)
- Should use 100% of capital by default (allocation=1.0)
- Should allow overnight holds (not forced same-day exits)
- Should respect PDT rules using PDTTracker

CHANGES REQUIRED:

1. Rename class:
   ```python
   class UnifiedTraderAgent(BaseAgent):  # was IntradayTraderAgent
   ```

2. Modify monitoring scope:
   ```python
   def get_stocks_to_monitor(self):
       """Combine existing holdings + watchlist"""
       holdings = [p.contract.symbol for p in self.ib.positions()]
       watchlist = load_json('market_opportunities.json')
       return list(set(holdings + watchlist))
   ```

3. Update capital allocation (use 100% by default):
   ```python
   def __init__(self, ib, allocation=1.0):  # Changed from 0.25
       self.allocation = allocation
       self.max_positions = 7
   
   def calculate_position_size(self):
       available = self.get_available_cash()
       current_positions = len(self.ib.positions())
       open_slots = self.max_positions - current_positions
       return available / max(open_slots, 1)
   ```

4. Modify exit logic (allow overnight holds):
   ```python
   def should_exit_position(self, ticker, price, vwap, rsi, holding_days):
       # Only exit on technical breakdown, not forced same-day
       if price < vwap and rsi < 40:
           return True, "Confirmed weakness"
       if rsi > 75:
           return True, "Extremely overbought"
       if holding_days > 3:
           return True, "Max hold period"
       return False, "Momentum intact"
   ```

5. Add PDT awareness:
   ```python
   def execute_exit(self, ticker):
       position = self.get_position(ticker)
       if position.buy_date == datetime.now().date():
           if not self.pdt_tracker.can_day_trade():
               logger.warning(f"Holding {ticker} overnight - PDT limit")
               return False
       self.place_sell_order(ticker)
       return True
   ```

6. Update logging:
   - "Unified Trading Agent" (not "Intraday Trader")
   - Log: "Monitoring X positions + Y opportunities = Z stocks"
   - Log: "Position size: $X per stock (Y slots available)"

7. Integration:
   - day_trader.py: run_unified_trading() instead of run_intraday_trading()
   - Command line: --allocation 1.0 (default 100%)

Please refactor the agent following this spec. Keep all existing technical analysis logic (VWAP, RSI, ATR) unchanged. Focus on scope expansion (monitor all) and exit logic flexibility (allow overnight).

Create test_unified_trader.py to validate:
- Monitors existing + watchlist
- Position sizing correct
- PDT tracking works
- Overnight holds allowed
```

---

### **Prompt 4: Flask Dashboard**

```
I need you to create a Flask web dashboard to monitor the trading bot from my phone while away from my PC.

REQUIREMENTS:

1. Dashboard features:
   - Live terminal output (last 500 lines, auto-scroll)
   - Account summary (net liquidation, cash, day's P&L)
   - Active positions table (ticker, qty, entry, current, P&L)
   - Trade history log (all trades with timestamps)
   - Performance charts (P&L over time, position allocation pie chart)
   - System status (bot state, IBKR connection, market status)

2. Technology:
   - Flask + Flask-SocketIO (real-time updates)
   - Chart.js for visualizations
   - Responsive CSS (mobile-friendly)
   - SQLite for trade history storage

3. File structure:
   ```
   /monitoring_dashboard/
   ├── app.py                 # Flask app
   ├── static/
   │   ├── css/dashboard.css
   │   └── js/dashboard.js    # WebSocket client, charts
   ├── templates/
   │   └── index.html         # Main dashboard
   └── data/
       └── trades.db          # SQLite database
   ```

4. API endpoints:
   ```python
   GET  /                      # Dashboard HTML
   GET  /api/status            # System status JSON
   GET  /api/positions         # Current positions JSON
   GET  /api/account           # Account summary JSON
   GET  /api/trades            # Trade history JSON
   GET  /api/logs              # Latest log lines JSON
   WebSocket /ws               # Real-time updates
   ```

5. Data sources:
   - Logs: Read from day_trader logs directory
   - Positions: Query IBKR API
   - Account: Query IBKR API
   - Trades: Read from trades.db (created by PDTTracker)

6. Design:
   - Dark theme (easy on eyes)
   - Mobile-first responsive design
   - Color-coded logs (INFO=white, WARNING=yellow, ERROR=red)
   - Real-time updates via WebSocket (no page refresh needed)

7. Access:
   - Run on port 5000
   - Access from phone: http://192.168.x.x:5000 (local network)
   - Include instructions for remote access via ngrok

Please create a minimal but functional dashboard. Focus on core features first (status, positions, logs). Charts can be added later if needed.

Include:
- requirements_dashboard.txt (Flask, Flask-SocketIO, etc.)
- README_DASHBOARD.md (setup instructions)
- Example screenshots of what it should look like
```

---

### **Prompt 5: Telegram Bot**

```
I need you to create a Telegram bot for mobile notifications and remote control of the trading bot.

REQUIREMENTS:

1. Notifications (automatic):
   - Trade execution: "🟢 BUY ALEC: 3 shares @ $1.565"
   - Trade exit: "🔴 SELL HOND: 1 share @ $17.05 (+$0.10, +0.6%)"
   - Alerts: "⚠️ PDT limit: 2/3 day trades used"
   - Daily summary: "📊 End of day: 3 trades, +$45.20 (+2.4%)"

2. Commands:
   - /start - Subscribe to notifications
   - /status - Bot status & current positions
   - /positions - Detailed position breakdown
   - /pnl - Today's P&L summary
   - /trades - Last 5 trades
   - /stop - Emergency shutdown
   - /logs - Last 50 log lines

3. Implementation:
   - Use python-telegram-bot library
   - Store bot token in .env file (keep secure)
   - Only allow commands from authorized chat_id
   - Integrate into day_trading_agents.py (send notifications on trades)

4. Setup process:
   - Create bot via BotFather → get API token
   - User sends /start to bot → bot saves chat_id
   - Bot sends notifications to saved chat_id

5. Security:
   - .env file with TELEGRAM_BOT_TOKEN
   - Whitelist authorized chat_ids
   - Require password for sensitive commands (/stop)

6. File structure:
   ```
   telegram_bot.py            # Main bot logic
   telegram_notifications.py  # Helper to send notifications
   .env                       # Bot token (don't commit)
   README_TELEGRAM.md         # Setup instructions
   ```

Please implement this with:
- telegram_bot.py: Standalone bot that can run separately
- telegram_notifications.py: Helper functions to send messages from trading bot
- Integration example: How to call from day_trading_agents.py on trade execution
- Setup guide: Step-by-step for creating bot and getting token

Include error handling: If Telegram API fails, trading should continue (don't crash).
```

---

## 🎯 SUMMARY & NEXT STEPS

### What We're Building:
1. **Dynamic Portfolio Manager**: Uses 100% of capital, actively rotates positions daily
2. **Flask Dashboard**: Web interface for monitoring from phone
3. **Telegram Bot**: Mobile notifications and remote control

### Key Improvements Over Current Bot:
- ✅ Uses full capital ($1,918 vs $4.43)
- ✅ Reviews existing positions daily (not ignored)
- ✅ Allows overnight holds (not forced same-day exits)
- ✅ PDT-aware (tracks and prevents violations)
- ✅ Unified strategy (no arbitrary "day trade" vs "hold" distinction)
- ✅ Remote monitoring (dashboard + Telegram)

### Implementation Order:
1. **Today**: Let bot finish, check current positions
2. **Tomorrow**: Implement core portfolio manager (Phase 1.8, PDT tracker, unified agent)
3. **Day After**: Build monitoring dashboard + Telegram bot
4. **Launch**: Deploy unified portfolio manager in paper trading mode

### Success Criteria:
- [ ] Bot manages 100% of capital efficiently
- [ ] No PDT violations
- [ ] Can monitor from phone via dashboard or Telegram
- [ ] Portfolio Review correctly identifies weak positions to rotate out
- [ ] Positive returns over 1 month (any amount = success for paper trading)

---

**Ready to implement when bot finishes today's session!** 🚀
