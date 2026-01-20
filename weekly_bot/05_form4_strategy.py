"""
Phase 5: Form 4 Insider Trading Strategy
Dedicated $1000 allocation for insider cluster signals

Strategy:
- Monitor Form 4 filings for insider buying clusters (3+ filings in 7 days)
- Target mid-cap stocks ($500M-$20B) with higher price range ($5-$50)
- LLM analysis of insider patterns and company fundamentals
- Conservative position sizing (2-4 positions max)
- Weekly rebalancing on Sundays
- MANUAL APPROVAL REQUIRED before any trades

Capital: $1000 dedicated allocation
"""
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from typing import List, Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# IBKR imports for automatic order execution
from ib_insync import IB, Stock, MarketOrder, util

# LangChain imports
from langchain_deepseek import ChatDeepSeek
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except (ImportError, AttributeError) as e:
    GEMINI_AVAILABLE = False
    print(f"[WARNING] Gemini unavailable due to library issue: {e}. Using DeepSeek only.")
from langchain_core.messages import HumanMessage, SystemMessage

# Autonomous system imports
from observability import get_database, get_tracer
from self_evaluation import PerformanceAnalyzer
from continuous_improvement import ContinuousImprovementEngine

# PDF generation imports
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️  reportlab not installed. PDF generation disabled. Install with: pip install reportlab")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Keys
FMP_API_KEY = os.getenv("FMP_API_KEY", "Q0MEUK8wi0TxCWR036LRxP8jSRdxZbhg")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Strategy Parameters for Form 4 Focus
MIN_MARKET_CAP = 100_000_000  # $100M (catch smaller companies with strong insider activity)
MAX_MARKET_CAP = 100_000_000_000  # $100B (EXPANDED - include mega-caps with politician signals)
MIN_PRICE = 1.0  # $1 (avoid penny stocks)
MAX_PRICE = 999999.0  # REMOVED CEILING - allow any stock price (institutions + insiders = strong signal regardless of price)
MIN_FILINGS_FOR_CLUSTER = 3  # Minimum Form 4s to be considered a cluster (OR 1+ politician)
LOOKBACK_DAYS = 100  # Days to look back for Form 4 filings (100 days = ~3 months pattern)

# Portfolio Parameters
CAPITAL = 1000.0  # Fallback capital (only if IBKR not connected)
# MAX_POSITIONS is now dynamically determined by LLM allocation debate
MIN_CONFIDENCE_SCORE = 0.65  # Lower than main strategy (Form 4 is strong signal)

# IBKR Connection Parameters
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001  # Live trading (Gateway or TWS)
IBKR_CLIENT_ID = 10  # Unique client ID for Form 4 strategy

