import asyncio
import aiohttp
import os
from dotenv import load_dotenv
import logging

# --- Configuration ---
load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

async def test_fetch_target_tickers():
    """
    Tests the FMP stock screener to ensure it's fetching tickers with the correct market cap.
    """
    logging.info("Testing FMP stock screener for market cap filter...")
    
    # Parameters to test: fetch top 5 stocks with market cap under $350 million
    params = {
        "marketCapMoreThan": 50000000,
        "marketCapLowerThan": 350000000,
        "isEtf": "false",
        "isActivelyTrading": "true",
        "exchange": "NASDAQ,NYSE",
        "limit": 5,  # Limit to 5 for a quick test
        "apikey": FMP_API_KEY
    }
    screener_url = "https://financialmodelingprep.com/api/v3/stock-screener"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(screener_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                if not data:
                    logging.warning("Test query returned no tickers. The filter might be too restrictive or there's an API issue.")
                    return

                logging.info(f"FMP screener returned {len(data)} tickers for the test.")
                logging.info("--- Top 5 Tickers and their Market Caps ---")
                for item in data:
                    symbol = item.get('symbol')
                    market_cap = item.get('marketCap', 'N/A')
                    logging.info(f"  - Ticker: {symbol}, Market Cap: {market_cap:,.0f}")
                logging.info("-------------------------------------------")
                
                # Verify the market caps
                all_caps_valid = all(item.get('marketCap', 0) < 350000000 for item in data)
                if all_caps_valid:
                    logging.info("✅ SUCCESS: All returned tickers have a market cap below $350,000,000.")
                else:
                    logging.error("❌ FAILURE: Some returned tickers have a market cap above $350,000,000.")

        except Exception as e:
            logging.critical(f"Could not fetch tickers from FMP screener during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch_target_tickers())
