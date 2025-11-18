"""
Validate Monte Carlo picks against IBKR without re-running full analysis.
Reads from full_analysis_results.json and validates top picks.
"""
import sys
import json
import logging
import os
from datetime import datetime
from ib_insync import IB, Stock
import ib_insync.util as ib_util

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared_state.state_manager import write_state
import monte_carlo_filter as mc

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("[ValidateMC]")

# Configuration
IB_HOST = '127.0.0.1'
IB_PORT = 4001
MAX_POSITIONS = 5
MIN_CONFIDENCE_SCORE = 0.75


def validate_ticker_in_ibkr(ib, ticker):
    """Quick validation to check if ticker exists in IBKR before trading."""
    try:
        contract = Stock(ticker, 'SMART', 'USD')
        details = ib_util.run(ib.reqContractDetailsAsync(contract))
        
        if not details:
            logger.warning(f"No contract details found for {ticker}")
            return False
        
        logger.info(f"[OK] Validated {ticker}: {details[0].contract.symbol}")
        return True
        
    except Exception as e:
        logger.error(f"Ticker validation failed for {ticker}: {e}")
        return False


def main():
    logger.info("="*80)
    logger.info("Monte Carlo Validation - Starting")
    logger.info("="*80)
    
    # Load full analysis results
    try:
        with open('full_analysis_results.json', 'r') as f:
            results = json.load(f)
        logger.info(f"Loaded {len(results)} analysis results")
    except Exception as e:
        logger.error(f"Failed to load full_analysis_results.json: {e}")
        sys.exit(1)
    
    # Filter BUY recommendations with high confidence
    buy_recommendations = [
        res for res in results 
        if res and res.get("decision") == "BUY" and res.get("confidence", 0) >= MIN_CONFIDENCE_SCORE
    ]
    logger.info(f"Found {len(buy_recommendations)} BUY recommendations with confidence >= {MIN_CONFIDENCE_SCORE}")
    
    if not buy_recommendations:
        logger.error("No high-confidence BUY recommendations found.")
        sys.exit(1)
    
    # Run Monte Carlo simulation
    logger.info("Running Monte Carlo simulation to rank stocks...")
    mc_results = mc.run_monte_carlo_filter(buy_recommendations, max_positions=MAX_POSITIONS)
    
    if not mc_results or not isinstance(mc_results, list):
        logger.error("Monte Carlo simulation failed to return rankings.")
        sys.exit(1)
    
    # Connect to IBKR once for all validations
    logger.info("Connecting to IBKR...")
    ib = IB()
    try:
        ib_util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
        logger.info("Connected to IBKR successfully")
        
        # Validate tickers and build top picks list
        logger.info(f"Validating top {MAX_POSITIONS} Monte Carlo picks against IBKR...")
        top_picks = []
        sharpe_ratios = {}  # Not used in simple ranking
        
        for candidate in mc_results:
            if len(top_picks) >= MAX_POSITIONS:
                break
            
            ticker = candidate['ticker']
            if validate_ticker_in_ibkr(ib, ticker):
                candidate['sharpe_ratio'] = sharpe_ratios.get(ticker, 0.0)
                top_picks.append(candidate)
                logger.info(f"[OK] Top pick #{len(top_picks)}: {ticker} (confidence: {candidate.get('confidence', 0):.2f})")
            else:
                logger.warning(f"[WARNING] Ticker {ticker} not found in IBKR. Skipping...")
    
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IBKR")
    
    if not top_picks:
        logger.error("No valid tickers found in Monte Carlo rankings.")
        sys.exit(1)
    
    # Update phase state with top picks
    write_state('phase_state', {
        'current_phase': 'analysis_complete',
        'top_picks': top_picks,
        'timestamp': datetime.now().isoformat()
    })
    
    logger.info("="*80)
    logger.info(f"[OK] Successfully validated {len(top_picks)} top picks:")
    for i, pick in enumerate(top_picks, 1):
        logger.info(f"  {i}. {pick['ticker']} - {pick.get('confidence', 0):.2f} confidence")
    logger.info("="*80)
    logger.info("Updated phase_state.json with validated picks")


if __name__ == '__main__':
    main()
