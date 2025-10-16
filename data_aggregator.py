"""
data_aggregator.py

This script serves as the "producer" in the producer-consumer model.
It is responsible for generating the `full_market_data.json` file, which acts as
the primary data source for the main multi-agent system.

It works by importing the already-functional `get_stock_data_tool` from the
`tools.py` module and orchestrating its execution for all tickers listed in
`us_tickers.json`.
"""

import json
import logging
import os
from datetime import datetime

# Import the known-working tool from tools.py
from tools import get_stock_data_tool

# --- Configuration ---
TICKERS_FILE = "us_tickers.json"
OUTPUT_FILE = "full_market_data.json"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "data_aggregator.log")

# --- Logging Setup ---
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def get_tickers() -> list:
    """Loads tickers from the static JSON file."""
    try:
        with open(TICKERS_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list) and all(isinstance(item, dict) and 'ticker' in item for item in data):
                return [item['ticker'] for item in data]
            else:
                logging.error(f"Invalid format in {TICKERS_FILE}. Expected a list of objects with a 'ticker' key.")
                return []
    except FileNotFoundError:
        logging.error(f"FATAL: Ticker file not found at {TICKERS_FILE}")
        return []
    except json.JSONDecodeError:
        logging.error(f"FATAL: Could not decode JSON from {TICKERS_FILE}")
        return []
    except Exception as e:
        logging.error(f"FATAL: An unexpected error occurred while reading {TICKERS_FILE}: {e}")
        return []

def run_full_aggregation():
    """
    Orchestrates the data aggregation process by using the imported get_stock_data_tool.
    """
    logging.info("--- Starting Data Aggregation using 'get_stock_data_tool' ---")

    tickers = get_tickers()
    if not tickers:
        logging.critical("No tickers found. Aborting aggregation.")
        return

    logging.info(f"Found {len(tickers)} tickers to process.")

    all_market_data = {}
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    all_market_data[today_str] = {}

    for ticker in tickers:
        logging.info(f"--- Processing ticker: {ticker} ---")
        # Call the imported tool to get data for the current ticker
        stock_data = get_stock_data_tool(ticker)
        
        if stock_data and not stock_data.get("error"):
            all_market_data[today_str][ticker] = stock_data
            logging.info(f"Successfully aggregated data for {ticker}.")
        else:
            logging.error(f"Failed to get data for {ticker}. Error: {stock_data.get('error', 'Unknown')}")

    if not all_market_data[today_str]:
        logging.error("Aggregation failed for all tickers. Not writing to output file.")
        return

    logging.info(f"Aggregation complete. Writing data for {len(all_market_data[today_str])} tickers to {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(all_market_data, f, indent=2)
        logging.info(f"Successfully wrote aggregated data to {OUTPUT_FILE}.")
        print("Success: data_aggregator.py ran without errors and created full_market_data.json.")
    except IOError as e:
        logging.error(f"Failed to write to {OUTPUT_FILE}: {e}")

if __name__ == "__main__":
    run_full_aggregation()