
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
MAX_MARKET_CAP = 20_000_000_000 # $20 Billion

# Price Range (for day trading)
MIN_PRICE = 1.0  # $1
MAX_PRICE = 18.0 # $18

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

    logging.info(f"Screening for tickers with market cap between ${MIN_MARKET_CAP/1_000_000:.0f}M and ${MAX_MARKET_CAP/1_000_000_000:.0f}B and price between ${MIN_PRICE} and ${MAX_PRICE}.")

    try:
        # Query both NYSE and NASDAQ exchanges
        all_tickers = []
        exchanges = ["NASDAQ", "NYSE"]
        
        for exchange in exchanges:
            logging.info(f"Querying {exchange}...")
            url = "https://financialmodelingprep.com/api/v3/stock-screener"
            params = {
                "marketCapMoreThan": MIN_MARKET_CAP,
                "marketCapLowerThan": MAX_MARKET_CAP,
                "priceMoreThan": MIN_PRICE,
                "priceLowerThan": MAX_PRICE,
                "isActivelyTrading": "true",
                "exchange": exchange,
                "limit": 1000,
                "apikey": FMP_API_KEY
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data:
                logging.info(f"Found {len(data)} tickers on {exchange}")
                all_tickers.extend(data)
            else:
                logging.warning(f"No tickers found on {exchange}")

        if not all_tickers:
            logging.warning("No tickers found from FMP matching the criteria. The output file will be empty.")
            return
        
        # Remove duplicates by ticker symbol
        seen_tickers = set()
        unique_tickers = []
        for ticker_data in all_tickers:
            ticker = ticker_data.get('symbol')
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_tickers.append(ticker_data)
        
        data = unique_tickers
        logging.info(f"Total unique tickers across all exchanges: {len(data)}")

        # Blacklist: Known problematic tickers (ADRs, foreign stocks with restrictions)
        BLACKLIST = {'BBAR', 'YPF', 'VALE', 'PAM', 'TX', 'BBD', 'ITUB', 'PBR', 'SID'}
        
        # Filter out ADRs (American Depositary Receipts) - often have trading restrictions
        # ADR tickers often end in certain patterns or have 'ADR' in company name
        filtered_data = []
        adr_keywords = ['ADR', 'ADS', 'DEPOSITARY', 'SA DE CV', 'NV', 'PLC', 'LTD', 'BANCO']
        
        for item in data:
            ticker = item.get('symbol', '')
            company_name = item.get('companyName', '').upper()
            
            # Skip blacklisted tickers
            if ticker in BLACKLIST:
                logging.debug(f"Filtering out blacklisted ticker: {ticker}")
                continue
            
            # Skip if company name contains ADR indicators
            is_adr = any(keyword in company_name for keyword in adr_keywords)
            
            # Skip common foreign ADR suffixes
            if ticker.endswith('.A') or ticker.endswith('.B') or ticker.endswith('.C'):
                is_adr = True
            
            if not is_adr:
                filtered_data.append(item)
            else:
                logging.debug(f"Filtering out potential ADR: {ticker} ({company_name})")
        
        data = filtered_data
        logging.info(f"After ADR/blacklist filtering: {len(data)} tickers remaining")

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
