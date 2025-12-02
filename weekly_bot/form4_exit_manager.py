"""
Form 4 Position Exit Manager
Monitors positions from Form 4 strategy and makes intelligent exit decisions

Strategy:
- Runs daily (or multiple times per day) to monitor open positions
- Tracks P&L, days held, and new insider activity
- Uses multi-agent LLM debate (DeepSeek + Gemini) for exit decisions
- Executes sells automatically via IBKR when consensus reached
- Logs all decisions for accountability

Exit Triggers:
1. Time-based: Hold period expired (recommended 7-21 days)
2. Profit target: Up +15-20% → LLM re-analyzes
3. Stop loss: Down -8-10% → immediate exit consideration
4. Signal reversal: Insiders started selling → red flag
5. Manual override: User can force exit

Run Schedule:
- Daily after market close (4:30 PM ET) - recommended
- OR 2-3x during market hours for active management
- OR continuous monitoring (adjust CHECK_INTERVAL)
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# IBKR imports
from ib_insync import IB, Stock, MarketOrder, LimitOrder, util

# LangChain imports
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# Autonomous system imports
from observability import get_database, get_tracer

# Setup logging (UTF-8 for Windows console compatibility)
import sys
if sys.platform == 'win32':
    # Fix Windows console encoding
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/form4_exit_manager_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API Keys
FMP_API_KEY = os.getenv("FMP_API_KEY", "Q0MEUK8wi0TxCWR036LRxP8jSRdxZbhg")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Exit Parameters
PROFIT_TARGET_PCT = 15.0  # Review trigger at +15% (not automatic sell)
STOP_LOSS_PCT = -8.0  # Stop loss at -8% (capital protection)
FORCE_EXIT_DAYS = 90  # Extended hold review at 90 days (informational, not forced exit)
CHECK_INTERVAL = 3600  # Check every hour (3600 seconds)

# IBKR Connection
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001
IBKR_CLIENT_ID = 11  # Unique client ID for exit manager


class Form4ExitManager:
    """Monitor and manage exits for Form 4 positions + Autonomous Learning"""
    
    def __init__(self):
        self.output_dir = Path("weekly_bot/form4_reports")
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        self.exit_log_dir = Path("weekly_bot/form4_reports/exit_logs")
        self.exit_log_dir.mkdir(exist_ok=True, parents=True)
        
        # Initialize IBKR
        self.ib = None
        self.ibkr_connected = False
        
        # Autonomous system components
        self.agent_name = "form4_strategy"  # Same agent as entry bot
        # Use absolute path for database (parent directory of weekly_bot)
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(parent_dir, "databases", "trading_history.db")
        self.db = get_database(db_path)
        self.tracer = get_tracer()
        
        # Initialize both LLMs for multi-agent debate
        self.deepseek_llm = None
        self.gemini_llm = None
        self.multi_agent_available = False
        
        self._initialize_llms()
    
    def _initialize_llms(self):
        """Initialize DeepSeek and Gemini for multi-agent debate"""
        if DEEPSEEK_API_KEY:
            try:
                self.deepseek_llm = ChatDeepSeek(
                    model="deepseek-reasoner",
                    temperature=0.1
                )
                logger.info("[OK] DeepSeek Reasoner initialized")
                print("[+] DEEPSEEK AGENT: Ready for exit analysis")
            except Exception as e:
                logger.warning(f"DeepSeek initialization failed: {e}")
        
        if GOOGLE_API_KEY:
            try:
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model="gemini-3-pro-preview",
                    temperature=0.1
                )
                logger.info("[OK] Gemini 3 Pro initialized")
                print("[+] GEMINI AGENT: Ready for exit analysis")
            except Exception as e:
                logger.warning(f"Gemini initialization failed: {e}")
        
        if self.deepseek_llm and self.gemini_llm:
            self.multi_agent_available = True
            print("[+] MULTI-AGENT DEBATE: ENABLED for exit decisions\n")
        else:
            logger.warning("[WARN] Multi-agent debate not available - using single LLM or rule-based")
            print("[!] WARNING: Limited exit analysis without both LLMs\n")
    
    def connect_to_ibkr(self) -> bool:
        """Connect to IBKR for position tracking and order execution"""
        try:
            self.ib = IB()
            logger.info(f"[CONNECT] Connecting to IBKR at {IBKR_HOST}:{IBKR_PORT}...")
            
            util.run(self.ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID))
            self.ib.reqMarketDataType(3)  # Delayed data
            
            self.ibkr_connected = True
            logger.info("[SUCCESS] Connected to IBKR")
            print("[+] IBKR CONNECTED: Monitoring positions\n")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] IBKR connection failed: {e}")
            print(f"[ERROR] Cannot monitor positions without IBKR connection")
            self.ibkr_connected = False
            return False
    
    def disconnect_from_ibkr(self):
        """Disconnect from IBKR"""
        if self.ib and self.ibkr_connected:
            try:
                self.ib.disconnect()
                logger.info("[DISCONNECT] Disconnected from IBKR")
            except Exception as e:
                logger.warning(f"Error disconnecting: {e}")
    
    def load_approved_positions(self) -> Dict:
        """Load most recent approved positions file"""
        try:
            # Find most recent approved_positions file
            position_files = sorted(
                self.output_dir.glob("approved_positions_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            if not position_files:
                logger.warning("No approved positions file found")
                return {}
            
            latest_file = position_files[0]
            logger.info(f"[LOAD] Loading positions from {latest_file.name}")
            
            with open(latest_file, 'r') as f:
                return json.load(f)
        
        except Exception as e:
            logger.error(f"Failed to load approved positions: {e}")
            return {}
    
    def get_current_positions(self) -> List[Dict]:
        """
        Get current positions from IBKR and match with approved positions
        Returns list of positions with current P&L and status
        
        IMPROVED: Evaluates ALL IBKR positions, using tracking data when available
        but fallback to IBKR avgCost if position not tracked.
        """
        if not self.ibkr_connected:
            logger.error("Not connected to IBKR")
            return []
        
        # Get ALL portfolio positions from IBKR
        portfolio = self.ib.portfolio()
        
        if not portfolio:
            logger.info("No positions in IBKR portfolio")
            return []
        
        # Load approved positions file for additional context (optional)
        approved_data = self.load_approved_positions()
        approved_map = {}
        if approved_data:
            for approved_pos in approved_data.get('approved_positions', []):
                approved_map[approved_pos['symbol']] = approved_pos
        
        # Load database tracking data (optional)
        db_positions = {}
        try:
            from observability import get_database
            db = get_database()
            active_positions = db.get_active_positions(agent_name=self.agent_name)
            for pos in active_positions:
                db_positions[pos['symbol']] = pos
        except Exception as e:
            logger.debug(f"Database positions unavailable: {e}")
        
        current_positions = []
        
        # Evaluate EVERY position in IBKR account
        for ibkr_position in portfolio:
            symbol = ibkr_position.contract.symbol
            current_price = ibkr_position.marketPrice
            quantity = ibkr_position.position
            
            # Skip if quantity is zero
            if quantity == 0:
                continue
            
            # Determine entry price (priority: database > approved file > IBKR avgCost)
            entry_price = None
            entry_date = None
            days_held = 0
            recommended_hold_days = 14  # Default
            original_analysis = {}
            
            # Try database first (most reliable)
            if symbol in db_positions:
                entry_price = db_positions[symbol].get('entry_price')
                # Column is called 'entry_timestamp' not 'entry_date'
                entry_date_str = db_positions[symbol].get('entry_timestamp') or db_positions[symbol].get('entry_date')
                if entry_date_str:
                    try:
                        entry_date = datetime.fromisoformat(entry_date_str.replace(' ', 'T'))
                        days_held = (datetime.now() - entry_date).days
                        logger.info(f"[DB] {symbol}: Entry {entry_date_str} = {days_held} days held")
                    except Exception as e:
                        logger.warning(f"[DB] {symbol}: Failed to parse entry_timestamp '{entry_date_str}': {e}")
            
            # Try approved positions file (Form4 strategy)
            if not entry_price and symbol in approved_map:
                approved_pos = approved_map[symbol]
                execution = approved_pos.get('execution', {})
                if execution.get('status') == 'FILLED':
                    entry_price = execution.get('fill_price')
                    recommended_hold_days = approved_pos.get('analysis', {}).get('hold_period_days', 14)
                    original_analysis = approved_pos.get('analysis', {})
                    
                    # Parse entry date
                    entry_timestamp = approved_data.get('approved_at') or execution.get('timestamp', datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
                    try:
                        entry_date = datetime.strptime(entry_timestamp.split('.')[0].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
                        days_held = (datetime.now() - entry_date).days
                    except:
                        pass
            
            # Fallback to IBKR avgCost (always available)
            if not entry_price:
                entry_price = ibkr_position.averageCost
                logger.info(f"[IBKR] {symbol}: Using IBKR avgCost ${entry_price:.2f} (no tracking data)")
            
            # Calculate P&L
            pnl_dollars = (current_price - entry_price) * quantity
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            
            current_positions.append({
                'symbol': symbol,
                'quantity': quantity,
                'entry_price': entry_price,
                'current_price': current_price,
                'pnl_dollars': pnl_dollars,
                'pnl_pct': pnl_pct,
                'days_held': days_held,
                'entry_date': entry_date.strftime('%Y-%m-%d') if entry_date else 'UNKNOWN',
                'original_analysis': original_analysis,
                'recommended_hold_days': recommended_hold_days,
                'market_value': current_price * quantity,
                'cost_basis': entry_price * quantity
            })
        
        return current_positions
    
    def check_for_insider_selling(self, symbol: str, days: int = 7) -> Dict:
        """
        Check if insiders have started selling (signal reversal)
        Returns: Dict with selling activity details
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            url = "https://financialmodelingprep.com/api/v4/insider-trading"
            params = {
                'symbol': symbol,
                'apikey': FMP_API_KEY,
                'page': 0
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return {'error': 'API request failed'}
            
            transactions = response.json()
            
            # Filter to recent transactions
            recent_txns = [
                t for t in transactions
                if start_date <= datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') <= end_date
            ]
            
            buys = sum(1 for t in recent_txns if t.get('acquistionOrDisposition') == 'A')
            sells = sum(1 for t in recent_txns if t.get('acquistionOrDisposition') == 'D')
            
            return {
                'total_transactions': len(recent_txns),
                'buys': buys,
                'sells': sells,
                'net_sentiment': buys - sells,
                'reversal_detected': sells > buys and sells > 0
            }
        
        except Exception as e:
            logger.warning(f"Failed to check insider activity for {symbol}: {e}")
            return {'error': str(e)}
    
    def get_recent_news(self, symbol: str, days: int = 7) -> List[Dict]:
        """Fetch recent news for symbol"""
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock_news"
            params = {
                'tickers': symbol,
                'limit': 5,
                'apikey': FMP_API_KEY
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()[:3]
        except Exception as e:
            logger.warning(f"Failed to fetch news for {symbol}: {e}")
        
        return []
    
    def multi_agent_exit_debate(self, position: Dict, insider_activity: Dict, news: List[Dict]) -> Dict:
        """
        Multi-agent debate for exit decision
        Both models analyze whether to HOLD or SELL
        
        Returns: Dict with consensus decision and reasoning
        """
        symbol = position['symbol']
        logger.info(f"[DEBATE] Multi-agent debate: Should we exit {symbol}?")
        
        system_prompt = f"""You are an expert equity analyst evaluating whether to HOLD or SELL a position.

CRITICAL GUIDELINES - FINANCIALLY INTELLIGENT EXITS ONLY:
1. CAPITAL PROTECTION: Stop loss at {STOP_LOSS_PCT}% is absolute - protects capital from further losses
2. THESIS VALIDITY: Is the original investment thesis still intact? If yes, consider holding.
3. MOMENTUM & UPSIDE: If position profitable, does momentum continue or is upside exhausted?
4. INSIDER ACTIVITY: New insider selling = thesis reversal, strong sell signal
5. NEWS IMPACT: Negative developments that break the investment case?
6. OPPORTUNITY COST: Are there SIGNIFICANTLY better opportunities that justify liquidating this winner?

PHILOSOPHY - "LET WINNERS RUN":
- Profit target (+{PROFIT_TARGET_PCT}%) is a REVIEW TRIGGER, not an automatic sell
- Only recommend SELL at profit if: (a) Momentum clearly exhausted, OR (b) Thesis deteriorating, OR (c) Superior opportunity available
- Time held is IRRELEVANT - evaluate on financial merit, not calendar days
- Holding 10 profitable positions > forcing exits to buy 4 new ones
- Default to HOLD for profitable positions unless clear financial reason to exit

SELL ONLY WHEN:
- Stop loss triggered (capital protection)
- Insider selling + thesis breakdown
- Profit taken but momentum exhausted AND better opportunity exists
- Fundamental deterioration makes continued holding risky
- Insider selling detected = Red flag
- Original thesis broken = Exit

Return JSON format:
{{
    "decision": "HOLD" or "SELL",
    "confidence": 0.0-1.0,
    "reasoning": "clear explanation of decision",
    "urgency": "LOW", "MEDIUM", or "HIGH"
}}"""
        
        # Build context
        insider_summary = ""
        if not insider_activity.get('error'):
            reversal_flag = "🚨 REVERSAL DETECTED" if insider_activity.get('reversal_detected') else "✓ No reversal"
            insider_summary = f"""
Recent Insider Activity (last 7 days):
- Buys: {insider_activity.get('buys', 0)}
- Sells: {insider_activity.get('sells', 0)}
- Net sentiment: {insider_activity.get('net_sentiment', 0)}
- {reversal_flag}
"""
        
        user_prompt = f"""Should we exit position in {symbol}?

POSITION STATUS:
- Entry Price: ${position['entry_price']:.2f}
- Current Price: ${position['current_price']:.2f}
- P&L: ${position['pnl_dollars']:.2f} ({position['pnl_pct']:+.1f}%)
- Days Held: {position['days_held']} / {position['recommended_hold_days']} recommended
- Market Value: ${position['market_value']:.2f}

TARGETS:
- Profit Target: +{PROFIT_TARGET_PCT}% (${position['entry_price'] * (1 + PROFIT_TARGET_PCT/100):.2f})
- Stop Loss: {STOP_LOSS_PCT}% (${position['entry_price'] * (1 + STOP_LOSS_PCT/100):.2f})

{insider_summary}

RECENT NEWS:
{chr(10).join([f"- {n.get('title', 'N/A')}" for n in news]) if news else "- No significant news"}

ORIGINAL ANALYSIS:
Confidence: {position['original_analysis'].get('confidence', 0):.0%}
Thesis: {position['original_analysis'].get('reasoning', 'N/A')[:200]}...

Provide your EXIT decision in JSON format."""
        
        # Round 1: Independent analysis
        print(f"\n[DEBATE] {symbol}: Round 1 - Independent Exit Analysis")
        
        deepseek_response = None
        gemini_response = None
        
        # DeepSeek Analysis
        try:
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            deepseek_raw = self.deepseek_llm.invoke(messages)
            deepseek_text = deepseek_raw.content if hasattr(deepseek_raw, 'content') else str(deepseek_raw)
            
            import re
            json_match = re.search(r'\{[^{}]*"decision"[^{}]*\}', deepseek_text, re.DOTALL)
            if json_match:
                deepseek_response = json.loads(json_match.group())
                print(f"   ✓ DeepSeek: {deepseek_response['decision']} ({deepseek_response['confidence']:.0%} confidence)")
        except Exception as e:
            logger.warning(f"DeepSeek analysis failed: {e}")
        
        # Gemini Analysis
        try:
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            gemini_raw = self.gemini_llm.invoke(messages)
            
            # Handle different response formats from Gemini
            if hasattr(gemini_raw, 'content'):
                gemini_text = gemini_raw.content
                if isinstance(gemini_text, list):
                    # Gemini 3 Pro returns list of content parts
                    gemini_text = ' '.join([str(part) if isinstance(part, str) else str(part.get('text', '')) for part in gemini_text])
            else:
                gemini_text = str(gemini_raw)
            
            json_match = re.search(r'\{[^{}]*"decision"[^{}]*\}', gemini_text, re.DOTALL)
            if json_match:
                gemini_response = json.loads(json_match.group())
                print(f"   ✓ Gemini: {gemini_response['decision']} ({gemini_response['confidence']:.0%} confidence)")
        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e}")
        
        # Handle failures
        if not deepseek_response and not gemini_response:
            logger.error("Both models failed - using rule-based decision")
            return self._rule_based_exit_decision(position, insider_activity)
        
        if not deepseek_response:
            print(f"   [!] DeepSeek failed - using Gemini only")
            return {**gemini_response, 'agreement_score': 0.5, 'analysis_type': 'SINGLE_AGENT'}
        
        if not gemini_response:
            print(f"   [!] Gemini failed - using DeepSeek only")
            return {**deepseek_response, 'agreement_score': 0.5, 'analysis_type': 'SINGLE_AGENT'}
        
        # Check for agreement
        both_agree = deepseek_response['decision'] == gemini_response['decision']
        avg_confidence = (deepseek_response['confidence'] + gemini_response['confidence']) / 2
        
        print(f"[CONSENSUS] {symbol}: {'AGREE' if both_agree else 'DISAGREE'} - {deepseek_response['decision']} vs {gemini_response['decision']}")
        
        if both_agree:
            # Strong consensus
            return {
                'decision': deepseek_response['decision'],
                'confidence': avg_confidence,
                'reasoning': f"CONSENSUS: {deepseek_response['reasoning']}",
                'urgency': deepseek_response.get('urgency', 'MEDIUM'),
                'agreement_score': 1.0,
                'deepseek_view': deepseek_response,
                'gemini_view': gemini_response,
                'analysis_type': 'MULTI_AGENT_CONSENSUS'
            }
        else:
            # Disagreement - flag for manual review
            print(f"   [!] Models disagree - flagging for manual review")
            return {
                'decision': 'HOLD',  # Conservative: hold when uncertain
                'confidence': 0.5,
                'reasoning': f"DISAGREEMENT: DeepSeek says {deepseek_response['decision']}, Gemini says {gemini_response['decision']}. Manual review recommended.",
                'urgency': 'HIGH',
                'agreement_score': 0.0,
                'requires_manual_review': True,
                'deepseek_view': deepseek_response,
                'gemini_view': gemini_response,
                'analysis_type': 'MULTI_AGENT_DISAGREE'
            }
    
    def _rule_based_exit_decision(self, position: Dict, insider_activity: Dict) -> Dict:
        """
        Fallback rule-based exit decision when LLMs unavailable
        """
        pnl_pct = position['pnl_pct']
        days_held = position['days_held']
        recommended_days = position['recommended_hold_days']
        
        # Stop loss triggered
        if pnl_pct <= STOP_LOSS_PCT:
            return {
                'decision': 'SELL',
                'confidence': 1.0,
                'reasoning': f"Stop loss triggered: {pnl_pct:.1f}% loss exceeds {STOP_LOSS_PCT}%",
                'urgency': 'HIGH',
                'analysis_type': 'RULE_BASED'
            }
        
        # Profit target reached - trigger review, don't auto-sell
        if pnl_pct >= PROFIT_TARGET_PCT:
            return {
                'decision': 'HOLD',  # Changed from SELL to HOLD - let winners run
                'confidence': 0.6,
                'reasoning': f"Profit target reached: {pnl_pct:.1f}% gain. Recommend LLM analysis to confirm if upside exhausted or better opportunities available.",
                'urgency': 'MEDIUM',
                'analysis_type': 'RULE_BASED',
                'requires_llm_review': True  # Flag for intelligent evaluation
            }
        
        # Hold period exceeded + insider selling
        if days_held > recommended_days and insider_activity.get('reversal_detected'):
            return {
                'decision': 'SELL',
                'confidence': 0.8,
                'reasoning': f"Hold period exceeded ({days_held} days) AND insider selling detected",
                'urgency': 'MEDIUM',
                'analysis_type': 'RULE_BASED'
            }
        
        # Extended hold period review (informational only, not forced exit)
        if days_held >= 90:  # Changed from 21 to 90 days - positions held on merit, not calendar
            return {
                'decision': 'HOLD',  # Changed from SELL to HOLD
                'confidence': 0.5,
                'reasoning': f"Extended hold period ({days_held} days) - recommend LLM review for thesis validity",
                'urgency': 'LOW',
                'analysis_type': 'RULE_BASED',
                'requires_llm_review': True  # Flag for manual evaluation
            }
        
        # Default: HOLD
        return {
            'decision': 'HOLD',
            'confidence': 0.6,
            'reasoning': f"Within normal parameters: {pnl_pct:+.1f}% P&L, {days_held}/{recommended_days} days held",
            'urgency': 'LOW',
            'analysis_type': 'RULE_BASED'
        }
    
    def execute_exit(self, position: Dict, decision: Dict) -> Dict:
        """
        Execute sell order for position
        Returns execution details
        """
        if not self.ibkr_connected:
            logger.error("Cannot execute exit - not connected to IBKR")
            return {'status': 'FAILED', 'reason': 'No IBKR connection'}
        
        symbol = position['symbol']
        quantity = position['quantity']
        
        try:
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Use market order for exits (ensure fill)
            order = MarketOrder('SELL', quantity)
            order.tif = 'IOC'  # Immediate or cancel
            order.outsideRth = True
            
            logger.info(f"📤 Placing SELL order: {quantity} shares of {symbol}")
            print(f"\n[EXECUTING] Selling {quantity} shares of {symbol}...")
            
            trade = self.ib.placeOrder(contract, order)
            
            # Wait for fill (up to 30 seconds)
            for i in range(30):
                self.ib.sleep(1)
                if trade.orderStatus.status in ['Filled', 'Cancelled']:
                    break
            
            if trade.orderStatus.status == 'Filled':
                fill_price = trade.orderStatus.avgFillPrice
                pnl = (fill_price - position['entry_price']) * quantity
                pnl_pct = ((fill_price - position['entry_price']) / position['entry_price']) * 100
                
                # AUTONOMOUS: Log exit trade to database
                self.db.log_trade({
                    'timestamp': datetime.now().isoformat(),
                    'symbol': symbol,
                    'action': 'SELL',
                    'quantity': quantity,
                    'price': fill_price,
                    'agent_name': self.agent_name,
                    'reason': decision.get('exit_reason', 'Exit manager decision'),
                    'profit_loss': pnl,
                    'profit_loss_pct': pnl_pct,
                    'metadata': {
                        'entry_price': position['entry_price'],
                        'days_held': position['days_held'],
                        'exit_trigger': decision.get('exit_action', 'UNKNOWN'),
                        'consensus': decision.get('consensus', 'N/A'),
                        'current_pnl_pct': position.get('current_pnl_pct', 0)
                    }
                })
                
                # AUTONOMOUS: Remove from active positions
                self.db.remove_active_position(
                    symbol=symbol,
                    exit_price=fill_price,
                    exit_reason=decision.get('exit_reason', 'Exit manager'),
                    agent_name=self.agent_name
                )
                
                logger.info(f"✅ {symbol}: FILLED {quantity} shares @ ${fill_price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)")
                print(f"   [FILLED] ${pnl:.2f} ({pnl_pct:+.1f}%) realized")
                
                return {
                    'status': 'FILLED',
                    'symbol': symbol,
                    'quantity': quantity,
                    'fill_price': fill_price,
                    'pnl_dollars': pnl,
                    'pnl_pct': pnl_pct,
                    'entry_price': position['entry_price'],
                    'days_held': position['days_held']
                }
            else:
                logger.warning(f"[WARN] {symbol}: Order not filled - status: {trade.orderStatus.status}")
                return {'status': 'NOT_FILLED', 'reason': trade.orderStatus.status}
        
        except Exception as e:
            logger.error(f"[ERROR] Failed to execute exit for {symbol}: {e}")
            return {'status': 'ERROR', 'reason': str(e)}
    
    def save_exit_log(self, position: Dict, decision: Dict, execution: Dict):
        """Save exit decision and execution details"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        log_data = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'position': position,
            'decision': decision,
            'execution': execution
        }
        
        log_file = self.exit_log_dir / f"exit_{position['symbol']}_{timestamp}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        logger.info(f"[LOG] Exit log saved: {log_file.name}")
    
    def run(self, dry_run: bool = False):
        """
        Main monitoring loop
        
        Args:
            dry_run: If True, analyze but don't execute trades
        """
        print("\n" + "="*80)
        print("FORM 4 EXIT MANAGER - POSITION MONITORING")
        print("="*80)
        print(f"Mode: {'DRY RUN (No Execution)' if dry_run else 'LIVE TRADING'}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
        
        # Connect to IBKR
        if not self.connect_to_ibkr():
            logger.error("Cannot proceed without IBKR connection")
            return
        
        try:
            # Get current positions
            positions = self.get_current_positions()
            
            if not positions:
                logger.info("No positions to monitor")
                print("[INFO] No open positions found")
                return
            
            logger.info(f"[MONITOR] {len(positions)} position(s)")
            print(f"\n[MONITORING] {len(positions)} position(s)\n")
            
            exit_decisions = []
            
            for position in positions:
                symbol = position['symbol']
                print("="*80)
                print(f"ANALYZING: {symbol}")
                print("="*80)
                print(f"Entry: ${position['entry_price']:.2f} | Current: ${position['current_price']:.2f}")
                print(f"P&L: ${position['pnl_dollars']:.2f} ({position['pnl_pct']:+.1f}%)")
                print(f"Days Held: {position['days_held']} / {position['recommended_hold_days']}")
                print()
                
                # Check for insider selling
                insider_activity = self.check_for_insider_selling(symbol, days=7)
                
                # Get recent news
                news = self.get_recent_news(symbol, days=7)
                
                # Multi-agent debate for exit decision
                if self.multi_agent_available:
                    decision = self.multi_agent_exit_debate(position, insider_activity, news)
                else:
                    decision = self._rule_based_exit_decision(position, insider_activity)
                
                print(f"\n[DECISION] {decision['decision']} (confidence: {decision['confidence']:.0%})")
                print(f"[REASONING] {decision['reasoning']}")
                print(f"[URGENCY] {decision.get('urgency', 'MEDIUM')}")
                
                if decision.get('requires_manual_review'):
                    print(f"[ALERT] [!] MANUAL REVIEW REQUIRED - Models disagree!")
                
                # Execute if SELL decision
                if decision['decision'] == 'SELL':
                    if dry_run:
                        print(f"\n[DRY RUN] Would sell {position['quantity']} shares of {symbol}")
                        execution = {'status': 'DRY_RUN'}
                    else:
                        print(f"\n[EXECUTING] Selling position...")
                        execution = self.execute_exit(position, decision)
                else:
                    print(f"\n[HOLDING] Position maintained")
                    execution = {'status': 'HOLD'}
                
                # Save decision log
                self.save_exit_log(position, decision, execution)
                
                exit_decisions.append({
                    'position': position,
                    'decision': decision,
                    'execution': execution
                })
                
                print()
            
            # Summary
            print("="*80)
            print("EXIT MANAGER SUMMARY")
            print("="*80)
            
            sell_count = sum(1 for d in exit_decisions if d['decision']['decision'] == 'SELL')
            hold_count = len(exit_decisions) - sell_count
            executed_count = sum(1 for d in exit_decisions if d['execution']['status'] == 'FILLED')
            
            print(f"Positions Analyzed: {len(exit_decisions)}")
            print(f"Sell Decisions: {sell_count}")
            print(f"Hold Decisions: {hold_count}")
            
            if not dry_run:
                print(f"Orders Executed: {executed_count}")
            
            # Show P&L summary
            total_realized_pnl = sum(
                d['execution'].get('pnl_dollars', 0) 
                for d in exit_decisions 
                if d['execution']['status'] == 'FILLED'
            )
            
            if total_realized_pnl != 0:
                print(f"\nTotal Realized P&L: ${total_realized_pnl:.2f}")
            
            print("="*80 + "\n")
            
        finally:
            self.disconnect_from_ibkr()


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Form 4 Exit Manager")
    parser.add_argument('--dry-run', action='store_true', help="Analyze but don't execute trades")
    parser.add_argument('--continuous', action='store_true', help="Run continuously (monitor loop)")
    
    args = parser.parse_args()
    
    manager = Form4ExitManager()
    
    if args.continuous:
        logger.info("Starting continuous monitoring mode...")
        print("[MODE] Continuous monitoring - Press Ctrl+C to stop\n")
        
        import time
        try:
            while True:
                manager.run(dry_run=args.dry_run)
                logger.info(f"Waiting {CHECK_INTERVAL} seconds until next check...")
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            print("\n[STOPPED] Monitoring terminated")
    else:
        # Single run
        manager.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
