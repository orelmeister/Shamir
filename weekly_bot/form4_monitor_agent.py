"""
Form 4 Position Monitoring Agent
Autonomous daily monitoring with LLM-based hold/sell decisions

Run daily at 5:00 PM via Task Scheduler to:
1. Load active positions from database
2. Check each position independently (price, news, insider activity)
3. Ask LLM: HOLD / SELL / EXTEND?
4. Execute exits via IBKR
5. Generate daily monitoring report
"""

import os
import sqlite3
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

# IBKR imports
from ib_insync import IB, Stock, MarketOrder, util

# LangChain imports
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'weekly_bot/logs/monitor_agent_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API Keys
FMP_API_KEY = os.getenv("FMP_API_KEY", "Q0MEUK8wi0TxCWR036LRxP8jSRdxZbhg")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# IBKR Connection Parameters
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001  # Live trading
IBKR_CLIENT_ID = 11  # Unique client ID for monitor agent

# Database path
DATABASE_PATH = Path("trading_history.db")


class Form4MonitorAgent:
    """Autonomous monitoring agent for Form 4 positions"""
    
    def __init__(self):
        self.output_dir = Path("weekly_bot/form4_reports/monitoring")
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Initialize IBKR connection
        self.ib = None
        self.ibkr_connected = False
        
        # Initialize LLM (Try DeepSeek first, then Gemini)
        self.llm = None
        self.llm_available = False
        
        # Try DeepSeek Reasoner first
        if DEEPSEEK_API_KEY:
            try:
                self.llm = ChatDeepSeek(
                    model="deepseek-reasoner",
                    temperature=0.1
                )
                self.llm_available = True
                logger.info("✓ Initialized DeepSeek Reasoner")
            except Exception as e:
                logger.warning(f"DeepSeek initialization failed: {e}")
        
        # Fallback to Gemini 2.5 Pro
        if not self.llm and GOOGLE_API_KEY:
            try:
                self.llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-pro",
                    temperature=0.1
                )
                self.llm_available = True
                logger.info("✓ Initialized Gemini 2.5 Pro")
            except Exception as e:
                logger.warning(f"Gemini initialization failed: {e}")
        
        if not self.llm:
            logger.error("❌ NO LLM AVAILABLE - Cannot make intelligent hold/sell decisions!")
            raise RuntimeError("LLM required for monitoring agent. Please set DEEPSEEK_API_KEY or GOOGLE_API_KEY")
    
    def connect_to_ibkr(self) -> bool:
        """Connect to IBKR for order execution"""
        try:
            self.ib = IB()
            logger.info(f"🔌 Connecting to IBKR at {IBKR_HOST}:{IBKR_PORT}...")
            
            # Use run() for Python 3.12+ compatibility
            util.run(self.ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID))
            
            # Request delayed market data (free)
            self.ib.reqMarketDataType(3)
            
            self.ibkr_connected = True
            logger.info("✅ Connected to IBKR successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to IBKR: {e}")
            self.ibkr_connected = False
            return False
    
    def disconnect_from_ibkr(self):
        """Disconnect from IBKR"""
        if self.ib and self.ibkr_connected:
            try:
                self.ib.disconnect()
                logger.info("🔌 Disconnected from IBKR")
            except Exception as e:
                logger.warning(f"Error disconnecting from IBKR: {e}")
    
    def load_active_positions(self) -> List[Dict]:
        """Load all ACTIVE positions from database"""
        if not DATABASE_PATH.exists():
            logger.warning(f"Database not found: {DATABASE_PATH}")
            return []
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='form4_positions'
            """)
            
            if not cursor.fetchone():
                logger.warning("form4_positions table does not exist")
                conn.close()
                return []
            
            # Fetch active positions
            cursor.execute("""
                SELECT id, symbol, entry_date, entry_price, shares, 
                       hold_period_days, current_price, days_held, 
                       unrealized_pnl, llm_reasoning, last_check_date,
                       analysis_confidence, analysis_bull_case, analysis_bear_case
                FROM form4_positions 
                WHERE status = 'ACTIVE'
                ORDER BY entry_date DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            positions = []
            for row in rows:
                positions.append({
                    'id': row[0],
                    'symbol': row[1],
                    'entry_date': row[2],
                    'entry_price': row[3],
                    'shares': row[4],
                    'hold_period_days': row[5],
                    'current_price': row[6],
                    'days_held': row[7],
                    'unrealized_pnl': row[8],
                    'llm_reasoning': row[9],
                    'last_check_date': row[10],
                    'analysis_confidence': row[11],
                    'analysis_bull_case': row[12],
                    'analysis_bear_case': row[13]
                })
            
            logger.info(f"📊 Loaded {len(positions)} active positions")
            return positions
            
        except Exception as e:
            logger.error(f"Error loading positions: {e}")
            return []
    
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current price from FMP"""
        url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}"
        params = {"apikey": FMP_API_KEY}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0].get('price')
        except Exception as e:
            logger.warning(f"Failed to fetch price for {symbol}: {e}")
        
        return None
    
    def fetch_recent_news(self, symbol: str, days: int = 7) -> List[Dict]:
        """Fetch recent news for symbol"""
        url = f"https://financialmodelingprep.com/api/v3/stock_news"
        params = {
            "tickers": symbol,
            "limit": 5,
            "apikey": FMP_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()[:3]  # Top 3 news items
        except Exception as e:
            logger.warning(f"Failed to fetch news for {symbol}: {e}")
        
        return []
    
    def fetch_new_insider_activity(self, symbol: str, since_date: str) -> List[Dict]:
        """Fetch any new insider activity since entry date"""
        url = "https://financialmodelingprep.com/api/v4/insider-trading"
        params = {"apikey": FMP_API_KEY, "page": 0}
        
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                all_transactions = response.json()
                
                # Filter for this symbol and dates after entry
                since_dt = datetime.strptime(since_date, '%Y-%m-%d')
                new_activity = [
                    t for t in all_transactions
                    if t.get('symbol') == symbol and
                       datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') > since_dt
                ]
                
                return new_activity[:5]  # Max 5 new transactions
        except Exception as e:
            logger.warning(f"Failed to fetch insider activity for {symbol}: {e}")
        
        return []
    
    def check_position(self, position: Dict) -> Dict:
        """
        Check single position and make hold/sell/extend decision
        Returns: Dict with action, reasoning, new_hold_period
        """
        symbol = position['symbol']
        entry_date = datetime.strptime(position['entry_date'], '%Y-%m-%d')
        days_held = (datetime.now() - entry_date).days
        
        logger.info(f"🔍 Checking {symbol} (held {days_held}/{position['hold_period_days']} days)...")
        
        # Fetch current market data
        current_price = self.fetch_current_price(symbol)
        if not current_price:
            logger.warning(f"  Could not fetch current price for {symbol}")
            return {
                'action': 'HOLD',
                'reasoning': 'Unable to fetch current price, defaulting to HOLD',
                'new_hold_period': None
            }
        
        # Calculate P&L
        entry_price = position['entry_price']
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        unrealized_pnl = (current_price - entry_price) * position['shares']
        
        # Fetch recent news and insider activity
        news = self.fetch_recent_news(symbol, days=7)
        new_insiders = self.fetch_new_insider_activity(symbol, position['entry_date'])
        
        # Build context for LLM
        context = self._build_llm_context(
            position, current_price, pnl_pct, unrealized_pnl, days_held, news, new_insiders
        )
        
        # Ask LLM for decision
        decision = self.llm_decision(context, symbol)
        
        # Update database with current info
        self._update_position_check(
            position['id'], current_price, days_held, unrealized_pnl, decision['reasoning']
        )
        
        return decision
    
    def _build_llm_context(self, position: Dict, current_price: float, pnl_pct: float,
                           unrealized_pnl: float, days_held: int, news: List[Dict],
                           new_insiders: List[Dict]) -> str:
        """Build context string for LLM decision"""
        symbol = position['symbol']
        
        # Format news
        news_text = "No recent news" if not news else "\n".join([
            f"  - {item.get('title', 'N/A')}" for item in news
        ])
        
        # Format new insider activity
        if new_insiders:
            insider_text = f"{len(new_insiders)} new insider transactions since entry:\n"
            for txn in new_insiders:
                disposition = "BUY" if txn.get('acquistionOrDisposition') == 'A' else "SELL"
                shares = txn.get('securitiesTransacted', 0)
                role = txn.get('typeOfOwner', 'Unknown')
                insider_text += f"  - {disposition} {shares:,} shares by {role}\n"
        else:
            insider_text = "No new insider activity"
        
        context = f"""
