"""
Phase 2: Analyst Agent
Analyzes stocks using LLMs and Monte Carlo simulation to rank and select top picks.
"""
import json
import logging
import os
import sys
from datetime import datetime
from multiprocessing import Pool, cpu_count

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ib_insync import IB, Stock
import ib_insync.util as ib_util
from langchain_community.chat_models import ChatOllama
from langchain_google_vertexai import ChatVertexAI
from langchain_deepseek import ChatDeepSeek

# Import shared utilities
from shared_state.state_manager import read_state, write_state
from market_hours import is_market_open
import monte_carlo_filter as mc

# Configuration
FULL_ANALYSIS_FILE = "full_analysis_results.json"
MIN_CONFIDENCE_SCORE = 0.75
MAX_POSITIONS = 5
IB_HOST = '127.0.0.1'
IB_PORT = 4001

# LLM API Keys
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
FORCE_ONLINE_LLMS = os.getenv('FORCE_ONLINE_LLMS', 'false').lower() == 'true'

# Generate run ID
RUN_ID = datetime.now().strftime('%Y%m%d_%H%M%S')

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'analyst_{RUN_ID}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Analyst] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def validate_ticker_in_ibkr(ticker):
    """Quick validation to check if ticker exists in IBKR before trading."""
    ib = IB()
    try:
        ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
        contract = Stock(ticker, 'SMART', 'USD')
        details = ib_util.run(ib.reqContractDetailsAsync(contract))
        ib.disconnect()
        
        if not details:
            logger.warning(f"No contract details found for {ticker}")
            return False
        
        logger.debug(f"Validated {ticker}: {details[0].contract.symbol}")
        return True
        
    except Exception as e:
        logger.error(f"Ticker validation failed for {ticker}: {e}")
        if ib.isConnected():
            ib.disconnect()
        return False


def analysis_worker(stock_data, worker_id, force_online_llms):
    """Worker function for parallel analysis using LLMs."""
    # Setup worker-specific logger
    worker_log = os.path.join(log_dir, f'analyst_worker_{RUN_ID}_{worker_id}.log')
    worker_logger = logging.getLogger(f'analyst_worker_{worker_id}')
    worker_logger.setLevel(logging.INFO)
    if not worker_logger.hasHandlers():
        file_handler = logging.FileHandler(worker_log, mode='w')
        file_handler.setFormatter(logging.Formatter(f'%(asctime)s - [Analyst-{worker_id}] - %(message)s'))
        worker_logger.addHandler(file_handler)

    ticker = stock_data.get("ticker", "Unknown")
    worker_logger.info(f"Starting analysis for {ticker}")

    prompt = f"""
    You are an aggressive growth stock analyst targeting 50%+ returns in 30 days.
    
    Analyze the following stock data with STRICT criteria for high-growth micro-caps:
    
    MANDATORY REQUIREMENTS:
    - Market cap: $50M-$350M (micro-cap growth zone)
    - Revenue growth: >30% YoY (fast growers only)
    - Recent positive catalysts (earnings beat, new contracts, breakthrough news)
    - Strong price momentum (technical strength)
    - Clear growth story with potential for 2x-5x appreciation
    
    DECISION CRITERIA:
    - BUY: High conviction (confidence ≥0.80), meets all requirements, explosive growth potential
    - HOLD: Does not meet strict growth criteria or confidence <0.80
    
    CONFIDENCE SCORING (0.0-1.0):
    - 0.90-1.0: Exceptional - multiple catalysts, explosive revenue growth, strong momentum
    - 0.80-0.89: Strong - meets all criteria with solid fundamentals
    - 0.70-0.79: Good but not aggressive enough for our strategy
    - <0.70: HOLD - insufficient growth potential
    
    Focus on: Small caps poised for breakout, recent IPOs scaling fast, companies with
    disruptive technology, or stocks with recent positive inflection points.
    
    Data: {json.dumps(stock_data, indent=2)}

    Return ONLY a JSON object with "ticker", "decision" (BUY or HOLD), "confidence" (0.0-1.0), and "reasoning" (be specific about growth catalysts).
    """
    
    try:
        # Dynamic LLM Switching
        if force_online_llms or is_market_open():
            if force_online_llms:
                worker_logger.info(f"FORCE_ONLINE_LLMS is True. Using online models for {ticker}.")
            else:
                worker_logger.info(f"Market is OPEN. Using online models for {ticker}.")
            
            try:
                llm = ChatDeepSeek(model="deepseek-reasoner", api_key=DEEPSEEK_API_KEY)
                model_name = 'DeepSeek'
                response = llm.invoke(prompt)
            except Exception as e:
                worker_logger.warning(f"DeepSeek failed for {ticker}: {e}. Falling back to Gemini.")
                llm = ChatVertexAI(model_name="gemini-2.5-flash")
                model_name = 'Gemini'
                response = llm.invoke(prompt)
        else:
            worker_logger.info(f"Market is CLOSED. Using local Ollama model for {ticker}.")
            llm = ChatOllama(model="llama3.1:8b")
            model_name = 'Ollama'
            response = llm.invoke(prompt)

        analysis = json.loads(response.content)
        analysis['model'] = model_name
        
        final_result = stock_data.copy()
        final_result.update(analysis)
        return final_result
    except Exception as e:
        worker_logger.error(f"Error analyzing {ticker}: {e}", exc_info=True)
        return {"ticker": ticker, "decision": "ERROR", "reasoning": str(e)}