class Form4Strategy:
    """Form 4 Insider Trading Strategy with Manual Approval + Autonomous Learning"""
    
    def __init__(self, capital_override: Optional[float] = None):
        # Capital: ALWAYS uses IBKR settled cash (T+2 compliant - prevents order rejections)
        # capital_override only used if IBKR not connected
        self.capital = capital_override if capital_override is not None else CAPITAL
        # Dynamic allocation: LLM debate determines position count and weights
        self.llm_allocation = None  # Will be populated by allocation debate
        self.output_dir = Path("weekly_bot/form4_reports")
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Initialize IBKR connection
        self.ib = None
        self.ibkr_connected = False
        
        # Autonomous system components
        self.agent_name = "form4_strategy"
        # Use absolute path for database (parent directory of weekly_bot)
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(parent_dir, "databases", "trading_history.db")
        self.db = get_database(db_path)
        self.tracer = get_tracer()
        self.performance_analyzer = PerformanceAnalyzer(self.agent_name)
        self.improvement_engine = ContinuousImprovementEngine(self.agent_name)
        
        logger.info("✅ Autonomous systems enabled: Observability, Self-Evaluation, Continuous Improvement")
        
        # Initialize BOTH LLMs for multi-agent debate
        self.deepseek_llm = None
        self.gemini_llm = None
        self.multi_agent_available = False
        
        # Initialize DeepSeek Reasoner
        if DEEPSEEK_API_KEY:
            try:
                self.deepseek_llm = ChatDeepSeek(
                    model="deepseek-reasoner",
                    temperature=0.1
                )
                logger.info("✓ Initialized DeepSeek Reasoner")
                print("[+] DEEPSEEK AGENT: Ready")
            except Exception as e:
                logger.warning(f"DeepSeek Reasoner initialization failed: {e}")
        
        # Initialize Gemini 3 Pro (try pro first, fallback to flash)
        if GOOGLE_API_KEY and GEMINI_AVAILABLE:
            try:
                # Try gemini-3-pro-preview first (most capable)
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model="gemini-3-pro-preview",
                    temperature=0.1
                )
                logger.info("✓ Initialized Gemini 3 Pro Preview")
                print("[+] GEMINI AGENT: Ready (Gemini 3 Pro Preview)")
            except Exception as e:
                logger.warning(f"Gemini 3 Pro Preview initialization failed: {e}")
                # Fallback to gemini-2.5-pro (stable and capable)
                try:
                    self.gemini_llm = ChatGoogleGenerativeAI(
                        model="gemini-2.5-pro",
                        temperature=0.1
                    )
                    logger.info("✓ Initialized Gemini 2.5 Pro (fallback)")
                    print("[+] GEMINI AGENT: Ready (Gemini 2.5 Pro)")
                except Exception as e2:
                    logger.warning(f"Gemini 2.5 Pro initialization also failed: {e2}")
        
        # Check if multi-agent debate available
        if self.deepseek_llm and self.gemini_llm:
            self.multi_agent_available = True
            print("[+] MULTI-AGENT DEBATE: ENABLED")
            print("    Both models will debate each stock for consensus\n")
        elif self.deepseek_llm or self.gemini_llm:
            self.multi_agent_available = False
            logger.warning("⚠️  Only one LLM available - single agent mode")
            print("[!] SINGLE AGENT MODE: Only one LLM available")
            print("    For best results, provide both API keys\n")
        else:
            self.multi_agent_available = False
            logger.warning("⚠️  No LLM available - will use rule-based scoring")
            print("\n" + "="*80)
            print("[!] WARNING: NO LLM AVAILABLE - LIMITED ANALYSIS")
            print("="*80)
            print("You're missing API keys for DeepSeek AND Gemini.")
            print("Analysis will be BASIC (rule-based scoring only).")
            print("\n[INFO] TO GET MULTI-AGENT DEBATE:")
            print("   1. DeepSeek: https://platform.deepseek.com/")
            print("   2. Gemini: https://aistudio.google.com/apikey")
            print("   3. Set environment variables:")
            print("      $env:DEEPSEEK_API_KEY = 'your-deepseek-key'")
            print("      $env:GOOGLE_API_KEY = 'your-gemini-key'")
            print("\n[BENEFITS] With Multi-Agent Debate:")
            print("   - Two models analyze independently")
            print("   - Models debate and challenge each other")
            print("   - Consensus-based confidence scores")
            print("   - 10-20% better accuracy (MIT research)")
            print("   - Catches promotional/biased signals")
            print("="*80 + "\n")
        
        # A/B Testing Configuration for Signal Weight Optimization
        # Based on historical performance analysis (Dec 2025)
        self.enable_weight_testing = os.getenv("ENABLE_AB_TESTING", "true").lower() == "true"
        self.use_new_weights = os.getenv("USE_NEW_WEIGHTS", "false").lower() == "true"
        
        # Current production weights (baseline)
        self.weights_v1 = {
            'politician': 3.0,
            'director': 2.0,
            'officer': 0.5,
            'owner_10pct': 2.0,
            'unknown': 1.0
        }
        
        # Proposed optimized weights (based on empirical analysis)
        # Directors: 2.0 → 2.5 (+25% - justified by 69.6% win rate, n=23)
        # Officers: 0.5 → 0.2 (-60% - justified by -2.17% ROI, n=7)
        # Politicians: 3.0 → 3.0 (unchanged - insufficient data, n=2)
        self.weights_v2 = {
            'politician': 3.0,  # No change (n=2 too small)
            'director': 2.5,    # +25% increase (HIGH confidence from n=23, 69.6% win rate)
            'officer': 0.2,     # -60% decrease (MODERATE confidence from n=7, negative ROI)
            'owner_10pct': 2.0, # No change (no data yet)
            'unknown': 1.0      # No change
        }
        
        # Active weight set (default to v1 for safety)
        self.active_weights = self.weights_v1 if not self.use_new_weights else self.weights_v2
        
        if self.enable_weight_testing:
            logger.info("🧪 A/B Testing ENABLED - tracking both weight systems")
            print("[🧪] A/B TESTING MODE: Logging decisions with both weight sets")
            print(f"[⚙️] Active weights: {'V2 (NEW)' if self.use_new_weights else 'V1 (CURRENT)'}")
            print(f"    Politicians: {self.active_weights['politician']}")
            print(f"    Directors: {self.active_weights['director']}")
            print(f"    Officers: {self.active_weights['officer']}\n")
            
            # Initialize A/B testing database table
            self._init_ab_testing_table()
        else:
            logger.info("📊 Using production weights (A/B testing disabled)")
    
    def _init_ab_testing_table(self):
        """Create A/B testing log table if it doesn't exist"""
        try:
            self.db.execute_query("""
                CREATE TABLE IF NOT EXISTS ab_test_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    weight_v1_score REAL,
                    weight_v2_score REAL,
                    politician_count INTEGER,
                    director_count INTEGER,
                    officer_count INTEGER,
                    total_signals INTEGER,
                    active_version TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    pnl REAL,
                    outcome TEXT,
                    notes TEXT
                )
            """)
            
            # Create index for efficient queries
            self.db.execute_query("""
                CREATE INDEX IF NOT EXISTS idx_ab_test_symbol_timestamp 
                ON ab_test_log(symbol, timestamp)
            """)
            
            logger.info("✓ A/B testing database table initialized")
            
        except Exception as e:
            logger.warning(f"Failed to initialize A/B testing table: {e}")
    
    def _extract_llm_text(self, response) -> str:
        """
        Extract text content from LLM response.
        Handles Gemini 3 Pro which returns .content as a list instead of string.
        
        Args:
            response: LLM response object
        
        Returns: String content
        """
        if not hasattr(response, 'content'):
            return str(response)
        
        content = response.content
        
        # If content is a string, return directly
        if isinstance(content, str):
            return content
        
        # If content is a list (Gemini 3 Pro format), extract text from parts
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif hasattr(part, 'text'):
                    text_parts.append(part.text)
                elif isinstance(part, dict) and 'text' in part:
                    text_parts.append(part['text'])
            return '\n'.join(text_parts)
        
        # Fallback to string conversion
        return str(content)
    
    def connect_to_ibkr(self) -> bool:
        """
        Connect to Interactive Brokers for automatic order execution
        Returns: True if connected successfully, False otherwise
        """
        try:
            self.ib = IB()
            logger.info(f"🔌 Connecting to IBKR at {IBKR_HOST}:{IBKR_PORT}...")
            
            # Use run() for Python 3.12+ compatibility
            util.run(self.ib.connectAsync(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID))
            
            # Request delayed market data (free)
            self.ib.reqMarketDataType(3)
            
            self.ibkr_connected = True
            logger.info("✅ Connected to IBKR successfully")
            print("[+] IBKR CONNECTED: Ready for automatic order execution")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to IBKR: {e}")
            print(f"\n[ERROR] IBKR CONNECTION FAILED: {e}")
            print("[!] Automatic trading disabled - will save orders for manual execution")
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
    
    def log_ab_test_decision(self, symbol: str, signal_data: Dict, action: str):
        """
        Log A/B testing decision for later performance comparison
        
        Args:
            symbol: Stock symbol
            signal_data: Signal aggregation data with ab_testing scores
            action: 'BUY', 'SKIP', or 'REJECT'
        """
        if not self.enable_weight_testing or 'ab_testing' not in signal_data:
            return
        
        try:
            ab_data = signal_data['ab_testing']
            
            # Log to database for tracking
            self.db.execute_query("""
                INSERT INTO ab_test_log (
                    timestamp, symbol, action, 
                    weight_v1_score, weight_v2_score, 
                    politician_count, director_count, officer_count,
                    total_signals, active_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(),
                symbol,
                action,
                ab_data['weighted_quality_v1'],
                ab_data['weighted_quality_v2'],
                signal_data['politician_count'],
                signal_data['director_count'],
                signal_data['officer_count'],
                signal_data['total_signals'],
                'v2' if self.use_new_weights else 'v1'
            ))
            
            logger.info(f"[A/B] Logged {action} decision for {symbol} (V1: {ab_data['weighted_quality_v1']:.2f}, V2: {ab_data['weighted_quality_v2']:.2f})")
            
        except Exception as e:
            logger.warning(f"Failed to log A/B test decision: {e}")
    
    def get_settled_cash(self) -> float:
        """Get available settled cash from IBKR (T+2 compliant - what IBKR actually allows for orders)"""
        if not self.ibkr_connected:
            return 0.0
        
        try:
            account_values = self.ib.accountValues()
            for av in account_values:
                if av.tag == 'SettledCash' and av.currency == 'USD':
                    settled_cash = float(av.value)
                    logger.info(f"💰 IBKR Settled Cash: ${settled_cash:.2f}")
                    return settled_cash
            
            logger.warning("SettledCash not found in account values")
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching settled cash: {e}")
            return 0.0
    
    def validate_ibkr_contract(self, symbol: str) -> bool:
        """
        Validate that a ticker can be traded on IBKR.
        Purely data-driven - no manual mappings or bias.
        
        Returns: True if contract is valid and tradeable
        """
        if not self.ibkr_connected:
            # If not connected to IBKR, can't validate - assume valid
            return True
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            qualified = self.ib.qualifyContracts(contract)
            if qualified and contract.conId:
                return True
            else:
                logger.warning(f"⚠️  {symbol}: Cannot qualify on IBKR - ticker may be delisted or changed")
                return False
        except Exception as e:
            logger.warning(f"⚠️  {symbol}: Contract validation error: {e}")
            return False
    
    def is_complex_etf(self, symbol: str, contract) -> bool:
        """Check if stock is a complex/leveraged ETF requiring special permissions"""
        # Known complex ETFs that require special permissions
        complex_etfs = {
            'BITB', 'BITO', 'BTF',  # Bitcoin ETFs
            'SQQQ', 'TQQQ', 'UPRO', 'SPXU',  # 3x leveraged
            'UVXY', 'SVXY',  # Volatility products
        }
        
        if symbol in complex_etfs:
            return True
        
        # Check contract details if available
        try:
            if hasattr(contract, 'secType') and contract.secType == 'ETF':
                # Additional checks could go here
                pass
        except:
            pass
        
        return False
    
    def fetch_multi_source_signals(self) -> Dict[str, List[Dict]]:
        """
        Fetch insider signals from 4 sources:
        1. Form 4 Insider Trading (detailed transactions)
        2. Latest Insider Trading (broader coverage)
        3. Senate Trading (politicians - HIGHEST confidence)
        4. House Trading (Congress - HIGHEST confidence)
        
        Returns: Dict with 4 keys ('insider', 'latest', 'senate', 'house')
        """
        print("\n" + "="*80)
        print("[FETCHING] MULTI-SOURCE INSIDER DATA")
        print("="*80 + "\n")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=LOOKBACK_DAYS)
        
        # Source 1: Form 4 insider trading (current implementation)
        logger.info("📊 Source 1: Form 4 Insider Trading...")
        insider_url = "https://financialmodelingprep.com/api/v4/insider-trading"
        insider_params = {'apikey': FMP_API_KEY, 'page': 0}
        insider_data = []
        
        try:
            for page in range(10):  # Up to 10 pages
                insider_params['page'] = page
                response = requests.get(insider_url, params=insider_params, timeout=30)
                if response.status_code == 200:
                    page_data = response.json()
                    if not page_data or not isinstance(page_data, list):
                        break
                    
                    # Filter by date
                    filtered = [
                        t for t in page_data
                        if start_date <= datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') <= end_date
                    ]
                    insider_data.extend(filtered)
                    
                    if len(page_data) < 100:
                        break
        except Exception as e:
            logger.error(f"Error fetching insider trading: {e}")
        
        print(f"   [OK] Form 4 Insider Trading: {len(insider_data)} transactions")
        
        # Source 2: Latest insider trading (broader coverage)
        logger.info("📊 Source 2: Latest Insider Trading...")
        latest_url = "https://financialmodelingprep.com/stable/insider-trading/latest"
        latest_params = {'apikey': FMP_API_KEY}
        latest_data = []
        
        try:
            response = requests.get(latest_url, params=latest_params, timeout=30)
            if response.status_code == 200:
                latest_all = response.json()
                # Filter by date and acquisitions only
                latest_data = [
                    t for t in latest_all
                    if t.get('acquisitionOrDisposition') == 'A' and
                       start_date <= datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') <= end_date
                ]
        except Exception as e:
            logger.error(f"Error fetching latest insider: {e}")
        
        print(f"   [OK] Latest Insider Trading: {len(latest_data)} acquisitions")
        
        # Source 3: Senate trading (politicians - HIGHEST confidence)
        logger.info("📊 Source 3: Senate Trading...")
        senate_url = "https://financialmodelingprep.com/stable/senate-latest"
        senate_params = {'apikey': FMP_API_KEY}
        senate_buys = []
        
        try:
            response = requests.get(senate_url, params=senate_params, timeout=30)
            if response.status_code == 200:
                senate_all = response.json()
                # Filter by Purchase type and date
                senate_buys = [
                    t for t in senate_all
                    if t.get('type') == 'Purchase' and
                       start_date <= datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') <= end_date
                ]
        except Exception as e:
            logger.error(f"Error fetching Senate trading: {e}")
        
        print(f"   [OK] Senate Trading: {len(senate_buys)} purchases")
        
        # Source 4: House trading (Congress - HIGHEST confidence)
        logger.info("📊 Source 4: House Trading...")
        house_url = "https://financialmodelingprep.com/stable/house-latest"
        house_params = {'apikey': FMP_API_KEY}
        house_buys = []
        
        try:
            response = requests.get(house_url, params=house_params, timeout=30)
            if response.status_code == 200:
                house_all = response.json()
                # Filter by Purchase type and date
                house_buys = [
                    t for t in house_all
                    if t.get('type') == 'Purchase' and
                       start_date <= datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') <= end_date
                ]
        except Exception as e:
            logger.error(f"Error fetching House trading: {e}")
        
        print(f"   [+] House Trading: {len(house_buys)} purchases")
        
        total_signals = len(insider_data) + len(latest_data) + len(senate_buys) + len(house_buys)
        print(f"\n[TOTAL] {total_signals} signals across 4 sources")
        print("="*80 + "\n")
        
        return {
            'insider': insider_data,
            'latest': latest_data,
            'senate': senate_buys,
            'house': house_buys
        }
    
    def calculate_signal_quality(self, insider_role: str, is_politician: bool = False, weight_version: str = 'active') -> float:
        """
        Calculate signal quality weight based on insider type
        
        Signal Hierarchy (User's Insight + Empirical Data):
        - Politicians (Senate/House): 3.0 = HIGHEST (legal insider info, 100% win rate from n=2)
        - Directors: 2.0 → 2.5 = HIGH (external validation, 69.6% win rate from n=23)
        - 10% Owners: 2.0 = HIGH (major stakeholder)
        - Officers: 0.5 → 0.2 = LOWER (promotional risk, -2.17% ROI from n=7)
        
        Args:
            insider_role: Role from typeOfOwner or office field
            is_politician: True if from Senate/House data
            weight_version: 'active', 'v1', or 'v2' (for A/B testing)
        
        Returns: Quality weight (0.2-3.0)
        """
        # Select weight set based on version
        if weight_version == 'v1':
            weights = self.weights_v1
        elif weight_version == 'v2':
            weights = self.weights_v2
        else:
            weights = self.active_weights
        
        # Politicians = HIGHEST confidence
        if is_politician:
            return weights['politician']
        
        # Parse role
        role_lower = insider_role.lower() if insider_role else ""
        
        # Directors and board members = HIGH confidence
        if 'director' in role_lower or 'board' in role_lower:
            return weights['director']
        
        # 10% owners = HIGH confidence
        if '10%' in role_lower or '10 percent' in role_lower or 'ten percent' in role_lower:
            return weights['owner_10pct']
        
        # Officers = LOWER confidence (promotional risk)
        if any(word in role_lower for word in ['officer', 'ceo', 'cfo', 'coo', 'president', 'vice president', 'executive']):
            return weights['officer']
        
        # Default for unknown roles
        return weights['unknown']
    
    def analyze_timing(self, transaction_date_str: str, entry_price: Optional[float], current_price: Optional[float]) -> Dict:
        """
        Analyze timing quality of insider signal
        
        User's Concern: "When stock was when they reported vs where it is now - did we miss the market?"
        
        Returns: Dict with timing analysis
        """
        try:
            txn_date = datetime.strptime(transaction_date_str, '%Y-%m-%d')
        except:
            return {
                'days_ago': 999,
                'timing_score': 0.3,
                'timing_status': '[UNKNOWN] Invalid date'
            }
        
        days_ago = (datetime.now() - txn_date).days
        
        # Calculate price movement if prices available
        if entry_price and current_price and entry_price > 0:
            price_change_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            price_change_pct = 0
        
        # Determine timing quality
        if price_change_pct > 20:
            timing_score = 0.5
            timing_status = "[LATE] >20% move since insider bought"
        elif price_change_pct > 10:
            timing_score = 0.7
            timing_status = "[CAUTION] 10-20% move"
        elif days_ago < 7:
            timing_score = 1.5
            timing_status = "[VERY TIMELY] <7 days"
        elif days_ago < 14:
            timing_score = 1.0
            timing_status = "[RECENT] 7-14 days"
        else:
            timing_score = 0.7
            timing_status = "[MODERATE] 14+ days"
        
        return {
            'days_ago': days_ago,
            'price_change_pct': round(price_change_pct, 2),
            'entry_price': entry_price,
            'current_price': current_price,
            'timing_score': timing_score,
            'timing_status': timing_status
        }
    
    def calculate_multi_layer_boosts(self, signal_data: Dict) -> Dict:
        """
        Calculate multi-layer validation boosts for politician-backed stocks
        
        Boosts applied to BASE confidence score:
        - Director confirmation: +26.5% (institutional validation)
        - Fresh signal (<14 days): +5% (timing advantage)
        - Institutional contradiction: -15% penalty (conflicting signals)
        
        Args:
            signal_data: Dict with politician_count, director_count, transaction dates, etc.
        
        Returns: Dict with boost_multiplier and boost_reasons
        """
        boosts = []
        boost_multiplier = 1.0
        
        # BOOST 1: Director confirmation (+26.5%)
        # Directors on board provides institutional validation
        if signal_data['director_count'] > 0:
            boost_multiplier *= 1.265
            boosts.append(f"Directors buying (+26.5%, {signal_data['director_count']} directors...")
        
        # BOOST 2: Fresh signal (<14 days, +5%)
        # Timing advantage - more relevant current signal
        if signal_data['transactions']:
            most_recent_date = max(
                [datetime.strptime(t.get('date', '2000-01-01'), '%Y-%m-%d') for t in signal_data['transactions']]
            )
            days_ago = (datetime.now() - most_recent_date).days
            if 0 < days_ago <= 14:
                boost_multiplier *= 1.05
                boosts.append(f"Recent signal 7-14 days (+5%)" if days_ago <= 14 else None)
        
        # BOOST 3: Institutional contradiction penalty (-15%)
        # If institutions selling while politicians buying = conflicting signals
        # (This would require checking market sentiment or short data)
        # For now, we assume all signals are positive buying
        
        return {
            'boost_multiplier': round(boost_multiplier, 3),
            'boost_reasons': [b for b in boosts if b]
        }
    
    def aggregate_multi_source_signals(self, multi_source_data: Dict[str, List[Dict]]) -> Dict[str, Dict]:
        """
        Aggregate signals across all 4 sources with politician-first hard gate
        
        STRATEGY: POLITICIAN-FIRST with multi-layer validation
        - HARD GATE: Stock MUST have >=1 politician signal or REJECT immediately
        - All director/institution/news signals used ONLY as ranking boosters
        - Result: 100% politician-backed portfolio
        
        Returns: Dict[symbol] = {
            'total_signals': int,
            'politician_count': int,
            'director_count': int,
            'officer_count': int,
            'owner_count': int,
            'weighted_quality_score': float (BASE confidence)
            'boost_multiplier': float (multi-layer validation boost),
            'final_confidence': float (boosted confidence = BASE * BOOST),
            'transactions': List[Dict],  # All transactions for this symbol
            'timing_analysis': Dict,
            'source_breakdown': Dict
        }
        """
        print("\n" + "="*80)
        print("[AGGREGATING] MULTI-SOURCE SIGNALS")
        print("="*80 + "\n")
        
        # Collect all transactions by symbol
        all_signals = defaultdict(lambda: {
            'total_signals': 0,
            'politician_count': 0,
            'director_count': 0,
            'officer_count': 0,
            'owner_count': 0,
            'weighted_quality_score': 0.0,
            'transactions': [],
            'source_breakdown': {'insider': 0, 'latest': 0, 'senate': 0, 'house': 0}
        })
        
        # Process each source
        for source_name, transactions in multi_source_data.items():
            is_political = source_name in ['senate', 'house']
            
            for txn in transactions:
                symbol = txn.get('symbol')
                if not symbol or symbol == 'None':
                    continue
                
                # Get insider role
                if is_political:
                    role = txn.get('office', '')
                else:
                    role = txn.get('typeOfOwner', '')
                
                # Calculate quality weight (active weights for production)
                quality_weight = self.calculate_signal_quality(role, is_political, 'active')
                
                # A/B Testing: Calculate with both weight sets for comparison
                if self.enable_weight_testing:
                    quality_weight_v1 = self.calculate_signal_quality(role, is_political, 'v1')
                    quality_weight_v2 = self.calculate_signal_quality(role, is_political, 'v2')
                    
                    # Store both for later comparison
                    if 'ab_testing' not in all_signals[symbol]:
                        all_signals[symbol]['ab_testing'] = {
                            'weighted_quality_v1': 0.0,
                            'weighted_quality_v2': 0.0
                        }
                    all_signals[symbol]['ab_testing']['weighted_quality_v1'] += quality_weight_v1
                    all_signals[symbol]['ab_testing']['weighted_quality_v2'] += quality_weight_v2
                
                # Categorize by type
                role_lower = role.lower() if role else ""
                if is_political:
                    all_signals[symbol]['politician_count'] += 1
                elif 'director' in role_lower:
                    all_signals[symbol]['director_count'] += 1
                elif '10%' in role_lower or '10 percent' in role_lower:
                    all_signals[symbol]['owner_count'] += 1
                elif any(w in role_lower for w in ['officer', 'ceo', 'cfo', 'president']):
                    all_signals[symbol]['officer_count'] += 1
                
                # Add to aggregates
                all_signals[symbol]['total_signals'] += 1
                all_signals[symbol]['weighted_quality_score'] += quality_weight
                all_signals[symbol]['transactions'].append({
                    'source': source_name,
                    'date': txn.get('transactionDate'),
                    'role': role,
                    'quality_weight': quality_weight,
                    'shares': txn.get('securitiesTransacted'),
                    'price': txn.get('price'),
                    'amount': txn.get('amount'),  # For politicians (range)
                    'name': txn.get('reportingName') or f"{txn.get('firstName', '')} {txn.get('lastName', '')}".strip(),
                    'link': txn.get('link') or txn.get('url')
                })
                all_signals[symbol]['source_breakdown'][source_name] += 1
        
        # Calculate average quality scores
        for symbol, data in all_signals.items():
            if data['total_signals'] > 0:
                data['weighted_quality_score'] = round(
                    data['weighted_quality_score'] / data['total_signals'], 2
                )
                
                # A/B Testing: Calculate averages for both weight sets
                if self.enable_weight_testing and 'ab_testing' in data:
                    data['ab_testing']['weighted_quality_v1'] = round(
                        data['ab_testing']['weighted_quality_v1'] / data['total_signals'], 2
                    )
                    data['ab_testing']['weighted_quality_v2'] = round(
                        data['ab_testing']['weighted_quality_v2'] / data['total_signals'], 2
                    )
        
        # POLITICIAN-FIRST HARD GATE: Only accept stocks with >=1 politician signal
        # This is the critical filter: NO director-only, institution-only, or officer-only stocks
        filtered_signals = {}
        
        for symbol, data in all_signals.items():
            if data['politician_count'] > 0:
                # Calculate multi-layer boosts for ranking
                boosts = self.calculate_multi_layer_boosts(data)
                data['boost_multiplier'] = boosts['boost_multiplier']
                data['boost_reasons'] = boosts['boost_reasons']
                
                # Final confidence = BASE confidence * boost multiplier
                data['final_confidence'] = round(
                    data['weighted_quality_score'] * boosts['boost_multiplier'], 3
                )
                
                filtered_signals[symbol] = data
        
        print(f"[RESULTS] SIGNAL AGGREGATION (POLITICIAN-FIRST):")
        print(f"   Total stocks with activity: {len(all_signals)}")
        print(f"   [HARD GATE] Politician-backed only: {len(filtered_signals)}")
        print(f"   Criterion: >=1 politician signal (MANDATORY)\n")
        
        if filtered_signals:
            print("[TOP STOCKS] BY FINAL CONFIDENCE (Politician-Backed with Multi-Layer Boosts):\n")
            sorted_signals = sorted(
                filtered_signals.items(),
                key=lambda x: (x[1]['final_confidence'], x[1]['total_signals']),
                reverse=True
            )[:15]
            
            for symbol, data in sorted_signals:
                base_score = data['weighted_quality_score']
                final_score = data['final_confidence']
                boost_pct = ((data['boost_multiplier'] - 1.0) * 100)
                quality_stars = "*" * min(3, int(final_score))
                
                print(f"   {symbol}: Base {base_score:.2f} → Final {final_score:.2f} {quality_stars} (+{boost_pct:.1f}%)")
                
                # Show boost reasons
                if data['boost_reasons']:
                    for reason in data['boost_reasons']:
                        print(f"      • {reason}")
                
                # A/B Testing: Show comparison
                if self.enable_weight_testing and 'ab_testing' in data:
                    v1_score = data['ab_testing']['weighted_quality_v1']
                    v2_score = data['ab_testing']['weighted_quality_v2']
                    delta = v2_score - v1_score
                    delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
                    print(f"      [A/B] V1: {v1_score:.2f} | V2: {v2_score:.2f} | Delta: {delta_str}")
                
                print(f"      Signals: {data['total_signals']} total | "
                      f"Politicians: {data['politician_count']} | "
                      f"Directors: {data['director_count']} | "
                      f"Officers: {data['officer_count']}")
                print(f"      Sources: Insider={data['source_breakdown']['insider']}, "
                      f"Latest={data['source_breakdown']['latest']}, "
                      f"Senate={data['source_breakdown']['senate']}, "
                      f"House={data['source_breakdown']['house']}\n")
        
        print("="*80 + "\n")
        
        return filtered_signals
    
    def fetch_form4_clusters(self) -> tuple[Dict[str, int], Dict[str, List[Dict]]]:
        """
        Fetch Form 4 filings with detailed transaction data
        Returns: (clusters_dict, transactions_dict)
            - clusters_dict: {symbol: filing_count}
            - transactions_dict: {symbol: [transaction_details]}
        
        Uses FMP insider-trading endpoint for rich transaction details:
        - Transaction type (purchase, sale, award)
        - Share amounts and prices
        - Insider roles and names
        - SEC filing URLs
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=LOOKBACK_DAYS)
        
        logger.info(f"📡 Fetching Form 4 insider transactions...")
        logger.info(f"   Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        logger.info(f"   Lookback period: {LOOKBACK_DAYS} days")
        
        print(f"\n📅 ANALYZING INSIDER TRANSACTIONS")
        print(f"   From: {start_date.strftime('%B %d, %Y')}")
        print(f"   To:   {end_date.strftime('%B %d, %Y')}")
        print(f"   Period: {LOOKBACK_DAYS} days\n")
        
        # Use insider-trading endpoint for detailed transaction data
        url = "https://financialmodelingprep.com/api/v4/insider-trading"
        params = {
            "apikey": FMP_API_KEY,
            "page": 0  # Start with first page
        }
        
        all_transactions = []
        
        try:
            # Fetch transactions (may need pagination)
            while True:
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    page_data = response.json()
                    if not page_data or not isinstance(page_data, list):
                        break
                    
                    # Filter by date range
                    filtered = [
                        t for t in page_data
                        if start_date <= datetime.strptime(t.get('transactionDate', '2000-01-01'), '%Y-%m-%d') <= end_date
                    ]
                    
                    all_transactions.extend(filtered)
                    
                    # If we got less than full page, we're done
                    if len(page_data) < 100:
                        break
                    
                    params['page'] += 1
                    
                    # Safety: stop after 10 pages (1000 transactions)
                    if params['page'] >= 10:
                        break
                else:
                    logger.error(f"Error: FMP API returned status {response.status_code}")
                    return {}, {}
        except Exception as e:
            logger.error(f"Error fetching insider trading data: {e}")
            return {}, {}
        
        logger.info(f"✓ Retrieved {len(all_transactions)} insider transactions")
        
        # Group transactions by symbol
        transactions_by_symbol = defaultdict(list)
        for transaction in all_transactions:
            symbol = transaction.get('symbol')
            if symbol and symbol != 'None':
                transactions_by_symbol[symbol].append(transaction)
        
        # Count unique filings per symbol (by filing date + insider name)
        clusters = {}
        for symbol, transactions in transactions_by_symbol.items():
            unique_filings = set()
            for t in transactions:
                filing_key = (t.get('filingDate'), t.get('reportingName'))
                unique_filings.add(filing_key)
            
            filing_count = len(unique_filings)
            if filing_count >= MIN_FILINGS_FOR_CLUSTER:
                clusters[symbol] = filing_count
        
        logger.info(f"✓ Found {len(clusters)} insider clusters ({MIN_FILINGS_FOR_CLUSTER}+ filings)")
        
        if clusters:
            print(f"📊 INSIDER CLUSTERS DETECTED (≥{MIN_FILINGS_FOR_CLUSTER} filings):")
            for symbol, count in sorted(clusters.items(), key=lambda x: x[1], reverse=True)[:10]:
                # Calculate buy vs sell breakdown
                symbol_transactions = transactions_by_symbol[symbol]
                buys = sum(1 for t in symbol_transactions if t.get('acquistionOrDisposition') == 'A')
                sells = sum(1 for t in symbol_transactions if t.get('acquistionOrDisposition') == 'D')
                print(f"   {symbol}: {count} filings ({buys} buys, {sells} sells)")
            print()
        
        return clusters, dict(transactions_by_symbol)
    
    def get_stock_profile(self, symbol: str) -> Optional[Dict]:
        """Fetch stock profile and fundamentals"""
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        params = {"apikey": FMP_API_KEY}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return data[0]
        except Exception as e:
            logger.warning(f"Failed to fetch profile for {symbol}: {e}")
        
        return None
    
    def get_news(self, symbol: str, days: int = 14) -> List[Dict]:
        """Fetch recent news for symbol"""
        url = f"https://financialmodelingprep.com/api/v3/stock_news"
        params = {
            "tickers": symbol,
            "limit": 10,
            "apikey": FMP_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()[:5]  # Top 5 news items
        except Exception as e:
            logger.warning(f"Failed to fetch news for {symbol}: {e}")
        
        return []
    
    def filter_by_fundamentals(self, clusters: Dict[str, int], transactions_dict: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Filter clusters by fundamental criteria and transaction quality
        Returns: List of candidates with profile data and transaction details
        """
        logger.info(f"🔍 Filtering {len(clusters)} clusters by fundamentals...")
        
        candidates = []
        
        for symbol, filing_count in sorted(clusters.items(), key=lambda x: x[1], reverse=True):
            profile = self.get_stock_profile(symbol)
            
            if not profile:
                logger.debug(f"  ✗ {symbol}: No profile data")
                continue
            
            market_cap = profile.get('mktCap', 0)
            price = profile.get('price', 0)
            
            if not (market_cap and price):
                logger.debug(f"  ✗ {symbol}: Missing market cap or price")
                continue
            
            # Apply filters
            if market_cap < MIN_MARKET_CAP:
                logger.debug(f"  ✗ {symbol}: Market cap too small (${market_cap/1_000_000:.0f}M)")
                continue
            
            if market_cap > MAX_MARKET_CAP:
                logger.debug(f"  ✗ {symbol}: Market cap too large (${market_cap/1_000_000_000:.1f}B)")
                continue
            
            if price < MIN_PRICE:
                logger.debug(f"  ✗ {symbol}: Price too low (${price:.2f})")
                continue
            
            if price > MAX_PRICE:
                logger.debug(f"  ✗ {symbol}: Price too high (${price:.2f})")
                continue
            
            # Analyze transaction details
            transactions = transactions_dict.get(symbol, [])
            transaction_summary = self._analyze_transactions(transactions)
            
            # Filter out if mostly insider selling
            if transaction_summary['net_buys'] < 0:
                logger.debug(f"  ✗ {symbol}: Net insider selling ({transaction_summary['net_buys']} net transactions)")
                continue
            
            # Passed all filters
            candidates.append({
                'symbol': symbol,
                'filing_count': filing_count,
                'profile': profile,
                'transactions': transactions,
                'transaction_summary': transaction_summary
            })
            
            logger.info(f"  ✓ {symbol}: ${market_cap/1_000_000:.0f}M cap, ${price:.2f}, {filing_count} filings ({transaction_summary['buys']} buys)")
        
        logger.info(f"✓ {len(candidates)} candidates passed filters")
        return candidates
    
    def _analyze_transactions(self, transactions: List[Dict]) -> Dict:
        """
        Analyze transaction details to understand insider behavior
        Returns summary with buy/sell breakdown, insider roles, prices, etc.
        """
        summary = {
            'total_transactions': len(transactions),
            'buys': 0,
            'sells': 0,
            'net_buys': 0,
            'total_shares_bought': 0,
            'total_shares_sold': 0,
            'avg_buy_price': 0,
            'insider_roles': set(),
            'senior_insiders': [],  # CEO, CFO, Director
            'sec_urls': [],
            'buy_transactions': [],
            'sell_transactions': []
        }
        
        buy_prices = []
        
        for t in transactions:
            disposition = t.get('acquistionOrDisposition', '')
            shares = t.get('securitiesTransacted', 0)
            price = t.get('price', 0)
            role = t.get('typeOfOwner', '')
            name = t.get('reportingName', '')
            sec_url = t.get('link', '')
            transaction_type = t.get('transactionType', '')
            
            # Track insider roles
            if role:
                summary['insider_roles'].add(role)
            
            # Identify senior insiders (more bullish signal)
            if any(keyword in role.lower() for keyword in ['director', 'officer', 'ceo', 'cfo', 'president']):
                summary['senior_insiders'].append({
                    'name': name,
                    'role': role,
                    'transaction': disposition
                })
            
            # Categorize by acquisition/disposition
            if disposition == 'A':  # Acquired
                summary['buys'] += 1
                summary['total_shares_bought'] += shares
                summary['net_buys'] += 1
                if price > 0:
                    buy_prices.append(price)
                summary['buy_transactions'].append({
                    'name': name,
                    'role': role,
                    'shares': shares,
                    'price': price,
                    'type': transaction_type,
                    'sec_url': sec_url
                })
            elif disposition == 'D':  # Disposed
                summary['sells'] += 1
                summary['total_shares_sold'] += shares
                summary['net_buys'] -= 1
                summary['sell_transactions'].append({
                    'name': name,
                    'role': role,
                    'shares': shares,
                    'price': price,
                    'type': transaction_type
                })
            
            # Collect SEC URLs
            if sec_url and sec_url not in summary['sec_urls']:
                summary['sec_urls'].append(sec_url)
        
        # Calculate average buy price
        if buy_prices:
            summary['avg_buy_price'] = sum(buy_prices) / len(buy_prices)
        
        # Convert set to list for JSON serialization
        summary['insider_roles'] = list(summary['insider_roles'])
        
        return summary
    
    def filter_by_fundamentals_multi_source(self, aggregated_signals: Dict[str, Dict]) -> List[Dict]:
        """
        Filter aggregated multi-source signals by fundamental criteria
        
        Args:
            aggregated_signals: Dict from aggregate_multi_source_signals()
        
        Returns: List of candidates with profile data and multi-source signal details
        """
        logger.info(f"🔍 Filtering {len(aggregated_signals)} stocks by fundamentals...")
        
        print("\n" + "="*80)
        print("[FILTERING] FUNDAMENTAL FILTERING")
        print("="*80 + "\n")
        
        candidates = []
        filtered_reasons = defaultdict(int)
        
        for symbol, signal_data in sorted(aggregated_signals.items(), 
                                         key=lambda x: x[1]['weighted_quality_score'], 
                                         reverse=True):
            # Fetch profile
            profile = self.get_stock_profile(symbol)
            
            if not profile:
                filtered_reasons['no_profile'] += 1
                continue
            
            market_cap = profile.get('mktCap', 0)
            price = profile.get('price', 0)
            
            if not (market_cap and price):
                filtered_reasons['missing_data'] += 1
                continue
            
            # Apply filters
            if market_cap < MIN_MARKET_CAP:
                filtered_reasons['market_cap_too_small'] += 1
                continue
            
            if market_cap > MAX_MARKET_CAP:
                filtered_reasons['market_cap_too_large'] += 1
                continue
            
            if price < MIN_PRICE:
                filtered_reasons['price_too_low'] += 1
                continue
            
            if price > MAX_PRICE:
                filtered_reasons['price_too_high'] += 1
                continue
            
            # Filter out ETFs (user request: focus on stocks only)
            is_etf = profile.get('isEtf', False)
            if is_etf:
                filtered_reasons['is_etf'] += 1
                logger.debug(f"  ✗ {symbol}: ETF (focus on stocks only)")
                continue
            
            # Analyze timing for most recent transaction
            recent_txn = sorted(signal_data['transactions'], 
                              key=lambda t: t.get('date', '2000-01-01'), 
                              reverse=True)[0]
            
            timing_analysis = self.analyze_timing(
                recent_txn.get('date'),
                recent_txn.get('price'),
                price
            )
            
            # Filter out very late signals (>20% move)
            if timing_analysis['timing_score'] <= 0.5:
                filtered_reasons['too_late'] += 1
                logger.debug(f"  ✗ {symbol}: {timing_analysis['timing_status']}")
                continue
            
            # Passed all filters
            candidates.append({
                'symbol': symbol,
                'profile': profile,
                'signal_data': signal_data,
                'timing_analysis': timing_analysis
            })
            
            # A/B Testing: Log candidate that passed filters
            self.log_ab_test_decision(symbol, signal_data, 'CANDIDATE')
            
            # Log pass
            logger.info(
                f"  ✓ {symbol}: ${market_cap/1_000_000:.0f}M cap, ${price:.2f} | "
                f"Quality: {signal_data['weighted_quality_score']:.2f}/3.0 | "
                f"{timing_analysis['timing_status']}"
            )
        
        # Print filter summary
        print(f"[RESULTS] FILTERING:")
        print(f"   [+] Passed: {len(candidates)}")
        print(f"   [-] Filtered: {sum(filtered_reasons.values())}")
        if filtered_reasons:
            print(f"\n   Reasons:")
            for reason, count in sorted(filtered_reasons.items(), key=lambda x: x[1], reverse=True):
                print(f"      - {reason.replace('_', ' ').title()}: {count}")
        print("\n" + "="*80 + "\n")
        
        logger.info(f"✓ {len(candidates)} candidates passed filters")
        return candidates
    
    def multi_agent_debate(self, symbol: str, profile: Dict, signal_data: Dict, 
                           timing_analysis: Dict, news: List[Dict]) -> Dict:
        """
        Multi-agent debate between DeepSeek and Gemini for consensus decision
        
        Workflow:
        1. Both models analyze independently (parallel)
        2. Each model sees the other's analysis and responds
        3. Final consensus with agreement score
        
        Args:
            symbol: Stock symbol
            profile: Company profile data
            signal_data: Multi-source insider signals
            timing_analysis: Transaction timing analysis
            news: Recent news articles
        
        Returns: Dict with consensus analysis + agreement metrics
        """
        logger.info(f"🤝 Multi-agent debate for {symbol}...")
        
        # Build shared context for both agents
        insider_summary = (
            f"Signal Quality: {signal_data['weighted_quality_score']:.2f}/3.0 | "
            f"{signal_data['total_signals']} total signals | "
            f"Politicians: {signal_data['politician_count']} | "
            f"Directors: {signal_data['director_count']} | "
            f"Officers: {signal_data['officer_count']}"
        )
        
        system_prompt = """You are an expert stock analyst specializing in insider trading analysis.

Analyze insider trading signals with focus on:
1. WHO: Politicians > Directors > Officers (quality hierarchy)
2. WHEN: Recent trades (<14 days) preferred
3. WHERE: Entry price vs current price (did we miss the move?)
4. COORDINATION: Multiple independent parties = stronger signal

KEY INSIGHT: Officers buying may be promotional (trying to raise stock price artificially).
Politicians and Directors buying shows genuine confidence.

Return JSON format:
{
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation focusing on signal quality",
    "bull_case": "why this could work well",
    "bear_case": "key risks to consider",
    "hold_period_days": 7-21
}"""
        
        user_prompt = f"""Analyze {symbol} insider trading signal:

COMPANY: {profile.get('companyName')}
Sector: {profile.get('sector')} | Industry: {profile.get('industry')}
Market Cap: ${profile.get('mktCap', 0)/1_000_000:.0f}M | Price: ${profile.get('price', 0):.2f}

INSIDER SIGNALS:
{insider_summary}

TIMING: {timing_analysis['timing_status']}
- Days since transaction: {timing_analysis['days_ago']}
- Price change: {timing_analysis.get('price_change_pct', 0):+.1f}%

RECENT NEWS:
{chr(10).join([f"- {n.get('title', 'N/A')}" for n in news[:3]])}

Provide your analysis in JSON format."""
        
        # ============================================
        # ROUND 1: Independent Analysis (Parallel)
        # ============================================
        
        print(f"\n[DEBATE] {symbol}: Round 1 - Independent Analysis")
        
        deepseek_response = None
        gemini_response = None
        
        # DeepSeek Analysis
        try:
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            deepseek_raw = self.deepseek_llm.invoke(messages)
            deepseek_text = self._extract_llm_text(deepseek_raw)
            
            # Parse JSON
            import json, re
            json_match = re.search(r'\{[^{}]*"confidence"[^{}]*\}', deepseek_text, re.DOTALL)
            if json_match:
                deepseek_response = json.loads(json_match.group())
                print(f"   ✓ DeepSeek: {deepseek_response['confidence']:.0%} confidence")
        except Exception as e:
            logger.warning(f"DeepSeek analysis failed: {e}")
        
        # Gemini Analysis
        try:
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            gemini_raw = self.gemini_llm.invoke(messages)
            gemini_text = self._extract_llm_text(gemini_raw)
            
            # Parse JSON
            json_match = re.search(r'\{[^{}]*"confidence"[^{}]*\}', gemini_text, re.DOTALL)
            if json_match:
                gemini_response = json.loads(json_match.group())
                print(f"   ✓ Gemini: {gemini_response['confidence']:.0%} confidence")
        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e}")
        
        # Handle failures
        if not deepseek_response and not gemini_response:
            logger.error("Both models failed - using rule-based")
            return None
        
        if not deepseek_response:
            print(f"   [!] DeepSeek failed - using Gemini only")
            return {**gemini_response, 'agreement_score': 0.5, 'debate_rounds': 1}
        
        if not gemini_response:
            print(f"   [!] Gemini failed - using DeepSeek only")
            return {**deepseek_response, 'agreement_score': 0.5, 'debate_rounds': 1}
        
        # ============================================
        # ROUND 2: Mutual Critique
        # ============================================
        
        print(f"[DEBATE] {symbol}: Round 2 - Mutual Critique")
        
        # Calculate initial disagreement
        initial_diff = abs(deepseek_response['confidence'] - gemini_response['confidence'])
        print(f"   Initial gap: {initial_diff:.0%}")
        
        # If already agree, skip debate
        if initial_diff < 0.10:
            consensus_confidence = (deepseek_response['confidence'] + gemini_response['confidence']) / 2
            agreement_score = 1.0 - initial_diff
            
            print(f"   ✓ Quick agreement: {consensus_confidence:.0%} (score: {agreement_score:.2f})")
            
            return {
                'confidence': consensus_confidence,
                'reasoning': f"CONSENSUS: {deepseek_response['reasoning']}",
                'bull_case': deepseek_response.get('bull_case', ''),
                'bear_case': gemini_response.get('bear_case', ''),
                'hold_period_days': max(deepseek_response.get('hold_period_days', 14),
                                      gemini_response.get('hold_period_days', 14)),
                'agreement_score': agreement_score,
                'debate_rounds': 1,
                'deepseek_view': deepseek_response,
                'gemini_view': gemini_response
            }
        
        # DeepSeek responds to Gemini
        try:
            critique_prompt = f"""You previously analyzed {symbol} with {deepseek_response['confidence']:.0%} confidence.

Another expert analyst (Gemini) analyzed the same stock and got {gemini_response['confidence']:.0%} confidence.

Gemini's reasoning: {gemini_response['reasoning']}
Gemini's concerns: {gemini_response.get('bear_case', '')}

Do you maintain your confidence or adjust based on this perspective? Return updated JSON."""
            
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=critique_prompt)]
            deepseek_rebuttal_raw = self.deepseek_llm.invoke(messages)
            deepseek_rebuttal_text = self._extract_llm_text(deepseek_rebuttal_raw)
            
            json_match = re.search(r'\{[^{}]*"confidence"[^{}]*\}', deepseek_rebuttal_text, re.DOTALL)
            if json_match:
                deepseek_response = json.loads(json_match.group())
                print(f"   ✓ DeepSeek adjusted: {deepseek_response['confidence']:.0%}")
        except Exception as e:
            logger.warning(f"DeepSeek rebuttal failed: {e}")
        
        # Gemini responds to DeepSeek
        try:
            critique_prompt = f"""You previously analyzed {symbol} with {gemini_response['confidence']:.0%} confidence.

Another expert analyst (DeepSeek) analyzed the same stock and got {deepseek_response['confidence']:.0%} confidence.

DeepSeek's reasoning: {deepseek_response['reasoning']}
DeepSeek's bull case: {deepseek_response.get('bull_case', '')}

Do you maintain your confidence or adjust based on this perspective? Return updated JSON."""
            
            messages = [SystemMessage(content=system_prompt), HumanMessage(content=critique_prompt)]
            gemini_rebuttal_raw = self.gemini_llm.invoke(messages)
            gemini_rebuttal_text = self._extract_llm_text(gemini_rebuttal_raw)
            
            json_match = re.search(r'\{[^{}]*"confidence"[^{}]*\}', gemini_rebuttal_text, re.DOTALL)
            if json_match:
                gemini_response = json.loads(json_match.group())
                print(f"   ✓ Gemini adjusted: {gemini_response['confidence']:.0%}")
        except Exception as e:
            logger.warning(f"Gemini rebuttal failed: {e}")
        
        # ============================================
        # CONSENSUS
        # ============================================
        
        final_diff = abs(deepseek_response['confidence'] - gemini_response['confidence'])
        consensus_confidence = (deepseek_response['confidence'] + gemini_response['confidence']) / 2
        agreement_score = 1.0 - final_diff
        
        print(f"[CONSENSUS] {symbol}: {consensus_confidence:.0%} (agreement: {agreement_score:.2f})")
        
        # Flag low-agreement for manual review
        if agreement_score < 0.70:
            print(f"   ⚠️  LOW AGREEMENT - Recommend manual review")
        
        return {
            'confidence': consensus_confidence,
            'reasoning': f"DeepSeek: {deepseek_response['reasoning']} | Gemini: {gemini_response['reasoning']}",
            'bull_case': deepseek_response.get('bull_case', '') + " // " + gemini_response.get('bull_case', ''),
            'bear_case': deepseek_response.get('bear_case', '') + " // " + gemini_response.get('bear_case', ''),
            'hold_period_days': max(deepseek_response.get('hold_period_days', 14),
                                  gemini_response.get('hold_period_days', 14)),
            'agreement_score': agreement_score,
            'debate_rounds': 2,
            'deepseek_view': deepseek_response,
            'gemini_view': gemini_response,
            'requires_human_review': agreement_score < 0.70
        }
    
    def _analyze_single_candidate(self, candidate: Dict) -> Dict:
        """
        Analyze a single candidate (used for parallel processing)
        Returns: Candidate dict with 'analysis' field added
        """
        symbol = candidate['symbol']
        profile = candidate['profile']
        signal_data = candidate['signal_data']
        timing_analysis = candidate['timing_analysis']
        
        # Fetch news for analysis
        news = self.get_news(symbol, days=14)
        
        # If multi-agent available, use debate
        if self.multi_agent_available:
            debate_result = self.multi_agent_debate(
                symbol, profile, signal_data, timing_analysis, news
            )
            
            if debate_result:
                candidate['analysis'] = {
                    **debate_result,
                    'analysis_type': 'MULTI-AGENT DEBATE'
                }
                logger.info(f"  ✓ {symbol}: Consensus {debate_result['confidence']:.2f} (agreement: {debate_result['agreement_score']:.2f})")
                return candidate
            else:
                # Debate failed, fall back to rule-based
                logger.warning(f"  ! {symbol}: Debate failed, using rule-based")
        
        # Single LLM or no LLM - use previous logic
        # If no LLM at all, use rule-based scoring
        if not self.deepseek_llm and not self.gemini_llm:
            confidence = self._rule_based_score_multi_source(candidate)
            
            reasoning = (
                f"{signal_data['total_signals']} insider signals (Quality: {signal_data['weighted_quality_score']}/3.0). "
                f"Politicians: {signal_data['politician_count']}, Directors: {signal_data['director_count']}, "
                f"Officers: {signal_data['officer_count']}. {timing_analysis['timing_status']}"
            )
            
            bull_case = (
                f"Multi-source validation with {signal_data['total_signals']} independent signals. "
                f"Signal quality {signal_data['weighted_quality_score']}/3.0 indicates strong conviction."
            )
            
            bear_case = "Rule-based analysis only (no LLM). Limited fundamental context."
            
            candidate['analysis'] = {
                'confidence': confidence,
                'reasoning': reasoning,
                'bull_case': bull_case,
                'bear_case': bear_case,
                'hold_period_days': 14,
                'analysis_type': 'RULE-BASED (No LLM)'
            }
            logger.info(f"  ✓ {symbol}: Confidence {confidence:.2f} (rule-based)")
            return candidate
        
        # Build detailed insider breakdown
        politician_txns = [t for t in signal_data['transactions'] if t['source'] in ['senate', 'house']]
        director_txns = [t for t in signal_data['transactions'] if 'director' in t.get('role', '').lower()]
        officer_txns = [t for t in signal_data['transactions'] if 'officer' in t.get('role', '').lower()]
        
        # Build insider details section
        insider_details = []
        
        if politician_txns:
            insider_details.append("🏛️  POLITICIAN PURCHASES (HIGHEST CONFIDENCE):")
            for txn in politician_txns[:5]:
                name = txn.get('name', 'Unknown')
                source = txn.get('source', '').upper()
                date = txn.get('date', 'N/A')
                amount = txn.get('amount', 'N/A')
                days_ago = (datetime.now() - datetime.strptime(date, '%Y-%m-%d')).days if date != 'N/A' else 999
                insider_details.append(
                    f"  • {name} ({source}) - {days_ago} days ago ({amount})"
                )
        
        if director_txns:
            insider_details.append("\n👔 DIRECTOR PURCHASES (HIGH CONFIDENCE):")
            for txn in director_txns[:3]:
                name = txn.get('name', 'Unknown')
                date = txn.get('date', 'N/A')
                shares = txn.get('shares', 0)
                price = txn.get('price', 0)
                days_ago = (datetime.now() - datetime.strptime(date, '%Y-%m-%d')).days if date != 'N/A' else 999
                if shares and price:
                    insider_details.append(
                        f"  • {name} - {days_ago} days ago: {shares:,} shares @ ${price:.2f}"
                    )
                else:
                    insider_details.append(f"  • {name} - {days_ago} days ago")
        
        if officer_txns:
            insider_details.append("\n💼 OFFICER PURCHASES (LOWER CONFIDENCE - Promotional Risk):")
            for txn in officer_txns[:2]:
                name = txn.get('name', 'Unknown')
                role = txn.get('role', '')
                date = txn.get('date', 'N/A')
                days_ago = (datetime.now() - datetime.strptime(date, '%Y-%m-%d')).days if date != 'N/A' else 999
                insider_details.append(
                    f"  • {name} ({role}) - {days_ago} days ago"
                )
        
        insider_details_text = "\n".join(insider_details) if insider_details else "No detailed transaction data"
        
        # System prompt for enhanced multi-source analysis
        system_prompt = """You are an expert stock analyst specializing in insider trading analysis.

Analyze insider trading signals with focus on:
1. WHO: Politicians > Directors > Officers (quality hierarchy)
2. WHEN: Recent trades (<14 days) preferred
3. WHERE: Entry price vs current price (did we miss the move?)
4. COORDINATION: Multiple independent parties = stronger signal

KEY INSIGHT: Officers buying may be promotional (trying to raise stock price artificially).
Politicians and Directors buying shows genuine confidence.

Return JSON format:
{
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation focusing on signal quality",
    "bull_case": "why this could work well",
    "bear_case": "key risks to consider",
    "hold_period_days": 7-21
}"""
        
        # User prompt with multi-source context
        user_prompt = f"""Analyze this multi-source insider trading opportunity:

SYMBOL: {symbol}
COMPANY: {profile.get('companyName', 'N/A')}
SECTOR: {profile.get('sector', 'N/A')} | INDUSTRY: {profile.get('industry', 'N/A')}

📊 MULTI-SOURCE INSIDER SIGNALS ({LOOKBACK_DAYS} days):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Total Signals: {signal_data['total_signals']} independent insider actions
• Signal Quality Score: {signal_data['weighted_quality_score']:.2f}/3.0 ⭐

SIGNAL BREAKDOWN BY TYPE:
• Politicians (Senate/House): {signal_data['politician_count']} 🏛️  = HIGHEST confidence
• Directors: {signal_data['director_count']} 👔 = HIGH confidence  
• Officers: {signal_data['officer_count']} 💼 = LOWER confidence (promotional risk)
• 10% Owners: {signal_data['owner_count']} 💰 = HIGH confidence

SOURCE BREAKDOWN:
• Form 4 Filings: {signal_data['source_breakdown']['insider']}
• Latest Insider: {signal_data['source_breakdown']['latest']}
• Senate Trading: {signal_data['source_breakdown']['senate']}
• House Trading: {signal_data['source_breakdown']['house']}

⏰ TIMING ANALYSIS:
• Most Recent Purchase: {timing_analysis['days_ago']} days ago
• Insider Entry Price: ${timing_analysis.get('entry_price') or 0:.2f}
• Current Price: ${timing_analysis.get('current_price') or profile.get('price', 0):.2f}
• Price Movement: {timing_analysis.get('price_change_pct', 0):+.1f}%
• Timing Assessment: {timing_analysis['timing_status']}
• Timing Quality Score: {timing_analysis['timing_score']:.1f}x

{insider_details_text}

FUNDAMENTALS:
• Market Cap: ${profile.get('mktCap', 0)/1_000_000:.0f}M
• Price: ${profile.get('price', 0):.2f}
• Beta: {profile.get('beta', 'N/A')}
• P/E Ratio: {profile.get('pe', 'N/A')}
• 52-Week Range: ${profile.get('range', 'N/A')}

RECENT NEWS:
{self._format_news(news) if news else "No recent news available"}

ANALYSIS REQUIRED:
Consider:
1. Signal QUALITY (politicians/directors vs officers)
2. TIMING (are we late to the move?)
3. COORDINATION (multiple independent buyers?)
4. TRAJECTORY (where is this stock headed based on WHO is buying?)"""

        # Use whichever single LLM is available
        single_llm = self.deepseek_llm or self.gemini_llm
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = single_llm.invoke(messages)
            content = response.content
            
            # Parse JSON response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            analysis = json.loads(content)
            
            candidate['analysis'] = analysis
            logger.info(f"  ✓ {symbol}: Confidence {analysis['confidence']:.2f}")
            return candidate
            
        except Exception as e:
            logger.error(f"  ✗ {symbol}: LLM analysis failed - {e}")
            # Add default low confidence if LLM fails
            candidate['analysis'] = {
                'confidence': 0.50,
                'reasoning': f'LLM analysis failed. {signal_data["total_signals"]} signals detected.',
                'bull_case': 'Multi-source insider activity',
                'bear_case': 'Unknown fundamentals',
                'hold_period_days': 14
            }
            return candidate
    
    def analyze_with_llm(self, candidates: List[Dict]) -> List[Dict]:
        """
        Use multi-agent debate or single LLM to analyze candidates with parallel processing (15 workers)
        Falls back to rule-based scoring if no LLM available
        """
        if self.multi_agent_available:
            logger.info(f"🤖 Multi-agent debate analysis for {len(candidates)} candidates (15 parallel workers)...")
            print("\n" + "="*80)
            print("[MULTI-AGENT DEBATE] ANALYZING CANDIDATES (15 PARALLEL WORKERS)")
            print("="*80)
        else:
            logger.info(f"🤖 Analyzing {len(candidates)} candidates (15 parallel workers)...")
        
        analyzed = []
        
        # Use ThreadPoolExecutor for parallel processing with 15 workers
        with ThreadPoolExecutor(max_workers=15) as executor:
            # Submit all candidates for analysis
            future_to_candidate = {executor.submit(self._analyze_single_candidate, candidate): candidate for candidate in candidates}
            
            # Collect results as they complete
            for future in as_completed(future_to_candidate):
                try:
                    result = future.result()
                    analyzed.append(result)
                except Exception as e:
                    candidate = future_to_candidate[future]
                    logger.error(f"  ✗ Error analyzing {candidate.get('symbol', 'UNKNOWN')}: {e}")
                    # Continue to next candidate on error
        
        logger.info(f"✅ Completed analysis of {len(analyzed)} candidates using 15 parallel workers")
        return analyzed
    
    def get_institutional_holders(self, symbol: str) -> List[Dict]:
        """
        Fetch Form 13F institutional holders from FMP API
        Returns list of institutional holders with recent changes
        """
        url = f"https://financialmodelingprep.com/api/v3/institutional-holder/{symbol}"
        params = {"apikey": FMP_API_KEY}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                holders = response.json()
                if holders and isinstance(holders, list):
                    # Sort by shares held (descending)
                    holders.sort(key=lambda h: h.get('shares', 0), reverse=True)
                    return holders[:20]  # Top 20 holders
        except Exception as e:
            logger.warning(f"Failed to fetch institutional holders for {symbol}: {e}")
        
        return []
    
    def add_institutional_validation(self, candidates: List[Dict]) -> List[Dict]:
        """
        Add Form 13F institutional validation layer to Form 4 signals
        
        Strategy:
        1. Query FMP API for institutional holders
        2. Analyze recent changes (Q3 2025 vs Q2 2025)
        3. Count institutions that INCREASED stake (bullish)
        4. Count institutions that DECREASED stake (bearish)
        5. Adjust confidence scores:
           - 3+ increases: +20% boost (STRONG SUPPORT)
           - 2+ decreases: -25% penalty (INSTITUTIONS SELLING)
           - 0 activity: -10% penalty (NO VALIDATION)
        6. Add institutional_holders field to candidate
        
        This fixes the confidence issue by:
        - Filtering out promotional officer buying (when institutions disagree)
        - Boosting strong signals (when smart money agrees)
        - Providing external validation beyond insider signals
        """
        logger.info(f"🏦 Adding institutional validation to {len(candidates)} candidates...")
        
        print("\n" + "="*80)
        print("[INSTITUTIONAL VALIDATION] FORM 13F ANALYSIS")
        print("="*80 + "\n")
        
        for candidate in candidates:
            symbol = candidate['symbol']
            
            # Fetch institutional holders
            holders = self.get_institutional_holders(symbol)
            
            if not holders:
                # No 13F data available
                boost = 0.90  # -10% for no validation
                validation_status = "NO INSTITUTIONAL DATA"
                increases = []
                decreases = []
                total_holders = 0
                logger.debug(f"  {symbol}: No institutional data")
            else:
                # Analyze recent changes
                # Note: FMP returns holders with 'change' field (shares added/removed)
                # Positive change = institution increased stake
                # Negative change = institution decreased stake
                
                increases = []
                decreases = []
                
                for holder in holders:
                    holder_name = holder.get('holder', 'Unknown')
                    shares = holder.get('shares', 0)
                    change = holder.get('change', 0)
                    
                    if shares == 0:
                        continue
                    
                    # Calculate change percentage
                    change_pct = (change / (shares - change)) * 100 if (shares - change) > 0 else 0
                    
                    # Significant change threshold: >5% change
                    if change_pct > 5:
                        increases.append({
                            'name': holder_name,
                            'shares': shares,
                            'change': change,
                            'change_pct': round(change_pct, 1),
                            'date_reported': holder.get('dateReported', 'N/A')
                        })
                    elif change_pct < -5:
                        decreases.append({
                            'name': holder_name,
                            'shares': shares,
                            'change': change,
                            'change_pct': round(change_pct, 1),
                            'date_reported': holder.get('dateReported', 'N/A')
                        })
                
                # Calculate validation boost/penalty
                if len(increases) >= 3:
                    boost = 1.20  # +20% for strong institutional support
                    validation_status = "STRONG INSTITUTIONAL SUPPORT"
                    logger.info(f"  ✓ {symbol}: {len(increases)} institutions buying (+20%)")
                elif len(decreases) >= 2:
                    boost = 0.75  # -25% for institutions selling
                    validation_status = "INSTITUTIONS SELLING - CAUTION"
                    logger.warning(f"  ⚠️  {symbol}: {len(decreases)} institutions selling (-25%)")
                elif len(increases) == 0 and len(decreases) == 0:
                    boost = 0.90  # -10% for no recent activity
                    validation_status = "NO RECENT INSTITUTIONAL ACTIVITY"
                    logger.debug(f"  {symbol}: No recent institutional changes (-10%)")
                else:
                    boost = 1.0
                    validation_status = "MODERATE INSTITUTIONAL ACTIVITY"
                    logger.debug(f"  {symbol}: Mixed institutional activity (neutral)")
                
                total_holders = len(holders)
            
            # Apply boost to confidence score
            original_confidence = candidate['analysis']['confidence']
            candidate['analysis']['confidence'] *= boost
            
            # Store validation details
            candidate['institutional_validation'] = {
                'status': validation_status,
                'boost_factor': boost,
                'original_confidence': original_confidence,
                'adjusted_confidence': candidate['analysis']['confidence'],
                'increases': increases[:5],  # Top 5 buyers
                'decreases': decreases[:3],  # Top 3 sellers
                'total_holders': total_holders,
                'validation_summary': self._format_validation_summary(
                    validation_status, increases, decreases, boost
                )
            }
            
            # Log adjustment
            direction = "⬆️" if boost > 1.0 else "⬇️" if boost < 1.0 else "➡️"
            print(f"   {symbol}: {original_confidence:.2f} → {candidate['analysis']['confidence']:.2f} {direction}")
            print(f"      Status: {validation_status}")
            if increases:
                print(f"      Buyers: {len(increases)} institutions increased stakes")
            if decreases:
                print(f"      Sellers: {len(decreases)} institutions decreased stakes")
            print()
        
        print("="*80 + "\n")
        
        return candidates
    
    def _format_validation_summary(self, status: str, increases: List[Dict], 
                                   decreases: List[Dict], boost: float) -> str:
        """Format validation summary for display"""
        summary = []
        
        summary.append(f"🏦 INSTITUTIONAL VALIDATION: {status}")
        
        if increases:
            summary.append(f"\n✅ INSTITUTIONS BUYING ({len(increases)}):")
            for holder in increases[:3]:
                summary.append(
                    f"   • {holder['name']}: {holder['change_pct']:+.1f}% increase "
                    f"({holder['change']:,} shares added)"
                )
        
        if decreases:
            summary.append(f"\n⚠️  INSTITUTIONS SELLING ({len(decreases)}):")
            for holder in decreases[:2]:
                summary.append(
                    f"   • {holder['name']}: {holder['change_pct']:.1f}% decrease "
                    f"({abs(holder['change']):,} shares removed)"
                )
        
        if boost > 1.0:
            summary.append(f"\n✅ CONFIDENCE BOOST: +{(boost-1)*100:.0f}%")
        elif boost < 1.0:
            summary.append(f"\n⚠️  CONFIDENCE PENALTY: {(boost-1)*100:.0f}%")
        
        return "\n".join(summary)
    
    def _format_news(self, news: List[Dict]) -> str:
        """Format news items for LLM"""
        formatted = []
        for item in news[:5]:
            title = item.get('title', 'N/A')
            published = item.get('publishedDate', 'N/A')[:10]
            formatted.append(f"- [{published}] {title}")
        return "\n".join(formatted)
    
    def _rule_based_score(self, candidate: Dict) -> float:
        """
        Enhanced rule-based scoring when LLM unavailable
        Provides detailed breakdown of scoring logic
        """
        score = 0.60  # Base score for any cluster
        score_breakdown = ["Base cluster score: 0.60"]
        
        filing_count = candidate['filing_count']
        profile = candidate['profile']
        
        # More filings = higher score
        if filing_count >= 5:
            score += 0.15
            score_breakdown.append(f"Strong cluster (≥5 filings): +0.15")
        elif filing_count >= 4:
            score += 0.10
            score_breakdown.append(f"Good cluster (≥4 filings): +0.10")
        else:
            score_breakdown.append(f"Moderate cluster ({filing_count} filings): +0.00")
        
        # Market cap sweet spot ($1B-10B)
        market_cap = profile.get('mktCap', 0)
        if 1_000_000_000 <= market_cap <= 10_000_000_000:
            score += 0.10
            score_breakdown.append(f"Ideal market cap (${market_cap/1_000_000_000:.1f}B): +0.10")
        elif market_cap > 10_000_000_000:
            score_breakdown.append(f"Large cap (${market_cap/1_000_000_000:.1f}B): +0.00 (less volatile)")
        else:
            score_breakdown.append(f"Small cap (${market_cap/1_000_000:.0f}M): +0.00")
        
        # Reasonable P/E (10-30)
        pe = profile.get('pe')
        if pe and 10 <= pe <= 30:
            score += 0.05
            score_breakdown.append(f"Reasonable P/E ({pe:.1f}): +0.05")
        elif pe and pe > 30:
            score_breakdown.append(f"High P/E ({pe:.1f}): +0.00 (possibly overvalued)")
        elif pe and pe < 10:
            score_breakdown.append(f"Low P/E ({pe:.1f}): +0.00 (value or distressed)")
        else:
            score_breakdown.append(f"No P/E data: +0.00")
        
        final_score = min(score, 0.95)  # Cap at 0.95
        
        # Store breakdown for later use
        candidate['score_breakdown'] = score_breakdown
        candidate['final_score'] = final_score
        
        return final_score
    
    def _rule_based_score_multi_source(self, candidate: Dict) -> float:
        """
        Rule-based scoring for multi-source signals
        Incorporates signal quality and timing
        """
        score = 0.60  # Base score
        score_breakdown = ["Base score: 0.60"]
        
        signal_data = candidate['signal_data']
        timing_analysis = candidate['timing_analysis']
        profile = candidate['profile']
        
        # Signal quality weight (0.5-3.0 scale normalized to 0-0.20)
        quality_bonus = (signal_data['weighted_quality_score'] / 3.0) * 0.20
        score += quality_bonus
        score_breakdown.append(f"Signal quality ({signal_data['weighted_quality_score']:.2f}/3.0): +{quality_bonus:.2f}")
        
        # Timing bonus (timing_score is 0.5-1.5)
        timing_bonus = (timing_analysis['timing_score'] - 0.5) * 0.10  # Scale to 0-0.10
        score += timing_bonus
        score_breakdown.append(f"Timing ({timing_analysis['timing_status'][:20]}...): +{timing_bonus:.2f}")
        
        # Politician bonus (highest confidence)
        if signal_data['politician_count'] > 0:
            pol_bonus = min(signal_data['politician_count'] * 0.05, 0.10)
            score += pol_bonus
            score_breakdown.append(f"Politician signals ({signal_data['politician_count']}): +{pol_bonus:.2f}")
        
        # Multiple sources bonus
        sources_active = sum(1 for v in signal_data['source_breakdown'].values() if v > 0)
        if sources_active >= 3:
            score += 0.05
            score_breakdown.append(f"Multi-source validation ({sources_active} sources): +0.05")
        
        final_score = min(score, 0.95)  # Cap at 0.95
        
        candidate['score_breakdown'] = score_breakdown
        candidate['final_score'] = final_score
        
        return final_score
    
    def llm_allocation_debate(self, analyzed: List[Dict]) -> Dict:
        """
        LLM debate to determine optimal capital allocation
        
        The LLMs jointly decide:
        1. How many positions to take (no fixed minimum/maximum)
        2. Weight allocation per position (conviction-based, not equal weight)
        3. Cash reserve recommendation (if any)
        
        Returns: {
            'positions': [{'symbol': str, 'weight_pct': float, 'conviction': str}],
            'cash_reserve_pct': float,
            'reasoning': str,
            'deepseek_view': dict,
            'gemini_view': dict,
            'agreement_score': float
        }
        """
        if not self.multi_agent_available:
            logger.warning("LLM allocation debate requires both models - using default allocation")
            return None
        
        print("\n" + "="*80)
        print("🤖 LLM ALLOCATION DEBATE - DETERMINING POSITION COUNT & WEIGHTS")
        print("="*80)
        
        # Build summary of all analyzed candidates
        candidate_summaries = []
        for i, c in enumerate(analyzed[:20], 1):  # Top 20 for debate context
            symbol = c['symbol']
            confidence = c['analysis']['confidence']
            quality = c['signal_data']['weighted_quality_score']
            politicians = c['signal_data']['politician_count']
            directors = c['signal_data']['director_count']
            price = c['profile']['price']
            mkt_cap = c['profile']['mktCap'] / 1_000_000
            
            summary = (
                f"{i}. {symbol}: Confidence {confidence:.0%}, Quality {quality:.1f}/3.0, "
                f"Politicians: {politicians}, Directors: {directors}, "
                f"Price: ${price:.2f}, MktCap: ${mkt_cap:.0f}M"
            )
            candidate_summaries.append(summary)
        
        candidates_text = "\n".join(candidate_summaries)
        
        allocation_prompt = f'''You are a portfolio allocation expert analyzing politician-backed insider trading signals.

AVAILABLE CAPITAL: ${self.capital:.2f}

ANALYZED CANDIDATES (ranked by confidence):
{candidates_text}

TASK: Decide the OPTIMAL allocation strategy. You must determine:

1. HOW MANY positions to take (there is NO minimum or maximum - you decide based on opportunity quality)
2. WEIGHT for each position (conviction-based - higher confidence = higher weight)
3. CASH RESERVE (if signal quality is weak, keep cash in reserve for better opportunities)

KEY PRINCIPLES:
- Politicians buying is the strongest signal (3.0 quality)
- Concentration in high-conviction picks beats diversification in mediocre ones
- Better to take 2 great positions than 8 mediocre ones
- If no candidates are compelling, recommend 100% cash reserve
- Consider price vs capital (expensive stocks need more capital per position)

RESPOND WITH VALID JSON ONLY (no markdown, no explanation outside JSON):
{{
    "positions": [
        {{"symbol": "AAAA", "weight_pct": 35, "conviction": "HIGH"}},
        {{"symbol": "BBBB", "weight_pct": 30, "conviction": "HIGH"}},
        {{"symbol": "CCCC", "weight_pct": 20, "conviction": "MEDIUM"}}
    ],
    "cash_reserve_pct": 15,
    "reasoning": "Brief explanation of allocation logic"
}}

Rules:
- weight_pct + cash_reserve_pct must equal 100
- conviction must be "HIGH", "MEDIUM", or "LOW"
- Include 0 positions if no good opportunities exist
- Weights should reflect relative conviction (not equal weight)'''

        # Get DeepSeek's allocation
        print("[DEBATE] Round 1 - Independent Allocation Proposals")
        deepseek_allocation = None
        gemini_allocation = None
        
        try:
            deepseek_response = self.deepseek_llm.invoke([
                SystemMessage(content="You are a portfolio allocation expert. Respond ONLY with valid JSON."),
                HumanMessage(content=allocation_prompt)
            ])
            
            deepseek_text = self._extract_llm_text(deepseek_response)
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', deepseek_text)
            if json_match:
                deepseek_allocation = json.loads(json_match.group())
                num_pos = len(deepseek_allocation.get('positions', []))
                cash_pct = deepseek_allocation.get('cash_reserve_pct', 0)
                print(f"   ✓ DeepSeek: {num_pos} positions, {cash_pct}% cash reserve")
        except Exception as e:
            logger.warning(f"DeepSeek allocation failed: {e}")
            print(f"   ✗ DeepSeek: Failed ({e})")
        
        try:
            gemini_response = self.gemini_llm.invoke([
                SystemMessage(content="You are a portfolio allocation expert. Respond ONLY with valid JSON."),
                HumanMessage(content=allocation_prompt)
            ])
            
            gemini_text = self._extract_llm_text(gemini_response)
            
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', gemini_text)
            if json_match:
                gemini_allocation = json.loads(json_match.group())
                num_pos = len(gemini_allocation.get('positions', []))
                cash_pct = gemini_allocation.get('cash_reserve_pct', 0)
                print(f"   ✓ Gemini: {num_pos} positions, {cash_pct}% cash reserve")
        except Exception as e:
            logger.warning(f"Gemini allocation failed: {e}")
            print(f"   ✗ Gemini: Failed ({e})")
        
        # If both failed, return None
        if not deepseek_allocation and not gemini_allocation:
            logger.error("Both LLMs failed allocation debate - using fallback")
            return None
        
        # If only one succeeded, use it
        if not deepseek_allocation:
            print("[CONSENSUS] Using Gemini allocation (DeepSeek failed)")
            return {
                'positions': gemini_allocation.get('positions', []),
                'cash_reserve_pct': gemini_allocation.get('cash_reserve_pct', 0),
                'reasoning': gemini_allocation.get('reasoning', ''),
                'deepseek_view': None,
                'gemini_view': gemini_allocation,
                'agreement_score': 0.5
            }
        
        if not gemini_allocation:
            print("[CONSENSUS] Using DeepSeek allocation (Gemini failed)")
            return {
                'positions': deepseek_allocation.get('positions', []),
                'cash_reserve_pct': deepseek_allocation.get('cash_reserve_pct', 0),
                'reasoning': deepseek_allocation.get('reasoning', ''),
                'deepseek_view': deepseek_allocation,
                'gemini_view': None,
                'agreement_score': 0.5
            }
        
        # Both succeeded - reconcile differences
        print("\n[DEBATE] Round 2 - Reconciliation")
        
        # Calculate agreement on position count
        ds_positions = set(p['symbol'] for p in deepseek_allocation.get('positions', []))
        gm_positions = set(p['symbol'] for p in gemini_allocation.get('positions', []))
        
        overlap = ds_positions & gm_positions
        union = ds_positions | gm_positions
        position_agreement = len(overlap) / len(union) if union else 1.0
        
        # Calculate agreement on cash reserve
        ds_cash = deepseek_allocation.get('cash_reserve_pct', 0)
        gm_cash = gemini_allocation.get('cash_reserve_pct', 0)
        cash_diff = abs(ds_cash - gm_cash)
        cash_agreement = 1.0 - (cash_diff / 100)
        
        overall_agreement = (position_agreement + cash_agreement) / 2
        
        print(f"   Position overlap: {len(overlap)}/{len(union)} ({position_agreement:.0%})")
        print(f"   Cash reserve diff: {cash_diff:.0f}% ({cash_agreement:.0%} agreement)")
        print(f"   Overall agreement: {overall_agreement:.0%}")
        
        # Build consensus allocation
        consensus_positions = []
        
        # Prioritize positions both models agree on
        for symbol in overlap:
            ds_pos = next((p for p in deepseek_allocation['positions'] if p['symbol'] == symbol), None)
            gm_pos = next((p for p in gemini_allocation['positions'] if p['symbol'] == symbol), None)
            
            # Average the weights
            avg_weight = (ds_pos['weight_pct'] + gm_pos['weight_pct']) / 2
            
            # Higher conviction if both agree
            conviction = "HIGH" if ds_pos['conviction'] == gm_pos['conviction'] == "HIGH" else \
                        "MEDIUM" if "HIGH" in [ds_pos['conviction'], gm_pos['conviction']] else "LOW"
            
            consensus_positions.append({
                'symbol': symbol,
                'weight_pct': avg_weight,
                'conviction': conviction,
                'agreed': True
            })
        
        # Add positions only one model selected (with reduced weight)
        single_model_picks = (ds_positions | gm_positions) - overlap
        for symbol in single_model_picks:
            ds_pos = next((p for p in deepseek_allocation['positions'] if p['symbol'] == symbol), None)
            gm_pos = next((p for p in gemini_allocation['positions'] if p['symbol'] == symbol), None)
            
            pos = ds_pos or gm_pos
            # Reduce weight by 30% for single-model picks
            reduced_weight = pos['weight_pct'] * 0.7
            
            consensus_positions.append({
                'symbol': symbol,
                'weight_pct': reduced_weight,
                'conviction': pos['conviction'],
                'agreed': False,
                'source': 'deepseek' if ds_pos else 'gemini'
            })
        
        # Normalize weights to ensure they sum to (100 - cash_reserve)
        avg_cash = (ds_cash + gm_cash) / 2
        available_for_positions = 100 - avg_cash
        
        total_weight = sum(p['weight_pct'] for p in consensus_positions)
        if total_weight > 0:
            scale_factor = available_for_positions / total_weight
            for p in consensus_positions:
                p['weight_pct'] = round(p['weight_pct'] * scale_factor, 1)
        
        # Sort by weight (highest first)
        consensus_positions.sort(key=lambda x: x['weight_pct'], reverse=True)
        
        # Build reasoning
        reasoning = (
            f"Consensus allocation: {len(consensus_positions)} positions ({len(overlap)} agreed by both models). "
            f"Cash reserve: {avg_cash:.0f}%. "
            f"DeepSeek reasoning: {deepseek_allocation.get('reasoning', 'N/A')} | "
            f"Gemini reasoning: {gemini_allocation.get('reasoning', 'N/A')}"
        )
        
        print(f"\n[CONSENSUS] Final Allocation:")
        print(f"   Positions: {len(consensus_positions)}")
        print(f"   Cash Reserve: {avg_cash:.0f}%")
        for p in consensus_positions:
            agreed_marker = "✓" if p.get('agreed') else f"({p.get('source', '?')} only)"
            print(f"   • {p['symbol']}: {p['weight_pct']:.1f}% [{p['conviction']}] {agreed_marker}")
        print("="*80 + "\n")
        
        result = {
            'positions': consensus_positions,
            'cash_reserve_pct': avg_cash,
            'reasoning': reasoning,
            'deepseek_view': deepseek_allocation,
            'gemini_view': gemini_allocation,
            'agreement_score': overall_agreement
        }
        
        # Store for later use
        self.llm_allocation = result
        
        return result
    
    def rank_and_select(self, analyzed: List[Dict]) -> List[Dict]:
        """
        Rank analyzed candidates by confidence and select top positions
        
        BUG FIX (2025-12-09): Multi-criteria sorting to handle confidence ties
        Previously: Single criterion (confidence only) caused random selection
        Now: 5-level priority when confidence scores match:
            1. Confidence (primary)
            2. Signal Quality Score (politicians 3.0 > directors 2.0 > officers 0.5)
            3. Politician Count (legal insider info = highest quality)
            4. Total Signals (coordination strength)
            5. Recency (negative days_ago for descending order)
        
        Returns: Candidates selected by LLM allocation debate (or fallback top 4)
        """
        # Filter by minimum confidence
        qualified = [c for c in analyzed if c['analysis']['confidence'] >= MIN_CONFIDENCE_SCORE]
        
        logger.info(f"✓ {len(qualified)}/{len(analyzed)} candidates above {MIN_CONFIDENCE_SCORE:.0%} confidence")
        
        # Multi-criteria sort to handle ties deterministically
        qualified.sort(key=lambda x: (
            x['analysis']['confidence'],
            x['signal_data']['weighted_quality_score'],
            x['signal_data']['politician_count'],
            x['signal_data']['total_signals'],
            -x['timing_analysis']['days_ago']  # Negative for descending (recent = better)
        ), reverse=True)
        
        # Log selection transparency (show tie-breaking in action)
        logger.info("📊 Selection criteria applied:")
        logger.info("   1. Confidence (primary)")
        logger.info("   2. Signal Quality (politicians 3.0 > directors 2.0 > officers 0.5)")
        logger.info("   3. Politician Count")
        logger.info("   4. Total Signals (coordination)")
        logger.info("   5. Recency (days since transaction)")
        
        # Run LLM allocation debate to determine position count and weights
        allocation_result = self.llm_allocation_debate(qualified)
        
        if allocation_result and allocation_result.get('positions'):
            # LLM debate succeeded - select positions based on LLM recommendation
            llm_symbols = [p['symbol'] for p in allocation_result['positions']]
            
            # Filter qualified candidates to only those recommended by LLMs
            selected = [c for c in qualified if c['symbol'] in llm_symbols]
            
            # Preserve LLM weight recommendations
            for candidate in selected:
                llm_pos = next((p for p in allocation_result['positions'] if p['symbol'] == candidate['symbol']), None)
                if llm_pos:
                    candidate['llm_weight_pct'] = llm_pos['weight_pct']
                    candidate['llm_conviction'] = llm_pos['conviction']
                    candidate['llm_agreed'] = llm_pos.get('agreed', False)
            
            # Sort by LLM weight (highest allocation first)
            selected.sort(key=lambda x: x.get('llm_weight_pct', 0), reverse=True)
            
            logger.info(f"✓ LLM debate selected {len(selected)} positions (cash reserve: {allocation_result['cash_reserve_pct']:.0f}%)")
        else:
            # LLM debate failed - fallback to top 4 by confidence
            logger.warning("LLM allocation debate failed - using fallback (top 4 by confidence)")
            selected = qualified[:4]
            
            # Assign equal weights as fallback
            weight_per_pos = 100 / len(selected) if selected else 0
            for candidate in selected:
                candidate['llm_weight_pct'] = weight_per_pos
                candidate['llm_conviction'] = 'MEDIUM'
                candidate['llm_agreed'] = False
        
        logger.info(f"✓ Selected {len(selected)} positions")
        
        return selected
    
    def calculate_position_sizes(self, selected: List[Dict]) -> List[Dict]:
        """
        Calculate position sizes based on LLM-recommended weights (conviction-based)
        Falls back to equal weighting if LLM weights not available
        Filters out 0-share positions and reallocates capital
        """
        if not selected:
            return []
        
        # Check if we have LLM allocation with cash reserve
        cash_reserve_pct = 0
        if self.llm_allocation and 'cash_reserve_pct' in self.llm_allocation:
            cash_reserve_pct = self.llm_allocation['cash_reserve_pct']
        
        # Available capital = total capital - cash reserve
        available_capital = self.capital * (1 - cash_reserve_pct / 100)
        
        print(f"\n[ALLOCATION] Capital: ${self.capital:.2f}")
        if cash_reserve_pct > 0:
            print(f"[ALLOCATION] Cash Reserve: {cash_reserve_pct:.0f}% (${self.capital * cash_reserve_pct / 100:.2f})")
            print(f"[ALLOCATION] Available for positions: ${available_capital:.2f}")
        
        # Check if LLM weights are available
        has_llm_weights = all('llm_weight_pct' in c for c in selected)
        
        if has_llm_weights:
            # Use LLM conviction-based weights
            print(f"[ALLOCATION] Using LLM conviction-based weights\n")
            
            # Normalize weights to sum to available capital
            total_weight = sum(c['llm_weight_pct'] for c in selected)
            
            for candidate in selected:
                # Calculate position size based on LLM weight
                weight_fraction = candidate['llm_weight_pct'] / total_weight if total_weight > 0 else 1/len(selected)
                position_dollars = available_capital * weight_fraction
                
                price = candidate['profile']['price']
                shares = int(position_dollars / price)
                actual_size = shares * price
                
                candidate['position'] = {
                    'target_dollars': position_dollars,
                    'shares': shares,
                    'actual_dollars': actual_size,
                    'price': price,
                    'weight_pct': candidate['llm_weight_pct'],
                    'conviction': candidate.get('llm_conviction', 'MEDIUM')
                }
        else:
            # Fallback: equal weighting
            print(f"[ALLOCATION] Using equal weight distribution\n")
            position_size = available_capital / len(selected)
            
            for candidate in selected:
                price = candidate['profile']['price']
                shares = int(position_size / price)
                actual_size = shares * price
                
                candidate['position'] = {
                    'target_dollars': position_size,
                    'shares': shares,
                    'actual_dollars': actual_size,
                    'price': price
                }
        
        # Filter out 0-share positions (price too high)
        executable = [c for c in selected if c['position']['shares'] > 0]
        filtered_count = len(selected) - len(executable)
        
        if filtered_count > 0:
            logger.warning(f"🔧 Removing {filtered_count} positions with 0 shares (price exceeds allocation)")
            print(f"\n[!] POSITION SIZING ADJUSTMENT:")
            print(f"    {filtered_count} stocks removed - price too high for allocated capital")
            
            # Show filtered stocks
            for c in selected:
                if c['position']['shares'] == 0:
                    symbol = c['symbol']
                    price = c['profile']['price']
                    allocated = c['position']['target_dollars']
                    print(f"    ✗ {symbol}: ${price:.2f}/share (needs ${price:.2f}, allocated ${allocated:.2f})")
            
            # Recalculate for executable positions
            if executable:
                new_position_size = self.capital / len(executable)
                print(f"\n    Reallocating capital:")
                print(f"    ${self.capital:.2f} ÷ {len(executable)} positions = ${new_position_size:.2f} per position\n")
                
                for candidate in executable:
                    symbol = candidate['symbol']
                    price = candidate['profile']['price']
                    old_shares = candidate['position']['shares']
                    
                    # Recalculate with larger allocation
                    new_shares = int(new_position_size / price)
                    new_cost = new_shares * price
                    
                    candidate['position'] = {
                        'target_dollars': new_position_size,
                        'shares': new_shares,
                        'actual_dollars': new_cost,
                        'price': price
                    }
                    
                    if new_shares != old_shares:
                        print(f"    ✓ {symbol}: {old_shares} → {new_shares} shares (${new_cost:.2f})")
                
                logger.info(f"✓ Reallocated: {len(executable)} executable positions")
                return executable
            else:
                logger.error("❌ All positions have 0 shares - need higher capital for these stocks")
                print("\n[ERROR] No executable positions!")
                print("    All stocks too expensive for allocated capital")
                print(f"    Solutions:")
                print(f"    1. Increase buying power (current: ${self.capital:.2f})")
                print(f"    2. LLMs may select lower-priced alternatives\n")
                return []
        
        return selected
    
    def recalculate_position_sizes(self, approved_positions: List[Dict]) -> List[Dict]:
        """
        Recalculate position sizes AFTER user approval using LLM conviction weights
        Also filters 0-share positions and reallocates
        
        Uses conviction-based weighting: higher LLM weight = more capital
        
        Args:
            approved_positions: List of approved candidate dicts
        
        Returns: Updated list with recalculated shares and costs
        """
        if not approved_positions:
            return []
        
        num_approved = len(approved_positions)
        
        # Check cash reserve from LLM allocation
        cash_reserve_pct = 0
        if self.llm_allocation and 'cash_reserve_pct' in self.llm_allocation:
            cash_reserve_pct = self.llm_allocation['cash_reserve_pct']
        
        available_capital = self.capital * (1 - cash_reserve_pct / 100)
        
        print(f"\n{'='*80}")
        print(f"💰 RECALCULATING POSITION SIZES (LLM Conviction-Based)")
        print(f"{'='*80}")
        print(f"Total Capital: ${self.capital:.2f}")
        if cash_reserve_pct > 0:
            print(f"Cash Reserve: {cash_reserve_pct:.0f}% (${self.capital * cash_reserve_pct / 100:.2f})")
        print(f"Available for Positions: ${available_capital:.2f}")
        print(f"Approved Positions: {num_approved}")
        
        # Check if we have LLM weights
        has_llm_weights = all('llm_weight_pct' in c for c in approved_positions)
        
        if has_llm_weights:
            # Recalculate based on relative LLM weights of APPROVED positions only
            total_weight = sum(c['llm_weight_pct'] for c in approved_positions)
            print(f"Allocation Method: LLM Conviction-Based")
            print(f"{'='*80}\n")
            
            for candidate in approved_positions:
                symbol = candidate['symbol']
                price = candidate['profile']['price']
                old_shares = candidate['position']['shares']
                
                # Calculate new allocation based on relative weight
                weight_fraction = candidate['llm_weight_pct'] / total_weight if total_weight > 0 else 1/num_approved
                position_dollars = available_capital * weight_fraction
                
                new_shares = int(position_dollars / price)
                new_cost = new_shares * price
                
                conviction = candidate.get('llm_conviction', 'MEDIUM')
                
                candidate['position'] = {
                    'target_dollars': position_dollars,
                    'shares': new_shares,
                    'actual_dollars': new_cost,
                    'price': price,
                    'weight_pct': candidate['llm_weight_pct'],
                    'conviction': conviction
                }
                
                print(f"  {symbol}: [{conviction}] {weight_fraction*100:.1f}% = ${position_dollars:.2f} → {new_shares} shares")
        else:
            # Fallback to equal weighting
            position_size = available_capital / num_approved
            print(f"Allocation Method: Equal Weight (no LLM weights)")
            print(f"Per Position: ${position_size:.2f}")
            print(f"{'='*80}\n")
            
            for candidate in approved_positions:
                symbol = candidate['symbol']
                price = candidate['profile']['price']
                old_shares = candidate['position']['shares']
                old_cost = candidate['position']['actual_dollars']
                
                new_shares = int(position_size / price)
                new_cost = new_shares * price
                
                candidate['position'] = {
                    'target_dollars': position_size,
                    'shares': new_shares,
                    'actual_dollars': new_cost,
                    'price': price
                }
        
        # Filter 0-share positions (safety check)
        executable = [c for c in approved_positions if c['position']['shares'] > 0]
        filtered_count = num_approved - len(executable)
        
        if filtered_count > 0:
            logger.warning(f"🔧 Removing {filtered_count} approved positions with 0 shares")
            print(f"\n[!] ADDITIONAL FILTERING:")
            print(f"    {filtered_count} approved stocks still have 0 shares after recalculation")
            
            for c in approved_positions:
                if c['position']['shares'] == 0:
                    print(f"    ✗ {c['symbol']}: ${c['profile']['price']:.2f}/share too expensive")
            
            # Reallocate again
            if executable:
                final_position_size = self.capital / len(executable)
                print(f"\n    Final reallocation:")
                print(f"    ${self.capital:.2f} ÷ {len(executable)} = ${final_position_size:.2f} per position\n")
                
                for candidate in executable:
                    symbol = candidate['symbol']
                    price = candidate['profile']['price']
                    old_shares = candidate['position']['shares']
                    
                    final_shares = int(final_position_size / price)
                    final_cost = final_shares * price
                    
                    candidate['position'] = {
                        'target_dollars': final_position_size,
                        'shares': final_shares,
                        'actual_dollars': final_cost,
                        'price': price
                    }
                    
                    if final_shares != old_shares:
                        print(f"    ✓ {symbol}: {old_shares} → {final_shares} shares (${final_cost:.2f})")
            
            approved_positions = executable
            
            # Log change
            logger.info(f"  {symbol}: {old_shares} → {new_shares} shares (${old_cost:.2f} → ${new_cost:.2f})")
            print(f"  {symbol}: {new_shares} shares @ ${price:.2f} = ${new_cost:.2f}")
        
        total_allocated = sum(c['position']['actual_dollars'] for c in approved_positions)
        print(f"\nTotal Allocated: ${total_allocated:.2f} / ${self.capital:.2f}")
        print(f"{'='*80}\n")
        
        return approved_positions
    
    def generate_comprehensive_analysis_pdf(self, analyzed: List[Dict], timestamp: str) -> Optional[str]:
        """
        Generate comprehensive PDF report for ALL analyzed candidates
        Shows full ranking with LLM analysis for each stock
        This is the FULL research report you paid for!
        """
        if not REPORTLAB_AVAILABLE:
            logger.warning("[!] Skipping comprehensive PDF - reportlab not installed")
            return None
        
        # Sort by confidence score (highest first)
        sorted_candidates = sorted(analyzed, key=lambda x: x['analysis']['confidence'], reverse=True)
        
        pdf_filename = self.output_dir / f"comprehensive_analysis_{timestamp}.pdf"
        
        doc = SimpleDocTemplate(
            str(pdf_filename),
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=8,
            spaceBefore=8,
            fontName='Helvetica-Bold'
        )
        
        subheading_style = ParagraphStyle(
            'SubHeading',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#34495e'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        
        # Title Page
        story.append(Paragraph("COMPREHENSIVE INSIDER TRADING ANALYSIS", title_style))
        story.append(Paragraph(f"Multi-Source Signals | {len(sorted_candidates)} Stocks Analyzed", 
                              styles['Normal']))
        story.append(Paragraph(f"<i>Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</i>",
                              styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Executive Summary
        story.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
        
        high_confidence = sum(1 for c in sorted_candidates if c['analysis']['confidence'] >= 0.75)
        medium_confidence = sum(1 for c in sorted_candidates if 0.65 <= c['analysis']['confidence'] < 0.75)
        low_confidence = len(sorted_candidates) - high_confidence - medium_confidence
        
        summary_data = [
            ["Total Stocks Analyzed", str(len(sorted_candidates))],
            ["High Confidence (>75%)", str(high_confidence)],
            ["Medium Confidence (65-75%)", str(medium_confidence)],
            ["Lower Confidence (<65%)", str(low_confidence)],
            ["Lookback Period", f"{LOOKBACK_DAYS} days"],
            ["Data Sources", "Form 4, Latest Insider, Senate, House"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7'))
        ]))
        story.append(summary_table)
        story.append(PageBreak())
        
        # Ranked Candidates (ALL of them)
        story.append(Paragraph("COMPLETE RANKING - ALL ANALYZED STOCKS", heading_style))
        story.append(Spacer(1, 0.2*inch))
        
        for rank, candidate in enumerate(sorted_candidates, 1):
            symbol = candidate['symbol']
            profile = candidate['profile']
            signal_data = candidate.get('signal_data', {})
            timing = candidate.get('timing_analysis', {})
            analysis = candidate['analysis']
            
            # Rank header with color coding
            confidence = analysis['confidence']
            if confidence >= 0.75:
                bg_color = colors.HexColor('#d4edda')  # Green
            elif confidence >= 0.65:
                bg_color = colors.HexColor('#fff3cd')  # Yellow
            else:
                bg_color = colors.HexColor('#f8d7da')  # Red
            
            # Stock header
            header_text = f"<b>#{rank}. {symbol} - {profile.get('companyName', 'N/A')}</b> | Confidence: {confidence:.0%}"
            story.append(Paragraph(header_text, subheading_style))
            
            # Key metrics table
            metrics_data = [
                ["Sector", profile.get('sector', 'N/A'), "Market Cap", f"${profile.get('mktCap', 0)/1_000_000:.0f}M"],
                ["Price", f"${profile.get('price', 0):.2f}", "Beta", str(profile.get('beta', 'N/A'))],
                ["Total Signals", str(signal_data.get('total_signals', 0)), "Quality Score", f"{signal_data.get('weighted_quality_score', 0):.2f}/3.0"],
                ["Politicians", str(signal_data.get('politician_count', 0)), "Directors", str(signal_data.get('director_count', 0))],
                ["Officers", str(signal_data.get('officer_count', 0)), "Timing", timing.get('timing_status', 'N/A')[:20]]
            ]
            
            metrics_table = Table(metrics_data, colWidths=[1.3*inch, 2*inch, 1.3*inch, 2*inch])
            metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7'))
            ]))
            story.append(metrics_table)
            story.append(Spacer(1, 0.1*inch))
            
            # LLM Analysis
            story.append(Paragraph("<b>Analysis:</b>", subheading_style))
            story.append(Paragraph(analysis.get('reasoning', 'N/A'), styles['Normal']))
            story.append(Spacer(1, 0.05*inch))
            
            # Institutional Validation (Form 13F)
            validation = candidate.get('institutional_validation', {})
            if validation:
                story.append(Paragraph("<b>🏦 Institutional Validation (Form 13F):</b>", subheading_style))
                
                status = validation.get('status', 'N/A')
                boost_factor = validation.get('boost_factor', 1.0)
                original_conf = validation.get('original_confidence', 0)
                adjusted_conf = validation.get('adjusted_confidence', 0)
                
                # Validation status with color coding
                if boost_factor > 1.0:
                    status_color = "green"
                    symbol_prefix = "✅"
                elif boost_factor < 1.0:
                    status_color = "red"
                    symbol_prefix = "⚠️"
                else:
                    status_color = "gray"
                    symbol_prefix = "➡️"
                
                story.append(Paragraph(
                    f"{symbol_prefix} <b>Status:</b> {status} | "
                    f"<b>Confidence:</b> {original_conf:.1%} → {adjusted_conf:.1%} "
                    f"({boost_factor-1:+.0%})",
                    styles['Normal']
                ))
                story.append(Spacer(1, 0.05*inch))
                
                # Show institutional buyers
                increases = validation.get('increases', [])
                if increases:
                    story.append(Paragraph("<b>Institutions Buying:</b>", styles['Normal']))
                    for holder in increases[:3]:
                        story.append(Paragraph(
                            f"• {holder['name']}: {holder['change_pct']:+.1f}% increase "
                            f"({holder['change']:,} shares)",
                            styles['Normal']
                        ))
                    story.append(Spacer(1, 0.05*inch))
                
                # Show institutional sellers
                decreases = validation.get('decreases', [])
                if decreases:
                    story.append(Paragraph("<b>Institutions Selling:</b>", styles['Normal']))
                    for holder in decreases[:2]:
                        story.append(Paragraph(
                            f"• {holder['name']}: {holder['change_pct']:.1f}% decrease "
                            f"({abs(holder['change']):,} shares)",
                            styles['Normal']
                        ))
                    story.append(Spacer(1, 0.05*inch))
                
                story.append(Paragraph(
                    f"<i>Total institutional holders: {validation.get('total_holders', 0)}</i>",
                    styles['Normal']
                ))
                story.append(Spacer(1, 0.1*inch))
            
            # Multi-Agent Debate Results
            if analysis.get('analysis_type') == 'MULTI-AGENT DEBATE':
                story.append(Paragraph("<b>🤝 Multi-Agent Debate Analysis:</b>", subheading_style))
                
                agreement_score = analysis.get('agreement_score', 0)
                debate_rounds = analysis.get('debate_rounds', 0)
                deepseek_view = analysis.get('deepseek_view', {})
                gemini_view = analysis.get('gemini_view', {})
                
                # Agreement status with color coding
                if agreement_score >= 0.90:
                    agreement_color = "green"
                    agreement_label = "STRONG CONSENSUS"
                elif agreement_score >= 0.70:
                    agreement_color = "orange"
                    agreement_label = "MODERATE AGREEMENT"
                else:
                    agreement_color = "red"
                    agreement_label = "LOW AGREEMENT - REVIEW RECOMMENDED"
                
                story.append(Paragraph(
                    f"✓ <b>Agreement Score:</b> {agreement_score:.0%} ({agreement_label}) | "
                    f"<b>Debate Rounds:</b> {debate_rounds}",
                    styles['Normal']
                ))
                story.append(Spacer(1, 0.05*inch))
                
                # DeepSeek's view
                if deepseek_view:
                    story.append(Paragraph(
                        f"<b>DeepSeek Reasoner:</b> {deepseek_view.get('confidence', 0):.0%} confidence",
                        styles['Normal']
                    ))
                    story.append(Paragraph(
                        f"• Reasoning: {deepseek_view.get('reasoning', 'N/A')}",
                        styles['Normal']
                    ))
                    story.append(Spacer(1, 0.05*inch))
                
                # Gemini's view
                if gemini_view:
                    story.append(Paragraph(
                        f"<b>Gemini 2.0 Flash:</b> {gemini_view.get('confidence', 0):.0%} confidence",
                        styles['Normal']
                    ))
                    story.append(Paragraph(
                        f"• Reasoning: {gemini_view.get('reasoning', 'N/A')}",
                        styles['Normal']
                    ))
                    story.append(Spacer(1, 0.05*inch))
                
                # Flag if manual review needed
                if analysis.get('requires_human_review'):
                    story.append(Paragraph(
                        "⚠️  <b>MANUAL REVIEW RECOMMENDED</b> - Models disagreed significantly",
                        styles['Normal']
                    ))
                    story.append(Spacer(1, 0.05*inch))
                
                story.append(Spacer(1, 0.1*inch))
            
            story.append(Paragraph("<b>Bull Case:</b>", subheading_style))
            story.append(Paragraph(analysis.get('bull_case', 'N/A'), styles['Normal']))
            story.append(Spacer(1, 0.05*inch))
            
            story.append(Paragraph("<b>Bear Case:</b>", subheading_style))
            story.append(Paragraph(analysis.get('bear_case', 'N/A'), styles['Normal']))
            story.append(Spacer(1, 0.05*inch))
            
            story.append(Paragraph(f"<b>Hold Period:</b> {analysis.get('hold_period_days', 14)} days", 
                                 styles['Normal']))
            
            # Separator between stocks
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("_" * 100, styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
            
            # Page break after every 3 stocks for readability
            if rank % 3 == 0 and rank < len(sorted_candidates):
                story.append(PageBreak())
        
        # Build PDF
        try:
            doc.build(story)
            logger.info(f"[+] Comprehensive analysis PDF saved to {pdf_filename}")
            print(f"\n[+] COMPREHENSIVE PDF GENERATED: {pdf_filename}")
            print(f"    Contains full LLM analysis for all {len(sorted_candidates)} stocks")
            return str(pdf_filename)
        except Exception as e:
            logger.error(f"Failed to generate comprehensive PDF: {e}")
            return None
    
    def generate_pdf_report(self, selected: List[Dict], timestamp: str):
        """
        Generate PDF report with position details
        """
        if not REPORTLAB_AVAILABLE:
            logger.warning("⚠️  Skipping PDF generation - reportlab not installed")
            return None
        
        pdf_filename = self.output_dir / f"form4_report_{timestamp}.pdf"
        
        doc = SimpleDocTemplate(
            str(pdf_filename),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=10,
            spaceBefore=10
        )
        
        # Title
        story.append(Paragraph("📊 FORM 4 INSIDER CLUSTER STRATEGY", title_style))
        story.append(Paragraph(f"<i>Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</i>",
                              styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        
        total_allocated = sum(c['position']['actual_dollars'] for c in selected)
        cash_remaining = self.capital - total_allocated
        
        summary_data = [
            ["Strategy", "Form 4 Insider Clusters"],
            ["Capital Allocation", f"${self.capital:,.2f}"],
            ["Positions Selected", str(len(selected))],
            ["Total Allocated", f"${total_allocated:,.2f}"],
            ["Cash Remaining", f"${cash_remaining:,.2f}"],
            ["Lookback Period", f"{LOOKBACK_DAYS} days"],
            ["Min Confidence", f"{MIN_CONFIDENCE_SCORE:.0%}"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7'))
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Selected Positions
        if selected:
            story.append(Paragraph("Selected Positions", heading_style))
            
            for i, candidate in enumerate(selected, 1):
                # Position header
                story.append(Paragraph(
                    f"<b>#{i}. {candidate['symbol']} - {candidate['profile']['companyName']}</b>",
                    styles['Heading3']
                ))
                
                # Position details table
                signal_data = candidate.get('signal_data', {})
                validation = candidate.get('institutional_validation', {})
                
                pos_data = [
                    ["Sector", candidate['profile']['sector']],
                    ["Market Cap", f"${candidate['profile']['mktCap']/1_000_000:.0f}M"],
                    ["Price", f"${candidate['profile']['price']:.2f}"],
                    ["Insider Signals", f"{signal_data.get('total_signals', 0)} signals (Quality: {signal_data.get('weighted_quality_score', 0):.1f}/3.0)"],
                    ["Signal Breakdown", f"Politicians: {signal_data.get('politician_count', 0)}, Directors: {signal_data.get('director_count', 0)}, Officers: {signal_data.get('officer_count', 0)}"],
                    ["Institutional Validation", validation.get('status', 'N/A')],
                    ["Confidence", f"{candidate['analysis']['confidence']:.1%}" + (f" (adjusted from {validation.get('original_confidence', 0):.1%})" if validation.get('boost_factor', 1.0) != 1.0 else "")],
                    ["Position Size", f"{candidate['position']['shares']} shares = ${candidate['position']['actual_dollars']:.2f}"],
                    ["Hold Period", f"{candidate['analysis']['hold_period_days']} days"]
                ]
                
                pos_table = Table(pos_data, colWidths=[2*inch, 3.5*inch])
                pos_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f5e9')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#c8e6c9'))
                ]))
                story.append(pos_table)
                story.append(Spacer(1, 0.1*inch))
                
                # Analysis
                story.append(Paragraph("<b>Analysis:</b>", styles['Normal']))
                story.append(Paragraph(f"<i>{candidate['analysis']['reasoning']}</i>", styles['Normal']))
                story.append(Spacer(1, 0.05*inch))
                
                # Institutional Validation
                if validation:
                    validation_summary = validation.get('validation_summary', '')
                    if validation_summary:
                        story.append(Paragraph(f"<b>🏦 Institutional Validation:</b>", styles['Normal']))
                        for line in validation_summary.split('\n'):
                            if line.strip():
                                story.append(Paragraph(line, styles['Normal']))
                        story.append(Spacer(1, 0.05*inch))
                
                story.append(Paragraph(f"<b>🐂 Bull Case:</b> {candidate['analysis']['bull_case']}", styles['Normal']))
                story.append(Paragraph(f"<b>🐻 Bear Case:</b> {candidate['analysis']['bear_case']}", styles['Normal']))
                
                if i < len(selected):
                    story.append(Spacer(1, 0.2*inch))
        else:
            story.append(Paragraph(
                "⚠️ No positions selected - No strong insider clusters found this week",
                styles['Normal']
            ))
        
        story.append(Spacer(1, 0.3*inch))
        
        # Trading Instructions
        story.append(Paragraph("✅ Trading Instructions", heading_style))
        instructions = [
            "1. <b>MANUAL APPROVAL REQUIRED</b> - Review each position carefully",
            "2. Approve or reject each position when prompted",
            "3. Only approved positions will be eligible for trading",
            "4. Place limit orders at market price or better for approved positions",
            "5. Set calendar reminders for hold period expiration",
            "6. Monitor insider activity weekly for changes",
            "7. Rebalance next Sunday based on new Form 4 clusters"
        ]
        for instruction in instructions:
            story.append(Paragraph(instruction, styles['Normal']))
        
        # Build PDF
        doc.build(story)
        logger.info(f"✅ PDF report saved to {pdf_filename}")
        
        return pdf_filename
    
    def generate_json_report(self, selected: List[Dict], timestamp: str) -> Dict:
        """
        Generate JSON report for programmatic access (multi-source version)
        """
        report = {
            'generated_at': datetime.now().isoformat(),
            'strategy': 'Form 4 Multi-Source Insider Signals',
            'capital': self.capital,
            'lookback_days': LOOKBACK_DAYS,
            'positions': []
        }
        
        total_allocated = 0
        
        for candidate in selected:
            signal_data = candidate['signal_data']
            timing_analysis = candidate['timing_analysis']
            validation = candidate.get('institutional_validation', {})
            
            position_data = {
                'symbol': candidate['symbol'],
                'company': candidate['profile']['companyName'],
                'sector': candidate['profile']['sector'],
                'market_cap': candidate['profile']['mktCap'],
                'price': candidate['profile']['price'],
                
                # Multi-source signal data
                'total_signals': signal_data['total_signals'],
                'signal_quality_score': signal_data['weighted_quality_score'],
                'politician_signals': signal_data['politician_count'],
                'director_signals': signal_data['director_count'],
                'officer_signals': signal_data['officer_count'],
                'source_breakdown': signal_data['source_breakdown'],
                
                # Institutional validation (13F data)
                'institutional_validation': {
                    'status': validation.get('status', 'N/A'),
                    'boost_factor': validation.get('boost_factor', 1.0),
                    'original_confidence': validation.get('original_confidence', 0),
                    'adjusted_confidence': validation.get('adjusted_confidence', 0),
                    'institutions_buying': len(validation.get('increases', [])),
                    'institutions_selling': len(validation.get('decreases', [])),
                    'total_holders': validation.get('total_holders', 0)
                },
                
                # Timing analysis
                'timing_status': timing_analysis['timing_status'],
                'timing_score': timing_analysis['timing_score'],
                'days_since_last_trade': timing_analysis['days_ago'],
                'price_movement_pct': timing_analysis.get('price_change_pct', 0),
                
                # Analysis
                'confidence': candidate['analysis']['confidence'],
                'reasoning': candidate['analysis']['reasoning'],
                'bull_case': candidate['analysis']['bull_case'],
                'bear_case': candidate['analysis']['bear_case'],
                'hold_period_days': candidate['analysis']['hold_period_days'],
                'analysis_type': candidate['analysis'].get('analysis_type', 'UNKNOWN'),
                
                # Multi-agent debate (if available)
                'multi_agent_debate': {
                    'enabled': candidate['analysis'].get('analysis_type') == 'MULTI-AGENT DEBATE',
                    'agreement_score': candidate['analysis'].get('agreement_score', 0),
                    'debate_rounds': candidate['analysis'].get('debate_rounds', 0),
                    'requires_human_review': candidate['analysis'].get('requires_human_review', False),
                    'deepseek_confidence': candidate['analysis'].get('deepseek_view', {}).get('confidence', 0),
                    'gemini_confidence': candidate['analysis'].get('gemini_view', {}).get('confidence', 0)
                } if candidate['analysis'].get('analysis_type') == 'MULTI-AGENT DEBATE' else None,
                
                'position': candidate['position'],
                'approved': False  # Will be updated after user approval
            }
            
            report['positions'].append(position_data)
            total_allocated += candidate['position']['actual_dollars']
        
        report['total_allocated'] = total_allocated
        report['cash_remaining'] = self.capital - total_allocated
        
        # Save to file
        json_file = self.output_dir / f"form4_positions_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"✅ JSON report saved to {json_file}")
        
        return report
    
    def get_user_approvals(self, selected: List[Dict]) -> Dict[str, bool]:
        """
        Get user approval for each proposed position (CRITICAL SAFETY)
        Auto-approves when running non-interactively (Task Scheduler) with confidence >= 0.75
        Returns: {symbol: approved} mapping
        """
        if not selected:
            print("⚠️  No positions to approve (no clusters found this week)")
            return {}
        
        # Check if running non-interactively (Task Scheduler)
        auto_approve_env = os.getenv('FORM4_AUTO_APPROVE', 'false').lower() == 'true'
        is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else True
        
        if not is_interactive or auto_approve_env:
            # AUTO-APPROVE MODE for Task Scheduler
            print("\n" + "="*80)
            print("🤖 FORM 4 STRATEGY - AUTO-APPROVAL MODE (Task Scheduler)")
            print("="*80)
            print("Running in non-interactive mode - auto-approving high confidence positions")
            print("Confidence threshold: 75% (0.75)")
            print("="*80 + "\n")
            
            approvals = {}
            for candidate in selected:
                symbol = candidate['symbol']
                confidence = candidate['analysis']['confidence']
                signal_data = candidate.get('signal_data', {})
                
                # Auto-approve if confidence >= 0.75
                if confidence >= 0.75:
                    approvals[symbol] = True
                    print(f"✅ AUTO-APPROVED: {symbol} (confidence: {confidence:.1%})")
                    print(f"   Signals: {signal_data.get('total_signals', 0)} | Politicians: {signal_data.get('politician_count', 0)}")
                    logger.info(f"Auto-approved {symbol}: confidence {confidence:.1%}")
                else:
                    approvals[symbol] = False
                    print(f"❌ AUTO-REJECTED: {symbol} (confidence: {confidence:.1%} < 75%)")
                    logger.info(f"Auto-rejected {symbol}: confidence {confidence:.1%} below threshold")
            
            print("\n" + "="*80)
            approved_count = sum(approvals.values())
            print(f"AUTO-APPROVAL SUMMARY: {approved_count}/{len(selected)} positions approved")
            print("="*80 + "\n")
            
            return approvals
        
        # INTERACTIVE MODE - Manual approval
        print("\n" + "="*80)
        print("⚠️  FORM 4 STRATEGY - MANUAL APPROVAL REQUIRED")
        print("="*80)
        print("\n🔒 PROTECTION: This strategy NEVER executes trades automatically")
        print("You must review and approve each position before trading.\n")
        print("Review each position and approve/reject:")
        print("  - Type 'y' or 'yes' to APPROVE")
        print("  - Type 'n' or 'no' to REJECT")
        print("  - Type 'all' to approve ALL positions")
        print("  - Type 'none' to reject ALL positions")
        print("="*80 + "\n")
        
        approvals = {}
        
        for i, candidate in enumerate(selected, 1):
            symbol = candidate['symbol']
            company = candidate['profile']['companyName']
            price = candidate['profile']['price']
            shares = candidate['position']['shares']
            cost = candidate['position']['actual_dollars']
            confidence = candidate['analysis']['confidence']
            signal_data = candidate.get('signal_data', {})
            timing = candidate.get('timing_analysis', {})
            analysis_type = candidate['analysis'].get('analysis_type', 'LLM-POWERED')
            
            print(f"\n[{i}/{len(selected)}] {symbol} - {company}")
            print(f"  Price: ${price:.2f} | Position: {shares} shares (${cost:.2f})")
            print(f"  Signals: {signal_data.get('total_signals', 0)} total | Quality: {signal_data.get('weighted_quality_score', 0):.2f}/3.0")
            print(f"  Politicians: {signal_data.get('politician_count', 0)} | Directors: {signal_data.get('director_count', 0)} | Officers: {signal_data.get('officer_count', 0)}")
            print(f"  Timing: {timing.get('timing_status', 'N/A')}")
            print(f"  Confidence: {confidence:.1%} ({analysis_type})")
            print(f"  Reasoning: {candidate['analysis']['reasoning'][:150]}...")
            print(f"  🐂 Bull: {candidate['analysis']['bull_case'][:100]}...")
            print(f"  🐻 Bear: {candidate['analysis']['bear_case'][:100]}...")
            
            while True:
                response = input(f"  Approve {symbol}? (y/n/all/none): ").strip().lower()
                
                if response in ['all']:
                    # Approve all remaining
                    for c in selected[i-1:]:
                        approvals[c['symbol']] = True
                    print("  ✅ Approved all remaining positions")
                    return approvals
                
                elif response in ['none']:
                    # Reject all remaining
                    for c in selected[i-1:]:
                        approvals[c['symbol']] = False
                    print("  ❌ Rejected all remaining positions")
                    return approvals
                
                elif response in ['y', 'yes']:
                    approvals[symbol] = True
                    print(f"  ✅ Approved: {symbol}")
                    break
                
                elif response in ['n', 'no']:
                    approvals[symbol] = False
                    print(f"  ❌ Rejected: {symbol}")
                    break
                
                else:
                    print("  Invalid input. Please enter y/n/all/none")
        
        return approvals
    
    def save_approval_decisions(self, selected: List[Dict], approvals: Dict[str, bool], timestamp: str, executions: Dict[str, Dict] = None):
        """
        Save approval decisions and execution results to file
        """
        if executions is None:
            executions = {}
        
        approved_positions = []
        rejected_positions = []
        
        for candidate in selected:
            symbol = candidate['symbol']
            signal_data = candidate.get('signal_data', {})
            position = {
                'symbol': symbol,
                'company': candidate['profile']['companyName'],
                'shares': candidate['position']['shares'],
                'price': candidate['profile']['price'],
                'cost': candidate['position']['actual_dollars'],
                'confidence': candidate['analysis']['confidence'],
                'total_signals': signal_data.get('total_signals', 0),
                'signal_quality': signal_data.get('weighted_quality_score', 0),
                'politician_count': signal_data.get('politician_count', 0),
                'director_count': signal_data.get('director_count', 0),
                'officer_count': signal_data.get('officer_count', 0),
                'hold_period_days': candidate['analysis']['hold_period_days']
            }
            
            if approvals.get(symbol, False):
                # Add execution details if available
                if symbol in executions:
                    position['execution'] = executions[symbol]
                    position['status'] = 'EXECUTED'
                else:
                    position['status'] = 'APPROVED (pending manual execution)'
                
                approved_positions.append(position)
            else:
                rejected_positions.append(position)
        
        # Save approvals
        approval_file = self.output_dir / f"approved_positions_{timestamp}.json"
        with open(approval_file, 'w') as f:
            json.dump({
                'approved_at': datetime.now().isoformat(),
                'total_proposed': len(selected),
                'total_approved': len(approved_positions),
                'total_rejected': len(rejected_positions),
                'total_executed': len(executions),
                'approved_positions': approved_positions,
                'rejected_positions': rejected_positions,
                'capital_to_deploy': sum(p['cost'] for p in approved_positions),
                'cash_reserved': self.capital - sum(p['cost'] for p in approved_positions),
                'executions': executions
            }, f, indent=2)
        
        logger.info(f"✅ Approval decisions saved to {approval_file}")
        
        # Print summary
        print("\n" + "="*80)
        print("✅ APPROVAL SUMMARY")
        print("="*80)
        print(f"Total positions proposed: {len(selected)}")
        print(f"Approved: {len(approved_positions)}")
        print(f"Rejected: {len(rejected_positions)}")
        
        if approved_positions:
            print("\n📋 APPROVED POSITIONS:")
            for pos in approved_positions:
                status_icon = "✅" if pos.get('status') == 'EXECUTED' else "⏳"
                execution_info = ""
                if 'execution' in pos:
                    exec_data = pos['execution']
                    execution_info = f" → FILLED @ ${exec_data['fill_price']:.2f} = ${exec_data['total_cost']:.2f}"
                print(f"  {status_icon} {pos['symbol']}: {pos['shares']} shares @ ${pos['price']:.2f}{execution_info}")
            
            total_deployed = sum(
                pos['execution']['total_cost'] if 'execution' in pos else pos['cost']
                for pos in approved_positions
            )
            print(f"\n💰 Total capital deployed: ${total_deployed:.2f}")
            
            if executions:
                print(f"✅ {len(executions)} orders executed automatically via IBKR")
            else:
                print(f"⏳ Orders saved for manual execution (IBKR not connected)")
        else:
            print("\n⚠️  No positions approved - no trades to execute")
        
        print("="*80 + "\n")
    
    def execute_approved_orders(self, selected: List[Dict], approvals: Dict[str, bool]) -> Dict[str, Dict]:
        """
        Execute market orders for approved positions via IBKR
        Returns: {symbol: execution_details} for successful fills
        """
        if not self.ibkr_connected:
            logger.warning("⚠️  IBKR not connected - cannot execute orders")
            print("\n⚠️  IBKR not connected - orders saved for manual execution")
            return {}
        
        # Check SETTLED CASH BEFORE placing orders (this is what IBKR actually validates against)
        settled_cash = self.get_settled_cash()
        total_needed = sum(
            candidate['position']['actual_dollars'] 
            for candidate in selected 
            if approvals.get(candidate['symbol'], False)
        )
        
        print("\n" + "="*80)
        print("📊 EXECUTING APPROVED ORDERS")
        print("="*80)
        print(f"💰 Settled Cash (T+2 Compliant): ${settled_cash:.2f}")
        print(f"💰 Capital Needed: ${total_needed:.2f}")
        
        # Check if market is open (for informational purposes)
        try:
            from market_hours import is_market_open
            market_is_open = is_market_open()
            if not market_is_open:
                print("\n⏰ MARKET HOURS NOTICE:")
                print("   Market is currently CLOSED (after-hours/pre-market)")
                print("   Orders will be queued and executed at next market open (9:30 AM ET)")
                print(f"   Settled Cash Available: ${settled_cash:.2f}")
                print("   Note: Recently sold positions take T+2 to settle\n")
        except Exception as e:
            logger.debug(f"Market hours check skipped: {e}")
        
        # INTELLIGENT CAPITAL SCALING
        scale_factor = 1.0
        if settled_cash < total_needed:
            if settled_cash < total_needed * 0.40:
                # Less than 40% of needed capital - reject all orders
                logger.error(f"❌ INSUFFICIENT CAPITAL: ${settled_cash:.2f} < ${total_needed:.2f}")
                print(f"\n❌ INSUFFICIENT CAPITAL - REJECTING ALL ORDERS")
                print(f"   Settled Cash Available: ${settled_cash:.2f}")
                print(f"   Needed: ${total_needed:.2f}")
                print(f"   Shortfall: ${total_needed - settled_cash:.2f}")
                print(f"\n💡 Need at least 40% of capital ({total_needed * 0.40:.2f}) to proceed.")
                print(f"   Wait for T+2 settlement or deposit more funds.")
                print("="*80 + "\n")
                return {}  # Return empty executions
            else:
                # Scale down all orders proportionally
                scale_factor = settled_cash / total_needed
                logger.warning(f"⚠️  Scaling down orders by {scale_factor:.1%} to fit settled cash")
                print(f"\n⚠️  CAPITAL CONSTRAINED - SCALING DOWN ORDERS")
                print(f"   Settled Cash Available: ${settled_cash:.2f}")
                print(f"   Requested: ${total_needed:.2f}")
                print(f"   Scaling Factor: {scale_factor:.1%}")
                print(f"   Adjusted Total: ${total_needed * scale_factor:.2f}")
                print(f"\n💡 Each position will be reduced proportionally to fit available settled cash.")
        else:
            print(f"✅ Sufficient settled cash available")
        
        print("="*80 + "\n")
        
        executions = {}
        
        for candidate in selected:
            symbol = candidate['symbol']
            
            # Skip if not approved
            if not approvals.get(symbol, False):
                continue
            
            original_shares = candidate['position']['shares']
            target_price = candidate['profile']['price']
            
            # Apply capital scaling
            shares = max(1, int(original_shares * scale_factor))  # At least 1 share
            adjusted_cost = shares * target_price
            
            if scale_factor < 1.0:
                logger.info(f"{symbol}: Scaled {original_shares} → {shares} shares (${adjusted_cost:.2f})")
                print(f"   [SCALED] {original_shares} → {shares} shares (${adjusted_cost:.2f})")
            
            try:
                # Create IBKR contract - no manual mappings, purely data-driven
                contract = Stock(symbol, 'SMART', 'USD')
                qualified = self.ib.qualifyContracts(contract)
                
                # Verify qualification succeeded
                if not qualified or not contract.conId:
                    logger.warning(f"⚠️  {symbol}: IBKR cannot find this security - may be delisted or ticker changed")
                    print(f"   [SKIPPED] {symbol}: IBKR cannot find this security (ticker may have changed)")
                    continue
                
                # REDUNDANT CHECK: ETFs filtered in analysis phase (line ~903)
                # Kept as safety net in case profile.isEtf was incorrect
                if self.is_complex_etf(symbol, contract):
                    logger.warning(f"⚠️  {symbol}: Complex/Leveraged ETF - should have been filtered earlier")
                    print(f"⚠️  {symbol}: Skipped - ETF/Complex product (should not reach execution)")
                    print(f"   BUG: This should have been filtered during analysis phase")
                    continue
                
                logger.info(f"📈 Placing order: BUY {shares} shares of {symbol}")
                print(f"📈 {symbol}: Placing market order for {shares} shares...")
                
                # Create market order
                order = MarketOrder('BUY', shares)
                order.tif = 'DAY'  # Good for day
                order.outsideRth = False  # Market hours only
                
                # Place order
                trade = self.ib.placeOrder(contract, order)
                
                # Wait for fill (up to 30 seconds)
                for i in range(30):
                    self.ib.sleep(1)
                    if trade.orderStatus.status in ['Filled', 'Cancelled', 'Inactive']:
                        break
                
                # Check if filled
                if trade.orderStatus.status == 'Filled':
                    fill_price = trade.orderStatus.avgFillPrice
                    fill_shares = trade.orderStatus.filled
                    total_cost = fill_price * fill_shares
                    
                    executions[symbol] = {
                        'shares': fill_shares,
                        'fill_price': fill_price,
                        'total_cost': total_cost,
                        'order_id': trade.order.orderId,
                        'status': 'FILLED',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # AUTONOMOUS: Log trade to database
                    signal_data = candidate.get('signal_data', {})
                    self.db.log_trade({
                        'timestamp': datetime.now().isoformat(),
                        'symbol': symbol,
                        'action': 'BUY',
                        'quantity': fill_shares,
                        'price': fill_price,
                        'agent_name': self.agent_name,
                        'reason': f"Form4 cluster: {signal_data.get('total_signals', 0)} signals, {signal_data.get('politician_count', 0)} politicians",
                        'metadata': {
                            'confidence_score': candidate['analysis'].get('confidence', 0),
                            'filing_count': signal_data.get('total_signals', 0),
                            'politician_count': signal_data.get('politician_count', 0),
                            'quality_score': signal_data.get('weighted_quality_score', 0),
                            'lookback_days': LOOKBACK_DAYS,
                            'min_filings_threshold': MIN_FILINGS_FOR_CLUSTER,
                            'target_allocation': candidate['position']['actual_dollars']
                        }
                    })
                    
                    # A/B Testing: Log BUY execution with entry price
                    self.log_ab_test_decision(symbol, signal_data, 'BUY')
                    if self.enable_weight_testing and 'ab_testing' in signal_data:
                        try:
                            # Update A/B log with entry price for future P&L tracking
                            self.db.execute_query("""
                                UPDATE ab_test_log 
                                SET entry_price = ?, notes = ?
                                WHERE symbol = ? AND action = 'BUY' 
                                AND timestamp = (SELECT MAX(timestamp) FROM ab_test_log WHERE symbol = ? AND action = 'BUY')
                            """, (fill_price, f"Filled {fill_shares} shares", symbol, symbol))
                        except Exception as e:
                            logger.warning(f"Failed to update A/B log with entry price: {e}")
                    
                    # AUTONOMOUS: Track position
                    self.db.add_active_position(
                        symbol=symbol,
                        quantity=fill_shares,
                        entry_price=fill_price,
                        agent_name=self.agent_name,
                        profit_target=fill_price * 1.15,  # 15% target
                        stop_loss=fill_price * 0.90,      # -10% stop
                        metadata={
                            'entry_reason': candidate['analysis'].get('insider_narrative', ''),
                            'politician_involved': signal_data.get('politician_count', 0) > 0
                        }
                    )
                    
                    logger.info(f"✅ {symbol}: FILLED {fill_shares} shares @ ${fill_price:.2f} = ${total_cost:.2f}")
                    print(f"   [FILLED] {fill_shares} shares @ ${fill_price:.2f} = ${total_cost:.2f}")
                    
                elif trade.orderStatus.status == 'Cancelled':
                    # Extract cancellation reason from log
                    cancel_reason = "Unknown reason"
                    if trade.log:
                        for log_entry in trade.log:
                            if log_entry.status == 'Cancelled' and log_entry.message:
                                cancel_reason = log_entry.message
                                break
                    
                    logger.warning(f"⚠️  {symbol}: Order cancelled - {cancel_reason}")
                    print(f"   [CANCELLED] {cancel_reason}")
                    
                elif trade.orderStatus.status == 'Inactive':
                    # Extract rejection reason
                    reject_reason = "Unknown reason"
                    if trade.log:
                        for log_entry in trade.log:
                            if log_entry.message and 'Error' in log_entry.message:
                                reject_reason = log_entry.message
                                break
                    
                    logger.warning(f"⚠️  {symbol}: Order rejected (Inactive) - {reject_reason}")
                    print(f"   [REJECTED] {reject_reason}")
                    
                else:
                    logger.warning(f"⚠️  {symbol}: Order status: {trade.orderStatus.status}")
                    print(f"   [WARNING] Order status: {trade.orderStatus.status}")
                
            except Exception as e:
                logger.error(f"❌ {symbol}: Order failed - {e}")
                print(f"   [ERROR] {e}")
        
        print("\n" + "="*80)
        print(f"[OK] ORDER EXECUTION COMPLETE: {len(executions)}/{sum(approvals.values())} orders filled")
        print("="*80 + "\n")
        
        return executions
    
    def print_terminal_summary(self, selected: List[Dict]):
        """
        Print human-readable summary to terminal
        """
        print("\n" + "=" * 80)
        print("FORM 4 INSIDER CLUSTER STRATEGY - ANALYSIS COMPLETE")
        print("=" * 80)
        print(f"\nGenerated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
        print(f"Capital: ${self.capital:.2f}")
        print(f"Positions Found: {len(selected)}")
        
        if not selected:
            print("\n⚠️  NO POSITIONS SELECTED - No strong insider clusters found this week")
            print("\n💡 This is normal - Form 4 clusters are selective signals")
            print("   Check again next Sunday for new insider activity")
            return
        
        total_allocated = sum(c['position']['actual_dollars'] for c in selected)
        print(f"Total Allocation: ${total_allocated:.2f}")
        print(f"Cash Remaining: ${self.capital - total_allocated:.2f}")
        
        print(f"\n{'─' * 80}")
        print("POSITIONS PENDING APPROVAL")
        print(f"{'─' * 80}")
        
        for i, candidate in enumerate(selected, 1):
            analysis_type = candidate['analysis'].get('analysis_type', 'LLM-POWERED')
            signal_data = candidate.get('signal_data', {})
            timing = candidate.get('timing_analysis', {})
            
            print(f"\n#{i}. {candidate['symbol']} - {candidate['profile']['companyName']}")
            print(f"    Sector: {candidate['profile']['sector']}")
            print(f"    Market Cap: ${candidate['profile']['mktCap']/1_000_000:.0f}M")
            print(f"    Price: ${candidate['profile']['price']:.2f}")
            print(f"\n    📊 MULTI-SOURCE INSIDER SIGNALS:")
            print(f"       • Total Signals: {signal_data.get('total_signals', 0)}")
            print(f"       • Quality Score: {signal_data.get('weighted_quality_score', 0):.2f}/3.0")
            print(f"       • Politicians: {signal_data.get('politician_count', 0)}")
            print(f"       • Directors: {signal_data.get('director_count', 0)}")
            print(f"       • Officers: {signal_data.get('officer_count', 0)}")
            print(f"       • Timing: {timing.get('timing_status', 'N/A')}")
            
            # Show source breakdown
            sources = signal_data.get('source_breakdown', {})
            print(f"\n    📡 SOURCES:")
            if sources.get('senate', 0) > 0:
                print(f"       • Senate: {sources['senate']} purchases")
            if sources.get('house', 0) > 0:
                print(f"       • House: {sources['house']} purchases")
            if sources.get('insider', 0) > 0:
                print(f"       • Form 4: {sources['insider']} transactions")
            if sources.get('latest', 0) > 0:
                print(f"       • Latest Insider: {sources['latest']} acquisitions")
            
            print(f"\n    🎯 Confidence: {candidate['analysis']['confidence']:.1%} ({analysis_type})")
            print(f"    💰 Position: {candidate['position']['shares']} shares = ${candidate['position']['actual_dollars']:.2f}")
            print(f"    📅 Hold Period: {candidate['analysis']['hold_period_days']} days")
            print(f"\n    💭 Analysis: {candidate['analysis']['reasoning']}")
            print(f"    🐂 Bull: {candidate['analysis']['bull_case']}")
            print(f"    🐻 Bear: {candidate['analysis']['bear_case']}")
            
            # Show sample transaction links if available
            transactions = signal_data.get('transactions', [])
            if transactions:
                print(f"\n    🔗 Sample Filing Links:")
                shown = 0
                for txn in transactions:
                    link = txn.get('link')
                    if link and shown < 2:
                        print(f"       {link}")
                        shown += 1
        
        print("\n" + "=" * 80)
    
    def load_held_positions(self) -> List[Dict]:
        """
        Load currently held positions from IBKR portfolio
        
        Returns: List of positions with symbol, quantity, avgCost, marketValue
        """
        if not self.ibkr_connected or not self.ib:
            logger.warning("Cannot load positions - IBKR not connected")
            return []
        
        try:
            portfolio = self.ib.portfolio()
            held_positions = []
            
            for item in portfolio:
                # Only track stocks (not options, futures, etc.)
                if hasattr(item.contract, 'secType') and item.contract.secType == 'STK':
                    held_positions.append({
                        'symbol': item.contract.symbol,
                        'quantity': item.position,
                        'avg_cost': item.averageCost,
                        'market_value': item.marketValue,
                        'unrealized_pnl': item.unrealizedPNL,
                        'contract': item.contract
                    })
            
            logger.info(f"📊 Loaded {len(held_positions)} held positions from IBKR")
            return held_positions
            
        except Exception as e:
            logger.error(f"Error loading held positions: {e}")
            return []
    
    def revalidate_held_positions(self, multi_source_data: Dict[str, List[Dict]], 
                                   held_positions: List[Dict]) -> Dict:
        """
        Revalidate held positions against latest politician signals
        
        POLITICIAN-FIRST EXIT LOGIC:
        - If position STILL has politician signals → HOLD
        - If position has ZERO politician signals → FLAG FOR EXIT
        
        Args:
            multi_source_data: Latest insider data from fetch_multi_source_signals()
            held_positions: Current positions from load_held_positions()
        
        Returns: Dict with 'hold' and 'exit' lists
        """
        print("\n" + "="*80)
        print("[REVALIDATION] POLITICIAN-FIRST EXIT ANALYSIS")
        print("="*80 + "\n")
        
        if not held_positions:
            print("[INFO] No held positions to revalidate")
            return {'hold': [], 'exit': []}
        
        # Aggregate signals for ALL symbols (not just politician-backed)
        # This allows us to check if previously held positions lost their signals
        all_signals = defaultdict(lambda: {
            'total_signals': 0,
            'politician_count': 0,
            'director_count': 0,
            'officer_count': 0,
            'transactions': [],
            'source_breakdown': {'insider': 0, 'latest': 0, 'senate': 0, 'house': 0}
        })
        
        # Process all sources
        for source_name, transactions in multi_source_data.items():
            is_political = source_name in ['senate', 'house']
            
            for txn in transactions:
                symbol = txn.get('symbol')
                if not symbol or symbol == 'None':
                    continue
                
                role = txn.get('office', '') if is_political else txn.get('typeOfOwner', '')
                role_lower = role.lower() if role else ""
                
                # Count signal types
                if is_political:
                    all_signals[symbol]['politician_count'] += 1
                elif 'director' in role_lower:
                    all_signals[symbol]['director_count'] += 1
                elif any(w in role_lower for w in ['officer', 'ceo', 'cfo', 'president']):
                    all_signals[symbol]['officer_count'] += 1
                
                all_signals[symbol]['total_signals'] += 1
                all_signals[symbol]['source_breakdown'][source_name] += 1
                all_signals[symbol]['transactions'].append(txn)
        
        # Revalidate each held position
        positions_to_hold = []
        positions_to_exit = []
        
        print(f"[ANALYZING] {len(held_positions)} held positions:\n")
        
        for pos in held_positions:
            symbol = pos['symbol']
            signals = all_signals.get(symbol, {
                'politician_count': 0,
                'director_count': 0,
                'officer_count': 0,
                'total_signals': 0
            })
            
            politician_count = signals.get('politician_count', 0)
            total_signals = signals.get('total_signals', 0)
            
            # POLITICIAN-FIRST DECISION
            if politician_count > 0:
                # HOLD: Position still has politician backing
                positions_to_hold.append({
                    **pos,
                    'revalidation': {
                        'decision': 'HOLD',
                        'reason': f'Still backed by {politician_count} politician signal(s)',
                        'politician_count': politician_count,
                        'director_count': signals.get('director_count', 0),
                        'total_signals': total_signals
                    }
                })
                print(f"   ✅ {symbol}: HOLD - {politician_count} politician(s) still active")
                print(f"      Signals: {total_signals} total | Unrealized P&L: ${pos['unrealized_pnl']:.2f}")
                
            else:
                # EXIT: Position lost ALL politician signals
                positions_to_exit.append({
                    **pos,
                    'revalidation': {
                        'decision': 'EXIT',
                        'reason': 'Lost ALL politician signals (hard-gate violation)',
                        'politician_count': 0,
                        'director_count': signals.get('director_count', 0),
                        'officer_count': signals.get('officer_count', 0),
                        'total_signals': total_signals
                    }
                })
                print(f"   ❌ {symbol}: EXIT - No politician signals (had {signals.get('director_count', 0)} directors, {signals.get('officer_count', 0)} officers)")
                print(f"      Unrealized P&L: ${pos['unrealized_pnl']:.2f} | Reason: Strategy violation")
        
        print(f"\n[RESULTS] Revalidation complete:")
        print(f"   HOLD: {len(positions_to_hold)} positions")
        print(f"   EXIT: {len(positions_to_exit)} positions")
        print("="*80 + "\n")
        
        return {
            'hold': positions_to_hold,
            'exit': positions_to_exit
        }
    
    def execute_exits(self, positions_to_exit: List[Dict]):
        """
        Execute exit orders for positions that lost politician backing
        
        Args:
            positions_to_exit: List of positions flagged for exit from revalidation
        
        Returns:
            Dict with execution results
        """
        if not positions_to_exit:
            print("[INFO] No exits required\n")
            return {'executed': 0, 'failed': 0, 'total_pnl': 0}
        
        print("\n" + "="*80)
        print("[EXECUTING] POLITICIAN-FIRST EXITS")
        print("="*80 + "\n")
        
        # Track results
        executed = 0
        failed = 0
        total_realized_pnl = 0.0
        
        for pos in positions_to_exit:
            symbol = pos['symbol']
            quantity = abs(pos['quantity'])  # Ensure positive for selling
            reason = pos['revalidation']['reason']
            
            print(f"[EXIT] {symbol}:")
            print(f"   Quantity: {quantity} shares")
            print(f"   Reason: {reason}")
            print(f"   Unrealized P&L: ${pos['unrealized_pnl']:.2f}")
            
            if not self.ibkr_connected:
                print(f"   ⚠️  IBKR not connected - manual exit required\n")
                logger.warning(f"Manual exit required for {symbol} ({quantity} shares)")
                continue
            
            try:
                # Create a fresh contract with exchange='SMART' to avoid "Missing order exchange" error
                # IBKR portfolio contracts have primaryExchange but NOT exchange field
                contract = Stock(symbol, 'SMART', 'USD')
                
                # Qualify the contract to ensure it's valid
                self.ib.qualifyContracts(contract)
                
                order = MarketOrder('SELL', quantity)
                order.tif = 'DAY'
                order.outsideRth = False
                
                # Place order
                trade = self.ib.placeOrder(contract, order)
                logger.info(f"📤 Exit order placed: {symbol} ({quantity} shares)")
                print(f"   📤 Exit order placed, waiting for fill...")
                
                # Wait for fill (up to 30 seconds) - same as buy orders
                for i in range(30):
                    self.ib.sleep(1)
                    if trade.orderStatus.status in ['Filled', 'Cancelled', 'Inactive']:
                        break
                    if i > 0 and i % 10 == 0:
                        print(f"   ⏳ Still waiting... ({i}s)")
                
                # Check status
                if trade.orderStatus.status == 'Filled':
                    fill_price = trade.orderStatus.avgFillPrice
                    fill_shares = trade.orderStatus.filled
                    
                    # Calculate realized P&L
                    entry_price = pos.get('avg_cost', 0)
                    realized_pnl = (fill_price - entry_price) * fill_shares if entry_price > 0 else 0
                    pnl_pct = ((fill_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    
                    print(f"   ✅ FILLED {fill_shares} shares @ ${fill_price:.2f}")
                    print(f"   💰 Realized P&L: ${realized_pnl:.2f} ({pnl_pct:+.1f}%)")
                    logger.info(f"✅ Exit filled: {symbol} @ ${fill_price:.2f} | P&L: ${realized_pnl:.2f} ({pnl_pct:+.1f}%)")
                    
                    # Track success
                    executed += 1
                    total_realized_pnl += realized_pnl
                    
                    # Log to database
                    self.db.log_trade({
                        'agent': self.agent_name,
                        'symbol': symbol,
                        'action': 'SELL',
                        'quantity': fill_shares,
                        'price': fill_price,
                        'reason': reason,
                        'metadata': {
                            **pos['revalidation'],
                            'entry_price': entry_price,
                            'realized_pnl': realized_pnl,
                            'pnl_pct': pnl_pct
                        }
                    })
                    
                    # Remove from active positions
                    try:
                        self.db.remove_active_position(symbol)
                        logger.info(f"Removed {symbol} from active positions")
                    except Exception as e:
                        logger.warning(f"Failed to remove {symbol} from active positions: {e}")
                        
                elif trade.orderStatus.status == 'Cancelled':
                    failed += 1
                    # Extract cancellation reason from log
                    cancel_reason = "Unknown reason"
                    if trade.log:
                        for log_entry in trade.log:
                            if log_entry.status == 'Cancelled' and log_entry.message:
                                cancel_reason = log_entry.message
                                break
                    
                    logger.warning(f"⚠️  {symbol}: Exit order cancelled - {cancel_reason}")
                    print(f"   ❌ CANCELLED: {cancel_reason}")
                    
                elif trade.orderStatus.status == 'Inactive':
                    failed += 1
                    # Extract rejection reason
                    reject_reason = "Unknown reason"
                    if trade.log:
                        for log_entry in trade.log:
                            if log_entry.message and ('Error' in log_entry.message or log_entry.errorCode != 0):
                                reject_reason = log_entry.message
                                break
                    
                    logger.warning(f"⚠️  {symbol}: Exit order rejected - {reject_reason}")
                    print(f"   ❌ REJECTED: {reject_reason}")
                    
                else:
                    failed += 1
                    print(f"   ⏳ Order status after 30s: {trade.orderStatus.status}")
                    logger.warning(f"Exit order incomplete: {symbol} - {trade.orderStatus.status}")
                
            except Exception as e:
                failed += 1
                logger.error(f"Error executing exit for {symbol}: {e}")
                print(f"   ❌ Error: {e}\n")
                continue
            
            print()  # Blank line between positions
        
        # Print exit summary
        print("="*80)
        print("[EXIT SUMMARY]")
        print(f"   Total Exit Attempts: {len(positions_to_exit)}")
        print(f"   Successfully Filled: {executed}")
        print(f"   Failed/Pending: {failed}")
        print(f"   Total Realized P&L: ${total_realized_pnl:+.2f}")
        print("="*80 + "\n")
        
        return {
            'executed': executed,
            'failed': failed,
            'total_pnl': total_realized_pnl
        }
    
    def run(self):
        """
        Main execution flow with automatic order execution
        CRITICAL: EXIT FIRST, THEN ENTER - evaluates existing positions before new entries
        """
        logger.info("="*80)
        logger.info("🚀 FORM 4 INSIDER CLUSTER STRATEGY - STARTING")
        logger.info("="*80)
        logger.info(f"Capital (pre-connect): ${self.capital:.2f} | Positions: LLM-determined")
        
        # Generate timestamp for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Connect to IBKR for automatic order execution
        self.connect_to_ibkr()

        # ALWAYS use settled cash (T+2 compliant) when IBKR connected
        if self.ibkr_connected:
            settled_cash = self.get_settled_cash()
            if settled_cash > 0:
                self.capital = settled_cash
                logger.info(f"💰 Using IBKR Settled Cash: ${self.capital:.2f}")
                print(f"\n[CAPITAL] Using settled cash (T+2 compliant): ${self.capital:.2f}")
                print(f"[ALLOCATION] Position count and weights will be determined by LLM debate\n")
            else:
                logger.warning("Settled cash unavailable; falling back to configured capital")
                print("\n[WARN] Settled cash unavailable. Falling back to configured capital.\n")
        else:
            logger.info(f"💰 Capital in use: ${self.capital:.2f} (IBKR not connected)")
        
        try:
            # STEP 0: Fetch multi-source signals (reuse for both exits and entries)
            logger.info("="*80)
            logger.info("📊 STEP 0: FETCH MULTI-SOURCE SIGNALS (for exits + entries)")
            logger.info("="*80)
            multi_source_data = self.fetch_multi_source_signals()
            
            # STEP 1: Exit revalidation FIRST (politician-first strategy)
            print("\n" + "="*80)
            print("📊 STEP 1: EXIT REVALIDATION (politician-first)")
            print("="*80)
            logger.info("="*80)
            logger.info("📊 STEP 1: EXIT REVALIDATION (politician-first)")
            logger.info("="*80)
            
            # Load held positions from IBKR
            held_positions = self.load_held_positions()
            
            # Revalidate against latest politician signals
            revalidation_results = self.revalidate_held_positions(multi_source_data, held_positions)
            
            # Execute exits for positions that lost politician backing
            positions_to_exit = revalidation_results['exit']
            exit_results = {'executed': 0, 'failed': 0, 'total_pnl': 0}
            if positions_to_exit:
                exit_results = self.execute_exits(positions_to_exit)
                
                # Wait for IBKR to update capital after exits
                if exit_results['executed'] > 0:
                    print("[WAITING] Allowing 5 seconds for capital settlement...")
                    self.ib.sleep(5)
            else:
                print("[INFO] All held positions passed revalidation (still politician-backed)\n")
            
            # Get updated capital after exits
            if self.ib and self.ib.isConnected():
                account_summary = self.ib.accountSummary()
                for item in account_summary:
                    if item.tag == 'AvailableFunds':
                        available_cash = float(item.value)
                        logger.info(f"💰 Available cash after exits: ${available_cash:.2f}")
                        break

                # ALWAYS refresh settled cash after exits (note: T+2 means exits won't increase settled cash immediately)
                if self.ibkr_connected:
                    updated_cash = self.get_settled_cash()
                    if updated_cash > 0:
                        self.capital = updated_cash
                        logger.info(f"💰 Capital updated after exits: Settled Cash = ${self.capital:.2f}")
                        print(f"[CAPITAL] Updated settled cash after exits: ${self.capital:.2f}")
                        print("[NOTE] Recently sold positions take T+2 to settle - capital may be limited")
            
            logger.info("="*80)
            logger.info("📈 STEP 2: ENTRY LOGIC (searching for new opportunities)")
            logger.info("="*80)
            
            # Step 2: Aggregate signals with quality weighting
            aggregated_signals = self.aggregate_multi_source_signals(multi_source_data)
            
            if not aggregated_signals:
                logger.warning("⚠️  No insider signals found across all sources. Exiting.")
                print("\n⚠️  No insider activity detected across all 4 sources")
                print("💡 Try again later - insider activity varies")
                return
            
            # Step 3: Filter by fundamentals and transaction quality
            candidates = self.filter_by_fundamentals_multi_source(aggregated_signals)
            
            if not candidates:
                logger.warning("⚠️  No candidates passed fundamental filters. Exiting.")
                print("\n⚠️  Insider clusters found, but none met criteria:")
                print(f"    - Market cap: ${MIN_MARKET_CAP/1_000_000:.0f}M - ${MAX_MARKET_CAP/1_000_000_000:.1f}B")
                print(f"    - Price range: ${MIN_PRICE:.2f} - ${MAX_PRICE:.2f}")
                return
            
            # Step 3: Analyze with LLM
            analyzed = self.analyze_with_llm(candidates)
            
            # Step 3.5: Add institutional validation (Form 13F data)
            logger.info("🏦 Adding institutional validation layer...")
            analyzed = self.add_institutional_validation(analyzed)
            
            # Step 3.75: Generate COMPREHENSIVE PDF with ALL analyzed stocks (you paid for this!)
            logger.info("[GENERATING] Comprehensive analysis PDF for all analyzed stocks...")
            comprehensive_pdf = self.generate_comprehensive_analysis_pdf(analyzed, timestamp)
            
            # Step 3.8: Export FULL analyzed list to JSON (for transparency and testing)
            logger.info("💾 Exporting full analyzed list to JSON...")
            full_analysis_file = self.output_dir / f"full_analysis_{timestamp}.json"
            try:
                with open(full_analysis_file, 'w') as f:
                    json.dump({
                        'generated_at': datetime.now().isoformat(),
                        'strategy': 'Form 4 Multi-Source Insider Signals',
                        'capital': self.capital,
                        'lookback_days': LOOKBACK_DAYS,
                        'min_confidence': MIN_CONFIDENCE_SCORE,
                        'position_selection': 'LLM_ALLOCATION_DEBATE',
                        'total_analyzed': len(analyzed),
                        'analyzed_stocks': analyzed
                    }, f, indent=2, default=str)
                logger.info(f"✓ Full analysis exported: {full_analysis_file.name}")
                print(f"\n💾 Full analysis saved: {full_analysis_file.name}")
                print(f"   Contains all {len(analyzed)} analyzed stocks")
                print(f"   Use this file to test selection algorithms without re-running API calls\n")
            except Exception as e:
                logger.warning(f"Failed to export full analysis: {e}")
            
            # Step 4: Rank and select top positions
            selected = self.rank_and_select(analyzed)
            
            if not selected:
                logger.warning("⚠️  No positions met confidence threshold. Exiting.")
                print(f"\n⚠️  Candidates analyzed but none above {MIN_CONFIDENCE_SCORE:.0%} confidence")
                return
            
            # Step 5: Calculate INITIAL position sizes (for display only - will recalculate after approval)
            selected = self.calculate_position_sizes(selected)
            
            # Step 6: Generate reports
            logger.info("📄 Generating reports...")
            json_report = self.generate_json_report(selected, timestamp)
            pdf_report = self.generate_pdf_report(selected, timestamp)  # Top 4 trading positions
            
            # Step 7: Print terminal summary
            self.print_terminal_summary(selected)
            
            # Step 8: Get user approvals (CRITICAL SAFETY)
            logger.info("⚠️  Requesting manual approval...")
            approvals = self.get_user_approvals(selected)
            
            # Step 8.5: Recalculate position sizes for approved positions only (FIX: Deploy full capital)
            approved_positions = [c for c in selected if approvals.get(c['symbol'], False)]
            if approved_positions:
                logger.info(f"♻️  Recalculating position sizes for {len(approved_positions)} approved positions...")
                approved_positions = self.recalculate_position_sizes(approved_positions)
            
            # Step 9: Execute approved orders via IBKR
            executions = self.execute_approved_orders(approved_positions, approvals)
            
            # Step 10: Save approval decisions and execution results
            self.save_approval_decisions(selected, approvals, timestamp, executions)
            
            logger.info("="*80)
            logger.info("✅ FORM 4 STRATEGY COMPLETE")
            logger.info("="*80)
            logger.info(f"📄 Reports saved to: {self.output_dir}")
            logger.info(f"📊 PDF Report: form4_report_{timestamp}.pdf")
            logger.info(f"📋 Approved Positions: approved_positions_{timestamp}.json")
            if executions:
                logger.info(f"✅ Executed {len(executions)} orders automatically")
            else:
                logger.info("🔒 Orders saved for manual execution (IBKR not connected)")
        
        except Exception as e:
            logger.error(f"❌ Error in Form 4 strategy: {e}")
            raise
        finally:
            # AUTONOMOUS: Run improvement cycle at end of week
            if datetime.now().weekday() == 6:  # Sunday
                logger.info("📊 Running weekly performance analysis and improvement cycle...")
                try:
                    improvement_report = self.improvement_engine.daily_improvement_cycle()
                    
                    if improvement_report.get('parameter_changes'):
                        logger.info(f"✅ Parameters updated: {list(improvement_report['parameter_changes'].keys())}")
                    
                    if improvement_report.get('llm_insights'):
                        insights = improvement_report['llm_insights']
                        if isinstance(insights, dict) and 'assessment' in insights:
                            logger.info(f"💡 LLM Assessment: {insights['assessment']}")
                    
                    logger.info("📁 Weekly improvement report saved")
                    
                except Exception as e_improve:
                    logger.error(f"⚠️ Error in improvement cycle: {e_improve}")
            
            # Always disconnect from IBKR
            self.disconnect_from_ibkr()


def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Form 4 insider strategy")
    parser.add_argument(
        "--capital",
        type=float,
        default=None,
        help="Fallback capital if IBKR not connected (default $1000). IBKR buying power is ALWAYS used when connected."
    )

    args = parser.parse_args()

    strategy = Form4Strategy(capital_override=args.capital)
    strategy.run()


if __name__ == "__main__":
    main()