POSITION: {symbol}
Entry Date: {position['entry_date']}
Entry Price: ${position['entry_price']:.2f}
Current Price: ${current_price:.2f}
P&L: {pnl_pct:+.2f}% (${unrealized_pnl:+.2f})
Days Held: {days_held} / {position['hold_period_days']} recommended

SHARES: {position['shares']}
ORIGINAL CONFIDENCE: {position.get('analysis_confidence', 'N/A')}%

ORIGINAL ANALYSIS:
Bull Case: {position.get('analysis_bull_case', 'N/A')}
Bear Case: {position.get('analysis_bear_case', 'N/A')}

NEW INSIDER ACTIVITY:
{insider_text}

RECENT NEWS (Last 7 days):
{news_text}
"""
        return context
    
    def llm_decision(self, context: str, symbol: str) -> Dict:
        """
        Ask LLM for hold/sell/extend decision
        Returns: Dict with action, reasoning, new_hold_period
        """
        system_prompt = """You are an expert position manager for insider trading strategies.

Your job: Decide whether to HOLD, SELL, or EXTEND each position based on:
1. Original hold period vs days held
2. P&L performance
3. New insider activity (more buying = bullish, selling = bearish)
4. Recent news (positive/negative catalysts)
5. Original bull/bear case validity

DECISION RULES:
- HOLD: Default if within hold period and no major changes
- SELL: If target reached, bad news, or insider selling
- EXTEND: If new positive developments warrant longer hold

