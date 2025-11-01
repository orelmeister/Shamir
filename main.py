"""
main.py

This script is the single, unified entry point for the autonomous multi-agent trading bot.
It orchestrates the entire workflow, from data aggregation to trade execution and monitoring,
by executing a sequence of specialized agents.

NEWS FETCHING STRATEGY (Three-Tier Fallback):
1. Polygon API - Primary source (comprehensive, reliable)
2. yfinance - Secondary fallback (Yahoo Finance wrapper)
3. Firecrawl MCP - Final fallback (web crawling when APIs fail)
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
import asyncio
import aiohttp
from dotenv import load_dotenv
import yfinance as yf
from multiprocessing import Pool, cpu_count
import pandas as pd
from datetime import datetime
import argparse
import pytz

# LangChain and LLM Imports
from langchain_core.prompts import PromptTemplate
from langchain_google_vertexai import ChatVertexAI
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
import vertexai

# IBKR Trading Imports
from ib_insync import IB, Stock, Order, util

# Local Imports
from market_hours import is_market_open
import monte_carlo_filter as mc

# --- Configuration ---
load_dotenv()
FMP_API_KEY = os.getenv("FMP_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", 4001))
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")

# --- Control Flags ---
# CYCLE_INTERVAL_SECONDS = 3600  # Run the cycle every hour - This will be handled by the new loop logic
CONCURRENT_REQUESTS = 10
NEWS_FETCH_LIMIT = 100
# Sleep interval in seconds for the continuous loop
SCHEDULE_SLEEP_INTERVAL_SECONDS = 3600 # Sleep for 1 hour between checks in scheduled mode

# --- GROWTH-FOCUSED TRADING STRATEGY CONFIGURATION ---
# Risk Management
STOP_LOSS_PCT = 0.10            # -10% strict stop loss (cut losers fast)
TRAILING_STOP_TRIGGER = 0.20    # Activate trailing stop at +20% gain
TRAILING_STOP_PCT = 0.10        # Trail 10% below peak price

# Portfolio Settings
INITIAL_CAPITAL = 2000          # Starting capital allocation
MAX_POSITIONS = 5               # Maximum 5 concentrated positions
POSITION_SIZE_PCT = 0.20        # 20% per position (1/5 of capital)

# Time Rules
MIN_HOLD_DAYS = 2               # Minimum hold to avoid day trading pattern
MAX_HOLD_DAYS = None            # NO LIMIT - let winners run indefinitely!
DOWNTURN_CHECK_DAYS = 7         # Review positions declining for 7+ days

# Growth Focus Filters
MIN_REVENUE_GROWTH = 0.10       # Require 10%+ YoY revenue growth (realistic threshold)
MIN_CONFIDENCE_SCORE = 0.80     # High conviction only (LLM score >= 0.80)
MARKET_CAP_MIN = 50_000_000     # $50M minimum (micro-cap growth zone)
MARKET_CAP_MAX = 350_000_000    # $350M maximum (high growth potential)

# Technical Indicators for Downturn Detection
RSI_OVERSOLD_THRESHOLD = 40     # Sell if RSI drops below 40
MIN_LLM_HOLD_CONFIDENCE = 0.60  # Sell if LLM confidence drops below 0.60

# --- File & Directory Paths ---
LOG_DIR = "logs"
TRADING_QUEUE_FILE = "trading_queue.json"
FULL_ANALYSIS_FILE = "full_analysis_results.json"
AGGREGATED_DATA_FILE = "full_market_data.json"
POSITION_TRACKING_FILE = "weekly_bot_positions.json"  # Track entry prices, stops, trailing stops
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
MASTER_LOG_FILE = os.path.join(LOG_DIR, f"run_{RUN_ID}.json")

# --- Vertex AI Initialization ---
try:
    if not GOOGLE_CLOUD_PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")
    vertexai.init(project=GOOGLE_CLOUD_PROJECT)
except Exception as e:
    logging.basicConfig()
    logging.critical(f"Failed to initialize Vertex AI: {e}")

# --- Centralized Logging Setup ---
def setup_logging():
    """
    Sets up a centralized JSON logger for the entire application run.
    All logs will be written to a single, timestamped file.
    """
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    file_handler = logging.FileHandler(MASTER_LOG_FILE, mode='w')
    
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_record = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "agent": getattr(record, 'agent', 'Orchestrator'),
                "message": record.getMessage(),
            }
            if record.exc_info:
                log_record['exception'] = self.formatException(record.exc_info)
            return json.dumps(log_record)

    formatter = JsonFormatter()
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(agent)s] - %(message)s')
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)
    
    # Redirect ib_insync's noisy logs to a separate file for this run
    util.logToFile(os.path.join(LOG_DIR, f"ib_insync_{RUN_ID}.log"))
    logging.getLogger('ib_insync').propagate = False

    return logger

# --- Base Agent Class ---
class BaseAgent(ABC):
    """Abstract base class for all specialized agents."""
    def __init__(self, orchestrator, agent_name):
        self.orchestrator = orchestrator
        self.logger = orchestrator.logger
        self.agent_name = agent_name
        self.log_adapter = logging.LoggerAdapter(self.logger, {'agent': self.agent_name})

    def log(self, level, message, **kwargs):
        """Logs a message with the agent's name."""
        self.log_adapter.log(level, message, **kwargs)

    @abstractmethod
    def execute(self):
        """The main execution method for the agent."""
        pass