def analysis_worker_wrapper(args):
    """Helper to unpack arguments for imap_unordered."""
    return analysis_worker(*args)


def main():
    """Main execution for Phase 2: Analysis"""
    logger.info("=" * 80)
    logger.info("PHASE 2: ANALYST - Starting")
    logger.info("=" * 80)
    
    # Read phase state
    phase_state = read_state('phase_state')
    current_phase = phase_state.get('current_phase', 'unknown')
    
    if current_phase != 'aggregation_complete':
        logger.error(f"Expected phase 'aggregation_complete', got '{current_phase}'. Cannot proceed.")
        sys.exit(1)
    
    # Get stocks to analyze
    stocks_to_analyze = phase_state.get('stocks_for_analysis', [])
    
    if not stocks_to_analyze:
        logger.warning("No stocks to analyze. Skipping analysis phase.")
        write_state('phase_state', {
            'current_phase': 'analysis_complete',
            'top_picks': [],
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(0)
    
    logger.info(f"Analyzing {len(stocks_to_analyze)} stocks in parallel using {cpu_count()} workers")
    
    # Parallel analysis
    results = []
    with Pool(processes=cpu_count()) as pool:
        worker_args = [(stock, i, FORCE_ONLINE_LLMS) for i, stock in enumerate(stocks_to_analyze)]
        
        total_stocks = len(stocks_to_analyze)
        for i, result in enumerate(pool.imap_unordered(analysis_worker_wrapper, worker_args), 1):
            if result:
                results.append(result)
                ticker = result.get('ticker', 'Unknown')
                decision = result.get('decision', 'ERROR')
                logger.info(f"Progress: [{i}/{total_stocks}] - {ticker}: {decision}")
            else:
                logger.warning(f"Progress: [{i}/{total_stocks}] - Worker returned no result")
    
    # Save full analysis results
    try:
        with open(FULL_ANALYSIS_FILE, 'w') as f:
            json.dump(results, f, indent=4)
        logger.info(f"Saved full analysis for {len(results)} stocks to {FULL_ANALYSIS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save analysis results: {e}")
    
    # Filter BUY recommendations with high confidence
    buy_recommendations = [
        res for res in results 
        if res and res.get("decision") == "BUY" and res.get("confidence", 0) >= MIN_CONFIDENCE_SCORE
    ]
    logger.info(f"Found {len(buy_recommendations)} BUY recommendations with confidence >= {MIN_CONFIDENCE_SCORE}")
    
    if not buy_recommendations:
        logger.info("No high-confidence BUY recommendations. Ending analysis phase.")
        write_state('phase_state', {
            'current_phase': 'analysis_complete',
            'top_picks': [],
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(0)
    
    # Run Monte Carlo simulation
    logger.info("Running Monte Carlo simulation to rank stocks...")
    mc_results = mc.run_monte_carlo_filter(buy_recommendations)
    
    if not mc_results or not mc_results.get("ranked_tickers"):
        logger.error("Monte Carlo simulation failed to return rankings.")
        write_state('phase_state', {
            'current_phase': 'analysis_complete',
            'top_picks': [],
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(1)
    
    ranked_tickers = mc_results["ranked_tickers"]
    sharpe_ratios = mc_results["sharpe_ratios"]
    
    # Validate tickers and build top picks list
    logger.info(f"Validating top {MAX_POSITIONS} Monte Carlo picks against IBKR...")
    top_picks = []
    
    for ticker in ranked_tickers:
        if len(top_picks) >= MAX_POSITIONS:
            break
        
        candidate = next((rec for rec in buy_recommendations if rec['ticker'] == ticker), None)
        if candidate:
            if validate_ticker_in_ibkr(ticker):
                candidate['sharpe_ratio'] = sharpe_ratios.get(ticker, 0.0)
                top_picks.append(candidate)
                logger.info(f"✅ Top pick #{len(top_picks)}: {ticker} (Sharpe: {candidate['sharpe_ratio']:.2f})")
            else:
                logger.warning(f"⚠️ Ticker {ticker} not found in IBKR. Skipping...")
    
    if not top_picks:
        logger.error("No valid tickers found in Monte Carlo rankings.")
        write_state('phase_state', {
            'current_phase': 'analysis_complete',
            'top_picks': [],
            'timestamp': datetime.now().isoformat()
        })
        sys.exit(1)
    
    # Update phase state with top picks
    write_state('phase_state', {
        'current_phase': 'analysis_complete',
        'top_picks': top_picks,
        'analysis_timestamp': datetime.now().isoformat()
    })
    
    logger.info("=" * 80)
    logger.info(f"PHASE 2: ANALYST - Complete. Top {len(top_picks)} picks: {[p['ticker'] for p in top_picks]}")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error in Analyst phase: {e}", exc_info=True)
        sys.exit(1)
