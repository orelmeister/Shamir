import os
import json
import logging
import asyncio
import aiohttp
import yfinance as yf
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# --- Configuration ---
load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
TICKERS_FILE = "us_tickers.json"
OUTPUT_FILE = "full_market_data.json"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "data_aggregator_async.log")
CONCURRENT_REQUESTS = 10 # Limit the number of concurrent API requests

# --- Logging Setup ---
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# --- Helper Functions ---

async def fetch_target_tickers(session):
    """
    Fetches tickers from FMP's stock screener that match our market cap criteria.
    """
    logging.info("Fetching target tickers from FMP stock screener...")
    # URL encode the parameters
    params = {
        "marketCapMoreThan": 50000000,
        "marketCapLowerThan": 350000000,
        "isEtf": "false",
        "isActivelyTrading": "true",
        "exchange": "NASDAQ,NYSE",
        "limit": 2000, # Set a high limit to get all potential candidates
        "apikey": FMP_API_KEY
    }
    screener_url = "https://financialmodelingprep.com/api/v3/stock-screener"
    
    try:
        async with session.get(screener_url, params=params) as response:
            response.raise_for_status()
            data = await response.json()
            tickers = [item['symbol'] for item in data]
            logging.info(f"FMP screener returned {len(tickers)} tickers matching criteria.")
            return tickers
    except Exception as e:
        logging.critical(f"Could not fetch tickers from FMP screener: {e}")
        return []

async def fetch_fmp_data(session, ticker):
    """Asynchronously fetches comprehensive financial data from FMP."""
    profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
    income_statement_url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
    historical_price_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{ticker}"
    
    params = {"apikey": FMP_API_KEY}
    annual_params = {"apikey": FMP_API_KEY, "period": "annual", "limit": 1}
    historical_params = {"apikey": FMP_API_KEY, "timeseries": 100} # Get last 100 days

    try:
        # --- Parallel API Calls within FMP ---
        async with asyncio.TaskGroup() as tg:
            profile_task = tg.create_task(session.get(profile_url, params=params))
            income_task = tg.create_task(session.get(income_statement_url, params=annual_params))
            historical_task = tg.create_task(session.get(historical_price_url, params=historical_params))

        profile_resp = await profile_task
        income_resp = await income_task
        historical_resp = await historical_task

        profile_resp.raise_for_status()
        income_resp.raise_for_status()
        historical_resp.raise_for_status()

        profile_data = await profile_resp.json()
        income_data = await income_resp.json()
        historical_data = await historical_resp.json()

        # --- Process Data ---
        output = {"error": None}
        
        # Profile data
        if profile_data:
            profile = profile_data[0]
            output["market_cap"] = profile.get("mktCap", 0)
            output["price"] = profile.get("price", 0)
        else:
            output["market_cap"] = 0
            output["price"] = 0

        # Income statement data
        if income_data:
            latest_income_statement = income_data[0]
            output["revenue"] = latest_income_statement.get("revenue", 0)
            output["net_income"] = latest_income_statement.get("netIncome", 0)
        else:
            output["revenue"] = 0
            output["net_income"] = 0

        # Historical price data
        if historical_data and "historical" in historical_data:
            prices = [item['close'] for item in historical_data['historical']]
            if len(prices) >= 90:
                output["price_30d_avg"] = sum(prices[:30]) / 30
                output["price_90d_avg"] = sum(prices[:90]) / 90
            elif len(prices) >= 30:
                output["price_30d_avg"] = sum(prices[:30]) / 30
                output["price_90d_avg"] = None # Not enough data
            else:
                output["price_30d_avg"] = None
                output["price_90d_avg"] = None
        else:
            output["price_30d_avg"] = None
            output["price_90d_avg"] = None
            
        return output

    except Exception as e:
        logging.error(f"[FMP] Error for {ticker}: {e}")
        return {"error": f"FMP fetch failed: {e}"}

async def fetch_article_content(session, url):
    """Fetches the main text content from a news article URL."""
    if not url:
        return ""
    try:
        async with session.get(url, timeout=10) as response:
            response.raise_for_status()
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            # Find all paragraph tags and join their text.
            # This is a simple approach and might need refinement for specific sites.
            paragraphs = soup.find_all('p')
            return " ".join([p.get_text() for p in paragraphs])
    except Exception as e:
        logging.warning(f"[Scraper] Could not fetch article content from {url}: {e}")
        return ""

async def fetch_polygon_news(session, ticker):
    """Asynchronously fetches news from Polygon."""
    url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit=100&apiKey={POLYGON_API_KEY}"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            
            news_items = []
            # Limit to fetching the content of the top 10 articles to avoid excessive requests
            for item in data.get("results", [])[:10]:
                article_url = item.get("article_url")
                content = await fetch_article_content(session, article_url)
                news_items.append({
                    "title": item.get("title", ""),
                    "url": article_url,
                    "summary": content[:500] + "..." if content else "Summary not available." # Truncate for brevity
                })
            return {"news": news_items}
    except Exception as e:
        logging.error(f"[Polygon] News error for {ticker}: {e}")
        return {"news": [], "error": f"Polygon news fetch failed: {e}"}

