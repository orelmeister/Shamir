"""
Contains the specialized agents for the Day-Trading Bot.
"""

import logging
import json
import os
import time
import asyncio
import aiohttp
from datetime import datetime
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd
import yfinance as yf
from ib_insync import IB, Stock, MarketOrder, util
import pandas_ta as ta
from market_hours import is_market_open

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
        """Check if data is fresh for today, if not, aggregate new data."""
        self.log(logging.INFO, "--- [PHASE 0] Checking market data freshness. ---")
        
        # Check if data file exists and is from today
        if os.path.exists(AGGREGATED_DATA_FILE):
            try:
                # Check file modification time
                file_mod_time = datetime.fromtimestamp(os.path.getmtime(AGGREGATED_DATA_FILE))
                today = datetime.now().date()
                
                if file_mod_time.date() == today:
                    self.log(logging.INFO, f"{AGGREGATED_DATA_FILE} is already up-to-date for today ({today}). Skipping aggregation.")
                    return
                else:
                    self.log(logging.INFO, f"{AGGREGATED_DATA_FILE} is from {file_mod_time.date()}. Refreshing data for today ({today}).")
            except Exception as e:
                self.log(logging.WARNING, f"Could not check file modification time: {e}. Will refresh data.")
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
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
            tasks = [self._fetch_stock_data_with_semaphore(session, ticker, semaphore) for ticker in tickers]
            results = await asyncio.gather(*tasks)

        for data in results:
            if data and not data.get("error") and data.get("news"):
                all_market_data.append(data)
            elif data and not data.get("news"):
                self.log(logging.DEBUG, f"Discarding {data.get('ticker')} due to no news.")
        
        return all_market_data

    async def _fetch_target_tickers(self, session):
        self.log(logging.INFO, "Fetching target tickers from FMP stock screener for NYSE and NASDAQ.")
        all_tickers = set()
        exchanges_to_query = ["nyse", "nasdaq"]

        for exchange in exchanges_to_query:
            self.log(logging.INFO, f"Querying for exchange: {exchange.upper()}")
            params = {
                "marketCapMoreThan": 50000000,
                "marketCapLowerThan": 350000000,
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
                        self.log(logging.INFO, f"Found {len(page_tickers)} tickers for {exchange.upper()}.")
                    else:
                        self.log(logging.WARNING, f"No tickers returned for {exchange.upper()}.")

            except Exception as e:
                self.log(logging.ERROR, f"Could not fetch tickers from FMP screener for {exchange.upper()}: {e}")
                continue
        
        self.log(logging.INFO, f"Found a total of {len(all_tickers)} unique tickers across all exchanges.")
        return list(all_tickers)

    async def _fetch_stock_data_with_semaphore(self, session, ticker, semaphore):
        async with semaphore:
            return await self._fetch_stock_data(session, ticker)

    async def _fetch_stock_data(self, session, ticker):
        self.log(logging.DEBUG, f"Processing ticker: {ticker}")
        fmp_data = await self._fetch_fmp_data(session, ticker)
        
        news_items = []
        news_source = "None"

        # 1. Try Polygon
        polygon_data = await self._fetch_polygon_news(session, ticker)
        if polygon_data.get("news"):
            news_items = polygon_data["news"]
            news_source = "Polygon"
        
        # 2. Fallback to yfinance
        if not news_items:
            self.log(logging.DEBUG, f"No news from Polygon for {ticker}. Trying yfinance.")
            yfinance_data = await self._fetch_yfinance_news(ticker)
            if yfinance_data.get("news"):
                news_items = yfinance_data["news"]
                news_source = "yfinance"

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
            
            income_data_list = await income_resp.json()
            if not income_data_list:
                self.log(logging.ERROR, f"[FMP] No income statement for {ticker}.")
                return {"error": "No income statement"}

            income_data = income_data_list[0]

            return {
                "price": profile_data.get("price", 0), 
                "market_cap": profile_data.get("mktCap", 0),
                "company_name": profile_data.get("companyName"),
                "revenue": income_data.get("revenue", 0), 
                "net_income": income_data.get("netIncome", 0)
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
        - Micro-Cap Dynamics: Stocks under $350M market cap tend to be more volatile - factor this in
        
        **3. FUNDAMENTAL RISK ASSESSMENT**
        - Revenue & Profitability: Check for red flags (zero revenue, massive losses, negative trends)
        - Market Cap & Liquidity: Is the market cap between $50M-$350M (our target range)?
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
          "reasoning": "Strong catalyst: FDA approval news from yesterday with 10+ articles. Stock has history of 3-5% daily swings. $120M market cap in our target range. Moderate revenue ($50M) with growing trajectory. High volume spike (3x average) indicates trader interest. Clear entry opportunity at market open."
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


class IntradayTraderAgent(BaseDayTraderAgent):
    """
    This is the high-speed, algorithmic agent that executes trades during
    market hours based on technical indicators. It does NOT use an LLM for
    real-time decisions.
    """
    def __init__(self, orchestrator, allocation, paper_trade=True, profit_target_pct=0.014, stop_loss_pct=0.008):
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
        self.log(logging.INFO, f"Intraday Trader Agent initialized with {self.allocation*100}% capital allocation. Paper trading: {self.paper_trade}")

    def _connect_to_brokerage(self):
        """Connects to Interactive Brokers."""
        self.log(logging.INFO, "Connecting to Interactive Brokers...")
        self.ib = IB()
        try:
            # Adjust host and port if not using default TWS/Gateway settings
            # IB Gateway default is 4001 for both live and paper.
            # TWS default is 7496 for live and 7497 for paper.
            port = 4001 if self.paper_trade else 4001
            client_id = 2  # Changed to 2 to avoid conflict with other connections
            self.log(logging.INFO, f"Attempting connection to 127.0.0.1:{port} with clientId={client_id}...")
            
            # Use util.run() to properly handle the event loop for ib_insync
            # This ensures the async connection is properly awaited
            util.run(self.ib.connectAsync('127.0.0.1', port, clientId=client_id))
            
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
        """Loads the watchlist from the JSON file."""
        self.log(logging.INFO, "Loading day trading watchlist...")
        try:
            with open("day_trading_watchlist.json", 'r', encoding='utf-8-sig') as f:
                self.watchlist_data = json.load(f) # This is now a list of dicts
            
            if not self.watchlist_data:
                self.log(logging.WARNING, "Watchlist is empty after loading. No trades will be executed.")
            else:
                loaded_tickers = [item.get('ticker') for item in self.watchlist_data]
                self.log(logging.INFO, f"Loaded {len(self.watchlist_data)} stocks in the watchlist: {loaded_tickers}")
        except FileNotFoundError:
            self.log(logging.ERROR, "day_trading_watchlist.json not found. Pre-market analysis must run first.")
            self.watchlist_data = []
        except json.JSONDecodeError as e:
            self.log(logging.ERROR, f"Could not decode day_trading_watchlist.json: {e}. The file might be corrupt.")
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
            self.ib.sleep(2) # Give it a moment to populate - use ib.sleep for event loop compatibility
            acc_summary_list = self.ib.accountSummary()
            self.account_summary = {item.tag: item.value for item in acc_summary_list}

            # Find available cash and total account value
            available_cash = float(self.account_summary.get('AvailableFunds', 0))
            net_liquidation = float(self.account_summary.get('NetLiquidation', 0))

            self.log(logging.INFO, f"Account Summary: Available Funds: ${available_cash}, Net Liquidation: ${net_liquidation}")

            # Determine the total capital to use for day trading
            total_day_trading_capital = net_liquidation * self.allocation

            # Ensure we don't use more than the available cash
            if total_day_trading_capital > available_cash:
                self.log(logging.WARNING, f"Requested allocation (${total_day_trading_capital:.2f}) exceeds available cash (${available_cash:.2f}). Using available cash as the limit.")
                total_day_trading_capital = available_cash

            # Calculate capital per stock
            self.capital_per_stock = total_day_trading_capital / len(self.watchlist_data)
            self.log(logging.INFO, f"Total capital for day trading: ${total_day_trading_capital:.2f}. Capital per stock: ${self.capital_per_stock:.2f}")

        except Exception as e:
            self.log(logging.ERROR, f"Error calculating capital: {e}")
            self.capital_per_stock = 0


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
        
        for contract in contracts_for_data:
            # Qualify the contract first to ensure it's valid
            try:
                self.log(logging.INFO, f"Attempting to qualify contract for {contract.symbol}...")
                qualified = self.ib.qualifyContracts(contract)
                if qualified:
                    self.log(logging.INFO, f"[OK] Qualified contract for {contract.symbol}: {qualified[0].primaryExchange}")
                else:
                    self.log(logging.WARNING, f"[FAIL] Could not qualify contract for {contract.symbol}")
            except Exception as e:
                self.log(logging.ERROR, f"[ERROR] Error qualifying contract for {contract.symbol}: {e}")

        try:
            # In a real scenario, this would loop until market close.
            # For this test, we'll run it for a short duration (e.g., 5 minutes).
            loop_start_time = time.time()
            loop_duration_seconds = 300 # 5 minutes
            
            self.log(logging.INFO, f"Entering trading loop for {loop_duration_seconds}s or until market close...")
            
            while time.time() - loop_start_time < loop_duration_seconds and is_market_open():
                self.log(logging.INFO, "Trading loop iteration starting...")
                self.ib.sleep(5) # Poll for data every 5 seconds
                
                for contract in contracts_for_data: # Use the exchange-specific contract for data
                    try:
                        self.log(logging.INFO, f"Fetching historical data for {contract.symbol}...")
                        
                        # Get historical data to calculate indicators - try IBKR first, fallback to Polygon
                        df = None
                        try:
                            bars = self.ib.reqHistoricalData(
                                contract,
                                endDateTime='',
                                durationStr='1 D',
                                barSizeSetting='1 min',
                                whatToShow='TRADES',
                                useRTH=True,
                                formatDate=1
                            )
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

                        # Entry Logic: No position is open
                        if position is None:
                            # Enhanced entry with ATR volatility check
                            # Only enter if: Price > VWAP, RSI < 60, and ATR shows decent volatility (>1.5%)
                            atr_requirement = atr_pct is None or atr_pct >= 1.5  # If ATR unavailable, allow entry
                            
                            if current_price > vwap and rsi < 60 and atr_requirement:
                                quantity = int(self.capital_per_stock / current_price)
                                if quantity > 0:
                                    atr_info = f", ATR {atr_pct:.2f}% (volatile)" if atr_pct else ""
                                    self.log(logging.INFO, f"ENTRY SIGNAL for {contract.symbol}: Price ${current_price} > VWAP ${vwap:.2f}, RSI {rsi:.2f} < 60{atr_info}. Buying {quantity} shares.")
                                    
                                    # *** Use SMART routing for the best order execution price ***
                                    trade_contract = Stock(contract.symbol, 'SMART', 'USD')
                                    order = MarketOrder('BUY', quantity)
                                    trade = self.ib.placeOrder(trade_contract, order)
                                    
                                    self.ib.sleep(1)
                                    if trade.orderStatus.status == 'Filled':
                                        self.positions[contract.symbol] = {
                                            "quantity": trade.orderStatus.filled,
                                            "entry_price": trade.orderStatus.avgFillPrice,
                                            "contract": contract, # Store original data contract
                                            "atr_pct": atr_pct  # Store ATR at entry for reference
                                        }
                                        self.log(logging.INFO, f"BOUGHT {trade.orderStatus.filled} shares of {contract.symbol} at ${trade.orderStatus.avgFillPrice:.2f}")
                                    else:
                                        self.log(logging.WARNING, f"Buy order for {contract.symbol} not filled immediately. Status: {trade.orderStatus.status}")
                            else:
                                # Log why we're NOT buying
                                reasons = []
                                if not (current_price > vwap):
                                    reasons.append(f"Price ${current_price:.2f} <= VWAP ${vwap:.2f}")
                                if not (rsi < 60):
                                    reasons.append(f"RSI {rsi:.2f} >= 60 (overbought)")
                                if not atr_requirement:
                                    reasons.append(f"ATR {atr_pct:.2f}% < 1.5% (low volatility)")
                                if reasons:
                                    self.log(logging.INFO, f"NO ENTRY for {contract.symbol}: {', '.join(reasons)}")
                        
                        # Exit Logic: A position is open
                        else:
                            entry_price = position['entry_price']
                            profit_target = entry_price * (1 + self.profit_target_pct)
                            stop_loss = entry_price * (1 - self.stop_loss_pct)

                            if current_price >= profit_target:
                                self.log(logging.INFO, f"PROFIT TARGET for {contract.symbol}: Price ${current_price:.2f} >= Target ${profit_target:.2f}. Selling.")
                                trade_contract = Stock(contract.symbol, 'SMART', 'USD')
                                order = MarketOrder('SELL', position['quantity'])
                                self.ib.placeOrder(trade_contract, order)
                                del self.positions[contract.symbol]
                            
                            elif current_price <= stop_loss:
                                self.log(logging.INFO, f"STOP LOSS for {contract.symbol}: Price ${current_price:.2f} <= Stop ${stop_loss:.2f}. Selling.")
                                trade_contract = Stock(contract.symbol, 'SMART', 'USD')
                                order = MarketOrder('SELL', position['quantity'])
                                self.ib.placeOrder(trade_contract, order)
                                del self.positions[contract.symbol]

                    except Exception as e_stock:
                        self.log(logging.ERROR, f"An error occurred while processing {contract.symbol}: {e_stock}")
                        continue # Move to the next stock

            self.log(logging.INFO, "Trading loop finished for the day.")

        except Exception as e:
            self.log(logging.ERROR, f"An error occurred in the trading loop: {e}")
        finally:
            # Cancel subscriptions
            for contract in contracts_for_data:
                self.ib.cancelMktData(contract)
            self.log(logging.INFO, "Market data subscriptions cancelled.")

    def _liquidate_positions(self):
        """
        Liquidates all open positions at the end of the trading day.
        """
        if not self.positions:
            self.log(logging.INFO, "No open positions to liquidate.")
            return
        
        self.log(logging.INFO, f"Liquidating {len(self.positions)} open positions...")
        for symbol, position in list(self.positions.items()):
            try:
                trade_contract = Stock(symbol, 'SMART', 'USD')
                order = MarketOrder('SELL', position['quantity'])
                trade = self.ib.placeOrder(trade_contract, order)
                self.ib.sleep(1)
                
                if trade.orderStatus.status == 'Filled':
                    entry_price = position['entry_price']
                    exit_price = trade.orderStatus.avgFillPrice
                    pnl = (exit_price - entry_price) * position['quantity']
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    self.log(logging.INFO, f"LIQUIDATED {symbol}: Sold {position['quantity']} shares at ${exit_price:.2f}. P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
                    del self.positions[symbol]
                else:
                    self.log(logging.WARNING, f"Liquidation order for {symbol} not filled immediately. Status: {trade.orderStatus.status}")
            except Exception as e:
                self.log(logging.ERROR, f"Error liquidating {symbol}: {e}")
        
        self.log(logging.INFO, "Liquidation complete.")

    def run(self):
        """
        The main execution method for the IntradayTraderAgent.
        """
        try:
            self._connect_to_brokerage()
            self._load_watchlist()
            self._calculate_capital()

            # Main trading window logic
            if is_market_open():
                self._run_trading_loop()
            else:
                self.log(logging.INFO, "Market is closed. Skipping trading loop.")

        except Exception as e:
            self.log(logging.CRITICAL, f"A critical error occurred in the IntradayTraderAgent: {e}")
        finally:
            if self.ib and self.ib.isConnected():
                self._liquidate_positions()
                self.log(logging.INFO, "Disconnecting from Interactive Brokers.")
                self.ib.disconnect()
