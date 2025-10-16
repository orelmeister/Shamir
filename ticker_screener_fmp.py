
import os
import json
import logging
import requests
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")
OUTPUT_FILE = "us_tickers.json"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "ticker_screener_fmp.log")

# Market Cap Range
MIN_MARKET_CAP = 300_000_000  # $300 Million
MAX_MARKET_CAP = 10_000_000_000 # $10 Billion

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

def screen_tickers_fmp():
    """
    Screens for tickers using the FMP API based on market capitalization and saves them to a file.
    """
    logging.info("--- Starting Ticker Screening Process using FMP API ---")
    
    if not FMP_API_KEY:
        logging.critical("FMP_API_KEY not found in environment variables. Please check your .env file.")
        print("Error: FMP_API_KEY not found.")
        return

    logging.info(f"Screening for tickers with market cap between ${MIN_MARKET_CAP/1_000_000:.0f}M and ${MAX_MARKET_CAP/1_000_000_000:.0f}B.")

    try:
        # Construct the API URL for the FMP stock screener
        url = "https://financialmodelingprep.com/api/v3/stock-screener"
        params = {
            "marketCapMoreThan": MIN_MARKET_CAP,
            "marketCapLowerThan": MAX_MARKET_CAP,
            "isActivelyTrading": "true",
            "exchange": "NASDAQ", # Focusing on NASDAQ for quality
            "limit": 1000, # Set a reasonable limit
            "apikey": FMP_API_KEY
        }

        response = requests.get(url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        data = response.json()

        if not data:
            logging.warning("No tickers found from FMP matching the criteria. The output file will be empty.")
            return

        # FMP returns a list of objects, we just need the 'symbol'
        screened_tickers = [{"ticker": item['symbol']} for item in data]

        logging.info(f"Found {len(screened_tickers)} tickers matching the criteria from FMP.")

        # Save the tickers to the output file
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(screened_tickers, f, indent=2)
            
        logging.info(f"Successfully saved tickers to {OUTPUT_FILE}.")
        print(f"Success: FMP ticker screener ran without errors and created {OUTPUT_FILE} with {len(screened_tickers)} tickers.")

    except requests.exceptions.RequestException as e:
        logging.critical(f"An error occurred during the FMP API request: {e}")
        print(f"Error: FMP API request failed. See {LOG_FILE} for details.")
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}")
        print(f"Error: Ticker screening failed. See {LOG_FILE} for details.")

if __name__ == "__main__":
    screen_tickers_fmp()
