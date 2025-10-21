"""
utils.py

This module provides utility functions for the trading bot, such as checking
market hours.
"""

from datetime import datetime
import pytz
import json
import logging
import os
from ib_insync import util

def setup_logging(log_file_path, run_id):
    """
    Sets up a centralized JSON logger for an application run.
    All logs will be written to the specified file.
    """
    log_dir = os.path.dirname(log_file_path)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(log_file_path) # Use file path as a unique name
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(log_file_path, mode='w')
    
    # Add a handler to also print to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_record = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "agent": getattr(record, 'agent', 'Orchestrator'),
                "message": record.getMessage(),
            }
            if hasattr(record, 'data'):
                log_record['data'] = record.data
            if record.exc_info:
                log_record['exception'] = self.formatException(record.exc_info)
            return json.dumps(log_record)

    class ConsoleFormatter(logging.Formatter):
        def format(self, record):
            return f"[{record.levelname}] [{getattr(record, 'agent', 'Orchestrator')}] {record.getMessage()}"

    formatter = JsonFormatter()
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_formatter = ConsoleFormatter()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Add ib_insync logging to the same handlers
    ib_logger = logging.getLogger('ib_insync')
    util.logToFile(os.path.join(log_dir, f"ib_insync_{run_id}.log"))
    ib_logger.propagate = False
    
    return logger

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
