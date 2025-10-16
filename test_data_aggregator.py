import asyncio
import aiohttp
import logging
import os
from dotenv import load_dotenv

# This is a simplified version of the data aggregator for testing purposes.
# It focuses on validating the FMP screener functionality.

# --- Configuration ---
load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_fetch_target_tickers(session):
    """
    Tests the FMP stock screener functionality to ensure we get a list of tickers
    that match our market cap criteria.
    """
    logging.info("--- Testing FMP Stock Screener ---")
    params = {
        "marketCapMoreThan": 300000000,
        "marketCapLowerThan": 10000000000,
        "isEtf": "false",
        "isActivelyTrading": "true",
        "exchange": "NASDAQ,NYSE",
        "limit": 10,  # Limit to 10 for a quick test
        "apikey": FMP_API_KEY
    }
    screener_url = "https://financialmodelingprep.com/api/v3/stock-screener"
    
    try:
        async with session.get(screener_url, params=params) as response:
            response.raise_for_status()
            data = await response.json()
            
            if not data:
                logging.error("[FAIL] FMP screener returned no data.")
                return

            logging.info(f"[SUCCESS] FMP screener returned {len(data)} tickers.")
            logging.info("Sample of returned tickers:")
            for item in data:
                logging.info(f"  - Ticker: {item['symbol']}, Market Cap: ${item['marketCap']:,}")
            
            # Verification
            first_item = data[0]
            if 300_000_000 <= first_item['marketCap'] <= 10_000_000_000:
                logging.info("[SUCCESS] First item's market cap is within the expected range.")
            else:
                logging.error(f"[FAIL] First item's market cap ({first_item['marketCap']}) is OUTSIDE the expected range.")

    except Exception as e:
        logging.critical(f"[FAIL] An error occurred while testing the FMP screener: {e}")

async def main():
    async with aiohttp.ClientSession() as session:
        await test_fetch_target_tickers(session)

if __name__ == "__main__":
    # Check for API key before running
    if not FMP_API_KEY:
        logging.error("FMP_API_KEY is not set. Please check your .env file.")
    else:
        asyncio.run(main())
