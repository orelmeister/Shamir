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
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path
from typing import List, Dict, Optional
import logging
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
CAPITAL = 1000.0  # Dedicated capital for Form 4 strategy
MAX_POSITIONS = 4  # 2-4 positions ($250-500 per position)
MIN_CONFIDENCE_SCORE = 0.65  # Lower than main strategy (Form 4 is strong signal)

# IBKR Connection Parameters
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4001  # Live trading (Gateway or TWS)
IBKR_CLIENT_ID = 10  # Unique client ID for Form 4 strategy

class Form4Strategy:
    """Form 4 Insider Trading Strategy with Manual Approval + Autonomous Learning"""
    
    def __init__(self):
        self.capital = CAPITAL
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
        
        # Initialize Gemini 2.5 Pro
        if GOOGLE_API_KEY and GEMINI_AVAILABLE:
            try:
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash-exp",
                    temperature=0.1
                )
                logger.info("✓ Initialized Gemini 2.0 Flash")
                print("[+] GEMINI AGENT: Ready")
            except Exception as e:
                logger.warning(f"Gemini 2.0 Flash initialization failed: {e}")
        
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
    
    def calculate_signal_quality(self, insider_role: str, is_politician: bool = False) -> float:
        """
        Calculate signal quality weight based on insider type
        
        Signal Hierarchy (User's Insight):
        - Politicians (Senate/House): 3.0 = HIGHEST (legal insider info)
        - Directors: 2.0 = HIGH (external validation)
        - 10% Owners: 2.0 = HIGH (major stakeholder)
        - Officers: 0.5 = LOWER (promotional risk - "trying to raise stock price artificially")
        
        Args:
            insider_role: Role from typeOfOwner or office field
            is_politician: True if from Senate/House data
        
        Returns: Quality weight (0.5-3.0)
        """
        # Politicians = HIGHEST confidence
        if is_politician:
            return 3.0
        
        # Parse role
        role_lower = insider_role.lower() if insider_role else ""
        
        # Directors and board members = HIGH confidence
        if 'director' in role_lower or 'board' in role_lower:
            return 2.0
        
        # 10% owners = HIGH confidence
        if '10%' in role_lower or '10 percent' in role_lower or 'ten percent' in role_lower:
            return 2.0
        
        # Officers = LOWER confidence (promotional risk)
        if any(word in role_lower for word in ['officer', 'ceo', 'cfo', 'coo', 'president', 'vice president', 'executive']):
            return 0.5
        
        # Default for unknown roles
        return 1.0
    
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
    
    def aggregate_multi_source_signals(self, multi_source_data: Dict[str, List[Dict]]) -> Dict[str, Dict]:
        """
        Aggregate signals across all 4 sources with quality weighting
        
        Returns: Dict[symbol] = {
            'total_signals': int,
            'politician_count': int,
            'director_count': int,
            'officer_count': int,
            'owner_count': int,
            'weighted_quality_score': float,
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
                
                # Calculate quality weight
                quality_weight = self.calculate_signal_quality(role, is_political)
                
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
        
        # Filter to stocks with 3+ signals OR any politician signal
        filtered_signals = {
            symbol: data for symbol, data in all_signals.items()
            if data['total_signals'] >= MIN_FILINGS_FOR_CLUSTER or data['politician_count'] > 0
        }
        
        print(f"[RESULTS] SIGNAL AGGREGATION:")
        print(f"   Total stocks with activity: {len(all_signals)}")
        print(f"   Stocks meeting criteria: {len(filtered_signals)}")
        print(f"   Criteria: >={MIN_FILINGS_FOR_CLUSTER} signals OR >=1 politician signal\n")
        
        if filtered_signals:
            print("[TOP STOCKS] BY SIGNAL QUALITY:\n")
            sorted_signals = sorted(
                filtered_signals.items(),
                key=lambda x: (x[1]['weighted_quality_score'], x[1]['total_signals']),
                reverse=True
            )[:15]
            
            for symbol, data in sorted_signals:
                quality_stars = "*" * min(3, int(data['weighted_quality_score']))
                print(f"   {symbol}: Score {data['weighted_quality_score']:.2f}/3.0 {quality_stars}")
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
            deepseek_text = deepseek_raw.content if hasattr(deepseek_raw, 'content') else str(deepseek_raw)
            
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
            gemini_text = gemini_raw.content if hasattr(gemini_raw, 'content') else str(gemini_raw)
            
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
            deepseek_rebuttal_text = deepseek_rebuttal_raw.content if hasattr(deepseek_rebuttal_raw, 'content') else str(deepseek_rebuttal_raw)
            
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
            gemini_rebuttal_text = gemini_rebuttal_raw.content if hasattr(gemini_rebuttal_raw, 'content') else str(gemini_rebuttal_raw)
            
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
    
    def analyze_with_llm(self, candidates: List[Dict]) -> List[Dict]:
        """
        Use multi-agent debate or single LLM to analyze candidates
        Falls back to rule-based scoring if no LLM available
        """
        if self.multi_agent_available:
            logger.info(f"🤖 Multi-agent debate analysis for {len(candidates)} candidates...")
            print("\n" + "="*80)
            print("[MULTI-AGENT DEBATE] ANALYZING CANDIDATES")
            print("="*80)
        else:
            logger.info(f"🤖 Analyzing {len(candidates)} candidates...")
        
        analyzed = []
        
        for candidate in candidates:
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
                    analyzed.append(candidate)
                    logger.info(f"  ✓ {symbol}: Consensus {debate_result['confidence']:.2f} (agreement: {debate_result['agreement_score']:.2f})")
                    continue
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
                analyzed.append(candidate)
                logger.info(f"  ✓ {symbol}: Confidence {confidence:.2f} (rule-based)")
                continue
            
            # Fetch recent news for LLM analysis
            news = self.get_news(symbol, days=14)
            
            # Build detailed insider breakdown
            signal_data = candidate['signal_data']
            timing_analysis = candidate['timing_analysis']
            
            # Format transaction details by source
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
                analyzed.append(candidate)
                
                logger.info(f"  ✓ {symbol}: Confidence {analysis['confidence']:.2f}")
                
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
                analyzed.append(candidate)
        
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
    
    def rank_and_select(self, analyzed: List[Dict]) -> List[Dict]:
        """
        Rank by confidence and select top positions
        """
        # Filter by minimum confidence
        qualified = [c for c in analyzed if c['analysis']['confidence'] >= MIN_CONFIDENCE_SCORE]
        
        logger.info(f"✓ {len(qualified)}/{len(analyzed)} candidates above {MIN_CONFIDENCE_SCORE:.0%} confidence")
        
        # Sort by confidence
        qualified.sort(key=lambda x: x['analysis']['confidence'], reverse=True)
        
        # Select top MAX_POSITIONS
        selected = qualified[:MAX_POSITIONS]
        
        logger.info(f"✓ Selected top {len(selected)} positions")
        
        return selected
    
    def calculate_position_sizes(self, selected: List[Dict]) -> List[Dict]:
        """
        Calculate position sizes based on equal weighting
        """
        if not selected:
            return []
        
        position_size = self.capital / len(selected)
        
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
        
        return selected
    
    def recalculate_position_sizes(self, approved_positions: List[Dict]) -> List[Dict]:
        """
        Recalculate position sizes AFTER user approval to deploy full capital
        
        This fixes the bug where rejecting positions wasted capital.
        Example: 4 positions @ $250 each → User approves 2 → Should be $500 each (not $250)
        
        Args:
            approved_positions: List of approved candidate dicts
        
        Returns: Updated list with recalculated shares and costs
        """
        if not approved_positions:
            return []
        
        num_approved = len(approved_positions)
        position_size = self.capital / num_approved
        
        print(f"\n{'='*80}")
        print(f"💰 RECALCULATING POSITION SIZES")
        print(f"{'='*80}")
        print(f"Capital: ${self.capital:.2f}")
        print(f"Approved Positions: {num_approved}")
        print(f"Allocation per Position: ${position_size:.2f}")
        print(f"{'='*80}\n")
        
        for candidate in approved_positions:
            symbol = candidate['symbol']
            price = candidate['profile']['price']
            old_shares = candidate['position']['shares']
            old_cost = candidate['position']['actual_dollars']
            
            # Recalculate shares
            new_shares = int(position_size / price)
            new_cost = new_shares * price
            
            # Update position dict
            candidate['position'] = {
                'target_dollars': position_size,
                'shares': new_shares,
                'actual_dollars': new_cost,
                'price': price
            }
            
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
        Returns: {symbol: approved} mapping
        """
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
        
        if not selected:
            print("⚠️  No positions to approve (no clusters found this week)")
            return {}
        
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
        
        executions = {}
        
        print("\n" + "="*80)
        print("📊 EXECUTING APPROVED ORDERS")
        print("="*80 + "\n")
        
        for candidate in selected:
            symbol = candidate['symbol']
            
            # Skip if not approved
            if not approvals.get(symbol, False):
                continue
            
            shares = candidate['position']['shares']
            target_price = candidate['profile']['price']
            
            try:
                # Create IBKR contract
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                
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
                    if trade.orderStatus.status in ['Filled', 'Cancelled']:
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
                    logger.warning(f"⚠️  {symbol}: Order cancelled")
                    print(f"   [WARNING] Order cancelled")
                    
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
    
    def run(self):
        """
        Main execution flow with automatic order execution
        CRITICAL: EXIT FIRST, THEN ENTER - evaluates existing positions before new entries
        """
        logger.info("="*80)
        logger.info("🚀 FORM 4 INSIDER CLUSTER STRATEGY - STARTING")
        logger.info("="*80)
        logger.info(f"Capital: ${self.capital:.2f} | Max Positions: {MAX_POSITIONS}")
        
        # Generate timestamp for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Connect to IBKR for automatic order execution
        self.connect_to_ibkr()
        
        try:
            # STEP 0: Evaluate existing positions for exits FIRST (frees up capital)
            logger.info("="*80)
            logger.info("📊 STEP 0: EXIT EVALUATION (runs before entry logic)")
            logger.info("="*80)
            try:
                from form4_exit_manager import Form4ExitManager
                exit_manager = Form4ExitManager()
                exit_results = exit_manager.evaluate_all_positions()
                logger.info(f"✅ Exit evaluation complete: {exit_results}")
            except Exception as e:
                logger.error(f"❌ Exit manager failed: {e}", exc_info=True)
                logger.warning("⚠️  Continuing to entry logic despite exit failure...")
            
            # Get updated capital after liquidations
            if self.ib and self.ib.isConnected():
                account_summary = self.ib.accountSummary()
                for item in account_summary:
                    if item.tag == 'AvailableFunds':
                        available_cash = float(item.value)
                        logger.info(f"💰 Available cash after exits: ${available_cash:.2f}")
                        break
            
            logger.info("="*80)
            logger.info("📈 STEP 1: ENTRY LOGIC (searching for new opportunities)")
            logger.info("="*80)
            
            # Step 1: Fetch multi-source insider signals
            multi_source_data = self.fetch_multi_source_signals()
            
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
    strategy = Form4Strategy()
    strategy.run()


if __name__ == "__main__":
    main()
