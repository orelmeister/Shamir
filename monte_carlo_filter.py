"""
Monte Carlo filtering and ranking for stock recommendations.
Simplified implementation for weekly bot Phase 2.
"""
import logging

logger = logging.getLogger("[MonteCarlo]")


def run_monte_carlo_filter(buy_recommendations, max_positions=5):
    """
    Rank BUY recommendations by confidence score.
    
    Args:
        buy_recommendations: List of stock dicts with 'ticker', 'decision', 'confidence', 'reasoning'
        max_positions: Maximum number of positions to return
        
    Returns:
        List of top-ranked stocks (dicts with ticker, confidence, reasoning)
    """
    if not buy_recommendations:
        logger.warning("No BUY recommendations provided to Monte Carlo filter")
        return []
    
    # Sort by confidence descending
    ranked = sorted(buy_recommendations, key=lambda x: x.get('confidence', 0.0), reverse=True)
    
    # Take top N
    top_picks = ranked[:max_positions]
    
    logger.info(f"Monte Carlo ranked {len(ranked)} stocks, returning top {len(top_picks)}")
    for i, pick in enumerate(top_picks, 1):
        logger.info(f"  {i}. {pick['ticker']} (confidence: {pick.get('confidence', 0.0):.2f})")
    
    return top_picks
