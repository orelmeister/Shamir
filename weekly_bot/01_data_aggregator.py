"""
01_data_aggregator.py

Phase 1: Data Collection
Gathers all necessary market and news data using FMP and Polygon APIs.

Inputs: None (fetches from external APIs)
Outputs: 
  - full_market_data.json (aggregated stock data with news)
  - Updates shared_state/phase_state.json

Usage:
    python weekly_bot/01_data_aggregator.py
"""

import json
import logging
import os
import sys
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
import yfinance as yf

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Local imports
from shared_state.state_manager import StateManager, update_phase_state

# --- Configuration ---
load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
CONCURRENT_REQUESTS = 10
NEWS_FETCH_LIMIT = 100

# Growth Focus Filters (from main.py config)
MIN_REVENUE_GROWTH = 0.10       # Require 10%+ YoY revenue growth
MARKET_CAP_MIN = 50_000_000     # $50M minimum
MARKET_CAP_MAX = 350_000_000    # $350M maximum

# Output file
OUTPUT_FILE = "full_market_data.json"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "agent": "DataAggregator", "message": "%(message)s"}',
    handlers=[
        logging.FileHandler(f"logs/phase1_aggregation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DataAggregator:
    """Phase 1: Data Collection Agent (standalone version)"""
    
    def __init__(self):
        self.state_manager = StateManager()
        logger.info("=" * 60)
        logger.info("PHASE 1: Data Aggregation")
        logger.info("=" * 60)
    
    async def run(self):
        """Main execution method"""
        try:
            # Update phase state
            update_phase_state("aggregation", "running")
            
            # Aggregate data
            aggregated_data = await self._aggregate_data()
            
            if not aggregated_data:
                logger.error("Aggregation failed, no data was collected.")
                update_phase_state("aggregation", "failed", error="No data collected")
                sys.exit(1)
            
            # PRE-LLM FILTER: Remove stocks without sufficient revenue growth
            logger.info(f"Applying pre-LLM revenue growth filter (>={MIN_REVENUE_GROWTH*100:.0f}% CAGR required)...")
            filtered_data = []
            for stock in aggregated_data:
                revenue_growth = stock.get("revenue_growth_cagr", 0)
                ticker = stock.get("ticker", "Unknown")
                if revenue_growth >= MIN_REVENUE_GROWTH:
                    filtered_data.append(stock)
                    logger.debug(f"✅ {ticker}: {revenue_growth*100:.1f}% CAGR")
                else:
                    logger.debug(f"❌ {ticker}: {revenue_growth*100:.1f}% < {MIN_REVENUE_GROWTH*100:.0f}%")
            
            logger.info(f"Pre-LLM filter: {len(aggregated_data)} stocks -> {len(filtered_data)} stocks (passed revenue growth filter)")
            aggregated_data = filtered_data
            
            if not aggregated_data:
                logger.warning("No stocks passed pre-LLM revenue growth filter.")
                update_phase_state("aggregation", "failed", error="No stocks passed filters")
                sys.exit(1)
            
            # Save aggregated data
            try:
                with open(OUTPUT_FILE, 'w') as f:
                    json.dump(aggregated_data, f, indent=4)
                logger.info(f"✅ Saved aggregated data for {len(aggregated_data)} tickers to {OUTPUT_FILE}")
            except Exception as e:
                logger.error(f"Failed to save aggregated data file: {e}")
                update_phase_state("aggregation", "failed", error=str(e))
                sys.exit(1)
            
            # Update phase state
            update_phase_state("aggregation", "completed")
            logger.info(f"✅ Phase 1 complete: {len(aggregated_data)} stocks ready for analysis")
            
        except Exception as e:
            logger.critical(f"Critical error during data aggregation: {e}", exc_info=True)
            update_phase_state("aggregation", "failed", error=str(e))
            sys.exit(1)
    
    async def _aggregate_data(self):
        """Fetch all stock data concurrently"""
        all_market_data = []
        async with aiohttp.ClientSession() as session:
            tickers = await self._fetch_target_tickers(session)
            if not tickers:
                logger.critical("No tickers returned from FMP screener.")
                return []
            
            logger.info(f"Found {len(tickers)} target tickers to process.")
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
            tasks = [self._fetch_stock_data_with_semaphore(session, ticker, semaphore) for ticker in tickers]
            results = await asyncio.gather(*tasks)
        
        for data in results:
            if data and not data.get("error") and data.get("news"):
                all_market_data.append(data)
            elif data and not data.get("news"):
                logger.info(f"Discarding {data.get('ticker')} due to no news.")
        
        return all_market_data
    
    async def _fetch_target_tickers(self, session):
        """Fetch target tickers from FMP stock screener"""
        logger.info("Fetching target tickers from FMP stock screener for NYSE and NASDAQ.")
        all_tickers = set()
        exchanges_to_query = ["nyse", "nasdaq"]
        
        for exchange in exchanges_to_query:
            logger.info(f"Querying for exchange: {exchange.upper()}")
            params = {
                "marketCapMoreThan": MARKET_CAP_MIN,
                "marketCapLowerThan": MARKET_CAP_MAX,
                "priceMoreThan": 1,
                "volumeMoreThan": 50000,
                "isEtf": "false",
                "isFund": "false",
                "country": "US",
                "exchange": exchange,
                "apikey": FMP_API_KEY
            }
            screener_url = "https://financialmodelingprep.com/api/v3/stock-screener"
            try:
                async with session.get(screener_url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if data:
                        page_tickers = {item['symbol'] for item in data}
                        all_tickers.update(page_tickers)
                        logger.info(f"Found {len(page_tickers)} tickers for {exchange.upper()}.")
                    else:
                        logger.warning(f"No tickers returned for {exchange.upper()}.")
            except Exception as e:
                logger.critical(f"Could not fetch tickers from FMP screener for {exchange.upper()}: {e}")
                continue
        
        logger.info(f"Found a total of {len(all_tickers)} unique tickers across all exchanges.")
        return list(all_tickers)
    
    async def _fetch_stock_data_with_semaphore(self, session, ticker, semaphore):
        async with semaphore:
            return await self._fetch_stock_data(session, ticker)
    
    async def _fetch_stock_data(self, session, ticker):
        """Fetch complete stock data (fundamentals + news)"""
        logger.debug(f"Processing ticker: {ticker}")
        fmp_data = await self._fetch_fmp_data(session, ticker)
        
        news_items = []
        news_source = "None"
        
        # 1. Try Polygon
        polygon_data = await self._fetch_polygon_news(session, ticker)
        if polygon_data.get("news"):
            news_items = polygon_data["news"]
            news_source = "Polygon"
        
        # 2. Fallback to FMP
        if not news_items:
            logger.info(f"No news from Polygon for {ticker}. Trying FMP.")
            fmp_news_data = await self._fetch_fmp_news(session, ticker)
            if fmp_news_data.get("news"):
                news_items = fmp_news_data["news"]
                news_source = "FMP"
        
        # 3. Final fallback to yfinance
        if not news_items:
            logger.info(f"No news from FMP for {ticker}. Trying yfinance.")
            yfinance_data = await self._fetch_yfinance_news(ticker)
            if yfinance_data.get("news"):
                news_items = yfinance_data["news"]
                news_source = "yfinance"
        
        logger.debug(f"Found {len(news_items)} news items for {ticker} from {news_source}.")
        
        combined_data = {
            "ticker": ticker,
            "price": fmp_data.get("price", 0),
            "market_cap": fmp_data.get("market_cap", 0),
            "revenue": fmp_data.get("revenue", 0),
            "net_income": fmp_data.get("net_income", 0),
            "revenue_growth_cagr": fmp_data.get("revenue_growth_cagr", 0),
            "news": news_items,
            "news_source": news_source,
            "error": fmp_data.get("error")
        }
        return combined_data
    
    async def _fetch_fmp_data(self, session, ticker):
        """Fetch fundamentals from FMP API"""
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
        income_url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
        params = {"apikey": FMP_API_KEY, "limit": 5, "period": "annual"}
        try:
            async with asyncio.TaskGroup() as tg:
                profile_task = tg.create_task(session.get(profile_url, params={"apikey": FMP_API_KEY}))
                income_task = tg.create_task(session.get(income_url, params=params))
            
            profile_resp = await profile_task
            income_resp = await income_task
            
            profile_data_list = await profile_resp.json()
            if not profile_data_list:
                logger.error(f"[FMP] No profile data for {ticker}.")
                return {"error": "No profile data"}
            
            profile_data = profile_data_list[0]
            
            income_data_list = await income_resp.json()
            if not income_data_list:
                logger.error(f"[FMP] No income statement for {ticker}.")
                return {"error": "No income statement"}
            
            # Calculate 5-year CAGR
            revenue_growth_cagr = 0
            if len(income_data_list) >= 5:
                latest_revenue_val = income_data_list[0].get("revenue", 0)
                oldest_revenue_val = income_data_list[4].get("revenue", 0)
                
                if oldest_revenue_val > 0 and latest_revenue_val > 0:
                    years = 4
                    revenue_growth_cagr = (latest_revenue_val / oldest_revenue_val) ** (1 / years) - 1
                    logger.debug(f"[FMP] {ticker} 5-year CAGR: {revenue_growth_cagr*100:.2f}%")
            elif len(income_data_list) >= 2:
                prior_revenue = income_data_list[1].get("revenue", 0)
                latest_revenue = income_data_list[0].get("revenue", 0)
                if prior_revenue > 0:
                    revenue_growth_cagr = (latest_revenue - prior_revenue) / prior_revenue
                    logger.debug(f"[FMP] {ticker} YoY growth (fallback): {revenue_growth_cagr*100:.2f}%")
            
            return {
                "price": profile_data.get("price", 0),
                "market_cap": profile_data.get("mktCap", 0),
                "company_name": profile_data.get("companyName"),
                "revenue": income_data_list[0].get("revenue", 0),
                "net_income": income_data_list[0].get("netIncome", 0),
                "revenue_growth_cagr": revenue_growth_cagr
            }
        except Exception as e:
            logger.error(f"[FMP] Error for {ticker}: {e}")
            return {"error": str(e)}
    
    async def _fetch_polygon_news(self, session, ticker):
        """Fetch news from Polygon API"""
        url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit={NEWS_FETCH_LIMIT}&apiKey={POLYGON_API_KEY}"
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                news_items = [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("article_url", ""),
                        "content": item.get("description", "")
                    }
                    for item in data.get("results", [])
                ]
                return {"news": news_items}
        except Exception as e:
            logger.error(f"[Polygon] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}
    
    async def _fetch_fmp_news(self, session, ticker):
        """Fetch news from FMP API"""
        url = f"https://financialmodelingprep.com/api/v3/stock_news"
        params = {
            "tickers": ticker,
            "limit": NEWS_FETCH_LIMIT,
            "apikey": FMP_API_KEY
        }
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                news_items = [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("text", ""),
                        "published_date": item.get("publishedDate", ""),
                        "site": item.get("site", "")
                    }
                    for item in data
                ]
                logger.debug(f"[FMP] Fetched {len(news_items)} news items for {ticker}.")
                return {"news": news_items}
        except Exception as e:
            logger.error(f"[FMP] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}
    
    async def _fetch_yfinance_news(self, ticker):
        """Fetch news from yfinance (fallback)"""
        try:
            loop = asyncio.get_event_loop()
            yf_ticker = await loop.run_in_executor(None, lambda: yf.Ticker(ticker))
            news = await loop.run_in_executor(None, lambda: yf_ticker.news)
            return {"news": [{"title": item.get("title", ""), "url": item.get("link")} for item in news[:5]]}
        except Exception as e:
            logger.error(f"[yfinance] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}


if __name__ == "__main__":
    aggregator = DataAggregator()
    asyncio.run(aggregator.run())
