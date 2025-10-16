# monte_carlo_filter.py
"""
This module provides a Monte Carlo simulation filter to rank stocks based on risk-adjusted return potential.
It uses historical price data to simulate future price paths and calculates Sharpe Ratios over multiple horizons.
"""

import os
import numpy as np
import pandas as pd
from polygon import RESTClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging

# --- Centralized Logging Setup ---
# This ensures that logs from this module are compatible with the main script's formatter
logger = logging.getLogger(__name__)
log_adapter = logging.LoggerAdapter(logger, {'agent': 'MonteCarlo'})

def log(level, message):
    """Logs a message with the agent's name."""
    log_adapter.log(level, message)

# Load environment variables
load_dotenv()
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

if not POLYGON_API_KEY:
    log(logging.WARNING, "POLYGON_API_KEY not set. Monte Carlo filter will not be available.")
    polygon_client = None
else:
    polygon_client = RESTClient(POLYGON_API_KEY)

def get_historical_data(ticker, days):
    """Fetches historical daily price data for a given ticker."""
    if not polygon_client:
        return None
    try:
        to_date = datetime.now().date()
        from_date = to_date - timedelta(days=days * 2) # Fetch more data to ensure we have enough trading days
        
        resp = polygon_client.get_aggs(
            ticker,
            1,
            "day",
            from_date.strftime("%Y-%m-%d"),
            to_date.strftime("%Y-%m-%d"),
        )
        if not resp:
            log(logging.WARNING, f"No historical data found for {ticker} from Polygon.")
            return None
            
        df = pd.DataFrame(resp)
        df['date'] = pd.to_datetime(df.timestamp, unit='ms')
        df = df.set_index('date')['close'].tail(days)
        return df
    except Exception as e:
        log(logging.ERROR, f"Error fetching historical data for {ticker}: {e}")
        return None

def monte_carlo_simulation(prices, num_simulations=100):
    """Runs a Monte Carlo simulation and returns the average Sharpe Ratio."""
    if prices is None or prices.empty:
        return 0

    log_returns = np.log(1 + prices.pct_change())
    mu = log_returns.mean()
    sigma = log_returns.std()
    
    # Simple simulation assuming constant daily volatility and drift
    # For a more advanced model, consider GARCH or other volatility models.
    simulated_returns = np.random.normal(mu, sigma, (len(prices), num_simulations))
    
    # Calculate Sharpe Ratio for each simulation path
    # Assuming risk-free rate is 0 for simplicity
    sharpe_ratios = simulated_returns.mean() / simulated_returns.std() * np.sqrt(252) # Annualized
    
    return np.mean(sharpe_ratios)

def run_monte_carlo_filter(buy_recommendations: list):
    """
    Filters and ranks a list of tickers using a multi-horizon Monte Carlo simulation.
    Expects a list of dictionaries, where each dictionary represents a stock
    and contains at least a "ticker" key.
    """
    if not polygon_client:
        log(logging.ERROR, "Cannot run Monte Carlo filter because POLYGON_API_KEY is not set.")
        return []

    buy_tickers = [item['ticker'] for item in buy_recommendations if 'ticker' in item]
    if not buy_tickers:
        log(logging.WARNING, "No valid tickers found in the buy recommendations.")
        return []

    horizons = {
        "weekly": 5,
        "monthly": 21,
        "yearly": 252
    }
    
    results = {ticker: {"scores": {}} for ticker in buy_tickers}
    
    for horizon_name, days in horizons.items():
        for ticker in buy_tickers:
            prices = get_historical_data(ticker, days)
            if prices is not None:
                sharpe_ratio = monte_carlo_simulation(prices)
                results[ticker]["scores"][horizon_name] = sharpe_ratio
            else:
                results[ticker]["scores"][horizon_name] = -np.inf # Penalize if data is missing

    # Award points based on winners in each horizon
    final_scores = {ticker: 0 for ticker in buy_tickers}
    for horizon_name in horizons.keys():
        winner = max(results, key=lambda t: results[t]["scores"].get(horizon_name, -np.inf))
        if results[winner]["scores"].get(horizon_name, -np.inf) > -np.inf:
            final_scores[winner] += 1
            log(logging.INFO, f"Monte Carlo winner for {horizon_name} horizon: {winner} (Sharpe: {results[winner]['scores'][horizon_name]:.2f})")

    # Sort tickers by their final score, descending
    ranked_tickers = sorted(final_scores, key=final_scores.get, reverse=True)
    
    log(logging.INFO, f"Monte Carlo ranked tickers: {ranked_tickers}")
    return ranked_tickers