async def fetch_yfinance_news(session, ticker):
    """
    Asynchronously fetches news from Yahoo Finance as a fallback.
    Note: yfinance is not async, so we run it in an executor.
    """
    logging.info(f"[yfinance] Attempting to fetch news for {ticker}...")
    try:
        loop = asyncio.get_event_loop()
        # yf.Ticker is a blocking call, run in executor
        yf_ticker = await loop.run_in_executor(None, lambda: yf.Ticker(ticker))
        news = await loop.run_in_executor(None, lambda: yf_ticker.news)

        if not news:
            logging.info(f"[yfinance] No news found for {ticker}.")
            return {"news": []}

        news_items = []
        # Limit to fetching the content of the top 3 articles
        for item in news[:3]:
            article_url = item.get("link")
            content = await fetch_article_content(session, article_url)
            news_items.append({
                "title": item.get("title", ""),
                "url": article_url,
                "summary": content[:500] + "..." if content else "Summary not available."
            })
        logging.info(f"[yfinance] Successfully fetched {len(news_items)} articles for {ticker}.")
        return {"news": news_items}
    except Exception as e:
        logging.error(f"[yfinance] News error for {ticker}: {e}")
        return {"news": [], "error": f"yfinance news fetch failed: {e}"}

async def fetch_stock_data(session, ticker):
    """Fetches data for a single stock from FMP and news from Polygon/yfinance."""
    logging.info(f"--- Processing ticker: {ticker} ---")
    
    # Run FMP and Polygon calls in parallel
    tasks = [
        fetch_fmp_data(session, ticker),
        fetch_polygon_news(session, ticker)
    ]
    results = await asyncio.gather(*tasks)
    
    fmp_data = results[0]
    polygon_data = results[1]

    # --- yfinance Fallback Logic ---
    # If Polygon returned no news, try yfinance
    if not polygon_data.get("news"):
        logging.info(f"[Fallback] No news from Polygon for {ticker}. Trying yfinance.")
        yfinance_data = await fetch_yfinance_news(session, ticker)
        # Use yfinance data if it's available
        if yfinance_data.get("news"):
            polygon_data = yfinance_data # Overwrite polygon_data with yfinance_data
    
    # Combine the results
    combined_data = {
        "ticker": ticker,
        "price": fmp_data.get("price", 0),
        "market_cap": fmp_data.get("market_cap", 0),
        "revenue": fmp_data.get("revenue", 0),
        "net_income": fmp_data.get("net_income", 0),
        "price_30d_avg": fmp_data.get("price_30d_avg"),
        "price_90d_avg": fmp_data.get("price_90d_avg"),
        "news": polygon_data.get("news", []),
        "error": None
    }

    # Propagate errors if any occurred
    if fmp_data.get("error") or polygon_data.get("error"):
        combined_data["error"] = f"FMP: {fmp_data.get('error')}, Polygon: {polygon_data.get('error')}"
        logging.error(f"Failed to get complete data for {ticker}. Errors: {combined_data['error']}")
    else:
        logging.info(f"Successfully aggregated data for {ticker}.")
        
    return ticker, combined_data

async def fetch_stock_data_with_semaphore(session, ticker, semaphore):
    """Wrapper to acquire semaphore before fetching stock data."""
    async with semaphore:
        return await fetch_stock_data(session, ticker)

async def main():
    """Main function to run the asynchronous data aggregation."""
    logging.info("--- Starting Asynchronous Data Aggregation ---")
    
    all_market_data = {}
    today_str = asyncio.get_event_loop().run_in_executor(None, lambda: __import__('datetime').datetime.utcnow().strftime('%Y-%m-%d'))
    today_str = await today_str
    all_market_data[today_str] = {}

    async with aiohttp.ClientSession() as session:
        # 1. Fetch pre-filtered tickers from FMP
        tickers = await fetch_target_tickers(session)
        if not tickers:
            logging.critical("No tickers returned from FMP screener. Halting.")
            return

        logging.info(f"Found {len(tickers)} target tickers to process.")

        # 2. Fetch detailed data for the filtered tickers using a semaphore
        semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
        tasks = []
        for ticker in tickers:
            # The semaphore is passed to the task-creating function
            task = asyncio.create_task(fetch_stock_data_with_semaphore(session, ticker, semaphore))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)

    for ticker, data in results:
        if not data.get("error"):
            all_market_data[today_str][ticker] = data

    if not all_market_data[today_str]:
        logging.error("Aggregation failed for all tickers. Not writing to output file.")
        return

    logging.info(f"Aggregation complete. Writing data for {len(all_market_data[today_str])} tickers to {OUTPUT_FILE}")
    try:
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(all_market_data, f, indent=2)
        logging.info(f"Successfully wrote aggregated data to {OUTPUT_FILE}.")
        print(f"Success: data_aggregator_async.py created {OUTPUT_FILE} with {len(all_market_data[today_str])} tickers.")
    except IOError as e:
        logging.error(f"Failed to write to {OUTPUT_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