Return ONLY valid JSON:
{
    "action": "HOLD" or "SELL" or "EXTEND",
    "reasoning": "2-3 sentence explanation",
    "new_hold_period": null or integer (days to extend)
}"""
        
        user_prompt = f"""
Analyze this position and decide: HOLD, SELL, or EXTEND?

{context}

Return JSON with action, reasoning, and new_hold_period (if extending).
"""
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            content = response.content
            
            # Extract JSON from response
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            decision = json.loads(content)
            
            # Validate action
            if decision.get('action') not in ['HOLD', 'SELL', 'EXTEND']:
                logger.warning(f"Invalid action from LLM: {decision.get('action')}, defaulting to HOLD")
                decision['action'] = 'HOLD'
            
            return decision
            
        except Exception as e:
            logger.error(f"Error getting LLM decision for {symbol}: {e}")
            return {
                'action': 'HOLD',
                'reasoning': f'Error in LLM analysis, defaulting to HOLD: {str(e)}',
                'new_hold_period': None
            }
    
    def execute_exit(self, position: Dict, reasoning: str) -> bool:
        """Execute sell order via IBKR"""
        symbol = position['symbol']
        shares = position['shares']
        
        logger.info(f"💰 EXECUTING SELL: {symbol} ({shares} shares)")
        
        if not self.ibkr_connected:
            logger.error("Cannot execute - IBKR not connected")
            return False
        
        try:
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Create market order
            order = MarketOrder('SELL', shares)
            order.tif = 'IOC'  # Immediate or Cancel
            order.outsideRth = True  # Allow after-hours
            
            # Place order
            trade = self.ib.placeOrder(contract, order)
            
            # Wait for fill (up to 10 seconds)
            for _ in range(10):
                self.ib.sleep(1)
                if trade.isDone():
                    break
            
            if trade.isDone() and trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                logger.info(f"  ✅ FILLED at ${fill_price:.2f}")
                
                # Update database
                self._close_position(
                    position['id'], fill_price, reasoning
                )
                
                return True
            else:
                logger.error(f"  ❌ Order not filled: {trade.orderStatus.status}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing sell order for {symbol}: {e}")
            return False
    
    def _update_position_check(self, position_id: int, current_price: float,
                               days_held: int, unrealized_pnl: float, llm_reasoning: str):
        """Update position with current check data"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE form4_positions 
                SET current_price = ?,
                    days_held = ?,
                    unrealized_pnl = ?,
                    llm_reasoning = ?,
                    last_check_date = ?
                WHERE id = ?
            """, (current_price, days_held, unrealized_pnl, llm_reasoning, 
                  datetime.now().strftime('%Y-%m-%d'), position_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating position check: {e}")
    
    def _extend_hold_period(self, position_id: int, new_hold_period: int):
        """Extend hold period for a position"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE form4_positions 
                SET hold_period_days = ?
                WHERE id = ?
            """, (new_hold_period, position_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"  📅 Hold period extended to {new_hold_period} days")
            
        except Exception as e:
            logger.error(f"Error extending hold period: {e}")
    
    def _close_position(self, position_id: int, exit_price: float, exit_reason: str):
        """Mark position as CLOSED in database"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE form4_positions 
                SET status = 'CLOSED',
                    exit_date = ?,
                    exit_price = ?,
                    exit_reason = ?
                WHERE id = ?
            """, (datetime.now().strftime('%Y-%m-%d'), exit_price, exit_reason, position_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"  ✅ Position marked CLOSED")
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
    
    def generate_daily_report(self, decisions: List[Dict]):
        """Generate daily monitoring report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"daily_monitoring_{timestamp}.json"
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'positions_checked': len(decisions),
            'actions': {
                'HOLD': sum(1 for d in decisions if d['decision']['action'] == 'HOLD'),
                'SELL': sum(1 for d in decisions if d['decision']['action'] == 'SELL'),
                'EXTEND': sum(1 for d in decisions if d['decision']['action'] == 'EXTEND')
            },
            'details': decisions
        }
        
        # Save JSON report
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📄 Report saved: {report_path}")
        
        # Print summary
        print("\n" + "="*80)
        print("DAILY MONITORING REPORT")
        print("="*80)
        print(f"Timestamp: {report['timestamp']}")
        print(f"Positions Checked: {report['positions_checked']}")
        print(f"\nActions:")
        print(f"  HOLD: {report['actions']['HOLD']}")
        print(f"  SELL: {report['actions']['SELL']}")
        print(f"  EXTEND: {report['actions']['EXTEND']}")
        print("="*80 + "\n")
    
    def run(self):
        """Main daily monitoring loop"""
        print("\n" + "="*80)
        print("FORM 4 MONITORING AGENT - DAILY CHECK")
        print("="*80)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
        
        # Connect to IBKR
        if not self.connect_to_ibkr():
            logger.error("❌ Cannot proceed without IBKR connection")
            return
        
        try:
            # Load active positions
            positions = self.load_active_positions()
            
            if not positions:
                logger.info("✓ No active positions to monitor")
                print("\n[+] No active positions to monitor\n")
                return
            
            print(f"[+] Monitoring {len(positions)} active positions\n")
            
            # Check each position
            decisions = []
            for position in positions:
                symbol = position['symbol']
                
                print(f"\n{'='*80}")
                print(f"CHECKING: {symbol}")
                print(f"{'='*80}")
                
                # Get decision
                decision = self.check_position(position)
                
                # Execute action
                if decision['action'] == 'SELL':
                    print(f"\n🚨 DECISION: SELL {symbol}")
                    print(f"Reasoning: {decision['reasoning']}\n")
                    success = self.execute_exit(position, decision['reasoning'])
                    decision['executed'] = success
                    
                elif decision['action'] == 'EXTEND':
                    print(f"\n📅 DECISION: EXTEND {symbol}")
                    print(f"Reasoning: {decision['reasoning']}")
                    print(f"New Hold Period: {decision['new_hold_period']} days\n")
                    self._extend_hold_period(position['id'], decision['new_hold_period'])
                    decision['executed'] = True
                    
                else:  # HOLD
                    print(f"\n✋ DECISION: HOLD {symbol}")
                    print(f"Reasoning: {decision['reasoning']}\n")
                    decision['executed'] = True
                
                decisions.append({
                    'symbol': symbol,
                    'position': position,
                    'decision': decision
                })
            
            # Generate daily report
            self.generate_daily_report(decisions)
            
            print("\n[+] Daily monitoring complete\n")
            
        finally:
            # Always disconnect
            self.disconnect_from_ibkr()


def main():
    """Main entry point"""
    try:
        agent = Form4MonitorAgent()
        agent.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"\n❌ FATAL ERROR: {e}\n")
        raise


if __name__ == "__main__":
    main()