# --- Agent 1: Data Aggregator ---
class DataAggregatorAgent(BaseAgent):
    """
    Responsible for gathering all necessary market and news data using FMP and Polygon.
    """
    def execute(self):
        self.log(logging.INFO, "--- [PHASE 1] Starting data collection. ---")

        if self.orchestrator.skip_aggregation:
            self.log(logging.INFO, f"Skipping online aggregation. Loading data from {AGGREGATED_DATA_FILE}.")
            try:
                with open(AGGREGATED_DATA_FILE, 'r') as f:
                    aggregated_data = json.load(f)
                self.log(logging.INFO, f"Successfully loaded {len(aggregated_data)} tickers from file.")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                self.log(logging.CRITICAL, f"Could not load aggregated data file: {e}. Halting cycle.")
                self.log(logging.CRITICAL, "Please run the script once without --skip-aggregation to generate the data file.")
                self.orchestrator.halt_cycle()
                return
        else:
            try:
                aggregated_data = asyncio.run(self._aggregate_data())
                
                if not aggregated_data:
                    self.log(logging.ERROR, "Aggregation failed, no data was collected. Halting cycle.")
                    self.orchestrator.halt_cycle()
                    return

                # PRE-LLM FILTER: Remove stocks without sufficient revenue growth (5-year CAGR)
                self.log(logging.INFO, f"Applying pre-LLM revenue growth filter (>={MIN_REVENUE_GROWTH*100:.0f}% CAGR required)...")
                filtered_data = []
                for stock in aggregated_data:
                    revenue_growth = stock.get("revenue_growth_cagr", 0)
                    ticker = stock.get("ticker", "Unknown")
                    if revenue_growth >= MIN_REVENUE_GROWTH:
                        filtered_data.append(stock)
                        self.log(logging.DEBUG, f"✅ {ticker}: {revenue_growth*100:.1f}% CAGR")
                    else:
                        self.log(logging.DEBUG, f"❌ {ticker}: {revenue_growth*100:.1f}% < {MIN_REVENUE_GROWTH*100:.0f}%")
                
                self.log(logging.INFO, f"Pre-LLM filter: {len(aggregated_data)} stocks -> {len(filtered_data)} stocks (passed revenue growth filter)")
                aggregated_data = filtered_data
                
                if not aggregated_data:
                    self.log(logging.WARNING, "No stocks passed pre-LLM revenue growth filter. Halting cycle.")
                    self.orchestrator.halt_cycle()
                    return

                # Save the aggregated data for future skipped runs
                try:
                    with open(AGGREGATED_DATA_FILE, 'w') as f:
                        json.dump(aggregated_data, f, indent=4)
                    self.log(logging.INFO, f"Successfully saved aggregated data for {len(aggregated_data)} tickers to {AGGREGATED_DATA_FILE}.")
                except Exception as e:
                    self.log(logging.ERROR, f"Failed to save aggregated data file: {e}")

            except Exception as e:
                self.log(logging.CRITICAL, f"A critical error occurred during data aggregation: {e}", exc_info=True)
                self.orchestrator.halt_cycle()
                return

        self.orchestrator.write_to_queue({
            "phase": "aggregation_complete",
            "stocks_for_analysis": aggregated_data
        })
        self.log(logging.INFO, f"--- Finished. Made data for {len(aggregated_data)} tickers available for analysis. ---")

    async def _aggregate_data(self):
        all_market_data = []
        async with aiohttp.ClientSession() as session:
            tickers = await self._fetch_target_tickers(session)
            if not tickers:
                self.log(logging.CRITICAL, "No tickers returned from FMP screener. Halting.")
                return []

            self.log(logging.INFO, f"Found {len(tickers)} target tickers to process.")
            semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
            tasks = [self._fetch_stock_data_with_semaphore(session, ticker, semaphore) for ticker in tickers]
            results = await asyncio.gather(*tasks)

        for data in results:
            if data and not data.get("error") and data.get("news"):
                all_market_data.append(data)
            elif data and not data.get("news"):
                self.log(logging.INFO, f"Discarding {data.get('ticker')} due to no news.")
        
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
                self.log(logging.CRITICAL, f"Could not fetch tickers from FMP screener for {exchange.upper()}: {e}")
                # If one exchange fails, we can still proceed with the others
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
        
        # 2. Fallback to yfinance (only provides title + URL, no content)
        if not news_items:
            self.log(logging.INFO, f"No news from Polygon for {ticker}. Trying yfinance.")
            yfinance_data = await self._fetch_yfinance_news(ticker)
            if yfinance_data.get("news"):
                news_items = yfinance_data["news"]
                news_source = "yfinance"

        self.log(logging.DEBUG, f"Found {len(news_items)} news items for {ticker} from {news_source}.")

        combined_data = {
            "ticker": ticker, "price": fmp_data.get("price", 0),
            "market_cap": fmp_data.get("market_cap", 0), "revenue": fmp_data.get("revenue", 0),
            "net_income": fmp_data.get("net_income", 0), 
            "revenue_growth_cagr": fmp_data.get("revenue_growth_cagr", 0),  # 5-year CAGR
            "news": news_items,
            "news_source": news_source,
            "error": fmp_data.get("error")
        }
        return combined_data

    async def _fetch_fmp_data(self, session, ticker):
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
        income_url = f"https://financialmodelingprep.com/api/v3/income-statement/{ticker}"
        params = {"apikey": FMP_API_KEY, "limit": 5, "period": "annual"}  # Fetch 5 years for CAGR calc
        try:
            async with asyncio.TaskGroup() as tg:
                profile_task = tg.create_task(session.get(profile_url, params={"apikey": FMP_API_KEY}))
                income_task = tg.create_task(session.get(income_url, params=params))
            
            profile_resp = await profile_task
            income_resp = await income_task
            
            profile_data_list = await profile_resp.json()
            if not profile_data_list:
                self.log(logging.ERROR, f"[FMP] No profile data for {ticker}.")
                return {"error": "No profile data"}

            profile_data = profile_data_list[0]
            
            income_data_list = await income_resp.json()
            if not income_data_list:
                self.log(logging.ERROR, f"[FMP] No income statement for {ticker}.")
                return {"error": "No income statement"}

            # Get latest year data
            income_data = income_data_list[0]
            latest_revenue = income_data.get("revenue", 0)
            
            # Calculate 5-year CAGR if we have sufficient data
            revenue_growth_cagr = 0
            if len(income_data_list) >= 5:
                latest_revenue_val = income_data_list[0].get("revenue", 0)
                oldest_revenue_val = income_data_list[4].get("revenue", 0)
                
                if oldest_revenue_val > 0 and latest_revenue_val > 0:
                    # CAGR = (Ending Value / Beginning Value) ^ (1 / Number of Years) - 1
                    years = 4  # 5 data points = 4 years of growth
                    revenue_growth_cagr = (latest_revenue_val / oldest_revenue_val) ** (1 / years) - 1
                    self.log(logging.DEBUG, f"[FMP] {ticker} 5-year CAGR: {revenue_growth_cagr*100:.2f}%")
            elif len(income_data_list) >= 2:
                # Fallback to simple YoY if less than 5 years available
                prior_revenue = income_data_list[1].get("revenue", 0)
                if prior_revenue > 0:
                    revenue_growth_cagr = (latest_revenue - prior_revenue) / prior_revenue
                    self.log(logging.DEBUG, f"[FMP] {ticker} YoY growth (fallback): {revenue_growth_cagr*100:.2f}%")

            return {
                "price": profile_data.get("price", 0), 
                "market_cap": profile_data.get("mktCap", 0),
                "company_name": profile_data.get("companyName"),
                "revenue": latest_revenue, 
                "net_income": income_data.get("netIncome", 0),
                "revenue_growth_cagr": revenue_growth_cagr  # Changed from revenue_growth_yoy to revenue_growth_cagr
            }
        except Exception as e:
            self.log(logging.ERROR, f"[FMP] Error for {ticker}: {e}")
            return {"error": str(e)}

    async def _fetch_polygon_news(self, session, ticker):
        url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit={NEWS_FETCH_LIMIT}&apiKey={POLYGON_API_KEY}"
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                # Polygon provides description (snippet) and article_url - extract both
                news_items = [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("article_url", ""),
                        "content": item.get("description", "")  # Polygon's content field
                    } 
                    for item in data.get("results", [])
                ]
                return {"news": news_items}
        except Exception as e:
            self.log(logging.ERROR, f"[Polygon] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}

    async def _fetch_yfinance_news(self, ticker):
        try:
            loop = asyncio.get_event_loop()
            yf_ticker = await loop.run_in_executor(None, lambda: yf.Ticker(ticker))
            news = await loop.run_in_executor(None, lambda: yf_ticker.news)
            # yfinance news items only have title and link (no useful content field)
            return {"news": [{"title": item.get("title", ""), "url": item.get("link")} for item in news[:5]]}
        except Exception as e:
            self.log(logging.ERROR, f"[yfinance] News error for {ticker}: {e}")
            return {"news": [], "error": str(e)}


# --- Agent 2: Analyst ---
class AnalystAgent(BaseAgent):
    """
    Analyzes stocks, uses LLMs for recommendations, and runs Monte Carlo simulations.
    """
    def execute(self):
        self.log(logging.INFO, "--- [PHASE 2] Starting analysis. ---")
        
        if self.orchestrator.rerun_analysis:
            self.log(logging.INFO, f"Re-running analysis from {FULL_ANALYSIS_FILE}.")
            try:
                with open(FULL_ANALYSIS_FILE, 'r') as f:
                    results = json.load(f)
                self.log(logging.INFO, f"Successfully loaded {len(results)} analysis results.")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                self.log(logging.CRITICAL, f"Could not load analysis file for re-run: {e}. Halting.")
                self.orchestrator.halt_cycle()
                return
        else:
            queue_data = self.orchestrator.read_from_queue()
            if queue_data.get("phase") != "aggregation_complete":
                self.log(logging.ERROR, "Expected 'aggregation_complete' phase. Halting.")
                self.orchestrator.halt_cycle()
                return

            stocks_to_analyze = queue_data.get("stocks_for_analysis", [])
            if not stocks_to_analyze:
                self.log(logging.WARNING, "No stocks to analyze. Skipping.")
                self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
                return

            self.log(logging.INFO, f"Analyzing {len(stocks_to_analyze)} stocks in parallel.")
            results = []
            with Pool(processes=cpu_count()) as pool:
                worker_args = [(stock, i, self.orchestrator.force_online_llms) for i, stock in enumerate(stocks_to_analyze)]
                
                total_stocks = len(stocks_to_analyze)
                # Use imap_unordered to get results as they complete for better progress tracking
                for i, result in enumerate(pool.imap_unordered(self._analysis_worker_wrapper, worker_args), 1):
                    if result:
                        results.append(result)
                        ticker = result.get('ticker', 'Unknown')
                        decision = result.get('decision', 'ERROR')
                        self.log(logging.INFO, f"Progress: [{i}/{total_stocks}] - Analyzed {ticker}. Decision: {decision}")
                    else:
                        self.log(logging.WARNING, f"Progress: [{i}/{total_stocks}] - A worker process returned no result.")

            # Save the full, unfiltered analysis results for potential re-runs
            try:
                with open(FULL_ANALYSIS_FILE, 'w') as f:
                    json.dump(results, f, indent=4)
                self.log(logging.INFO, f"Successfully saved full analysis for {len(results)} stocks to {FULL_ANALYSIS_FILE}.")
            except Exception as e:
                self.log(logging.ERROR, f"Failed to save full analysis results: {e}")

        buy_recommendations = [
            res for res in results 
            if res and res.get("decision") == "BUY" and res.get("confidence", 0) >= MIN_CONFIDENCE_SCORE
        ]
        self.log(logging.INFO, f"Found {len(buy_recommendations)} 'BUY' recommendations with confidence >= {MIN_CONFIDENCE_SCORE}.")

        if not buy_recommendations:
            self.log(logging.INFO, "No high-confidence 'BUY' recommendations to process. Ending analysis phase.")
            self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
            return

        self.log(logging.INFO, "Running Monte Carlo simulation to find the top pick...")
        top_pick_ticker_list = mc.run_monte_carlo_filter(buy_recommendations)
        
        if not top_pick_ticker_list:
            self.log(logging.ERROR, "Monte Carlo simulation failed to return a top pick.")
            self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
            return
        
        # Validate tickers in ranked order and select first valid one
        top_pick = None
        for ticker in top_pick_ticker_list:
            candidate = next((rec for rec in buy_recommendations if rec['ticker'] == ticker), None)
            if candidate:
                # Quick validation: check if ticker exists in IBKR
                if self._validate_ticker_in_ibkr(ticker):
                    top_pick = candidate
                    self.log(logging.INFO, f"✅ Selected valid ticker: {ticker}")
                    break
                else:
                    self.log(logging.WARNING, f"⚠️ Ticker {ticker} not found in IBKR. Trying next...")
        
        if not top_pick:
            self.log(logging.ERROR, "No valid tickers found in Monte Carlo rankings.")
            self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
            return

        self.log(logging.INFO, f"Top pick from Monte Carlo is: {top_pick['ticker']}")
        self.orchestrator.write_to_queue({
            "phase": "analysis_complete",
            "recommendation": top_pick
        })
        self.log(logging.INFO, "--- Finished. Top recommendation sent to queue. ---")

    def _validate_ticker_in_ibkr(self, ticker):
        """Quick validation to check if ticker exists in IBKR before trading."""
        ib = IB()
        try:
            ib.connect(IB_HOST, IB_PORT, clientId=1)
            contract = Stock(ticker, 'SMART', 'USD')
            details = ib.reqContractDetails(contract)
            ib.disconnect()
            
            if not details:
                self.log(logging.WARNING, f"No contract details found for {ticker}")
                return False
            
            self.log(logging.DEBUG, f"Validated {ticker}: {details[0].contract.symbol}")
            return True
            
        except Exception as e:
            self.log(logging.ERROR, f"Ticker validation failed for {ticker}: {e}")
            if ib.isConnected():
                ib.disconnect()
            return False

    @staticmethod
    def _analysis_worker_wrapper(args):
        """Helper to unpack arguments for imap_unordered."""
        return AnalystAgent._run_analysis_worker(*args)

    @staticmethod
    def _run_analysis_worker(stock_data, worker_id, force_online_llms):
        """Worker function for parallel analysis, using LLMs."""
        # Logging from multiprocessing workers is complex. We'll use a simple
        # file-based logger for each worker for debugging purposes.
        log_dir = "logs"
        log_file_path = os.path.join(log_dir, f'analyst_worker_{RUN_ID}_{worker_id}.log')
        worker_logger = logging.getLogger(f'analyst_worker_{worker_id}')
        worker_logger.setLevel(logging.INFO)
        if not worker_logger.hasHandlers():
            file_handler = logging.FileHandler(log_file_path, mode='w')
            file_handler.setFormatter(logging.Formatter(f'%(asctime)s - [Analyst-{worker_id}] - %(message)s'))
            worker_logger.addHandler(file_handler)

        ticker = stock_data.get("ticker", "Unknown")
        worker_logger.info(f"Starting analysis for {ticker}")

        prompt = f"""
        You are an aggressive growth stock analyst targeting 50%+ returns in 30 days.
        
        Analyze the following stock data with STRICT criteria for high-growth micro-caps:
        
        MANDATORY REQUIREMENTS:
        - Market cap: $50M-$350M (micro-cap growth zone)
        - Revenue growth: >30% YoY (fast growers only)
        - Recent positive catalysts (earnings beat, new contracts, breakthrough news)
        - Strong price momentum (technical strength)
        - Clear growth story with potential for 2x-5x appreciation
        
        DECISION CRITERIA:
        - BUY: High conviction (confidence ≥0.80), meets all requirements, explosive growth potential
        - HOLD: Does not meet strict growth criteria or confidence <0.80
        
        CONFIDENCE SCORING (0.0-1.0):
        - 0.90-1.0: Exceptional - multiple catalysts, explosive revenue growth, strong momentum
        - 0.80-0.89: Strong - meets all criteria with solid fundamentals
        - 0.70-0.79: Good but not aggressive enough for our strategy
        - <0.70: HOLD - insufficient growth potential
        
        Focus on: Small caps poised for breakout, recent IPOs scaling fast, companies with
        disruptive technology, or stocks with recent positive inflection points.
        
        Data: {json.dumps(stock_data, indent=2)}

        Return ONLY a JSON object with "ticker", "decision" (BUY or HOLD), "confidence" (0.0-1.0), and "reasoning" (be specific about growth catalysts).
        """
        
        try:
            # Dynamic LLM Switching with override
            if force_online_llms or is_market_open():
                if force_online_llms:
                    worker_logger.info(f"FORCE_ONLINE_LLMS is True. Using online models for {ticker}.")
                else:
                    worker_logger.info(f"Market is OPEN. Using online models for {ticker}.")
                
                try:
                    llm = ChatDeepSeek(model="deepseek-reasoner", api_key=DEEPSEEK_API_KEY)
                    model_name = 'DeepSeek'
                    response = llm.invoke(prompt)
                except Exception as e:
                    worker_logger.warning(f"DeepSeek failed for {ticker}: {e}. Falling back to Gemini.")
                    llm = ChatVertexAI(model_name="gemini-2.5-flash") # CORRECTED MODEL as per user instruction
                    model_name = 'Gemini'
                    response = llm.invoke(prompt)
            else:
                worker_logger.info(f"Market is CLOSED and override is OFF. Using local Ollama model for {ticker}.")
                llm = ChatOllama(model="llama3.1:8b")
                model_name = 'Ollama'
                response = llm.invoke(prompt)

            analysis = json.loads(response.content)
            analysis['model'] = model_name
            
            final_result = stock_data.copy()
            final_result.update(analysis)
            return final_result
        except Exception as e:
            worker_logger.error(f"An error occurred during LLM analysis for {ticker}: {e}", exc_info=True)
            return {"ticker": ticker, "decision": "ERROR", "reasoning": str(e)}

# --- Position Tracker for Stop Loss & Trailing Stop Management ---
class PositionTracker:
    """
    Manages position metadata including entry prices, stop losses, and trailing stops.
    Persists data to JSON file for continuity across bot runs.
    """
    def __init__(self, tracking_file=POSITION_TRACKING_FILE):
        self.tracking_file = tracking_file
        self.positions = self._load_positions()
    
    def _load_positions(self):
        """Load position data from JSON file."""
        if os.path.exists(self.tracking_file):
            with open(self.tracking_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_positions(self):
        """Save position data to JSON file."""
        with open(self.tracking_file, 'w') as f:
            json.dump(self.positions, f, indent=2)
    
    def add_position(self, symbol, entry_price, quantity, entry_date=None):
        """
        Record a new position with stop loss and initial tracking data.
        """
        if entry_date is None:
            entry_date = datetime.now().isoformat()
        
        stop_loss_price = entry_price * (1 - STOP_LOSS_PCT)
        
        self.positions[symbol] = {
            "entry_price": entry_price,
            "entry_date": entry_date,
            "quantity": quantity,
            "stop_loss_price": stop_loss_price,
            "trailing_stop_active": False,
            "trailing_stop_price": None,
            "highest_price": entry_price,
            "current_return_pct": 0.0,
            "days_held": 0
        }
        self._save_positions()
        return self.positions[symbol]
    
    def update_position(self, symbol, current_price):
        """
        Update position tracking with current price.
        Handles trailing stop activation and adjustment.
        Returns action: 'HOLD', 'STOP_OUT', or 'TRAILING_STOP_HIT'
        """
        if symbol not in self.positions:
            return 'HOLD'  # Position not tracked, no action
        
        pos = self.positions[symbol]
        entry_price = pos["entry_price"]
        current_return_pct = (current_price - entry_price) / entry_price
        pos["current_return_pct"] = current_return_pct
        
        # Update highest price achieved
        if current_price > pos["highest_price"]:
            pos["highest_price"] = current_price
        
        # Check -10% stop loss
        if current_price <= pos["stop_loss_price"]:
            self._save_positions()
            return 'STOP_OUT'
        
        # Activate trailing stop at +20% gain
        if not pos["trailing_stop_active"] and current_return_pct >= TRAILING_STOP_TRIGGER:
            pos["trailing_stop_active"] = True
            pos["trailing_stop_price"] = current_price * (1 - TRAILING_STOP_PCT)
            self._save_positions()
            return 'HOLD'  # Just activated, continue holding
        
        # Update trailing stop (10% below highest price)
        if pos["trailing_stop_active"]:
            new_trailing_stop = pos["highest_price"] * (1 - TRAILING_STOP_PCT)
            pos["trailing_stop_price"] = max(pos["trailing_stop_price"], new_trailing_stop)
            
            # Check if trailing stop hit
            if current_price <= pos["trailing_stop_price"]:
                self._save_positions()
                return 'TRAILING_STOP_HIT'
        
        self._save_positions()
        return 'HOLD'
    
    def remove_position(self, symbol):
        """Remove position from tracking (after selling)."""
        if symbol in self.positions:
            del self.positions[symbol]
            self._save_positions()
    
    def get_position(self, symbol):
        """Get position tracking data."""
        return self.positions.get(symbol, None)
    
    def get_all_positions(self):
        """Get all tracked positions."""
        return self.positions
    
    def update_days_held(self):
        """Update days held for all positions (call this daily)."""
        today = datetime.now().date()
        for symbol, pos in self.positions.items():
            entry_date = datetime.fromisoformat(pos["entry_date"]).date()
            pos["days_held"] = (today - entry_date).days
        self._save_positions()

# --- Agent 3: Portfolio Manager ---
class PortfolioManagerAgent(BaseAgent):
    """
    Executes trades based on the Analyst's final recommendation,
    focusing on rebalancing the entire portfolio.
    NOW WITH GROWTH STRATEGY: -10% stops, trailing stops, position limits.
    """
    def __init__(self, orchestrator, agent_name="PortfolioManager"):
        super().__init__(orchestrator, agent_name)
        self.position_tracker = PositionTracker()
    
    def execute(self):
        self.log(logging.INFO, "--- [PHASE 3] Starting trade execution with growth strategy. ---")
        
        # STEP 1: Check stop losses and trailing stops FIRST
        if is_market_open():
            self._check_stops_and_exits()
        else:
            self.log(logging.INFO, "Market closed - skipping stop loss checks until market opens.")
        queue_data = self.orchestrator.read_from_queue()

        if queue_data.get("phase") != "analysis_complete":
            self.log(logging.ERROR, "Expected 'analysis_complete' phase. Halting.")
            self.orchestrator.halt_cycle()
            return

        recommendation = queue_data.get("recommendation")
        if not recommendation or recommendation.get("decision") != "BUY":
            self.log(logging.INFO, "No 'BUY' recommendation to execute. Ending cycle.")
            self.orchestrator.write_to_queue({"phase": "execution_complete", "executed_trades": []})
            return

        # If market is closed, try to place pre-market orders or wait for market open
        if not is_market_open():
            # Check current time in ET timezone
            ny_tz = pytz.timezone('America/New_York')
            now_ny = datetime.now(ny_tz)
            market_open_time = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
            
            # Try to place pre-market orders (will check time window internally)
            self.log(logging.INFO, "Market is currently closed. Attempting pre-market order placement...")
            trade_result = self._place_moo_orders(recommendation)
            
            # Check if we were outside the safe window
            if trade_result.get('status') == 'OUTSIDE_WINDOW':
                self.log(logging.INFO, "Pre-market window closed. Checking when market opens...")
                now_ny = datetime.now(ny_tz)
                
                # If market opens soon (within 5 minutes), wait for it
                time_until_open = (market_open_time - now_ny).total_seconds()
                if 0 < time_until_open <= 300:  # 0-5 minutes until open
                    self.log(logging.INFO, f"Market opens in {time_until_open:.0f} seconds. Waiting to place LIMIT orders...")
                    import time
                    time.sleep(time_until_open + 5)  # Wait 5 sec after open
                    self.log(logging.INFO, "✅ Market now open. Placing LIMIT orders.")
                    trade_result = self._execute_rebalance(recommendation)
                elif time_until_open > 300:
                    self.log(logging.ERROR, f"Market opens in {time_until_open/60:.1f} minutes. Too long to wait. Exiting.")
                    trade_result = {"status": "FAILURE", "reason": "Too early to place orders"}
                else:
                    # Market already opened (time_until_open <= 0)
                    self.log(logging.INFO, "Market already open. Placing LIMIT orders now.")
                    trade_result = self._execute_rebalance(recommendation)
            
            # Handle any other failures
            elif trade_result.get('status') in ['FAILURE', 'MOO_REJECTED']:
                self.log(logging.ERROR, "Pre-market order placement failed. Attempting fallback to market-open execution...")
                now_ny = datetime.now(ny_tz)
                time_until_open = (market_open_time - now_ny).total_seconds()
                
                if 0 < time_until_open <= 300:
                    self.log(logging.INFO, f"Waiting {time_until_open:.0f} seconds for market open...")
                    import time
                    time.sleep(time_until_open + 5)
                    trade_result = self._execute_rebalance(recommendation)
                elif time_until_open <= 0:
                    self.log(logging.INFO, "Market already open. Executing now.")
                    trade_result = self._execute_rebalance(recommendation)
                else:
                    self.log(logging.ERROR, "Cannot place orders - too early and pre-market failed.")
            
            self.orchestrator.write_to_queue({
                "phase": "execution_complete",
                "executed_trades": trade_result.get('moo_orders', []) if 'moo_orders' in trade_result else trade_result.get('executed_trades', [])
            })
            return

        self.log(logging.INFO, f"Received 'BUY' recommendation for {recommendation['ticker']}. Initiating portfolio rebalance.")
        
        trade_result = self._execute_rebalance(recommendation)
        
        self.log(logging.INFO, f"Rebalancing result: {trade_result.get('status', 'UNKNOWN')}")
        
        self.orchestrator.write_to_queue({
            "phase": "execution_complete",
            "executed_trades": trade_result if trade_result.get('status') != "FAILURE" else []
        })
        self.log(logging.INFO, f"--- Finished. Rebalancing for {recommendation['ticker']} processed. ---")

    def _check_stops_and_exits(self):
        """
        Check all positions for stop loss hits and trailing stop exits.
        Execute immediate sell orders for positions that hit stops.
        """
        self.log(logging.INFO, "Checking stop losses and trailing stops for all positions...")
        
        ib = IB()
        try:
            ib.connect(IB_HOST, IB_PORT, clientId=1)
            ib.reqMarketDataType(3)
            
            current_positions = ib.portfolio()
            positions_to_sell = []
            
            for pos in current_positions:
                symbol = pos.contract.symbol
                current_price = pos.marketPrice
                
                if current_price <= 0:
                    self.log(logging.WARNING, f"Invalid price for {symbol}: {current_price}. Skipping stop check.")
                    continue
                
                # Update position tracking
                action = self.position_tracker.update_position(symbol, current_price)
                
                if action == 'STOP_OUT':
                    self.log(logging.CRITICAL, f"🛑 STOP LOSS HIT: {symbol} at ${current_price:.2f} (entry: ${self.position_tracker.get_position(symbol)['entry_price']:.2f}, -10% stop)")
                    positions_to_sell.append((symbol, pos.contract, pos.position, "STOP_LOSS"))
                
                elif action == 'TRAILING_STOP_HIT':
                    pos_data = self.position_tracker.get_position(symbol)
                    self.log(logging.INFO, f"📉 TRAILING STOP HIT: {symbol} at ${current_price:.2f} (highest: ${pos_data['highest_price']:.2f}, locking in +{pos_data['current_return_pct']*100:.1f}% gain)")
                    positions_to_sell.append((symbol, pos.contract, pos.position, "TRAILING_STOP"))
                
                elif action == 'HOLD':
                    pos_data = self.position_tracker.get_position(symbol)
                    if pos_data:
                        gain_pct = pos_data['current_return_pct'] * 100
                        trailing_status = "ACTIVE" if pos_data['trailing_stop_active'] else "NOT ACTIVE"
                        self.log(logging.INFO, f"✅ HOLDING: {symbol} at ${current_price:.2f} ({gain_pct:+.1f}%, trailing stop: {trailing_status})")
            
            # Execute sell orders for stopped positions
            for symbol, contract, quantity, reason in positions_to_sell:
                self.log(logging.INFO, f"Selling {quantity} shares of {symbol} ({reason})...")
                order = Order(action="SELL", totalQuantity=abs(quantity), orderType='MKT', outsideRth=True)
                trade = ib.placeOrder(contract, order)
                ib.sleep(2)
                self.log(logging.INFO, f"Sell order placed for {symbol} ({reason})")
                
                # Remove from position tracking
                self.position_tracker.remove_position(symbol)
            
            if positions_to_sell:
                self.log(logging.INFO, f"Sold {len(positions_to_sell)} positions due to stops.")
            else:
                self.log(logging.INFO, "No stop losses triggered. All positions within limits.")
        
        except Exception as e:
            self.log(logging.ERROR, f"Error checking stops: {e}", exc_info=True)
        finally:
            if ib.isConnected():
                ib.disconnect()

    def _update_moo_fill_prices(self):
        """
        Update position tracking with actual fill prices from executed MOO orders.
        Call this after market open to correct estimated entry prices.
        """
        self.log(logging.INFO, "🔄 Updating MOO fill prices with actual execution data...")
        
        ib = IB()
        try:
            ib.connect(IB_HOST, IB_PORT, clientId=1)
            ib.reqMarketDataType(3)
            
            current_positions = ib.portfolio()
            updated_count = 0
            
            for pos in current_positions:
                symbol = pos.contract.symbol
                actual_avg_cost = pos.averageCost
                quantity = int(pos.position)
                
                # Check if we have position tracking for this symbol
                tracked_pos = self.position_tracker.get_position(symbol)
                if tracked_pos and actual_avg_cost > 0:
                    # Update entry price with actual fill price
                    estimated_price = tracked_pos['entry_price']
                    if abs(actual_avg_cost - estimated_price) / estimated_price > 0.01:  # >1% difference
                        self.log(logging.INFO, f"📝 Updating {symbol}: Estimated ${estimated_price:.2f} → Actual ${actual_avg_cost:.2f}")
                        # Remove old tracking and add new with correct price
                        self.position_tracker.remove_position(symbol)
                        pos_data = self.position_tracker.add_position(symbol, actual_avg_cost, quantity)
                        self.log(logging.INFO, f"   Updated stop loss: ${pos_data['stop_loss_price']:.2f} (-10%)")
                        updated_count += 1
            
            if updated_count > 0:
                self.log(logging.INFO, f"✅ Updated {updated_count} position(s) with actual fill prices.")
            else:
                self.log(logging.INFO, "No position tracking updates needed.")
        
        except Exception as e:
            self.log(logging.ERROR, f"Error updating MOO fill prices: {e}", exc_info=True)
        finally:
            if ib.isConnected():
                ib.disconnect()

    def _place_moo_orders(self, recommendation):
        """
        Place pre-market orders that execute at 9:30 AM ET market open.
        Uses MKT orders (not MOO type) which are more forgiving on timing.
        Only places orders if we're in the safe window (9:00-9:27 AM ET).
        """
        # CRITICAL: Check if we're in the safe time window for pre-market orders
        ny_tz = pytz.timezone('America/New_York')
        now_ny = datetime.now(ny_tz)
        current_time = now_ny.time()
        
        # Safe window: 9:00-9:27 AM ET (3-minute buffer before issues can occur)
        window_start = datetime.strptime("09:00", "%H:%M").time()
        window_end = datetime.strptime("09:27", "%H:%M").time()
        
        if not (window_start <= current_time <= window_end):
            self.log(logging.WARNING, f"⏰ Outside safe pre-market window (9:00-9:27 AM ET). Current time: {now_ny.strftime('%H:%M:%S')} ET")
            self.log(logging.INFO, "Will use market-open execution with LIMIT orders instead.")
            return {"status": "OUTSIDE_WINDOW", "reason": f"Current time {now_ny.strftime('%H:%M:%S')} ET outside 9:00-9:27 AM window", "moo_orders": []}
        
        self.log(logging.INFO, f"✅ Within safe pre-market window: {now_ny.strftime('%H:%M:%S')} ET (9:00-9:27 AM)")
        self.log(logging.INFO, "=== Placing Pre-Market Orders for Market Open ===")
        
        ib = IB()
        try:
            self.log(logging.INFO, "Connecting to IBKR for pre-market order placement...")
            # Use util.run() for Python 3.12+ compatibility
            util.run(ib.connectAsync(IB_HOST, IB_PORT, clientId=1))
            ib.reqMarketDataType(3)
            
            account_summary = ib.accountSummary()
            portfolio_value_data = next((v for v in account_summary if v.tag == 'NetLiquidation' and v.currency == 'USD'), None)
            
            if not portfolio_value_data:
                self.log(logging.ERROR, "Could not determine Net Liquidation from IBKR.")
                return {"status": "FAILURE", "reason": "NetLiquidation not found."}

            total_portfolio_value = float(portfolio_value_data.value)
            current_positions = ib.portfolio()
            self.log(logging.INFO, f"Total Portfolio Value: ${total_portfolio_value:,.2f}")
            self.log(logging.INFO, f"Found {len(current_positions)} existing positions.")

            target_portfolio_symbols = {pos.contract.symbol for pos in current_positions}
            new_ticker = recommendation['ticker']
            
            # CHECK POSITION LIMIT
            if new_ticker not in target_portfolio_symbols:
                if len(current_positions) >= MAX_POSITIONS:
                    self.log(logging.WARNING, f"🚫 POSITION LIMIT REACHED: Already have {len(current_positions)} positions (max: {MAX_POSITIONS}). Cannot add {new_ticker}.")
                    return {"status": "LIMIT_REACHED", "reason": f"Max {MAX_POSITIONS} positions already held.", "moo_orders": []}
            
            target_portfolio_symbols.add(new_ticker)
            num_target_positions = len(target_portfolio_symbols)
            target_value_per_position = total_portfolio_value / num_target_positions
            
            self.log(logging.INFO, f"Target portfolio: {num_target_positions} stocks, ${target_value_per_position:,.2f} per position.")
            
            moo_orders_placed = []
            
            # Calculate rebalancing for existing positions
            for pos in current_positions:
                symbol, current_value, current_price = pos.contract.symbol, pos.marketValue, pos.marketPrice
                
                if current_price <= 0:
                    self.log(logging.WARNING, f"Invalid price for {symbol}. Skipping.")
                    continue
                
                value_diff = target_value_per_position - current_value
                if abs(value_diff) / target_value_per_position < 0.10:  # 10% tolerance
                    self.log(logging.INFO, f"{symbol} within tolerance. No trade needed.")
                    continue
                
                num_shares = int(abs(value_diff) / current_price)
                action = "BUY" if value_diff > 0 else "SELL"
                
                if num_shares > 0:
                    contract = Stock(symbol, 'SMART', 'USD')
                    order = Order(
                        action=action,
                        totalQuantity=num_shares,
                        orderType='MKT',  # Market order - executes at open when placed pre-market
                        tif='DAY',
                        outsideRth=True,
                        transmit=True
                    )
                    trade = ib.placeOrder(contract, order)
                    ib.sleep(1)  # Wait for order status
                    
                    # Check if order was rejected
                    if trade.orderStatus.status == 'Cancelled' or 'Error' in str(trade.log):
                        self.log(logging.ERROR, f"❌ Pre-market order rejected for {symbol}: {trade.log[-1].message if trade.log else 'Unknown error'}")
                        return {"status": "MOO_REJECTED", "reason": "IBKR rejected pre-market order", "moo_orders": []}
                    
                    self.log(logging.INFO, f"📋 Placed pre-market order: {action} {num_shares} {symbol} (executes at 9:30 AM open)")
                    moo_orders_placed.append(f"{action} {num_shares} {symbol} (MKT@open)")
            
            # Place MOO order for new ticker
            if new_ticker not in [pos.contract.symbol for pos in current_positions]:
                self.log(logging.INFO, f"Calculating MOO order for new stock: {new_ticker}")
                new_contract = Stock(new_ticker, 'SMART', 'USD')
                ticker_data = ib.reqMktData(new_contract, '', True, False, [])
                ib.sleep(2)
                
                price_estimate = ticker_data.close  # Use last close price for estimation
                if pd.notna(price_estimate) and price_estimate > 0:
                    quantity = int(target_value_per_position / price_estimate)
                    
                    if quantity > 0:
                        order = Order(
                            action='BUY',
                            totalQuantity=quantity,
                            orderType='MKT',  # Market order - executes at open when placed pre-market
                            tif='DAY',
                            outsideRth=True,
                            transmit=True
                        )
                        trade = ib.placeOrder(new_contract, order)
                        ib.sleep(1)  # Wait for order status
                        
                        # Check if order was rejected
                        if trade.orderStatus.status == 'Cancelled' or 'Error' in str(trade.log):
                            self.log(logging.ERROR, f"❌ Pre-market order rejected for {new_ticker}: {trade.log[-1].message if trade.log else 'Unknown error'}")
                            return {"status": "MOO_REJECTED", "reason": "IBKR rejected pre-market order", "moo_orders": []}
                        
                        self.log(logging.INFO, f"📋 Placed pre-market order: BUY {quantity} {new_ticker} (executes at 9:30 AM open)")
                        moo_orders_placed.append(f"BUY {quantity} {new_ticker} (MKT@open)")
                        
                        # Add position tracking with estimated entry price
                        # Will be updated with actual fill price when market opens
                        pos_data = self.position_tracker.add_position(new_ticker, price_estimate, quantity)
                        self.log(logging.INFO, f"📊 Position tracking started for {new_ticker}: Estimated entry=${price_estimate:.2f}, Stop=${pos_data['stop_loss_price']:.2f} (-10%)")
                else:
                    self.log(logging.ERROR, f"Could not estimate price for {new_ticker}. Skipping MOO order.")
            
            if not moo_orders_placed:
                self.log(logging.INFO, "Portfolio already balanced. No pre-market orders needed.")
                return {"status": "SUCCESS", "reason": "Already balanced.", "moo_orders": []}
            
            self.log(logging.INFO, f"✅ Placed {len(moo_orders_placed)} pre-market orders. They will execute at market open (9:30 AM ET).")
            self.log(logging.INFO, "📊 Position tracking will be updated with actual fill prices after market open.")
            return {"status": "SUCCESS_MOO", "moo_orders": moo_orders_placed}
        
        except Exception as e:
            self.log(logging.CRITICAL, f"Failed to place pre-market orders: {e}", exc_info=True)
            return {"status": "FAILURE", "reason": str(e), "moo_orders": []}
        finally:
            if ib.isConnected():
                ib.disconnect()

    def _execute_rebalance(self, recommendation):
        ib = IB()
        try:
            self.log(logging.INFO, "Connecting to IBKR for portfolio rebalancing...")
            ib.connect(IB_HOST, IB_PORT, clientId=1)
            ib.reqMarketDataType(3) # 1=Live, 2=Frozen, 3=Delayed, 4=Delayed/Frozen
            self.log(logging.INFO, "Set market data type to Delayed (3).")
            
            account_summary = ib.accountSummary()
            portfolio_value_data = next((v for v in account_summary if v.tag == 'NetLiquidation' and v.currency == 'USD'), None)
            
            if not portfolio_value_data:
                self.log(logging.ERROR, "Could not determine Net Liquidation from IBKR.")
                return {"status": "FAILURE", "reason": "NetLiquidation not found."}

            total_portfolio_value = float(portfolio_value_data.value)
            current_positions = ib.portfolio()
            self.log(logging.INFO, f"Total Portfolio Value: ${total_portfolio_value:,.2f}")
            self.log(logging.INFO, f"Found {len(current_positions)} existing positions.")

            target_portfolio_symbols = {pos.contract.symbol for pos in current_positions}
            new_ticker = recommendation['ticker']
            
            # CHECK POSITION LIMIT BEFORE ADDING NEW POSITION
            if new_ticker not in target_portfolio_symbols:
                if len(current_positions) >= MAX_POSITIONS:
                    self.log(logging.WARNING, f"🚫 POSITION LIMIT REACHED: Already have {len(current_positions)} positions (max: {MAX_POSITIONS}). Cannot add {new_ticker}.")
                    self.log(logging.INFO, f"Recommendation for {new_ticker} will be skipped. Consider selling a position first.")
                    return {"status": "LIMIT_REACHED", "reason": f"Max {MAX_POSITIONS} positions already held."}
            
            target_portfolio_symbols.add(new_ticker)
            
            num_target_positions = len(target_portfolio_symbols)
            if num_target_positions == 0:
                self.log(logging.WARNING, "No target positions to rebalance.")
                return {"status": "SUCCESS", "reason": "No positions to rebalance."}

            target_value_per_position = total_portfolio_value / num_target_positions
            self.log(logging.INFO, f"Target portfolio: {num_target_positions} stocks, each with a target value of ${target_value_per_position:,.2f}.")

            trades_to_make = []
            
            for pos in current_positions:
                symbol, current_value, current_price = pos.contract.symbol, pos.marketValue, pos.marketPrice
                self.log(logging.INFO, f"Evaluating existing position: {symbol}, Value: ${current_value:,.2f}, Price: ${current_price:,.2f}")

                if current_price <= 0:
                    self.log(logging.WARNING, f"Market price for {symbol} is invalid ({current_price}). Skipping rebalance for this stock.")
                    continue

                value_diff = target_value_per_position - current_value
                if abs(value_diff) / target_value_per_position < 0.10: # 10% tolerance
                    self.log(logging.INFO, f"Position {symbol} is within 10% tolerance. No trade needed.")
                    continue

                num_shares_to_trade = abs(value_diff) / current_price
                action = "BUY" if value_diff > 0 else "SELL"
                if num_shares_to_trade > 0:
                    trades_to_make.append({"action": action, "ticker": symbol, "quantity": int(num_shares_to_trade)})

            if new_ticker not in [pos.contract.symbol for pos in current_positions]:
                self.log(logging.INFO, f"Fetching market price for new stock: {new_ticker}")
                new_stock_contract = Stock(new_ticker, 'SMART', 'USD')
                ticker_data = ib.reqMktData(new_stock_contract, '', True, False, [])
                ib.sleep(2)

                new_stock_price = ticker_data.marketPrice()
                if pd.notna(new_stock_price) and new_stock_price > 0:
                    self.log(logging.INFO, f"Market price for {new_ticker} is ${new_stock_price:,.2f}")
                    quantity_to_buy = int(target_value_per_position / new_stock_price)
                    if quantity_to_buy > 0:
                        trades_to_make.append({
                            "action": "BUY", 
                            "ticker": new_ticker, 
                            "quantity": quantity_to_buy,
                            "price": new_stock_price  # Store price for position tracking
                        })
                else:
                    self.log(logging.ERROR, f"Could not get valid market price for {new_ticker}. Skipping trade.")

            if not trades_to_make:
                self.log(logging.INFO, "Portfolio is already balanced. No trades needed.")
                return {"status": "SUCCESS", "reason": "Portfolio already balanced."}

            self.log(logging.INFO, f"Rebalancing plan: {trades_to_make}")
            
            executed_trades_info = []
            for trade_order in trades_to_make:
                contract = Stock(trade_order['ticker'], 'SMART', 'USD')
                order = Order(
                    action=trade_order['action'], 
                    totalQuantity=trade_order['quantity'], 
                    orderType='MKT',
                    outsideRth=True  # Allow filling outside regular trading hours
                )
                trade = ib.placeOrder(contract, order)
                self.log(logging.INFO, f"Placed {trade_order['action']} order for {trade_order['quantity']} of {trade_order['ticker']} (eligible for after-hours).")
                
                # ADD POSITION TRACKING FOR NEW BUYS
                if trade_order['action'] == 'BUY' and 'price' in trade_order:
                    entry_price = trade_order['price']
                    quantity = trade_order['quantity']
                    ticker = trade_order['ticker']
                    
                    pos_data = self.position_tracker.add_position(ticker, entry_price, quantity)
                    self.log(logging.INFO, f"📊 Position tracking started for {ticker}: Entry=${entry_price:.2f}, Stop=${pos_data['stop_loss_price']:.2f} (-10%)")
                
                executed_trades_info.append(f"{trade_order['action']} {trade_order['quantity']} {trade_order['ticker']}")
            
            self.log(logging.INFO, "Waiting for trades to settle...")
            ib.sleep(15) 

            return {"status": "SUCCESS_REBALANCE", "executed_trades": executed_trades_info}

        except Exception as e:
            self.log(logging.CRITICAL, f"Failed to execute rebalancing via IBKR: {e}", exc_info=True)
            return {"status": "FAILURE", "reason": str(e)}
        finally:
            if ib.isConnected():
                self.log(logging.INFO, "Disconnecting from Interactive Brokers.")
                ib.disconnect()

# --- Agent 4: Monitoring ---
class MonitoringAgent(BaseAgent):
    """
    Observes the system's performance by analyzing the final log file.
    """
    def execute(self):
        self.log(logging.INFO, "--- [PHASE 4] Starting observation. ---")
        
        try:
            with open(MASTER_LOG_FILE, 'r') as f:
                log_entries = [json.loads(line) for line in f]
            
            critical_errors = [entry for entry in log_entries if entry['level'] == 'CRITICAL']
            trade_executions = [entry for entry in log_entries if entry['agent'] == 'PortfolioManager' and 'trade' in entry['message']]

            if critical_errors:
                self.log(logging.ERROR, f"Monitoring Analysis: Found {len(critical_errors)} critical error(s) in the run.")
            else:
                self.log(logging.INFO, "Monitoring Analysis: No critical errors found.")

            if trade_executions:
                self.log(logging.INFO, f"Monitoring Analysis: Found {len(trade_executions)} trade-related log entries.")
            else:
                self.log(logging.INFO, "Monitoring Analysis: No trade executions were logged.")

        except Exception as e:
            self.log(logging.ERROR, f"Failed to analyze log file: {e}")
            
        self.log(logging.INFO, "--- Finished observation. ---")

# --- Orchestrator Class ---
class Orchestrator:
    """
    Manages the overall workflow, executing agents in the correct sequence.
    """
    def __init__(self, force_online_llms=False, skip_to_portfolio=False, rerun_analysis=False, skip_aggregation=False, run_days=None, interval_minutes=60):
        self.logger = setup_logging()
        self.force_online_llms = force_online_llms
        self.skip_to_portfolio = skip_to_portfolio
        self.rerun_analysis = rerun_analysis
        self.skip_aggregation = skip_aggregation
        self.run_days = [day.capitalize() for day in run_days] if run_days else []
        self.interval_seconds = interval_minutes * 60
        self.agents = {
            "DataAggregator": DataAggregatorAgent(self, "DataAggregator"),
            "Analyst": AnalystAgent(self, "Analyst"),
            "PortfolioManager": PortfolioManagerAgent(self, "PortfolioManager"),
            "Monitoring": MonitoringAgent(self, "Monitoring")
        }
        self._halt_flag = False
        self.log_adapter = logging.LoggerAdapter(self.logger, {'agent': 'Orchestrator'})
        self.log(logging.INFO, f"Orchestrator initialized for run ID: {RUN_ID}.")
        if self.force_online_llms:
            self.log(logging.INFO, "Command-line override: Forcing online LLMs for this run.")
        if self.skip_to_portfolio:
            self.log(logging.INFO, "Command-line override: Skipping to Portfolio Manager phase.")
        if self.rerun_analysis:
            self.log(logging.INFO, "Command-line override: Re-running analysis from saved results.")
        if self.skip_aggregation:
            self.log(logging.INFO, "Command-line override: Skipping online data aggregation.")
        if self.run_days:
            self.log(logging.INFO, f"Scheduled mode enabled. Bot will run on: {', '.join(self.run_days)}.")
            self.log(logging.INFO, f"Checking schedule every {interval_minutes} minutes.")

    def log(self, level, message, **kwargs):
        self.log_adapter.log(level, message, **kwargs)

    def halt_cycle(self):
        self._halt_flag = True
        self.log(logging.WARNING, "Halt flag set. Current cycle will stop after the current agent.")

    def read_from_queue(self) -> dict:
        try:
            with open(TRADING_QUEUE_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.log(logging.ERROR, "Could not read from trading queue file.")
            return {}

    def write_to_queue(self, data: dict):
        try:
            with open(TRADING_QUEUE_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            self.log(logging.INFO, f"Successfully wrote phase '{data.get('phase')}' to queue.")
        except Exception as e:
            self.log(logging.ERROR, f"Failed to write to trading queue: {e}")

    def run_full_cycle(self):
        self.log(logging.INFO, "==================================================")
        self.log(logging.INFO, "=== Starting New Autonomous Trading Cycle... ===")
        self.log(logging.INFO, "==================================================")
        self._halt_flag = False
        
        try:
            if self.skip_to_portfolio:
                self.log(logging.INFO, "Skipping Data Aggregation and Analysis phases as requested.")
            elif self.rerun_analysis:
                self.log(logging.INFO, "Skipping Data Aggregation and running analysis from file.")
            else:
                if not self._halt_flag: self.agents["DataAggregator"].execute()

            if not self._halt_flag: self.agents["Analyst"].execute()
            
            if not self._halt_flag: self.agents["PortfolioManager"].execute()
            
            if self._halt_flag:
                 self.log(logging.ERROR, "=== Trading Cycle Halted Due to an Error. ===")
            else:
                 self.log(logging.INFO, "=== Full Trading Cycle Finished Successfully. ===")

        except Exception as e:
            self.log(logging.CRITICAL, f"A critical unhandled error occurred during the cycle: {e}", exc_info=True)
        
        finally:
            self.agents["Monitoring"].execute()
            # The sleep logic is now handled by the start() method.
            # self.log(logging.INFO, f"Waiting for {self.interval_seconds // 60} minutes before next cycle.")
            self.log(logging.INFO, "==================================================\n")

    def start(self):
        """Starts the orchestrator's execution loop."""
        if self.run_days:
            # Continuous scheduled mode with position monitoring
            self.log(logging.INFO, "Starting in continuous scheduled mode with position monitoring.")
            analysis_done_today = False
            moo_fills_updated = False  # Track if we've updated MOO fill prices today
            
            while True:
                today_name = datetime.now().strftime('%A')
                market_open = is_market_open()
                
                # Run full analysis cycle once per day on scheduled days
                if today_name in self.run_days and not analysis_done_today:
                    self.log(logging.INFO, f"Today is {today_name}, which is a scheduled run day. Starting full cycle.")
                    self.run_full_cycle()
                    analysis_done_today = True
                    moo_fills_updated = False  # Reset flag for new day
                    self.log(logging.INFO, f"Full cycle finished. Now monitoring positions every {self.interval_seconds // 60} minutes.")
                
                # Reset flags at midnight
                elif today_name not in self.run_days:
                    analysis_done_today = False
                    moo_fills_updated = False
                
                # Monitor positions and check stops every interval (regardless of analysis)
                if market_open:
                    # Update MOO fill prices once after market opens
                    if not moo_fills_updated and analysis_done_today:
                        self.agents["PortfolioManager"]._update_moo_fill_prices()
                        moo_fills_updated = True
                    
                    self.log(logging.INFO, f"🔍 Position monitoring check at {datetime.now().strftime('%I:%M %p ET')}")
                    self.agents["PortfolioManager"]._check_stops_and_exits()
                else:
                    self.log(logging.INFO, f"Market closed. Waiting {self.interval_seconds // 60} minutes before next check.")
                
                time.sleep(self.interval_seconds)
        else:
            # On-demand, single-run mode
            self.log(logging.INFO, "Starting in on-demand mode for a single run.")
            self.run_full_cycle()
            self.log(logging.INFO, "Single run complete. Exiting.")

def main():
    """Main entry point to start the orchestrator."""
    parser = argparse.ArgumentParser(description="Autonomous Multi-Agent Trading Bot")
    parser.add_argument(
        '--force-online',
        action='store_true',
        help="If set, forces the use of online LLMs (DeepSeek/Gemini) regardless of market hours."
    )
    parser.add_argument(
        '--rerun-analysis',
        action='store_true',
        help="If set, skips data aggregation and re-runs the analysis from the last saved full results."
    )
    parser.add_argument(
        '--skip-aggregation',
        action='store_true',
        help="If set, skips the online data aggregation and loads data from full_market_data.json."
    )
    parser.add_argument(
        '--skip-to-portfolio',
        action='store_true',
        help="If set, skips the Data Aggregation and Analyst phases and runs the Portfolio Manager directly."
    )
    parser.add_argument(
        '--run-days',
        nargs='+',
        choices=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        default=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],  # Default: Run on weekdays
        help="Enables scheduled mode. Runs the bot only on the specified days. Default: Monday-Friday. Example: --run-days Monday Thursday"
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=15,
        help="The interval in minutes between position monitoring checks in scheduled mode. Default is 15 minutes."
    )
    parser.add_argument(
        '--single-run',
        action='store_true',
        help="If set, runs once and exits (disables continuous monitoring mode)."
    )
    args = parser.parse_args()

    # If --single-run is specified, disable continuous mode
    run_days = None if args.single_run else args.run_days
    
    orchestrator = Orchestrator(
        force_online_llms=args.force_online, 
        skip_to_portfolio=args.skip_to_portfolio,
        rerun_analysis=args.rerun_analysis,
        skip_aggregation=args.skip_aggregation,
        run_days=run_days,
        interval_minutes=args.interval
    )
    orchestrator.start()

if __name__ == "__main__":
    main()
