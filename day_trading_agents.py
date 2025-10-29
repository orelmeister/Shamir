"""
Contains the specialized agents for the Day-Trading Bot.
Now includes autonomous capabilities: observability, self-evaluation, and continuous improvement.
"""

import logging
import json
import os
import time
import asyncio
import aiohttp
import math
import multiprocessing
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd
import yfinance as yf
from ib_insync import IB, Stock, MarketOrder, LimitOrder, StopOrder, Order, util
import pandas_ta as ta
from market_hours import is_market_open
from polygon import RESTClient

# Autonomous system imports
from observability import get_database, get_tracer
from self_evaluation import PerformanceAnalyzer, SelfHealingMonitor
from continuous_improvement import ContinuousImprovementEngine

# --- Setup and Configuration ---
load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
FMP_API_KEY = os.getenv("FMP_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# Configuration
AGGREGATED_DATA_FILE = "full_market_data.json"
CONCURRENT_REQUESTS = 10
NEWS_FETCH_LIMIT = 100

class BaseDayTraderAgent(ABC):
    """Abstract base class for all day-trading agents."""
    def __init__(self, orchestrator, agent_name):
        self.orchestrator = orchestrator
        self.logger = orchestrator.logger
        self.agent_name = agent_name
        self.log_adapter = logging.LoggerAdapter(self.logger, {'agent': self.agent_name})

    def log(self, level, message, **kwargs):
        """Logs a message with the agent's name."""
        self.log_adapter.log(level, message, **kwargs)

    @abstractmethod
    def run(self):
        """The main execution method for the agent."""
        pass


class DataAggregatorAgent(BaseDayTraderAgent):
    """
    Responsible for gathering all necessary market and news data using FMP and Polygon.
    Copied from main.py to make day_trader.py self-contained.
    """
    def __init__(self, orchestrator):
        super().__init__(orchestrator, "DataAggregatorAgent")
        self.log(logging.INFO, "Data Aggregator Agent initialized.")
    
    def run(self):
        """Check if data is fresh for today AND complete, if not, aggregate new data."""
        self.log(logging.INFO, "--- [PHASE 0] Checking market data freshness. ---")
        
        # Check if data file exists and is from today AND has sufficient data
        if os.path.exists(AGGREGATED_DATA_FILE):
            try:
                # Check file modification time
                file_mod_time = datetime.fromtimestamp(os.path.getmtime(AGGREGATED_DATA_FILE))
                today = datetime.now().date()
                
                # Load and check data quality
                with open(AGGREGATED_DATA_FILE, 'r') as f:
                    existing_data = json.load(f)
                
                # Data is valid if: from today AND has at least 20 stocks with news
                if file_mod_time.date() == today and len(existing_data) >= 20:
                    self.log(logging.INFO, f"{AGGREGATED_DATA_FILE} is fresh ({today}) with {len(existing_data)} stocks. Using cached data.")
                    return
                else:
                    self.log(logging.INFO, f"{AGGREGATED_DATA_FILE} is stale or insufficient ({len(existing_data)} stocks). Refreshing data.")
            except Exception as e:
                self.log(logging.WARNING, f"Could not validate existing data: {e}. Will refresh data.")
        else:
            self.log(logging.INFO, f"{AGGREGATED_DATA_FILE} not found. Collecting fresh market data.")
        
        # Aggregate new data
        try:
            aggregated_data = asyncio.run(self._aggregate_data())
            
            if not aggregated_data:
                self.log(logging.ERROR, "Aggregation failed, no data was collected.")
                return

            # Save the aggregated data
            with open(AGGREGATED_DATA_FILE, 'w') as f:
                json.dump(aggregated_data, f, indent=4)
            self.log(logging.INFO, f"Successfully saved aggregated data for {len(aggregated_data)} tickers to {AGGREGATED_DATA_FILE}.")

        except Exception as e:
            self.log(logging.CRITICAL, f"A critical error occurred during data aggregation: {e}", exc_info=True)
            raise

    async def _aggregate_data(self):
        all_market_data = []
        async with aiohttp.ClientSession() as session:
            tickers = await self._fetch_target_tickers(session)
            if not tickers:
                self.log(logging.CRITICAL, "No tickers returned from FMP screener.")
                return []

            self.log(logging.INFO, f"Found {len(tickers)} target tickers to process.")
            
            # Filter by yesterday's ATR (volatility pre-screening)
            self.log(logging.INFO, "Pre-filtering tickers by yesterday's ATR (must be > 1.0%)...")
            filtered_tickers = await self._filter_by_atr(tickers)
            self.log(logging.INFO, f"After ATR filter: {len(filtered_tickers)} tickers remain (from {len(tickers)}).")
            
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
            tasks = [self._fetch_stock_data_with_semaphore(session, ticker, semaphore) for ticker in filtered_tickers]
            results = await asyncio.gather(*tasks)

        for data in results:
            # MUST have news for LLM to analyze catalyst-driven volatility
            # Check if news list exists AND is not empty
            if data and not data.get("error") and data.get("news") and len(data.get("news", [])) > 0:
                all_market_data.append(data)
            elif data and (not data.get("news") or len(data.get("news", [])) == 0):
                self.log(logging.DEBUG, f"Discarding {data.get('ticker')} - no news found in last 3 days (LLM needs catalyst info).")
            elif data and data.get("error"):
                self.log(logging.DEBUG, f"Discarding {data.get('ticker')} due to error: {data.get('error')}")
        
        self.log(logging.INFO, f"Successfully collected data for {len(all_market_data)} stocks with news (from {len(filtered_tickers)} after ATR filter).")
        return all_market_data

    async def _fetch_target_tickers(self, session):
        # FIRST: Check if us_tickers.json exists (from ticker_screener_fmp.py)
        us_tickers_file = "us_tickers.json"
        if os.path.exists(us_tickers_file):
            self.log(logging.INFO, f"Loading pre-screened tickers from {us_tickers_file}...")
            with open(us_tickers_file, 'r') as f:
                ticker_data = json.load(f)
                # Extract ticker symbols from the list of dicts
                tickers = [item['ticker'] for item in ticker_data]
                self.log(logging.INFO, f"Loaded {len(tickers)} pre-screened tickers from {us_tickers_file}.")
                return tickers
        
        # FALLBACK: If us_tickers.json doesn't exist, fetch from FMP API
        self.log(logging.INFO, "us_tickers.json not found. Fetching target tickers from FMP stock screener for NYSE and NASDAQ.")
        all_tickers = set()
        exchanges_to_query = ["nyse", "nasdaq"]

        # FMP has a 1000 result limit, so we'll split by market cap ranges to get all stocks
        # $50M-$500M, $500M-$1B, $1B-$2B
        market_cap_ranges = [
            (50000000, 500000000),
            (500000000, 1000000000),
            (1000000000, 2000000000)
        ]

        for exchange in exchanges_to_query:
            self.log(logging.INFO, f"Querying for exchange: {exchange.upper()}")
            
            for cap_min, cap_max in market_cap_ranges:
                params = {
                    "marketCapMoreThan": cap_min,
                    "marketCapLowerThan": cap_max,
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
                            self.log(logging.DEBUG, f"Found {len(page_tickers)} tickers for {exchange.upper()} (${cap_min/1e6:.0f}M-${cap_max/1e6:.0f}M).")
                        else:
                            self.log(logging.DEBUG, f"No tickers returned for {exchange.upper()} (${cap_min/1e6:.0f}M-${cap_max/1e6:.0f}M).")

                except Exception as e:
                    self.log(logging.ERROR, f"Could not fetch tickers from FMP screener for {exchange.upper()} (${cap_min/1e6:.0f}M-${cap_max/1e6:.0f}M): {e}")
                    continue
            
            self.log(logging.INFO, f"Found {len([t for t in all_tickers])} total unique tickers so far for {exchange.upper()}.")
        
        self.log(logging.INFO, f"Found a total of {len(all_tickers)} unique tickers across all exchanges.")
        return list(all_tickers)

    async def _filter_by_atr(self, tickers: list) -> list:
        """
        Filter tickers by yesterday's ATR (Average True Range) - PARALLEL VERSION.
        Only keep stocks with historical volatility > 1.0%.
        This pre-screens out dead/quiet stocks before expensive LLM analysis.
        """
        from datetime import datetime, timedelta
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        self.log(logging.INFO, f"Calculating yesterday's ATR for {len(tickers)} tickers in parallel...")
        
        filtered = []
        
        # Use ThreadPoolExecutor for parallel yfinance calls (blocking I/O)
        max_workers = 15  # Optimal from testing (5-30 range tested)
        
        def calculate_atr_for_ticker(ticker):
            """Calculate ATR for a single ticker"""
            try:
                # Use yfinance for historical data (faster than IBKR for bulk queries)
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1mo", interval="1d")
                
                if hist.empty or len(hist) < 14:
                    return None
                
                # Calculate ATR (14-day period)
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean().iloc[-1]
                
                # Convert to percentage
                current_price = hist['Close'].iloc[-1]
                atr_pct = (atr / current_price) * 100
                
                # Return ticker if ATR > 1.0%
                if atr_pct >= 1.0:
                    return (ticker, atr_pct)
                else:
                    return None
                
            except Exception as e:
                return None
        
        # Run in executor to avoid blocking async loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {executor.submit(calculate_atr_for_ticker, ticker): ticker for ticker in tickers}
            
            # Process as they complete
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                if result:
                    ticker, atr_pct = result
                    filtered.append(ticker)
                    self.log(logging.DEBUG, f"{ticker}: ATR {atr_pct:.2f}% OK")
                
                completed += 1
                # Log progress every 100 tickers
                if completed % 100 == 0:
                    self.log(logging.INFO, f"Progress: {completed}/{len(tickers)} tickers processed ({len(filtered)} passed ATR filter)")
        
        self.log(logging.INFO, f"ATR filtering complete: {len(filtered)} tickers passed (from {len(tickers)})")
        return filtered

    async def _fetch_stock_data_with_semaphore(self, session, ticker, semaphore):
        async with semaphore:
            return await self._fetch_stock_data(session, ticker)

    async def _fetch_stock_data(self, session, ticker):
        self.log(logging.DEBUG, f"Processing ticker: {ticker}")
        fmp_data = await self._fetch_fmp_data(session, ticker)
        
        news_items = []
        news_source = "None"

        # Use ONLY Polygon for news (no yfinance fallback due to rate limits)
        polygon_data = await self._fetch_polygon_news(session, ticker)
        if polygon_data.get("news"):
            news_items = polygon_data["news"]
            news_source = "Polygon"
        else:
            self.log(logging.DEBUG, f"No news from Polygon for {ticker}. Skipping news.")

        self.log(logging.DEBUG, f"Found {len(news_items)} news items for {ticker} from {news_source}.")

        combined_data = {
            "ticker": ticker, "price": fmp_data.get("price", 0),
            "market_cap": fmp_data.get("market_cap", 0), "revenue": fmp_data.get("revenue", 0),
            "net_income": fmp_data.get("net_income", 0), "news": news_items,
            "error": fmp_data.get("error")
        }
        return combined_data

    async def _fetch_fmp_data(self, session, ticker):
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
        income_url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
        params = {"apikey": FMP_API_KEY, "limit": 1, "period": "annual"}
        try:
            async with asyncio.TaskGroup() as tg:
                profile_task = tg.create_task(session.get(profile_url, params={"apikey": FMP_API_KEY}))
                income_task = tg.create_task(session.get(income_url, params=params))
            
            # TaskGroup waits for all tasks when exiting context, use .result() not await
            profile_resp = profile_task.result()
            income_resp = income_task.result()
            
            profile_data_list = await profile_resp.json()
            if not profile_data_list:
                self.log(logging.ERROR, f"[FMP] No profile data for {ticker}.")
                return {"error": "No profile data"}

            profile_data = profile_data_list[0]
            
            # Income statement is optional - many stocks don't have it (SPACs, financials, etc.)
            income_data_list = await income_resp.json()
            revenue = 0
            net_income = 0
            
            if income_data_list:
                income_data = income_data_list[0]
                revenue = income_data.get("revenue", 0)
                net_income = income_data.get("netIncome", 0)
            else:
                self.log(logging.DEBUG, f"[FMP] No income statement for {ticker} (using profile data only).")

            return {
                "price": profile_data.get("price", 0), 
                "market_cap": profile_data.get("mktCap", 0),
                "company_name": profile_data.get("companyName"),
                "sector": profile_data.get("sector", "Unknown"),
                "industry": profile_data.get("industry", "Unknown"),
                "revenue": revenue, 
                "net_income": net_income
            }
        except Exception as e:
            self.log(logging.ERROR, f"[FMP] Error for {ticker}: {e}")
            return {"error": str(e)}

    async def _fetch_polygon_news(self, session, ticker):
        # Only fetch news from last 3 days to avoid old acquisition/merger news
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        
        url = (f"https://api.polygon.io/v2/reference/news?ticker={ticker}"
               f"&published_utc.gte={start_date}&published_utc.lte={end_date}"
               f"&limit={NEWS_FETCH_LIMIT}&apiKey={POLYGON_API_KEY}")
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                news_items = [{"title": item.get("title", ""), "url": item.get("article_url")} for item in data.get("results", [])]
                self.log(logging.DEBUG, f"[Polygon] Fetched {len(news_items)} news items for {ticker} (last 3 days).")
                return {"news": news_items}
        except Exception as e:
            self.log(logging.ERROR, f"[Polygon] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}

    async def _fetch_yfinance_news(self, ticker):
        try:
            loop = asyncio.get_event_loop()
            yf_ticker = await loop.run_in_executor(None, lambda: yf.Ticker(ticker))
            news = await loop.run_in_executor(None, lambda: yf_ticker.news)
            return {"news": [{"title": item.get("title", ""), "url": item.get("link")} for item in news[:5]]}
        except Exception as e:
            self.log(logging.ERROR, f"[yfinance] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}


class WatchlistAnalystAgent(BaseDayTraderAgent):
    """
    This agent runs pre-market to analyze market data and generate a watchlist
    of stocks with high potential for intraday movement.
    NO IBKR CONNECTION - purely LLM analysis.
    """
    def __init__(self, orchestrator):
        super().__init__(orchestrator, "WatchlistAnalystAgent")
        self.log(logging.INFO, "Watchlist Analyst Agent initialized.")

    def _get_day_trading_analysis(self, stock_data):
        ticker = stock_data.get('ticker', 'Unknown')
        self.log(logging.INFO, f"Analyzing {ticker} for day trading potential.")
        
        prompt = self._create_analysis_prompt(stock_data)
        response = None
        model_used = None

        # 1. Try DeepSeek first
        try:
            self.log(logging.INFO, f"Attempting analysis with DeepSeek for {ticker}...")
            deepseek_llm = ChatDeepSeek(model="deepseek-reasoner", api_key=DEEPSEEK_API_KEY, temperature=0)
            response = deepseek_llm.invoke(prompt, config={'request_timeout': 180})
            self.log(logging.INFO, f"DeepSeek analysis successful for {ticker}.")
            model_used = "DeepSeek"
        except Exception as e:
            self.log(logging.WARNING, f"DeepSeek failed for {ticker}: {e}. Falling back to Gemini.")
            
            # 2. Fallback to Gemini
            try:
                self.log(logging.INFO, f"Attempting analysis with Gemini for {ticker}...")
                gemini_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0)
                response = gemini_llm.invoke(prompt)
                self.log(logging.INFO, f"Gemini analysis successful for {ticker}.")
                model_used = "Gemini"
            except Exception as e_gemini:
                self.log(logging.ERROR, f"Gemini fallback also failed for {ticker}: {e_gemini}")
                return {"candidate_decision": "ERROR", "reasoning": f"All LLM analyses failed for {ticker}."}

        if response:
            return self._parse_analysis_response(response.content, ticker, model_used)
        else:
            return {"candidate_decision": "ERROR", "reasoning": f"LLM response was empty for {ticker}."}

    def _create_analysis_prompt(self, stock_data):
        """
        Creates the prompt for day trading analysis.
        """
        ticker = stock_data.get("ticker", "Unknown")
        # Convert the whole stock_data dict to a JSON string for the prompt
        stock_data_str = json.dumps(stock_data, indent=2)

        return f"""
        You are an Expert Day-Trading Analyst specializing in identifying high-volatility stocks with significant intraday movement potential.

        Analyze the provided data for the stock {ticker}. Conduct a comprehensive evaluation focusing on:
        
        **1. NEWS CATALYST ANALYSIS (Critical for Day Trading)**
        - Recent News Volume: Is there fresh news (within last 24-48 hours) that could drive today's trading?
        - Sentiment Impact: Is the news highly positive (major breakthrough, earnings beat, partnership) or negative (regulatory issues, earnings miss, controversy)?
        - News Quality: Is it from major outlets that will attract trader attention?
        - Catalyst Strength: Rate the likelihood this news will cause significant price movement (0-10 scale)
        
        **2. VOLATILITY & MOMENTUM INDICATORS**
        - Price Volatility: Does the stock show signs of high beta or recent sharp price swings?
        - Volume Patterns: Is there unusual or increasing volume that suggests growing trader interest?
        - Historical Volatility: Based on the data, does this stock typically move 2%+ intraday?
        - Small/Mid-Cap Dynamics: Stocks under $2B market cap tend to be more volatile - factor this in
        
        **3. FUNDAMENTAL RISK ASSESSMENT**
        - Revenue & Profitability: Check for red flags (zero revenue, massive losses, negative trends)
        - Market Cap & Liquidity: Is the market cap between $50M-$2B (our target range)?
        - Debt & Financial Health: Are there signs of financial distress that could cause unpredictable swings?
        - Business Model: Does the company have a clear business that traders can understand?
        
        **4. DAY TRADING VIABILITY**
        - Entry/Exit Potential: Can we realistically enter and exit this position during market hours?
        - Spread & Liquidity: Will the bid-ask spread eat into profits?
        - Predictability: While volatile, is the volatility based on rational factors (news, sector trends) vs pure speculation?
        
        **DECISION CRITERIA:**
        - GOOD Candidate: High news catalyst + Clear volatility potential + Acceptable fundamentals + Tradeable
        - BAD Candidate: No catalyst OR Fundamentally broken OR Too illiquid OR Pure speculation without basis
        
        **Confidence Score Guide:**
        - 0.90-1.0: Exceptional catalyst, strong volatility signals, perfect conditions
        - 0.75-0.89: Strong catalyst, good volatility indicators, solid opportunity
        - 0.70-0.74: Moderate catalyst, decent volatility, acceptable risk
        - Below 0.70: Reject (don't include these)

        Data: {stock_data_str}

        Return ONLY a JSON object with "candidate_decision", "confidence_score", and "reasoning".
        Example:
        {{
          "candidate_decision": "GOOD",
          "confidence_score": 0.85,
          "reasoning": "Strong catalyst: FDA approval news from yesterday with 10+ articles. Stock has history of 3-5% daily swings. $850M market cap in our target range with good liquidity. Moderate revenue ($150M) with growing trajectory. High volume spike (3x average) indicates trader interest. Clear entry opportunity at market open."
        }}
        """

    def _parse_analysis_response(self, response_content, ticker, model_used):
        """
        Parses the analysis response from the LLM.
        """
        try:
            # The response might be wrapped in markdown
            clean_response = response_content.strip().replace('```json', '').replace('```', '')
            analysis = json.loads(clean_response)
            analysis['model'] = model_used
            return analysis
        except json.JSONDecodeError as e:
            self.log(logging.ERROR, f"JSON decode error for {ticker} analysis response: {e}. Content: '{response_content}'")
            return {"candidate_decision": "ERROR", "reasoning": "LLM analysis response was not valid JSON."}

    def run(self):
        """
        Executes the full pre-market analysis workflow using parallel LLM processing.
        NO IBKR VALIDATION - analyzes all stocks from full_market_data.json.
        Skips analysis if watchlist is already fresh for today.
        """
        watchlist_path = "day_trading_watchlist.json"
        
        # Check if watchlist already exists and is fresh for today
        if os.path.exists(watchlist_path):
            watchlist_mtime = datetime.fromtimestamp(os.path.getmtime(watchlist_path))
            today_date = datetime.now().date()
            if watchlist_mtime.date() == today_date:
                self.log(logging.INFO, f"{watchlist_path} is already up-to-date for today ({today_date}). Skipping analysis.")
                return
        
        self.log(logging.INFO, "Loading full market data from full_market_data.json...")
        try:
            with open("full_market_data.json", 'r') as f:
                market_data = json.load(f)
        except FileNotFoundError:
            self.log(logging.CRITICAL, "full_market_data.json not found. Cannot generate watchlist.")
            return

        if not market_data:
            self.log(logging.CRITICAL, "full_market_data.json is empty. Cannot generate watchlist.")
            return

        # Analyze ALL stocks in parallel using LLM
        self.log(logging.INFO, f"Analyzing {len(market_data)} stocks in parallel using LLM.")

        candidates = []
        # Use a ThreadPoolExecutor to run analyses in parallel
        with ThreadPoolExecutor(max_workers=15) as executor:
            # Create a future for each stock analysis
            future_to_stock = {executor.submit(self._get_day_trading_analysis, stock_data): stock_data for stock_data in market_data}
            
            for future in as_completed(future_to_stock):
                stock_data = future_to_stock[future]
                ticker = stock_data.get('ticker', 'Unknown')
                try:
                    analysis = future.result()
                    if analysis and analysis.get("candidate_decision") == "GOOD" and analysis.get("confidence_score", 0) > 0.7:
                        self.log(logging.INFO, f"Analysis for {ticker} completed. Result: GOOD candidate with score > 0.7.")
                        # Use SMART routing - IBKR will automatically find the correct exchange
                        # No need to specify ISLAND, NASDAQ, or NYSE - SMART handles it all
                        candidates.append({
                            "ticker": ticker,
                            "primaryExchange": "SMART",  # Let IBKR's smart routing find the best venue
                            "confidence_score": analysis.get("confidence_score"),
                            "reasoning": analysis.get("reasoning"),
                            "model": analysis.get("model")
                        })
                    elif analysis and analysis.get("candidate_decision") == "GOOD":
                        self.log(logging.INFO, f"Analysis for {ticker} completed. Result: GOOD candidate, but score {analysis.get('confidence_score', 0)} is 0.7 or below. Discarding.")
                    elif analysis:
                        self.log(logging.INFO, f"Analysis for {ticker} completed. Result: {analysis.get('candidate_decision')}.")
                    else:
                        self.log(logging.WARNING, f"Analysis for {ticker} returned no result.")

                except Exception as exc:
                    self.log(logging.ERROR, f'{ticker} generated an exception during analysis: {exc}')

        # Sort candidates by confidence score in descending order
        sorted_candidates = sorted(candidates, key=lambda x: x.get('confidence_score', 0.0), reverse=True)
        
        # Take the top 10 candidates for the watchlist (or fewer if not enough good candidates)
        watchlist = sorted_candidates[:10]

        self.log(logging.INFO, f"Generated a watchlist with {len(watchlist)} candidates.")
        
        watchlist_path = "day_trading_watchlist.json"
        self.log(logging.INFO, f"Saving top candidates to {watchlist_path}...")
        with open(watchlist_path, 'w') as f:
            json.dump(watchlist, f, indent=4)
        
        self.log(logging.INFO, "Watchlist generation complete.")


class ATRPredictorAgent(BaseDayTraderAgent):
    """
    Uses LLM to predict TODAY's volatility based on morning news and yesterday's ATR.
    This helps filter stocks BEFORE deep analysis - only analyze stocks likely to move.
    """
    def __init__(self, orchestrator):
        super().__init__(orchestrator, "ATRPredictorAgent")
        self.log(logging.INFO, "ATR Predictor Agent initialized.")
    
    def run(self, market_data: list) -> list:
        """
        Predict ATR for each stock and return top candidates.
        
        Args:
            market_data: List of stock data from DataAggregatorAgent
            
        Returns:
            List of stocks with predicted ATR > 1.5%, sorted by confidence
        """
        self.log(logging.INFO, f"--- [PHASE 0.5] ATR Prediction for {len(market_data)} stocks ---")
        self.log(logging.INFO, f"Analyzing {len(market_data)} stocks in parallel with 15 workers...")
        
        predictions = []
        processed_count = 0
        
        # Use parallel processing for speed
        with ThreadPoolExecutor(max_workers=15) as executor:
            future_to_ticker = {
                executor.submit(self._predict_atr, stock): stock['ticker'] 
                for stock in market_data
            }
            
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                processed_count += 1
                
                # Log progress every 50 stocks
                if processed_count % 50 == 0:
                    self.log(logging.INFO, f"Progress: {processed_count}/{len(market_data)} stocks analyzed...")
                
                try:
                    result = future.result()
                    if result and result.get('predicted_atr', 0) >= 1.5:
                        predictions.append(result)
                        self.log(logging.INFO, 
                                f"{ticker}: Predicted ATR {result['predicted_atr']:.2f}% "
                                f"(confidence: {result['confidence']:.2f})")
                except Exception as e:
                    self.log(logging.ERROR, f"ATR prediction failed for {ticker}: {e}")
        
        # Sort by confidence * predicted_atr (highest potential first)
        predictions.sort(key=lambda x: x['confidence'] * x['predicted_atr'], reverse=True)
        
        # Return top 50 (or all if less than 50)
        top_predictions = predictions[:50]
        self.log(logging.INFO, f"ATR Prediction complete. Top {len(top_predictions)} stocks selected.")
        
        return top_predictions
    
    def _predict_atr(self, stock_data: dict) -> dict:
        """Predict ATR for a single stock using LLM."""
        ticker = stock_data['ticker']
        
        # Calculate yesterday's ATR (already done in filtering, but get it again)
        yesterday_atr = self._get_yesterday_atr(ticker)
        
        # Get sector info
        sector = stock_data.get('sector', 'Unknown')
        
        # Prepare news summary
        news = stock_data.get('news', [])
        if not news:
            return None
        
        news_summary = "\n".join([
            f"- {item.get('title', 'No title')} ({item.get('published_utc', 'Unknown time')})"
            for item in news[:5]  # Top 5 news items
        ])
        
        # Get VIX (market volatility indicator)
        vix = self._get_vix()
        
        # Create LLM prompt
        prompt = f"""You are a volatility prediction expert for day trading.

Analyze this stock and predict if it will have sufficient intraday volatility TODAY.

Ticker: {ticker}
Yesterday's ATR: {yesterday_atr:.2f}%
Sector: {sector}
Current Market VIX: {vix:.2f}

News Today (morning):
{news_summary}

Question: Will this stock have an ATR > 1.5% TODAY (9:30 AM - 4:00 PM ET)?

Consider:
1. Catalyst Strength: Is this major news (FDA approval, earnings beat, acquisition)?
2. News Timing: Is it breaking NOW (high impact) or old news (already priced in)?
3. Sector Volatility: Does {sector} typically move on this type of news?
4. Market Attention: Will traders notice this? High volume potential?
5. Historical Pattern: Yesterday's ATR was {yesterday_atr:.2f}% - will today exceed this?

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "predicted_atr": <float 0-10>,
  "confidence": <float 0-1>,
  "volatility_level": "<Low/Medium/High>",
  "reasoning": "<2-3 sentences why>"
}}"""
        
        try:
            # Try DeepSeek first (cheaper)
            llm = ChatDeepSeek(model="deepseek-reasoner", api_key=DEEPSEEK_API_KEY, temperature=0)
            response = llm.invoke(prompt)
            
            # Parse response
            content = response.content.strip()
            
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            
            # Add ticker to result
            result['ticker'] = ticker
            result['yesterday_atr'] = yesterday_atr
            result['sector'] = sector
            
            return result
            
        except Exception as e:
            self.log(logging.WARNING, f"ATR prediction failed for {ticker}: {e}")
            return None
    
    def _get_yesterday_atr(self, ticker: str) -> float:
        """Calculate yesterday's ATR for a stock."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo", interval="1d")
            
            if hist.empty or len(hist) < 14:
                return 0.0
            
            # Calculate ATR
            high_low = hist['High'] - hist['Low']
            high_close = abs(hist['High'] - hist['Close'].shift())
            low_close = abs(hist['Low'] - hist['Close'].shift())
            
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]
            
            current_price = hist['Close'].iloc[-1]
            atr_pct = (atr / current_price) * 100
            
            return round(atr_pct, 2)
            
        except Exception as e:
            self.log(logging.DEBUG, f"Error calculating ATR for {ticker}: {e}")
            return 0.0
    
    def _get_vix(self) -> float:
        """Get current VIX (volatility index) level."""
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            if not hist.empty:
                return round(hist['Close'].iloc[-1], 2)
        except:
            pass
        return 18.0  # Default assumption


class TickerValidatorAgent(BaseDayTraderAgent):
    """
    Validates tickers with IBKR to ensure they can actually be traded.
    Checks: contract exists, bid/ask data available, spread acceptable, volume sufficient.
    Integrates with knowledge graph to skip known failures.
    """
    def __init__(self, orchestrator):
        super().__init__(orchestrator, "TickerValidatorAgent")
        self.ib = None
        self.log(logging.INFO, "Ticker Validator Agent initialized.")
    
    def run(self, watchlist: list) -> list:
        """
        Validate tickers with IBKR and return only tradeable ones.
        
        Args:
            watchlist: List of top-ranked stocks from WatchlistAnalystAgent
            
        Returns:
            List of validated tickers (dicts with ticker + validation info)
        """
        self.log(logging.INFO, f"--- [PHASE 1.5] Validating {len(watchlist)} tickers with IBKR ---")
        
        # Connect to IBKR
        try:
            self.ib = IB()
            # Python 3.12 fix: Ensure event loop exists
            import asyncio
            import ib_insync.util as ib_util
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            
            ib_util.run(self.ib.connectAsync('127.0.0.1', 4001, clientId=2))
            self.log(logging.INFO, "Connected to IBKR successfully.")
        except Exception as e:
            self.log(logging.CRITICAL, f"Failed to connect to IBKR: {e}")
            return []
        
        validated = []
        
        for item in watchlist:
            ticker = item.get('ticker', item) if isinstance(item, dict) else item
            
            # Check memory: Has this ticker failed recently?
            if self._has_failed_recently(ticker):
                self.log(logging.WARNING, f"SKIP {ticker}: Previously failed validation")
                continue
            
            # Validate with IBKR
            validation = self._validate_ticker(ticker)
            
            if validation['valid']:
                validated.append({
                    'ticker': ticker,
                    'spread': validation['spread'],
                    'volume': validation['volume'],
                    'original_data': item
                })
                self.log(logging.INFO, 
                        f"VALID {ticker}: (spread={validation['spread']:.2f}%, "
                        f"vol={validation['volume']:,})")
            else:
                self.log(logging.WARNING, f"INVALID {ticker}: {validation['reason']}")
                # Store failure in memory
                self._record_failure(ticker, validation['reason'])
        
        # Disconnect from IBKR
        self.ib.disconnect()
        self.log(logging.INFO, f"Validation complete. {len(validated)}/{len(watchlist)} tickers are tradeable.")
        
        return validated
    
    def _validate_ticker(self, ticker: str) -> dict:
        """Validate a single ticker with IBKR using historical data (more reliable than reqMktData)."""
        try:
            # Create contract
            contract = Stock(ticker, 'SMART', 'USD')
            
            # Qualify contract first
            qualified_contracts = self.ib.qualifyContracts(contract)
            if not qualified_contracts:
                return {"valid": False, "reason": "Contract not found"}
            
            contract = qualified_contracts[0]
            
            # Use historical data instead of live market data (more reliable for validation)
            # Request last 2 days of 1-minute bars to check if data is available
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='2 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            
            if not bars or len(bars) < 10:
                return {"valid": False, "reason": "Insufficient historical data"}
            
            # Get recent bar for price check
            recent_bar = bars[-1]
            if not recent_bar.close or recent_bar.close <= 0:
                return {"valid": False, "reason": "Invalid price data"}
            
            # Calculate average volume from recent bars
            avg_volume = sum(bar.volume for bar in bars[-20:]) / min(20, len(bars))
            
            if avg_volume < 1000:
                return {"valid": False, "reason": f"Volume {int(avg_volume)} too low"}
            
            # Calculate spread from high-low range (approximate)
            spread_pct = ((recent_bar.high - recent_bar.low) / recent_bar.close) * 100
            
            return {
                "valid": True,
                "spread": round(spread_pct, 3),
                "volume": int(avg_volume)
            }
            
        except Exception as e:
            return {"valid": False, "reason": f"Error: {str(e)[:50]}"}
    
    def _has_failed_recently(self, ticker: str) -> bool:
        """Check if ticker has failed validation recently (via knowledge graph)."""
        # TODO: Integrate with knowledge graph to check for recent failures
        # For now, don't skip any tickers (first run establishes baseline)
        return False
    
    def _record_failure(self, ticker: str, reason: str):
        """Record validation failure in knowledge graph."""
        # TODO: Integrate with knowledge graph to store failures
        # For now, just log the failure
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        self.log(logging.DEBUG, f"Would record in memory: {ticker} failed validation on {today}: {reason}")


class PreMarketMomentumAgent(BaseDayTraderAgent):
    """
    Analyzes pre-market movement (8:00-9:25 AM) for validated tickers.
    Ranks stocks by momentum to prioritize which to trade first at 9:30 AM.
    """
    def __init__(self, orchestrator):
        super().__init__(orchestrator, "PreMarketMomentumAgent")
        self.ib = None
        self.log(logging.INFO, "Pre-Market Momentum Agent initialized.")
    
    def run(self, validated_tickers: list) -> list:
        """
        Analyze pre-market momentum and rank tickers.
        
        Args:
            validated_tickers: List of validated tickers from TickerValidatorAgent
            
        Returns:
            List of tickers ranked by momentum score (highest first)
        """
        self.log(logging.INFO, f"--- [PHASE 1.75] Analyzing pre-market momentum for {len(validated_tickers)} tickers ---")
        
        # Connect to IBKR if not connected
        if not self.ib or not self.ib.isConnected():
            try:
                self.ib = IB()
                # Python 3.12 fix: Ensure event loop exists
                import asyncio
                import ib_insync.util as ib_util
                try:
                    asyncio.get_event_loop()
                except RuntimeError:
                    asyncio.set_event_loop(asyncio.new_event_loop())
                
                ib_util.run(self.ib.connectAsync('127.0.0.1', 4001, clientId=3))
                self.log(logging.INFO, "Connected to IBKR for pre-market analysis.")
            except Exception as e:
                self.log(logging.ERROR, f"Failed to connect to IBKR: {e}")
                # Return unranked list if can't connect
                return validated_tickers
        
        ranked = []
        
        for item in validated_tickers:
            ticker = item['ticker']
            
            # Get pre-market data
            momentum_data = self._analyze_premarket(ticker)
            
            if momentum_data:
                item['premarket_change'] = momentum_data['pct_change']
                item['premarket_volume_ratio'] = momentum_data['volume_ratio']
                item['momentum_score'] = momentum_data['score']
                ranked.append(item)
                
                self.log(logging.INFO,
                        f"{ticker}: Pre-market {momentum_data['pct_change']:+.2f}%, "
                        f"Vol {momentum_data['volume_ratio']:.1f}x, "
                        f"Score: {momentum_data['score']:.1f}/10")
            else:
                # No pre-market data, give neutral score
                item['momentum_score'] = 5.0
                ranked.append(item)
        
        # Sort by momentum score (highest first)
        ranked.sort(key=lambda x: x['momentum_score'], reverse=True)
        
        # Disconnect
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
        
        top_ticker = ranked[0]['ticker'] if ranked else 'None'
        self.log(logging.INFO, f"Pre-market analysis complete. Top momentum: {top_ticker}")
        
        return ranked
    
    def _analyze_premarket(self, ticker: str) -> dict:
        """Analyze pre-market movement for a single ticker."""
        try:
            # Get pre-market data using yfinance (easier than IBKR for historical)
            stock = yf.Ticker(ticker)
            
            # Get today's data with pre/post market
            hist = stock.history(period="1d", interval="1m", prepost=True)
            
            if hist.empty:
                return None
            
            # Filter to pre-market hours (4:00 AM - 9:30 AM ET)
            # yfinance uses UTC, so we need to be careful
            # For simplicity, use the data we have
            
            # Get yesterday's close
            hist_day = stock.history(period="5d", interval="1d")
            if len(hist_day) < 2:
                return None
            
            yesterday_close = hist_day['Close'].iloc[-2]
            
            # Get current pre-market price (most recent)
            current_price = hist['Close'].iloc[-1]
            
            # Calculate % change
            pct_change = ((current_price - yesterday_close) / yesterday_close) * 100
            
            # Get pre-market volume
            premarket_volume = hist['Volume'].sum()
            
            # Get average daily volume
            avg_volume = hist_day['Volume'].mean()
            
            # Calculate volume ratio
            volume_ratio = premarket_volume / (avg_volume / 6.5) if avg_volume > 0 else 1.0  # 6.5 hours in trading day
            
            # Calculate momentum score (0-10)
            # Factors: price change (50%), volume surge (30%), absolute change (20%)
            score = (
                min(abs(pct_change) / 5.0, 1.0) * 5.0 +  # Max 5 points for 5%+ move
                min(volume_ratio / 3.0, 1.0) * 3.0 +      # Max 3 points for 3x volume
                min(abs(pct_change) / 10.0, 1.0) * 2.0    # Max 2 points for magnitude
            )
            
            return {
                'pct_change': round(pct_change, 2),
                'volume_ratio': round(volume_ratio, 2),
                'score': round(score, 1)
            }
            
        except Exception as e:
            self.log(logging.DEBUG, f"Pre-market analysis failed for {ticker}: {e}")
            return None


class IntradayTraderAgent(BaseDayTraderAgent):
    """
    This is the high-speed, algorithmic agent that executes trades during
    market hours based on technical indicators. It does NOT use an LLM for
    real-time decisions.
    """
    def __init__(self, orchestrator, allocation, paper_trade=True, profit_target_pct=0.018, stop_loss_pct=0.009):
        super().__init__(orchestrator, "IntradayTraderAgent")
        self.allocation = allocation
        self.paper_trade = paper_trade
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.ib = None
        self.watchlist_data = [] # Will now store dicts: {'ticker': 'X', 'primaryExchange': 'Y'}
        self.account_summary = {}
        self.capital_per_stock = 0
        self.positions = {} # To track open positions: { 'symbol': {...} }
        self.pending_orders = {} # Track pending orders: { 'symbol': {'trade': trade_obj, 'action': 'BUY', 'timestamp': time} }
        self.failed_orders = {} # Track recently failed/cancelled orders: { 'symbol': {'timestamp': time, 'reason': str} }
        
        # Daily profit target tracking
        self.starting_capital = 0  # Set when trading starts (entire account NetLiquidation)
        self.daily_profit_target = 0.026  # 2.6% whole account target (includes old positions)
        self.daily_target_reached = False
        self.sold_stocks = {}  # Track stocks sold at stop loss: {'symbol': {'sold_at': timestamp, 'can_reenter': True}}
        self.recovery_trades = set()  # Stocks bought after stop loss (accept lower profit target)
        
        # MOO (Market-On-Open) state tracking
        self.moo_placed = False  # Flag: MOO orders placed for today
        self.moo_monitored = False  # Flag: MOO fills monitored at 9:30 AM
        self.moo_trades = []  # List of MOO trade objects
        self.moo_stocks = []  # List of stocks with MOO orders
        
        # Autonomous system components
        self.db = get_database()
        self.tracer = get_tracer()
        self.performance_analyzer = PerformanceAnalyzer(self.agent_name)
        self.health_monitor = SelfHealingMonitor(self.agent_name)
        self.improvement_engine = ContinuousImprovementEngine(self.agent_name)
        
        # Performance optimization settings
        self.max_workers = max(4, multiprocessing.cpu_count() - 2)  # Leave 2 cores for OS
        self.last_health_check = time.time()
        self.health_check_interval = 60  # seconds (1 min for tighter monitoring)
        
        self.log(logging.INFO, f"Intraday Trader Agent initialized with {self.allocation*100}% capital allocation. Paper trading: {self.paper_trade}")
        self.log(logging.INFO, "Autonomous systems enabled: Observability, Self-Evaluation, Continuous Improvement")

    def _connect_to_brokerage(self):
        """Connects to Interactive Brokers."""
        self.log(logging.INFO, "Connecting to Interactive Brokers...")
        self.ib = IB()
        try:
            # Adjust host and port if not using default TWS/Gateway settings
            # IB Gateway default is 4001 for both live and paper.
            # TWS default is 7496 for live and 7497 for paper.
            port = 4001 if self.paper_trade else 4001
            client_id = 2  # Use same ID as pre-market phase to avoid conflicts
            self.log(logging.INFO, f"Attempting connection to 127.0.0.1:{port} with clientId={client_id}...")
            
            # Python 3.12 fix: Ensure event loop exists before connecting
            import asyncio
            import ib_insync.util as ib_util
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                # Create new event loop if none exists
                asyncio.set_event_loop(asyncio.new_event_loop())
            
            ib_util.run(self.ib.connectAsync('127.0.0.1', port, clientId=client_id))
            
            # Verify connection
            if not self.ib.isConnected():
                raise ConnectionError("Connection established but not confirmed")
            
            self.log(logging.INFO, f"Successfully connected to Interactive Brokers. Account: {self.ib.managedAccounts()}")
        except Exception as e:
            self.log(logging.ERROR, f"Failed to connect to Interactive Brokers: {e}")
            import traceback
            self.log(logging.ERROR, f"Traceback: {traceback.format_exc()}")
            raise ConnectionError("Could not connect to IBKR. Is TWS or Gateway running?")

    def _load_watchlist(self):
        """Loads the watchlist from the JSON file with intraday momentum data."""
        self.log(logging.INFO, "Loading day trading watchlist...")
        try:
            # Try loading from day_trading_watchlist.json (intraday scanner)
            watchlist_path = "day_trading_watchlist.json"
            if os.path.exists(watchlist_path):
                with open(watchlist_path, 'r', encoding='utf-8-sig') as f:
                    self.watchlist_data = json.load(f)
                self.log(logging.INFO, f"Loaded {len(self.watchlist_data)} stocks from intraday scanner (day_trading_watchlist.json)")
            else:
                # Fallback to ranked_tickers.json (pre-market analysis)
                with open("ranked_tickers.json", 'r', encoding='utf-8-sig') as f:
                    self.watchlist_data = json.load(f)
                self.log(logging.INFO, f"Loaded {len(self.watchlist_data)} stocks from pre-market analysis (ranked_tickers.json)")
            
            if not self.watchlist_data:
                self.log(logging.WARNING, "Watchlist is empty after loading. No trades will be executed.")
            else:
                loaded_tickers = [item.get('ticker') for item in self.watchlist_data]
                self.log(logging.INFO, f"Active watchlist: {loaded_tickers}")
                
                # Log momentum data for verification
                for item in self.watchlist_data[:5]:  # Show top 5
                    ticker = item.get('ticker')
                    confidence = item.get('confidence_score', 0)
                    reasoning = item.get('reasoning', '')
                    self.log(logging.INFO, f"  {ticker}: {confidence:.0f}% confidence - {reasoning[:100]}...")
                    
        except FileNotFoundError:
            self.log(logging.ERROR, "Neither day_trading_watchlist.json nor ranked_tickers.json found. Cannot trade.")
            self.watchlist_data = []
            self.watchlist_data = []
        except json.JSONDecodeError as e:
            self.log(logging.ERROR, f"Could not decode ranked_tickers.json: {e}. The file might be corrupt.")
            self.watchlist_data = []

    def _calculate_capital(self):
        """Calculates the capital to allocate per stock based on account value."""
        if not self.watchlist_data:
            self.log(logging.INFO, "No capital allocated as watchlist is empty.")
            return

        self.log(logging.INFO, "Calculating capital allocation...")
        try:
            # Fetch account summary
            self.ib.reqAccountSummary()
            time.sleep(2) # Give it a moment to populate
            acc_summary_list = self.ib.accountSummary()
            self.account_summary = {item.tag: item.value for item in acc_summary_list}

            # Find available cash and total account value
            # Use ExcessLiquidity - this is the ACTUAL buying power available even with PDT restrictions
            excess_liquidity = float(self.account_summary.get('ExcessLiquidity', 0))
            net_liquidation = float(self.account_summary.get('NetLiquidation', 0))
            settled_cash = float(self.account_summary.get('SettledCash', 0))

            self.log(logging.INFO, f"Account Summary: Excess Liquidity: ${excess_liquidity:.2f}, Net Liquidation: ${net_liquidation:.2f}, Settled Cash: ${settled_cash:.2f}")

            # Determine the total capital to use for day trading
            # For PDT-restricted accounts, use ExcessLiquidity which represents real buying power
            total_day_trading_capital = excess_liquidity * self.allocation

            # Safety check: ensure we have meaningful capital
            if total_day_trading_capital < 50:
                self.log(logging.WARNING, f"Excess liquidity too low (${excess_liquidity:.2f}). Cannot trade with ${total_day_trading_capital:.2f}.")
                return

            # Calculate capital per stock
            self.capital_per_stock = total_day_trading_capital / len(self.watchlist_data)
            self.log(logging.INFO, f"Total capital for day trading: ${total_day_trading_capital:.2f}. Capital per stock: ${self.capital_per_stock:.2f}")
            
            # Set starting capital for daily P&L tracking
            self.starting_capital = net_liquidation
            self.log(logging.INFO, f"Starting capital for daily P&L tracking: ${self.starting_capital:.2f}")

        except Exception as e:
            self.log(logging.ERROR, f"Error calculating capital: {e}")
            self.capital_per_stock = 0

    def _sync_positions_from_ibkr(self):
        """
        Syncs the in-memory positions dictionary with actual IBKR positions.
        This is critical for recovering state after bot restarts.
        """
        try:
            self.log(logging.INFO, "Syncing positions from IBKR account...")
            ibkr_positions = self.ib.positions()
            
            if not ibkr_positions:
                self.log(logging.INFO, "No open positions found in IBKR account.")
                return
            
            synced_count = 0
            for pos in ibkr_positions:
                symbol = pos.contract.symbol
                
                # Only sync positions for stocks in our watchlist
                watchlist_symbols = [item.get('ticker') for item in self.watchlist_data]
                if symbol in watchlist_symbols:
                    quantity = abs(pos.position)
                    entry_price = pos.avgCost
                    contract = Stock(symbol, 'SMART', 'USD')
                    
                    # CRITICAL: Qualify contract with IBKR before placing order
                    self.ib.qualifyContracts(contract)
                    
                    # Calculate profit target and stop loss
                    take_profit = entry_price * (1 + self.profit_target_pct)
                    stop_loss_price = entry_price * (1 - self.stop_loss_pct)
                    
                    # Place profit target order (LimitOrder)
                    tp_order = LimitOrder('SELL', quantity, take_profit)
                    tp_order.tif = 'DAY'  # Good for today only
                    tp_order.outsideRth = True
                    tp_order.transmit = True
                    tp_trade = self.ib.placeOrder(contract, tp_order)
                    self.ib.sleep(1.0)  # Increased wait time for order to process
                    
                    self.log(logging.INFO, f"SYNCED position: {symbol} - {quantity} shares @ ${entry_price:.4f}")
                    self.log(logging.INFO, f"   Placed profit target: SELL {quantity} @ ${take_profit:.2f} (+{self.profit_target_pct*100:.1f}%)")
                    self.log(logging.INFO, f"   Order status: {tp_trade.orderStatus.status}, Order ID: {tp_trade.order.orderId}")
                    
                    # Create position entry in our tracking dictionary
                    self.positions[symbol] = {
                        "quantity": quantity,
                        "entry_price": entry_price,
                        "contract": contract,
                        "atr_pct": None,  # Unknown from IBKR, will be recalculated
                        "take_profit_trade": tp_trade,
                        "stop_loss_price": stop_loss_price,
                        "entry_type": "SYNCED",
                        "entry_time": time.time()
                    }
                    synced_count += 1
                else:
                    self.log(logging.WARNING, f"Found position for {symbol} ({pos.position} shares @ ${pos.avgCost:.4f}) but it's NOT in today's watchlist. Will not manage this position.")
            
            if synced_count > 0:
                self.log(logging.INFO, f"Successfully synced {synced_count} positions from IBKR that match watchlist.")
            else:
                self.log(logging.INFO, "No watchlist positions found in IBKR account to sync.")
                
        except Exception as e:
            self.log(logging.ERROR, f"Error syncing positions from IBKR: {e}")
            import traceback
            self.log(logging.ERROR, f"Traceback: {traceback.format_exc()}")

    def _check_daily_profit_target(self):
        """
        Check if we've reached the daily profit target of 2.6% on the ENTIRE account.
        This includes old positions (not just today's trades).
        Returns True if target is reached, False otherwise.
        """
        try:
            # Get current account value (includes ALL positions - old and new)
            self.account_summary = {item.tag: item.value for item in self.ib.accountSummary() if item.tag in ['NetLiquidation', 'UnrealizedPnL', 'RealizedPnL']}
            current_value = float(self.account_summary.get('NetLiquidation', self.starting_capital))
            
            # Calculate daily profit for ENTIRE account
            daily_profit = current_value - self.starting_capital
            daily_profit_pct = (daily_profit / self.starting_capital) * 100 if self.starting_capital > 0 else 0
            
            self.log(logging.INFO, f"Whole Account P&L: ${daily_profit:+.2f} ({daily_profit_pct:+.2f}%) | Target: +{self.daily_profit_target*100}%")
            
            # Check if we've hit the 2.6% target on entire account
            if daily_profit_pct >= (self.daily_profit_target * 100):
                return True
            
            return False
            
        except Exception as e:
            self.log(logging.ERROR, f"Error checking daily profit target: {e}")
            return False

    def _place_moo_orders(self):
        """
        Place Market-On-Open (MOO) orders for top momentum stocks.
        Called once between 9:20-9:27 AM ET.
        Captures opening price momentum instead of entering late.
        """
        self.log(logging.INFO, "=" * 80)
        self.log(logging.INFO, "MOO PLACEMENT PHASE - Market-On-Open Orders")
        self.log(logging.INFO, "=" * 80)
        
        # FIRST: Check existing orders in IBKR and cancel duplicates
        self.log(logging.INFO, "Checking for existing orders in IBKR...")
        existing_trades = self.ib.openTrades()
        
        if existing_trades:
            self.log(logging.INFO, f"Found {len(existing_trades)} existing orders in IBKR")
            for trade in existing_trades:
                symbol = trade.contract.symbol
                action = trade.order.action
                qty = int(trade.order.totalQuantity)
                order_type = trade.order.orderType
                status = trade.orderStatus.status
                
                self.log(logging.INFO, f"  Existing: {symbol} {action} {qty} ({order_type}, {status})")
                
                # Cancel existing MOO/MKT orders to avoid duplicates
                if action == 'BUY' and order_type == 'MKT' and status in ['PreSubmitted', 'Submitted']:
                    self.log(logging.WARNING, f"Cancelling existing order for {symbol} to avoid duplicate")
                    self.ib.cancelOrder(trade.order)
                    self.ib.sleep(0.5)
        else:
            self.log(logging.INFO, "No existing orders found in IBKR")
        
        # Get top stocks from watchlist (already loaded)
        max_moo_orders = min(5, 4 - len(self.positions))  # Leave room for scanner entries
        
        if not self.watchlist_data:
            self.log(logging.WARNING, "No stocks in watchlist for MOO orders")
            return
        
        if len(self.positions) >= 4:
            self.log(logging.WARNING, "Already at max positions, skipping MOO orders")
            return
        
        # Select top stocks
        top_stocks = self.watchlist_data[:max_moo_orders]
        self.log(logging.INFO, f"Selected {len(top_stocks)} stocks for MOO orders:")
        for item in top_stocks:
            symbol = item.get('ticker')
            confidence = item.get('confidence_score', 0)
            self.log(logging.INFO, f"  • {symbol} ({confidence:.0f}% confidence)")
        
        # Place MOO orders
        for item in top_stocks:
            symbol = item.get('ticker')
            
            # Skip if already have position or pending order
            if symbol in self.positions:
                self.log(logging.INFO, f"Skipping {symbol} - already have position")
                continue
            
            try:
                # Create contract
                contract = Stock(symbol, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                
                # Try to get price using reqMktData first (might have cached data)
                self.ib.reqMarketDataType(3)  # Delayed/frozen data
                ticker = self.ib.reqMktData(contract, '', False, False)
                self.ib.sleep(2)
                
                # Check if we got valid prices
                import math
                price_sources = [ticker.last, ticker.close, ticker.bid, ticker.ask, ticker.marketPrice()]
                valid_prices = [p for p in price_sources if p and not math.isnan(p) and p > 0]
                
                # Cancel the subscription
                self.ib.cancelMktData(contract)
                
                if valid_prices:
                    # Got price data successfully!
                    estimated_price = valid_prices[0]
                    self.log(logging.INFO, f"Price for {symbol}: ${estimated_price:.2f}")
                else:
                    # No price data - try reconnecting to get fresh cached data
                    self.log(logging.WARNING, f"No price data for {symbol}, reconnecting to IBKR for fresh data...")
                    
                    # Disconnect
                    self.ib.disconnect()
                    self.ib.sleep(1)
                    
                    # Reconnect
                    import asyncio
                    import ib_insync.util as ib_util
                    try:
                        asyncio.get_event_loop()
                    except RuntimeError:
                        asyncio.set_event_loop(asyncio.new_event_loop())
                    
                    ib_util.run(self.ib.connectAsync('127.0.0.1', 4001, clientId=2))
                    self.log(logging.INFO, f"Reconnected to IBKR")
                    
                    # Try again with fresh connection
                    contract = Stock(symbol, 'SMART', 'USD')
                    self.ib.qualifyContracts(contract)
                    
                    self.ib.reqMarketDataType(3)
                    ticker = self.ib.reqMktData(contract, '', False, False)
                    self.ib.sleep(2)
                    
                    price_sources = [ticker.last, ticker.close, ticker.bid, ticker.ask, ticker.marketPrice()]
                    valid_prices = [p for p in price_sources if p and not math.isnan(p) and p > 0]
                    self.ib.cancelMktData(contract)
                    
                    if valid_prices:
                        estimated_price = valid_prices[0]
                        self.log(logging.INFO, f"Price for {symbol}: ${estimated_price:.2f} (after reconnect)")
                    else:
                        # Still no data - fall back to historical
                        self.log(logging.WARNING, f"Still no price data after reconnect, using historical data")
                        bars = self.ib.reqHistoricalData(
                            contract,
                            endDateTime='',
                            durationStr='1 D',
                            barSizeSetting='1 day',
                            whatToShow='TRADES',
                            useRTH=False
                        )
                        
                        if bars and len(bars) > 0:
                            estimated_price = bars[-1].close
                            self.log(logging.INFO, f"Price for {symbol}: ${estimated_price:.2f} (yesterday's close)")
                        else:
                            self.log(logging.WARNING, f"No historical data for {symbol}, skipping")
                            continue
                
                # Calculate shares
                shares = int(self.capital_per_stock / estimated_price)
                
                if shares < 1:
                    self.log(logging.WARNING, f"Insufficient capital for {symbol} @ ${estimated_price:.2f}, skipping")
                    continue
                
                # Create Market order (will execute at market open)
                moo_order = Order()
                moo_order.action = 'BUY'
                moo_order.totalQuantity = shares
                moo_order.orderType = 'MKT'  # Simple Market order
                moo_order.tif = 'DAY'
                moo_order.outsideRth = True
                moo_order.transmit = True
                
                # Place order
                trade = self.ib.placeOrder(contract, moo_order)
                
                self.log(logging.INFO, f"MOO order placed: {symbol} x{shares} shares @ ~${estimated_price:.2f}")
                
                # Track MOO trade
                self.moo_trades.append({
                    'symbol': symbol,
                    'trade': trade,
                    'shares': shares,
                    'estimated_price': estimated_price,
                    'contract': contract
                })
                self.moo_stocks.append(symbol)
                
            except Exception as e:
                self.log(logging.ERROR, f"Failed to place MOO order for {symbol}: {e}")
        
        self.moo_placed = True
        self.log(logging.INFO, f"MOO placement complete: {len(self.moo_trades)} orders placed")
        self.log(logging.INFO, f"MOO stocks: {self.moo_stocks}")

    def _monitor_moo_fills(self):
        """
        Monitor MOO order fills at market open (9:30 AM).
        Place profit targets immediately after fills.
        Add filled positions to tracking.
        """
        self.log(logging.INFO, "=" * 80)
        self.log(logging.INFO, "MOO FILL MONITORING - Checking Market Open Executions")
        self.log(logging.INFO, "=" * 80)
        
        if not self.moo_trades:
            self.log(logging.INFO, "No MOO trades to monitor")
            return
        
        # Wait 30 seconds for fills at market open
        self.log(logging.INFO, "Waiting for MOO fills (30 seconds)...")
        
        for i in range(30):
            self.ib.sleep(1)
            
            # Check each MOO trade
            for moo in self.moo_trades:
                # Skip if already processed
                if moo.get('processed'):
                    continue
                
                trade = moo['trade']
                symbol = moo['symbol']
                contract = moo['contract']
                status = trade.orderStatus.status
                
                if status == 'Filled':
                    # MOO filled!
                    fill_price = trade.orderStatus.avgFillPrice
                    filled_qty = trade.orderStatus.filled
                    
                    self.log(logging.INFO, f"MOO FILLED: {symbol} - {filled_qty} shares @ ${fill_price:.2f}")
                    
                    # Calculate profit target and stop loss
                    take_profit = fill_price * (1 + self.profit_target_pct)
                    stop_loss = fill_price * (1 - self.stop_loss_pct)
                    
                    # Place profit target (LimitOrder)
                    tp_order = LimitOrder('SELL', filled_qty, take_profit)
                    tp_trade = self.ib.placeOrder(contract, tp_order)
                    
                    self.log(logging.INFO, f"   Profit target: ${take_profit:.2f} (+{self.profit_target_pct*100:.1f}%)")
                    self.log(logging.INFO, f"   Stop loss: ${stop_loss:.2f} (-{self.stop_loss_pct*100:.1f}%)")
                    
                    # Add to positions (SAME dict as scanner entries)
                    self.positions[symbol] = {
                        "quantity": filled_qty,
                        "entry_price": fill_price,
                        "contract": contract,
                        "atr_pct": None,  # No ATR for MOO entries
                        "take_profit_trade": tp_trade,
                        "stop_loss_price": stop_loss,
                        "entry_type": "MOO",  # Tag as MOO entry
                        "entry_time": time.time()
                    }
                    
                    moo['processed'] = True
                    
                elif status in ['Cancelled', 'ApiCancelled', 'Inactive']:
                    self.log(logging.WARNING, f"MOO FAILED: {symbol} - {status}")
                    moo['processed'] = True
        
        # Summary
        filled_count = sum(1 for m in self.moo_trades if m.get('processed') and 
                          m['trade'].orderStatus.status == 'Filled')
        
        self.log(logging.INFO, f"MOO fill monitoring complete: {filled_count}/{len(self.moo_trades)} filled")
        self.moo_monitored = True

    def _run_trading_loop(self):
        """
        The core loop that fetches market data, applies indicators,
        and makes trade decisions with robust error handling.
        Uses delayed/snapshot data (free) instead of real-time streaming.
        """
        if not self.watchlist_data or self.capital_per_stock <= 0:
            self.log(logging.INFO, "Trading loop skipped due to empty watchlist or zero capital.")
            return

        self.log(logging.INFO, f"Starting the main trading loop for {len(self.watchlist_data)} stocks.")

        # --- 1. Create Contracts with SMART Routing (let IBKR find the exchange) ---
        contracts_for_data = []
        for item in self.watchlist_data:
            ticker = item.get('ticker')
            if ticker:
                # Use SMART routing - IBKR will automatically find the correct exchange
                contracts_for_data.append(Stock(ticker, 'SMART', 'USD'))
            else:
                self.log(logging.WARNING, f"Skipping invalid item in watchlist: {item}")
        
        if not contracts_for_data:
            self.log(logging.WARNING, "No valid contracts to trade after parsing watchlist. Ending loop.")
            return

        # --- 2. Request Delayed/Snapshot Market Data (Free, No Subscription Required) ---
        # Using snapshot=True means we get a single data snapshot, not streaming
        # Using delayed data (reqMarketDataType=3) which is free
        self.ib.reqMarketDataType(3)  # 3 = delayed data (free)
        
        # Contracts will be automatically qualified by IBKR when we request data
        self.log(logging.INFO, f"Preparing to fetch data for {len(contracts_for_data)} stocks...")
        self.log(logging.INFO, f"Contracts: {[c.symbol for c in contracts_for_data]}")
        
        try:
            # Run until market close (no time limit)
            loop_start_time = time.time()
            last_scanner_run = 0  # Track when we last ran the intraday scanner
            scanner_interval = 900  # Run scanner every 15 minutes (900 seconds)
            
            self.log(logging.INFO, f"Entering trading loop - will run until market close...")
            self.log(logging.INFO, f"Loop start time: {loop_start_time}, Market open: {is_market_open()}")
            self.log(logging.INFO, f"Scanner will refresh watchlist every {scanner_interval/60:.0f} minutes")
            
            while is_market_open():
                self.log(logging.INFO, "Trading loop iteration starting...")
                
                # --- 15-MINUTE SCANNER REFRESH ---
                # Run intraday scanner every 15 minutes to find fresh momentum stocks
                time_since_last_scan = time.time() - last_scanner_run
                if time_since_last_scan >= scanner_interval:
                    self.log(logging.INFO, f"Running 15-min intraday scanner (last scan {time_since_last_scan/60:.1f} min ago)...")
                    try:
                        import subprocess
                        import sys
                        
                        # Run the Polygon intraday scanner
                        result = subprocess.run(
                            [sys.executable, 'intraday_scanner_polygon.py'],
                            capture_output=True,
                            text=True,
                            timeout=120  # 2-minute timeout
                        )
                        
                        if result.returncode == 0:
                            self.log(logging.INFO, "Intraday scanner completed successfully. Reloading watchlist...")
                            
                            # Reload the updated watchlist
                            old_tickers = [item.get('ticker') for item in self.watchlist_data]
                            self._load_watchlist()
                            new_tickers = [item.get('ticker') for item in self.watchlist_data]
                            
                            # Log changes
                            added = set(new_tickers) - set(old_tickers)
                            removed = set(old_tickers) - set(new_tickers)
                            
                            if added:
                                self.log(logging.INFO, f"NEW momentum stocks added: {list(added)}")
                            if removed:
                                self.log(logging.INFO, f"Stocks removed from watchlist: {list(removed)}")
                            if not added and not removed:
                                self.log(logging.INFO, "Watchlist unchanged - same hot stocks still active")
                            
                            # Update contracts list for new watchlist
                            contracts_for_data = []
                            for item in self.watchlist_data:
                                ticker = item.get('ticker')
                                if ticker:
                                    contracts_for_data.append(Stock(ticker, 'SMART', 'USD'))
                            
                            self.log(logging.INFO, f"Trading {len(contracts_for_data)} stocks after refresh")
                            last_scanner_run = time.time()
                        else:
                            self.log(logging.WARNING, f"Scanner failed with exit code {result.returncode}: {result.stderr[:200]}")
                    except subprocess.TimeoutExpired:
                        self.log(logging.WARNING, "Scanner timed out after 2 minutes. Will retry next interval.")
                    except Exception as e:
                        self.log(logging.ERROR, f"Error running scanner: {e}. Continuing with current watchlist.")
                
                # Check if we've hit daily profit target
                if self._check_daily_profit_target():
                    self.log(logging.INFO, "DAILY PROFIT TARGET REACHED! Liquidating all positions and stopping trading.")
                    self._liquidate_positions()
                    self.daily_target_reached = True
                    break
                
                # Check pending orders first
                pending_to_remove = []
                for symbol, pending_info in list(self.pending_orders.items()):
                    trade = pending_info['trade']
                    age = time.time() - pending_info['timestamp']
                    
                    # Update order status
                    self.ib.sleep(0.1)
                    
                    if trade.orderStatus.status == 'Filled':
                        fill_price = trade.orderStatus.avgFillPrice
                        filled_quantity = trade.orderStatus.filled
                        
                        if pending_info['action'] == 'BUY':
                            self.positions[symbol] = {
                                "quantity": filled_quantity,
                                "entry_price": fill_price,
                                "contract": pending_info['contract'],
                                "atr_pct": pending_info.get('atr_pct')
                            }
                            self.log(logging.INFO, f"PENDING BUY FILLED: {filled_quantity} shares of {symbol} at ${fill_price:.2f}")
                            
                            # Log to database
                            capital = float(self.account_summary.get('NetLiquidation', 0))
                            self.db.log_trade({
                                'symbol': symbol,
                                'action': 'BUY',
                                'quantity': filled_quantity,
                                'price': fill_price,
                                'agent_name': self.agent_name,
                                'reason': f'Entry signal filled after {age:.1f}s',
                                'capital_at_trade': capital,
                                'position_size_pct': (filled_quantity * fill_price / capital * 100) if capital > 0 else 0,
                                'metadata': {
                                    'vwap': 0,
                                    'rsi': 0,
                                    'atr_pct': pending_info.get('atr_pct', 0),
                                    'current_price': fill_price
                                }
                            })
                        
                        pending_to_remove.append(symbol)
                    
                    elif trade.orderStatus.status in ['Cancelled', 'Inactive']:
                        self.log(logging.WARNING, f"Order for {symbol} was {trade.orderStatus.status}. Marking as failed to prevent immediate retry.")
                        # Track failed order with timestamp to prevent immediate retry
                        self.failed_orders[symbol] = {
                            'timestamp': time.time(),
                            'reason': trade.orderStatus.status,
                            'price_at_fail': pending_info.get('current_price', 0)
                        }
                        pending_to_remove.append(symbol)
                    
                    elif age > 30:  # Cancel if pending for more than 30 seconds
                        self.log(logging.WARNING, f"Order for {symbol} pending for {age:.0f}s. Cancelling.")
                        self.ib.cancelOrder(trade.order)
                        pending_to_remove.append(symbol)
                
                # Clean up filled/cancelled orders
                for symbol in pending_to_remove:
                    del self.pending_orders[symbol]
                
                if self.pending_orders:
                    self.log(logging.INFO, f"Pending orders: {list(self.pending_orders.keys())}")
                
                self.log(logging.INFO, f"Processing {len(contracts_for_data)} contracts...")
                
                # AUTONOMOUS: Periodic health check
                if time.time() - self.last_health_check > self.health_check_interval:
                    health_status = self.health_monitor.check_health(self)
                    if health_status['status'] == 'critical':
                        self.log(logging.ERROR, f"Critical health issues detected: {health_status['issues']}")
                        # Attempt self-healing
                        for issue in health_status['issues']:
                            if 'IBKR connection lost' in issue:
                                self.health_monitor.attempt_healing(self, 'ibkr_disconnected')
                    self.last_health_check = time.time()
                
                for contract in contracts_for_data: # Use the exchange-specific contract for data
                    try:
                        self.log(logging.INFO, f"Fetching historical data for {contract.symbol}...")
                        
                        # Get historical data to calculate indicators - try IBKR first, fallback to Polygon
                        # Request historical data with real-time subscription
                        df = None
                        try:
                            try:
                                bars = self.ib.reqHistoricalData(
                                    contract,
                                    endDateTime='',
                                    durationStr='10800 S',  # Last 10800 seconds (3 hours / ~360 bars) for better VWAP/RSI/ATR with real-time data
                                    barSizeSetting='30 secs',
                                    whatToShow='TRADES',
                                    useRTH=True,
                                    formatDate=1
                                )
                            except KeyboardInterrupt:
                                self.log(logging.INFO, f"Bot interrupted by user. Exiting gracefully...")
                                return
                            except Exception as e:
                                self.log(logging.ERROR, f"Error fetching IBKR data for {contract.symbol}: {e}")
                                bars = None
                                
                            if bars and len(bars) > 0:
                                df = util.df(bars)
                                # IBKR util.df() may not set DatetimeIndex properly, so fix it
                                if 'date' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
                                    df.set_index('date', inplace=True)
                                self.log(logging.INFO, f"IBKR data for {contract.symbol}: {len(bars)} bars, index={type(df.index).__name__}")
                        except Exception as e:
                            self.log(logging.INFO, f"IBKR error for {contract.symbol}: {e}")

                        # Fallback to Polygon API if IBKR data is not available
                        if df is None or df.empty:
                            self.log(logging.INFO, f"Using Polygon API fallback for {contract.symbol} historical data")
                            try:
                                from datetime import datetime, timedelta
                                import requests
                                
                                # Get today's date for intraday data
                                today = datetime.now().strftime('%Y-%m-%d')
                                
                                # Polygon aggregates/bars endpoint for 1-minute data
                                polygon_url = (
                                    f"https://api.polygon.io/v2/aggs/ticker/{contract.symbol}/range/1/minute/"
                                    f"{today}/{today}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_API_KEY}"
                                )
                                
                                response = requests.get(polygon_url)
                                response.raise_for_status()
                                data = response.json()
                                
                                if data.get('resultsCount', 0) > 0 and 'results' in data:
                                    results = data['results']
                                    # Convert Polygon data to DataFrame
                                    df = pd.DataFrame(results)
                                    # Rename columns to match IBKR format: v=volume, o=open, c=close, h=high, l=low, t=timestamp
                                    df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume', 't': 'timestamp'})
                                    # Convert timestamp from milliseconds to datetime and set as index
                                    df.index = pd.to_datetime(df['timestamp'], unit='ms')
                                    df.index.name = 'date'
                                    # Keep only OHLCV columns
                                    df = df[['open', 'high', 'low', 'close', 'volume']]
                                    # Ensure numeric types
                                    df = df.astype(float)
                                    self.log(logging.INFO, f"Polygon data for {contract.symbol}: {len(df)} bars, index type={type(df.index).__name__}, first index={df.index[0] if len(df) > 0 else 'empty'}")
                                else:
                                    self.log(logging.WARNING, f"Polygon returned no data for {contract.symbol}")
                            except Exception as e:
                                self.log(logging.WARNING, f"Polygon API fallback failed for {contract.symbol}: {e}")
                        
                        if df is None or df.empty:
                            self.log(logging.WARNING, f"No historical data available for {contract.symbol} from IBKR or Polygon. Skipping.")
                            continue
                        
                        if not isinstance(df.index, pd.DatetimeIndex):
                            self.log(logging.WARNING, f"Historical data for {contract.symbol} has invalid index type: {type(df.index)}")
                            continue

                        # --- Technical Analysis with pandas-ta ---
                        df.ta.vwap(append=True)
                        df.ta.rsi(append=True)
                        df.ta.atr(length=14, append=True)  # Add ATR for volatility measurement

                        # Get the latest values
                        latest_data = df.iloc[-1]
                        vwap_col = next((col for col in df.columns if 'VWAP' in col), None)
                        atr_col = next((col for col in df.columns if 'ATR' in col), None)
                        
                        if not vwap_col or pd.isna(latest_data[vwap_col]):
                            self.log(logging.WARNING, f"VWAP could not be calculated for {contract.symbol}. Check historical data.")
                            continue
                            
                        vwap = latest_data[vwap_col]
                        
                        # Check if RSI_14 exists in the dataframe
                        if 'RSI_14' not in df.columns:
                            self.log(logging.WARNING, f"RSI_14 not calculated for {contract.symbol} (need at least 14 bars). Skipping.")
                            continue
                            
                        rsi = latest_data['RSI_14']
                        atr = latest_data[atr_col] if atr_col and not pd.isna(latest_data[atr_col]) else None
                        current_price = latest_data['close']  # Get current price from latest bar

                        if pd.isna(rsi) or pd.isna(current_price):
                            self.log(logging.DEBUG, f"Indicator or price is NaN for {contract.symbol}. Skipping.")
                            continue
                        
                        # Calculate ATR percentage (ATR as % of current price) for volatility assessment
                        atr_pct = (atr / current_price * 100) if atr and current_price > 0 else None
                        
                        # Log indicator values to see why we're not trading
                        if atr_pct:
                            self.log(logging.INFO, f"{contract.symbol} - Price: ${current_price:.2f}, VWAP: ${vwap:.2f}, RSI: {rsi:.2f}, ATR: {atr_pct:.2f}%")
                        else:
                            self.log(logging.INFO, f"{contract.symbol} - Price: ${current_price:.2f}, VWAP: ${vwap:.2f}, RSI: {rsi:.2f}, ATR: N/A")

                        # --- Trade Decision Logic ---
                        position = self.positions.get(contract.symbol)

                        # Entry Logic: No position is open AND no pending order AND not recently failed
                        if position is None and contract.symbol not in self.pending_orders:
                            # Check if order recently failed/cancelled (wait before retry)
                            if contract.symbol in self.failed_orders:
                                failed_info = self.failed_orders[contract.symbol]
                                failed_time = failed_info['timestamp']
                                failed_reason = failed_info.get('reason', 'unknown')
                                time_since_fail = time.time() - failed_time
                                
                                # Different cooldowns based on failure reason
                                if failed_reason == 'stop_loss':
                                    cooldown_seconds = 300  # 5 minutes for stop loss
                                else:
                                    cooldown_seconds = 60  # 60 seconds for cancelled orders
                                
                                if time_since_fail < cooldown_seconds:
                                    continue  # Still in cooldown, skip this stock
                                else:
                                    # Enough time has passed, allow retry and remove from failed list
                                    self.log(logging.INFO, f"Retry allowed for {contract.symbol} after {time_since_fail:.0f}s cooldown")
                                    del self.failed_orders[contract.symbol]
                            
                            # DATABASE COORDINATION: Check if position already exists or was closed today
                            # This prevents conflicts with Exit Manager and duplicate entries
                            if self.db.is_position_active(contract.symbol):
                                self.log(logging.INFO, f"⏭️  Skipping {contract.symbol} - position already active (database check)")
                                continue
                            
                            if self.db.was_closed_today(contract.symbol):
                                self.log(logging.INFO, f"⏭️  Skipping {contract.symbol} - already traded today (re-entry protection)")
                                continue
                            
                            # Check if this stock was previously sold (don't re-enter unless it's a recovery trade)
                            if contract.symbol in self.sold_stocks and not self.sold_stocks[contract.symbol].get('can_reenter', False):
                                # Stock was sold for profit - don't re-enter
                                continue
                            
                            # Calculate pre-market gap from watchlist data
                            ticker_info = next((t for t in self.watchlist_data if t.get('ticker') == contract.symbol), None)
                            pre_market_gap = 0
                            if ticker_info and 'premarket_change' in ticker_info:
                                pre_market_gap = abs(ticker_info.get('premarket_change', 0))
                            
                            # Enhanced entry with TWO paths:
                            # Path 1: Gap-and-Go (5%+ pre-market gap - VWAP not required for momentum plays)
                            # Path 2: Standard Entry (Price > VWAP + ATR check)
                            gap_entry = pre_market_gap >= 5.0  # 5%+ gap qualifies for momentum entry
                            standard_entry = current_price > vwap and (atr_pct is None or atr_pct >= 0.3)  # 0.3% for 30-sec bars
                            
                            # Gap plays bypass VWAP requirement (momentum continuation), standard plays require VWAP
                            if rsi < 60 and (gap_entry or standard_entry):
                                quantity = int(self.capital_per_stock / current_price)
                                if quantity > 0:
                                    # Determine entry reason for logging
                                    if gap_entry:
                                        entry_reason = f"Gap-and-Go {pre_market_gap:.1f}% (momentum play)"
                                    else:
                                        entry_reason = f"Price>${vwap:.2f} VWAP, ATR {atr_pct:.2f}%"
                                    self.log(logging.INFO, f"ENTRY SIGNAL for {contract.symbol}: RSI {rsi:.2f} < 60, {entry_reason}. Buying {quantity} shares.")
                                    
                                    # *** BUY FIRST, then place take profit + stop loss AFTER confirmation ***
                                    trade_contract = Stock(contract.symbol, 'SMART', 'USD')
                                    
                                    # Calculate profit target (+2.6%) and stop loss (-0.9%)
                                    take_profit_price = current_price * 1.026  # +2.6%
                                    stop_loss_price = current_price * 0.991    # -0.9%
                                    
                                    self.log(logging.INFO, f"Placing BUY order for {contract.symbol}: {quantity} shares @ market (TP=${take_profit_price:.2f}, SL=${stop_loss_price:.2f})")
                                    
                                    # AUTONOMOUS: Trace trade execution
                                    with self.tracer.trace_trade_execution(contract.symbol, 'BUY'):
                                        # Step 1: Place MARKET BUY order first
                                        buy_order = MarketOrder('BUY', quantity)
                                        parent_trade = self.ib.placeOrder(trade_contract, buy_order)
                                        
                                        # Track pending order immediately
                                        self.pending_orders[contract.symbol] = {
                                            'trade': parent_trade,
                                            'action': 'BUY',
                                            'quantity': quantity,
                                            'timestamp': time.time(),
                                            'contract': contract,
                                            'atr_pct': atr_pct,
                                            'take_profit_price': take_profit_price,
                                            'stop_loss_price': stop_loss_price
                                        }
                                        
                                        # Wait up to 3 seconds for BUY to fill
                                        for _ in range(6):
                                            time.sleep(0.5)
                                            if parent_trade.orderStatus.status == 'Filled':
                                                break
                                        
                                        if parent_trade.orderStatus.status == 'Filled':
                                            fill_price = parent_trade.orderStatus.avgFillPrice
                                            filled_quantity = parent_trade.orderStatus.filled
                                            
                                            self.log(logging.INFO, f"BUY FILLED: {filled_quantity} shares of {contract.symbol} at ${fill_price:.2f}")
                                            
                                            # Step 2: NOW place OCO bracket orders AFTER BUY confirmed
                                            # Recalculate based on ACTUAL fill price
                                            actual_take_profit = fill_price * 1.026  # +2.6% from actual fill
                                            actual_stop_loss = fill_price * 0.991    # -0.9% from actual fill
                                            
                                            # Create unique OCA (One-Cancels-All) group for this position
                                            oca_group = f"OCA_{contract.symbol}_{int(time.time())}"
                                            
                                            # Take Profit order (LIMIT SELL)
                                            take_profit_order = LimitOrder('SELL', filled_quantity, actual_take_profit)
                                            take_profit_order.ocaGroup = oca_group
                                            take_profit_order.ocaType = 1  # Cancel all when one fills
                                            take_profit_order.tif = 'DAY'
                                            take_profit_order.outsideRth = False
                                            
                                            # Stop Loss order (STOP SELL) - Now part of OCO bracket!
                                            stop_loss_order = StopOrder('SELL', filled_quantity, actual_stop_loss)
                                            stop_loss_order.ocaGroup = oca_group  # SAME group as take profit
                                            stop_loss_order.ocaType = 1  # Cancel all when one fills
                                            stop_loss_order.tif = 'DAY'
                                            stop_loss_order.outsideRth = False
                                            
                                            # Place both OCO orders
                                            tp_trade = self.ib.placeOrder(trade_contract, take_profit_order)
                                            sl_trade = self.ib.placeOrder(trade_contract, stop_loss_order)
                                            
                                            self.log(logging.INFO, f"OCO Bracket placed: TP @ ${actual_take_profit:.2f} (+2.6%), SL @ ${actual_stop_loss:.2f} (-0.9%), OCA Group: {oca_group}")
                                            
                                            # Store position with OCO bracket references
                                            self.positions[contract.symbol] = {
                                                "quantity": filled_quantity,
                                                "entry_price": fill_price,
                                                "contract": contract,
                                                "atr_pct": atr_pct,
                                                "take_profit_trade": tp_trade,  # Reference to TP order
                                                "stop_loss_trade": sl_trade,    # Reference to SL order (OCO)
                                                "stop_loss_price": actual_stop_loss,
                                                "take_profit_price": actual_take_profit,
                                                "oca_group": oca_group  # Track OCO group
                                            }
                                            
                                            # DATABASE COORDINATION: Register position in shared database
                                            # This allows Exit Manager to see and manage this position
                                            self.db.add_active_position(
                                                symbol=contract.symbol,
                                                quantity=filled_quantity,
                                                entry_price=fill_price,
                                                agent_name='day_trader',
                                                profit_target=actual_take_profit,
                                                stop_loss=actual_stop_loss
                                            )
                                            
                                            # DATABASE: Log the entry trade
                                            self.db.log_trade({
                                                'symbol': contract.symbol,
                                                'action': 'BUY',
                                                'quantity': filled_quantity,
                                                'price': fill_price,
                                                'agent_name': 'day_trader',
                                                'reason': entry_reason,
                                                'metadata': {
                                                    'rsi': rsi,
                                                    'vwap': vwap,
                                                    'atr_pct': atr_pct,
                                                    'pre_market_gap': pre_market_gap,
                                                    'take_profit': actual_take_profit,
                                                    'stop_loss': actual_stop_loss
                                                }
                                            })
                                            
                                            self.log(logging.INFO, f"✅ Position registered in database: {contract.symbol} @ ${fill_price:.2f}")
                                            
                                            # Mark as recovery trade if re-entering after stop loss
                                            if contract.symbol in self.sold_stocks and self.sold_stocks[contract.symbol].get('can_reenter'):
                                                self.recovery_trades.add(contract.symbol)
                                                self.log(logging.INFO, f"RECOVERY TRADE for {contract.symbol} - bracket orders active")
                                            
                                            # Remove from pending
                                            del self.pending_orders[contract.symbol]
                                            
                                            # AUTONOMOUS: Log trade to database
                                            capital = float(self.account_summary.get('NetLiquidation', 0))
                                            self.db.log_trade({
                                                'symbol': contract.symbol,
                                                'action': 'BUY',
                                                'quantity': filled_quantity,
                                                'price': fill_price,
                                                'agent_name': self.agent_name,
                                                'reason': f'Entry signal: Price>${vwap:.2f} VWAP, RSI={rsi:.2f}<60, ATR={atr_pct:.2f}%',
                                                'capital_at_trade': capital,
                                                'position_size_pct': (filled_quantity * fill_price / capital * 100) if capital > 0 else 0,
                                                'metadata': {
                                                    'vwap': vwap,
                                                    'rsi': rsi,
                                                    'atr_pct': atr_pct,
                                                    'current_price': current_price
                                                }
                                            })
                                        else:
                                            self.log(logging.WARNING, f"Buy order for {contract.symbol} not filled after 3 seconds. Status: {parent_trade.orderStatus.status}. Will check next iteration.")
                            else:
                                # Log why we're NOT buying
                                reasons = []
                                if not (rsi < 60):
                                    reasons.append(f"RSI {rsi:.2f} >= 60 (overbought)")
                                if not gap_entry:
                                    if not (current_price > vwap):
                                        reasons.append(f"Price ${current_price:.2f} <= VWAP ${vwap:.2f}")
                                    if not (atr_pct is None or atr_pct >= 0.3):
                                        reasons.append(f"ATR {atr_pct:.2f}% < 0.3% (low volatility)")
                                else:
                                    # Gap play failed - should rarely happen (only RSI issue)
                                    reasons.append(f"Gap {pre_market_gap:.1f}% but failed other checks")
                                if reasons:
                                    self.log(logging.INFO, f"NO ENTRY for {contract.symbol}: {', '.join(reasons)}")
                        
                        # Exit Logic: A position is open - CHECK IF BRACKET ORDERS EXECUTED
                        else:
                            # With bracket orders, IBKR handles profit/stop automatically
                            # We just need to check if position was closed by bracket orders
                            entry_price = position['entry_price']
                            
                            # Get bracket order trades (placed AFTER BUY confirmation)
                            tp_trade = position.get('take_profit_trade', None)
                            sl_trade = position.get('stop_loss_trade', None)
                            
                            if tp_trade and sl_trade:
                                # Check if take profit order filled
                                position_closed = False
                                exit_reason = None
                                fill_price = None
                                
                                if tp_trade.orderStatus.status == 'Filled':
                                    position_closed = True
                                    exit_reason = 'profit_target'
                                    fill_price = tp_trade.orderStatus.avgFillPrice
                                    self.log(logging.INFO, f"TAKE PROFIT filled for {contract.symbol} at ${fill_price:.2f}")
                                
                                else:
                                    # Manual stop-loss monitoring (IBKR doesn't allow Stop SELL orders)
                                    try:
                                        # Get current market price
                                        ticker = self.ib.reqMktData(contract, '', False, False)
                                        self.ib.sleep(0.5)  # Wait for price update
                                        
                                        current_price = None
                                        if ticker.last and not math.isnan(ticker.last):
                                            current_price = ticker.last
                                        elif ticker.bid and not math.isnan(ticker.bid):
                                            current_price = ticker.bid
                                        
                                        stop_loss_price = position.get('stop_loss_price')
                                        
                                        if current_price and stop_loss_price and current_price <= stop_loss_price:
                                            # Stop loss triggered - place immediate market sell
                                            self.log(logging.WARNING, f"🛑 STOP LOSS triggered for {contract.symbol}: ${current_price:.2f} <= ${stop_loss_price:.2f}")
                                            
                                            filled_quantity = position['quantity']
                                            stop_loss_order = MarketOrder('SELL', filled_quantity)
                                            stop_loss_order.tif = 'IOC'  # Immediate-Or-Cancel
                                            stop_loss_order.outsideRth = True  # Allow after-hours
                                            sl_trade = self.ib.placeOrder(contract, stop_loss_order)
                                            
                                            # Wait for stop loss fill
                                            for _ in range(10):
                                                self.ib.sleep(1)
                                                if sl_trade.orderStatus.status == 'Filled':
                                                    position_closed = True
                                                    exit_reason = 'stop_loss'
                                                    fill_price = sl_trade.orderStatus.avgFillPrice
                                                    self.log(logging.INFO, f"STOP LOSS filled for {contract.symbol} at ${fill_price:.2f}")
                                                    # Cancel the take profit order
                                                    self.ib.cancelOrder(tp_trade.order)
                                                    break
                                        
                                        # Cancel ticker subscription
                                        self.ib.cancelMktData(contract)
                                    
                                    except Exception as e:
                                        self.log(logging.ERROR, f"Error checking stop loss for {contract.symbol}: {e}")
                                
                                # If position was closed by bracket order, log it
                                if position_closed and fill_price:
                                    filled_quantity = position['quantity']
                                    profit_loss = (fill_price - entry_price) * filled_quantity
                                    profit_loss_pct = ((fill_price - entry_price) / entry_price) * 100
                                    
                                    # DATABASE COORDINATION: Remove from active_positions and mark as closed_today
                                    self.db.remove_active_position(
                                        symbol=contract.symbol,
                                        exit_price=fill_price,
                                        exit_reason=exit_reason.upper(),
                                        agent_name='day_trader'
                                    )
                                    
                                    # AUTONOMOUS: Log trade to database
                                    capital = float(self.account_summary.get('NetLiquidation', 0))
                                    self.db.log_trade({
                                        'symbol': contract.symbol,
                                        'action': 'SELL',
                                        'quantity': filled_quantity,
                                        'price': fill_price,
                                        'agent_name': self.agent_name,
                                        'reason': f'Bracket order: {exit_reason}',
                                        'profit_loss': profit_loss,
                                        'profit_loss_pct': profit_loss_pct,
                                        'capital_at_trade': capital,
                                        'metadata': {
                                            'entry_price': entry_price,
                                            'exit_price': fill_price,
                                            'exit_reason': exit_reason
                                        }
                                    })
                                    
                                    self.log(logging.INFO, f"SOLD {filled_quantity} shares of {contract.symbol} at ${fill_price:.2f} for ${profit_loss:+.2f} P&L ({profit_loss_pct:+.2f}%)")
                                    
                                    # Handle post-exit logic
                                    if exit_reason == 'profit_target':
                                        # Mark as sold for profit - don't re-enter this stock today
                                        self.sold_stocks[contract.symbol] = {
                                            'sold_at': time.time(),
                                            'can_reenter': False,
                                            'reason': 'profit_target'
                                        }
                                        self.recovery_trades.discard(contract.symbol)
                                    
                                    elif exit_reason == 'stop_loss':
                                        # Add to failed_orders with 5-minute cooldown
                                        self.failed_orders[contract.symbol] = {
                                            'timestamp': time.time(),
                                            'reason': 'stop_loss',
                                            'price_at_fail': fill_price
                                        }
                                        self.log(logging.INFO, f"🚫 {contract.symbol} added to cooldown (5 min) after stop loss")
                                        
                                        # Mark as sold at stop loss - CAN re-enter after cooldown
                                        self.sold_stocks[contract.symbol] = {
                                            'sold_at': time.time(),
                                            'can_reenter': True,
                                            'reason': 'stop_loss',
                                            'last_price': fill_price
                                        }
                                        self.log(logging.INFO, f"⚡ {contract.symbol} now eligible for re-entry if momentum recovers (after cooldown)")
                                    
                                    # Remove position
                                    del self.positions[contract.symbol]
                            
                            else:
                                # Fallback: Legacy positions without bracket orders (shouldn't happen with new code)
                                self.log(logging.WARNING, f"{contract.symbol} position exists but no bracket orders found. Monitoring manually.")
                                # Keep the old manual monitoring as fallback (but this shouldn't execute for new trades)

                    except Exception as e_stock:
                        self.log(logging.ERROR, f"An error occurred while processing {contract.symbol}: {e_stock}")
                        continue # Move to the next stock
                
                # Sleep between iterations
                time.sleep(5)

            self.log(logging.INFO, "Trading loop finished for the day.")

        except Exception as e:
            self.log(logging.ERROR, f"An error occurred in the trading loop: {e}")
            import traceback
            self.log(logging.ERROR, f"Traceback: {traceback.format_exc()}")
        finally:
            # Cancel subscriptions
            for contract in contracts_for_data:
                self.ib.cancelMktData(contract)
            self.log(logging.INFO, "Market data subscriptions cancelled.")

    def _liquidate_positions(self):
        """
        Liquidates all open positions at the end of the trading day.
        Checks both in-memory positions AND actual IBKR positions as safety net.
        """
        # First, try to liquidate tracked positions
        tracked_symbols = set()
        if self.positions:
            self.log(logging.INFO, f"Liquidating {len(self.positions)} tracked positions...")
            for symbol, position in list(self.positions.items()):
                tracked_symbols.add(symbol)
                try:
                    trade_contract = Stock(symbol, 'SMART', 'USD')
                    # Get current price
                    bars = self.ib.reqHistoricalData(
                        trade_contract, endDateTime='', durationStr='1 D',
                        barSizeSetting='1 min', whatToShow='TRADES', useRTH=True
                    )
                    if bars:
                        current_price = bars[-1].close
                    else:
                        current_price = position['entry_price']  # Fallback
                    
                    order = MarketOrder('SELL', position['quantity'])
                    order.tif = 'IOC'  # Immediate-Or-Cancel for faster execution
                    order.outsideRth = True  # Allow after-hours execution
                    trade = self.ib.placeOrder(trade_contract, order)
                    
                    # Wait up to 10 seconds for fill
                    for _ in range(10):
                        time.sleep(1)
                        if trade.orderStatus.status == 'Filled':
                            break
                    
                    if trade.orderStatus.status == 'Filled':
                        entry_price = position['entry_price']
                        exit_price = trade.orderStatus.avgFillPrice
                        pnl = (exit_price - entry_price) * position['quantity']
                        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                        
                        # DATABASE COORDINATION: Remove from active positions
                        self.db.remove_active_position(
                            symbol=symbol,
                            exit_price=exit_price,
                            exit_reason='EOD_LIQUIDATION',
                            agent_name='day_trader'
                        )
                        
                        # DATABASE: Log liquidation trade
                        self.db.log_trade({
                            'symbol': symbol,
                            'action': 'SELL',
                            'quantity': position['quantity'],
                            'price': exit_price,
                            'agent_name': 'day_trader',
                            'reason': 'End-of-day liquidation',
                            'profit_loss': pnl,
                            'profit_loss_pct': pnl_pct
                        })
                        
                        self.log(logging.INFO, f"LIQUIDATED {symbol}: Sold {position['quantity']} shares at ${exit_price:.2f}. P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                        del self.positions[symbol]
                    else:
                        self.log(logging.WARNING, f"Liquidation order for {symbol} not filled immediately. Status: {trade.orderStatus.status}")
                except Exception as e:
                    self.log(logging.ERROR, f"Error liquidating tracked position {symbol}: {e}")
        else:
            self.log(logging.INFO, "No tracked positions to liquidate.")
        
        # SAFETY NET: Check actual IBKR positions and liquidate any we missed
        try:
            self.log(logging.INFO, "Checking IBKR account for any untracked positions...")
            ibkr_positions = self.ib.positions()
            
            watchlist_symbols = [item.get('ticker') for item in self.watchlist_data]
            untracked_count = 0
            
            for pos in ibkr_positions:
                symbol = pos.contract.symbol
                
                # Only liquidate positions in our watchlist that weren't already sold
                if symbol in watchlist_symbols and symbol not in tracked_symbols and pos.position > 0:
                    untracked_count += 1
                    self.log(logging.WARNING, f"FOUND UNTRACKED POSITION: {symbol} - {pos.position} shares @ ${pos.avgCost:.4f}. Liquidating now!")
                    
                    try:
                        trade_contract = Stock(symbol, 'SMART', 'USD')
                        # Get current price
                        bars = self.ib.reqHistoricalData(
                            trade_contract, endDateTime='', durationStr='1 D',
                            barSizeSetting='1 min', whatToShow='TRADES', useRTH=True
                        )
                        if bars:
                            current_price = bars[-1].close
                        else:
                            current_price = pos.avgCost  # Fallback
                        
                        order = MarketOrder('SELL', int(abs(pos.position)))
                        trade = self.ib.placeOrder(trade_contract, order)
                        time.sleep(1)
                        
                        if trade.orderStatus.status == 'Filled':
                            exit_price = trade.orderStatus.avgFillPrice
                            pnl = (exit_price - pos.avgCost) * abs(pos.position)
                            pnl_pct = ((exit_price - pos.avgCost) / pos.avgCost) * 100
                            
                            # DATABASE COORDINATION: Remove untracked position
                            self.db.remove_active_position(
                                symbol=symbol,
                                exit_price=exit_price,
                                exit_reason='EOD_LIQUIDATION_UNTRACKED',
                                agent_name='day_trader'
                            )
                            
                            # DATABASE: Log untracked liquidation
                            self.db.log_trade({
                                'symbol': symbol,
                                'action': 'SELL',
                                'quantity': int(abs(pos.position)),
                                'price': exit_price,
                                'agent_name': 'day_trader',
                                'reason': 'End-of-day liquidation (untracked position)',
                                'profit_loss': pnl,
                                'profit_loss_pct': pnl_pct
                            })
                            
                            self.log(logging.INFO, f"LIQUIDATED UNTRACKED {symbol}: Sold {abs(pos.position)} shares at ${exit_price:.2f}. P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                        else:
                            self.log(logging.WARNING, f"Liquidation order for untracked {symbol} not filled. Status: {trade.orderStatus.status}")
                    except Exception as e:
                        self.log(logging.ERROR, f"Error liquidating untracked position {symbol}: {e}")
            
            if untracked_count == 0:
                self.log(logging.INFO, "No untracked watchlist positions found in IBKR account.")
            else:
                self.log(logging.WARNING, f"Liquidated {untracked_count} previously untracked positions!")
                
        except Exception as e:
            self.log(logging.ERROR, f"Error checking IBKR positions for liquidation: {e}")
            import traceback
            self.log(logging.ERROR, f"Traceback: {traceback.format_exc()}")
        
        self.log(logging.INFO, "Liquidation complete.")

    def run(self):
        """
        The main execution method for the IntradayTraderAgent.
        Enhanced with MOO (Market-On-Open) pre-market phase.
        
        Timeline:
        - 9:20-9:27 AM ET: Place MOO orders (if watchlist ready)
        - 9:30 AM ET: Monitor MOO fills, place profit targets
        - 9:30 AM - 3:45 PM ET: Regular trading loop + position monitoring
        - 3:45 PM ET: Liquidate all positions
        """
        import pytz
        from datetime import datetime, time as dt_time
        
        try:
            self._connect_to_brokerage()
            self._load_watchlist()
            self._calculate_capital()
            self._sync_positions_from_ibkr()  # CRITICAL: Sync existing positions before trading

            # Get ET timezone
            et_tz = pytz.timezone('US/Eastern')
            
            # MOO timing windows
            moo_start_time = dt_time(9, 20)  # 9:20 AM ET
            moo_end_time = dt_time(9, 27)    # 9:27 AM ET (1 min buffer before cutoff)
            moo_fill_time = dt_time(9, 30)   # 9:30 AM ET (market open)
            moo_fill_end = dt_time(9, 30, 30)  # 30 seconds after open
            
            # Check if we're in MOO placement window
            now_et = datetime.now(et_tz)
            current_time = now_et.time()
            
            # Phase 1: MOO Placement (9:20-9:27 AM ET)
            if moo_start_time <= current_time < moo_end_time and not self.moo_placed:
                self.log(logging.INFO, "⏰ MOO PLACEMENT WINDOW - Placing pre-market orders")
                self._place_moo_orders()
            
            # Phase 2: MOO Fill Monitoring (9:30:00-9:30:30 AM ET)
            elif moo_fill_time <= current_time < moo_fill_end and self.moo_placed and not self.moo_monitored:
                self.log(logging.INFO, "⏰ MARKET OPENED - Monitoring MOO fills")
                self._monitor_moo_fills()
            
            # Phase 3: Regular Trading Loop (9:30 AM - 4:00 PM ET)
            if is_market_open():
                self._run_trading_loop()
            else:
                self.log(logging.INFO, "Market is closed. Skipping trading loop.")

        except Exception as e:
            self.log(logging.CRITICAL, f"A critical error occurred in the IntradayTraderAgent: {e}")
        finally:
            if self.ib and self.ib.isConnected():
                self._liquidate_positions()
                
                # AUTONOMOUS: Run end-of-day improvement cycle
                self.log(logging.INFO, "Running end-of-day performance analysis and improvement cycle...")
                try:
                    improvement_report = self.improvement_engine.daily_improvement_cycle()
                    
                    # Log summary of improvements
                    if improvement_report.get('parameter_changes'):
                        self.log(logging.INFO, f"Parameters updated based on performance: {list(improvement_report['parameter_changes'].keys())}")
                    
                    if improvement_report.get('llm_insights'):
                        insights = improvement_report['llm_insights']
                        if isinstance(insights, dict) and 'assessment' in insights:
                            self.log(logging.INFO, f"LLM Assessment: {insights['assessment']}")
                    
                    self.log(logging.INFO, f"Daily improvement report saved to reports/improvement/")
                    
                except Exception as e_improve:
                    self.log(logging.ERROR, f"Error in improvement cycle: {e_improve}")
                
                self.log(logging.INFO, "Disconnecting from Interactive Brokers.")
                self.ib.disconnect()
