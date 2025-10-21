# market_hours.py
"""
This module handles logic related to stock market hours, including checking if the market is open.

It uses the `pandas_market_calendars` library to get the market schedule and `pytz` for timezone handling.
Currently, it supports checking the market hours for the NYSE (New York Stock Exchange) only.

Functions:
- `is_market_open()`: Checks if the NYSE market is currently open.
- `get_market_open_close_times()`: Gets the NYSE market open and close times for the current day.
- `get_market_hours()`: Gets the NYSE market open and close times for a specific date.
"""

import pandas_market_calendars as mcal
from datetime import datetime
import pytz
import logging

def is_market_open():
    """
    Checks if the NYSE market is currently open using America/New_York timezone.
    Simplified to avoid pandas_market_calendars library issues.

    Returns:
        bool: True if the market is open, False otherwise.
    """
    try:
        ny_tz = pytz.timezone('America/New_York')
        
        # Get the current time in the NYSE timezone
        now_ny = datetime.now(ny_tz)
        
        # Simple check: weekday (0-4 = Mon-Fri) and between 9:30 AM - 4:00 PM
        is_weekday = now_ny.weekday() < 5
        current_time = now_ny.time()
        market_open_time = datetime.strptime("09:30", "%H:%M").time()
        market_close_time = datetime.strptime("16:00", "%H:%M").time()
        
        is_trading_hours = market_open_time <= current_time <= market_close_time
        
        if not is_weekday:
            logging.info(f"Market is closed (weekend). Current NY time: {now_ny.strftime('%Y-%m-%d %H:%M:%S')}")
            return False
        
        if not is_trading_hours:
            logging.info(f"Market is closed (outside trading hours). Current NY time: {now_ny.strftime('%Y-%m-%d %H:%M:%S')}")
            return False
        
        # Market is open
        return True

        # Get market open and close times from the schedule. These are in UTC.
        market_open_utc = schedule.iloc[0].market_open
        market_close_utc = schedule.iloc[0].market_close
        
        # Convert them to NY time for a clear log message
        market_open_ny = market_open_utc.astimezone(ny_tz)
        market_close_ny = market_close_utc.astimezone(ny_tz)

        # Check if current time is within the market hours
        is_open = market_open_ny <= now_ny <= market_close_ny
        
        if is_open:
            logging.info(f"Market is OPEN. Current NY Time: {now_ny.strftime('%H:%M:%S')}, Market Hours: {market_open_ny.strftime('%H:%M:%S')} - {market_close_ny.strftime('%H:%M:%S')}")
        else:
            logging.info(f"Market is CLOSED. Current NY Time: {now_ny.strftime('%H:%M:%S')}, Market Hours: {market_open_ny.strftime('%H:%M:%S')} - {market_close_ny.strftime('%H:%M:%S')}")
            
        return is_open
        
    except Exception as e:
        logging.error(f"An error occurred in is_market_open: {e}")
        # Default to closed on error to be safe
        return False

def get_market_open_close_times():
    """
    Gets the NYSE market open and close times for the current day.

    Returns:
        tuple(datetime.time, datetime.time) or (None, None): A tuple containing market open and close times (in NY timezone), 
                                                              or (None, None) if the market is closed today.
    """
    try:
        nyse = mcal.get_calendar('NYSE')
        ny_tz = pytz.timezone('America/New_York')
        
        # Get the current date in the NYSE timezone
        today_ny = datetime.now(ny_tz).date()
        
        # Get today's schedule
        schedule = nyse.schedule(start_date=today_ny, end_date=today_ny)

        if schedule.empty:
            logging.info(f"Market is closed today ({today_ny.strftime('%Y-%m-%d')}, weekend or holiday).")
            return None, None

        # Get market open and close times from the schedule. These are in UTC.
        market_open_utc = schedule.iloc[0].market_open
        market_close_utc = schedule.iloc[0].market_close
        
        # Convert them to NY time
        market_open_ny = market_open_utc.astimezone(ny_tz)
        market_close_ny = market_close_utc.astimezone(ny_tz)

        logging.info(f"Today's ({today_ny.strftime('%Y-%m-%d')}) market hours (ET): {market_open_ny.strftime('%H:%M:%S')} - {market_close_ny.strftime('%H:%M:%S')}")

        return market_open_ny.time(), market_close_ny.time()
        
    except Exception as e:
        logging.error(f"An error occurred in get_market_open_close_times: {e}", exc_info=True)
        # Default to closed on error to be safe
        return None, None

def get_market_hours(date_to_check):
    """
    Gets the NYSE market open and close times for a specific date.

    Args:
        date_to_check (datetime.date): The date to get the market hours for.

    Returns:
        tuple(datetime, datetime) or (None, None): A tuple containing market open and close datetimes (in US/Eastern), 
                                                     or (None, None) if the market is closed on that date.
    """
    try:
        nyse = mcal.get_calendar('NYSE')
        ny_tz = pytz.timezone('US/Eastern')
        
        schedule = nyse.schedule(start_date=date_to_check, end_date=date_to_check)

        if schedule.empty:
            return None, None

        market_open_utc = schedule.iloc[0].market_open
        market_close_utc = schedule.iloc[0].market_close
        
        # Localize to the correct timezone
        market_open_et = market_open_utc.astimezone(ny_tz)
        market_close_et = market_close_utc.astimezone(ny_tz)

        return market_open_et, market_close_et
        
    except Exception as e:
        logging.error(f"An error occurred in get_market_hours for date {date_to_check}: {e}", exc_info=True)
        return None, None
