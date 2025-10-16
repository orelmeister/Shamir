"""
utils.py

This module provides utility functions for the trading bot, such as checking
market hours.
"""

from datetime import datetime
import pytz

def is_market_open() -> bool:
    """
    Checks if the US stock market is currently open.
    Considers regular trading hours (9:30 AM to 4:00 PM ET) and ignores
    pre-market/after-hours trading. Does not account for market holidays.
    """
    # Get the current time in UTC
    utc_now = datetime.now(pytz.utc)

    # Convert the current time to Eastern Time
    eastern = pytz.timezone('US/Eastern')
    et_now = utc_now.astimezone(eastern)

    # Check if it's a weekday (Monday=0, Sunday=6)
    if et_now.weekday() > 4:
        return False

    # Define market open and close times in ET
    market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = et_now.replace(hour=16, minute=0, second=0, microsecond=0)

    # Check if the current time is within market hours
    return market_open <= et_now <= market_close
