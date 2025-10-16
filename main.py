"""
main.py

This script is the single, unified entry point for the autonomous multi-agent trading bot.
It orchestrates the entire workflow, from data aggregation to trade execution and monitoring,
by executing a sequence of specialized agents.
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

# --- File & Directory Paths ---
LOG_DIR = "logs"
TRADING_QUEUE_FILE = "trading_queue.json"
FULL_ANALYSIS_FILE = "full_analysis_results.json"
AGGREGATED_DATA_FILE = "full_market_data.json"
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
        
        # 2. Fallback to yfinance
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
        url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit={NEWS_FETCH_LIMIT}&apiKey={POLYGON_API_KEY}"
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                news_items = [{"title": item.get("title", ""), "url": item.get("article_url")} for item in data.get("results", [])]
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
            if res and res.get("decision") == "BUY" and res.get("confidence", 0) > 0.7
        ]
        self.log(logging.INFO, f"Found {len(buy_recommendations)} 'BUY' recommendations with confidence > 0.7.")

        if not buy_recommendations:
            self.log(logging.INFO, "No high-confidence 'BUY' recommendations to process. Ending analysis phase.")
            self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
            return

        self.log(logging.INFO, "Running Monte Carlo simulation to find the top pick...")
        top_pick_ticker = mc.run_monte_carlo_filter(buy_recommendations)
        
        if not top_pick_ticker:
            self.log(logging.ERROR, "Monte Carlo simulation failed to return a top pick.")
            self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
            return
            
        top_pick = next((rec for rec in buy_recommendations if rec['ticker'] == top_pick_ticker[0]), None)

        if not top_pick:
            self.log(logging.ERROR, f"Could not find top pick '{top_pick_ticker[0]}' in recommendations.")
            self.orchestrator.write_to_queue({"phase": "analysis_complete", "recommendations": []})
            return

        self.log(logging.INFO, f"Top pick from Monte Carlo is: {top_pick['ticker']}")
        self.orchestrator.write_to_queue({
            "phase": "analysis_complete",
            "recommendation": top_pick
        })
        self.log(logging.INFO, "--- Finished. Top recommendation sent to queue. ---")

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
        Analyze the following stock data. The market cap must be between $50M and $350M.
        The stock must have recent, positive news.
        Based on this, decide if the stock is a 'BUY' or 'HOLD'.
        Provide a confidence score (0.0-1.0) and detailed reasoning.

        Data: {json.dumps(stock_data, indent=2)}

        Return ONLY a JSON object with "ticker", "decision", "confidence", and "reasoning".
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

# --- Agent 3: Portfolio Manager ---
class PortfolioManagerAgent(BaseAgent):
    """
    Executes trades based on the Analyst's final recommendation,
    focusing on rebalancing the entire portfolio.
    """
    def execute(self):
        self.log(logging.INFO, "--- [PHASE 3] Starting trade execution. ---")
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

        if not is_market_open():
            self.log(logging.WARNING, "Market is currently closed. Trade execution will be deferred to the next run during market hours.")
            self.orchestrator.write_to_queue({"phase": "execution_deferred", "reason": "Market closed"})
            return

        self.log(logging.INFO, f"Received 'BUY' recommendation for {recommendation['ticker']}. Initiating portfolio rebalance.")
        
        trade_result = self._execute_rebalance(recommendation)
        
        self.log(logging.INFO, f"Rebalancing result: {trade_result.get('status', 'UNKNOWN')}")
        
        self.orchestrator.write_to_queue({
            "phase": "execution_complete",
            "executed_trades": trade_result if trade_result.get('status') != "FAILURE" else []
        })
        self.log(logging.INFO, f"--- Finished. Rebalancing for {recommendation['ticker']} processed. ---")

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
                        trades_to_make.append({"action": "BUY", "ticker": new_ticker, "quantity": quantity_to_buy})
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
            # Continuous scheduled mode
            self.log(logging.INFO, "Starting in continuous scheduled mode.")
            while True:
                today_name = datetime.now().strftime('%A')
                if today_name in self.run_days:
                    self.log(logging.INFO, f"Today is {today_name}, which is a scheduled run day. Starting cycle.")
                    self.run_full_cycle()
                    self.log(logging.INFO, f"Cycle finished. Sleeping for {self.interval_seconds // 60} minutes.")
                else:
                    self.log(logging.INFO, f"Today is {today_name}, not a scheduled run day. Sleeping.")
                
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
        help="Enables scheduled mode. Runs the bot only on the specified days. Example: --run-days Monday Thursday"
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help="The interval in minutes to wait between cycles in scheduled mode. Default is 60."
    )
    args = parser.parse_args()

    orchestrator = Orchestrator(
        force_online_llms=args.force_online, 
        skip_to_portfolio=args.skip_to_portfolio,
        rerun_analysis=args.rerun_analysis,
        skip_aggregation=args.skip_aggregation,
        run_days=args.run_days,
        interval_minutes=args.interval
    )
    orchestrator.start()

if __name__ == "__main__":
    main()
