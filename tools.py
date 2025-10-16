"""
tools.py

This module consolidates the core functionalities of the trading bot into a set of
tools that can be used by LangChain agents. Each function is designed to be a
standalone capability that an agent can invoke.
"""

from typing import Union
import os
import json
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_google_vertexai import ChatVertexAI
from langchain_deepseek import ChatDeepSeek
from polygon import RESTClient

from ib_insync import IB, Stock, Order
import monte_carlo_filter as mc
from market_hours import is_market_open

# --- Setup and Configuration ---
load_dotenv()
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
polygon_client = RESTClient(POLYGON_API_KEY)

# --- Tool Definitions ---

def get_stock_data_tool(ticker: str) -> dict:
    """
    Fetches and aggregates fundamental data, news, and price action for a given stock ticker
    from Polygon.io. Returns a dictionary of the aggregated data.
    This tool is used by the Data Aggregator Agent.
    It is designed to be resilient: if financial data is unavailable, it will log a warning
    and return the available data with financial fields set to 0.
    """
    logging.info(f"[DataTool] Fetching data for {ticker}...")
    stock_data = {
        "ticker": ticker,
        "market_cap": 0,
        "revenue": 0,
        "net_income": 0,
        "news": [],
        "error": None
    }

    try:
        # 1. Fundamental Data (with resilience)
        try:
            financials = list(polygon_client.vx.list_stock_financials(ticker, limit=1))
            if financials:
                income_statement = financials[0].financials.income_statement
                balance_sheet = financials[0].financials.balance_sheet
                
                if income_statement and income_statement.revenues:
                    stock_data["revenue"] = income_statement.revenues.value
                if income_statement and income_statement.net_income_loss:
                    stock_data["net_income"] = income_statement.net_income_loss.value
            else:
                logging.warning(f"[DataTool] Could not retrieve financials for {ticker}. Continuing without it.")
                stock_data["error"] = "Financials not found."
        except Exception as e:
            logging.warning(f"[DataTool] Error fetching financials for {ticker}: {e}. Continuing without it.")
            stock_data["error"] = f"Financials retrieval failed: {e}"

        details = polygon_client.get_ticker_details(ticker)
        if hasattr(details, 'market_cap'):
            stock_data["market_cap"] = details.market_cap
        
        # 2. Recent News
        today = datetime.now()
        ninety_days_ago = today - timedelta(days=90)
        news_resp = polygon_client.list_ticker_news(
            ticker, 
            published_utc_gte=ninety_days_ago.strftime('%Y-%m-%d'),
            limit=20 # Limit news to a manageable number
        )
        stock_data["news"] = [f"{n.title}" for n in news_resp]

        logging.info(f"[DataTool] Successfully aggregated data for {ticker} (Financials found: {stock_data['error'] is None}).")
        return stock_data
    except Exception as e:
        logging.error(f"[DataTool] A critical error occurred while aggregating data for {ticker}: {e}")
        stock_data["error"] = f"Critical error in data aggregation: {e}"
        return stock_data

def get_llm_analysis_tool(stock_data: Union[dict, str]) -> dict:
    """
    Performs analysis on a stock's data using the best available LLM.
    It dynamically switches between DeepSeek, Gemini (VertexAI), and a local Ollama
    model based on market hours and API availability.
    This tool is used by the Analyst Agent.
    It is robust to receiving either a dictionary or a JSON string as input.
    """
    # --- Input Validation and Parsing ---
    if isinstance(stock_data, str):
        try:
            # The agent sometimes passes a JSON string representation of the dictionary.
            stock_data = json.loads(stock_data)
        except json.JSONDecodeError:
            logging.error(f"[AnalystTool] Failed to decode JSON string: {stock_data}")
            return {"decision": "ERROR", "reasoning": "Invalid JSON format received."}

    # If the agent wraps the data in a key, extract it.
    if 'stock_data' in stock_data and isinstance(stock_data['stock_data'], dict):
        stock_data = stock_data['stock_data']

    ticker = stock_data.get("ticker", "Unknown")
    logging.info(f"[AnalystTool] Starting analysis for {ticker}...")
    
    # Define the prompt
    prompt = f"""
    Rules: Market Cap must be between $300M and $10B.
    The stock must have recent news. A stock with no news is not interesting.
    Analyze the sentiment of the news.
    Look at the 30-day and 90-day price change.
    Consider the debt-to-equity ratio.
    
    Based on this comprehensive analysis, decide if the stock is a 'BUY' or 'HOLD'.
    Provide a confidence score between 0.0 and 1.0 for your decision.
    Explain your reasoning in detail, referencing the data points you used.

    Data: {json.dumps(stock_data, indent=2)}

    Return ONLY a JSON object with "decision", "confidence_score" (0.0-1.0), and "reasoning".
    Do not include any other text or formatting.
    Example:
    {{
      "decision": "BUY",
      "confidence_score": 0.85,
      "reasoning": "The company has strong fundamentals, positive news sentiment, and recent price momentum."
    }}
    """

    # Dynamic Model Switching Logic
    if is_market_open():
        logging.info(f"[AnalystTool] Market is OPEN. Using online models for {ticker}. Primary: DeepSeek, Fallback: Gemini.")
        # 1. Try DeepSeek
        try:
            logging.info(f"[AnalystTool] Attempting analysis with DeepSeek for {ticker}...")
            deepseek_llm = ChatDeepSeek(
                model="deepseek-reasoner", 
                api_key=DEEPSEEK_API_KEY
            )
            response = deepseek_llm.invoke(prompt)
            analysis = json.loads(response.content)
            analysis['model'] = 'DeepSeek'
            logging.info(f"[AnalystTool] DeepSeek analysis successful for {ticker}.")
            return analysis
        except Exception as e:
            logging.warning(f"[AnalystTool] DeepSeek failed for {ticker}: {e}. Falling back to Gemini.")
            # 2. Fallback to Gemini (VertexAI)
            try:
                logging.info(f"[AnalystTool] Attempting analysis with Gemini for {ticker}...")
                gemini_llm = ChatVertexAI(model_name="gemini-2.5-flash")
                response = gemini_llm.invoke(prompt)
                analysis = json.loads(response.content)
                analysis['model'] = 'Gemini'
                logging.info(f"[AnalystTool] Gemini analysis successful for {ticker}.")
                return analysis
            except Exception as e2:
                logging.error(f"[AnalystTool] Gemini also failed for {ticker}: {e2}. Falling back to Ollama.")
                # 3. Final fallback to Ollama
                try:
                    logging.info(f"[AnalystTool] Attempting analysis with Ollama for {ticker}...")
                    ollama_llm = ChatOllama(model="llama3.1:8b")
                    response = ollama_llm.invoke(prompt)
                    # It's possible the response is already a dict, or a string
                    if isinstance(response.content, str):
                        analysis = json.loads(response.content)
                    else:
                        analysis = response.content # Assume it's a dict
                    analysis['model'] = 'Ollama'
                    logging.info(f"[AnalystTool] Ollama fallback analysis successful for {ticker}.")
                    return analysis
                except json.JSONDecodeError as json_err:
                    logging.error(f"[AnalystTool] Ollama response was not valid JSON for {ticker}: {json_err}. Response: {response.content}")
                    return {"decision": "ERROR", "reasoning": f"Ollama fallback failed to produce valid JSON. Content: {response.content}"}
                except Exception as e3:
                    logging.critical(f"[AnalystTool] All models failed for {ticker}: {e3}")
                    return {"decision": "ERROR", "reasoning": "All LLM providers failed."}
    else:
        logging.info(f"[AnalystTool] Market is CLOSED. Using local Ollama model for {ticker}.")
        try:
            ollama_llm = ChatOllama(model="llama3.1:8b")
            response = ollama_llm.invoke(prompt)
            if isinstance(response.content, str):
                analysis = json.loads(response.content)
            else:
                analysis = response.content # Assume it's a dict
            analysis['model'] = 'Ollama'
            logging.info(f"[AnalystTool] Ollama offline analysis successful for {ticker}.")
            return analysis
        except json.JSONDecodeError as json_err:
            logging.error(f"[AnalystTool] Ollama offline analysis failed for {ticker}: {json_err}. Response: {response.content}")
            return {"decision": "ERROR", "reasoning": f"Ollama failed to produce valid JSON. Content: {response.content}"}
        except Exception as e:
            logging.error(f"[AnalystTool] Ollama offline analysis failed for {ticker}: {e}")
            return {"decision": "ERROR", "reasoning": f"Ollama offline analysis failed: {e}"}
            return {"decision": "ERROR", "reasoning": "Local Ollama model failed."}

def run_monte_carlo_tool(buy_recommendations: list) -> dict:
    """
    Takes a list of 'BUY' recommendations from the Analyst Agent and runs a Monte Carlo
    simulation to determine the single best stock to trade based on risk-adjusted returns.
    Returns the top-ranked stock.
    This tool is used by the Analyst Agent.
    """
    logging.info(f"[AnalystTool] Running Monte Carlo filter on {len(buy_recommendations)} stocks.")
    if not buy_recommendations:
        return {"error": "No buy recommendations provided."}
        
    # The monte_carlo_filter expects a list of dictionaries
    ranked_stocks = mc.run_monte_carlo_filter(buy_recommendations)
    
    if not ranked_stocks:
        logging.warning("[AnalystTool] Monte Carlo simulation did not return any ranked stocks.")
        return {"error": "Monte Carlo simulation failed to produce a ranking."}
        
    top_stock = ranked_stocks[0]
    logging.info(f"[AnalystTool] Monte Carlo top pick: {top_stock.get('ticker')}")
    return top_stock

# --- Portfolio Manager Tools (IBKR Interaction) ---

# This is a placeholder for a secure way to manage the IB connection.
# In a real system, this would be a singleton or a connection pool.
_ib_connection = None

def get_ib_connection():
    """Helper to manage a single IB connection."""
    global _ib_connection
    if _ib_connection and _ib_connection.isConnected():
        return _ib_connection
    
    try:
        _ib_connection = IB()
        _ib_connection.connect('127.0.0.1', 4001, clientId=1)
        logging.info("Successfully connected to Interactive Brokers.")
        return _ib_connection
    except Exception as e:
        logging.critical(f"Failed to connect to Interactive Brokers: {e}")
        return None

def execute_trade_tool(ticker: str, action: str, quantity: int = 1) -> dict:
    """
    Executes a trade (BUY or SELL) for a given stock ticker through Interactive Brokers.
    This is a critical tool only available to the Portfolio Manager Agent.
    """
    ib = get_ib_connection()
    if not ib:
        return {"status": "FAILED", "reason": "No connection to Interactive Brokers."}

    if action.upper() not in ["BUY", "SELL"]:
        return {"status": "FAILED", "reason": "Invalid action. Must be BUY or SELL."}

    try:
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        order = Order()
        order.action = action.upper()
        order.orderType = "MKT"
        order.totalQuantity = quantity
        
        trade = ib.placeOrder(contract, order)
        logging.info(f"Placing order: {action} {quantity} {ticker}")
        
        # Basic wait for the order to be processed
        ib.sleep(2) 
        
        if trade.orderStatus.status == 'Filled':
            return {"status": "SUCCESS", "ticker": ticker, "action": action, "quantity": quantity, "fill_price": trade.orderStatus.avgFillPrice}
        else:
            return {"status": "SUBMITTED", "ticker": ticker, "action": action, "order_status": trade.orderStatus.status}

    except Exception as e:
        logging.error(f"Failed to execute trade for {ticker}: {e}")
        return {"status": "FAILED", "reason": str(e)}

def get_portfolio_status_tool() -> dict:
    """
    Retrieves the current portfolio status from Interactive Brokers, including positions
    and account values.
    This tool is only available to the Portfolio Manager Agent.
    """
    ib = get_ib_connection()
    if not ib:
        return {"error": "No connection to Interactive Brokers."}
        
    try:
        portfolio = ib.portfolio()
        positions = [
            {
                "ticker": pos.contract.symbol,
                "position": pos.position,
                "market_price": pos.marketPrice,
                "market_value": pos.marketValue,
                "average_cost": pos.averageCost,
            }
            for pos in portfolio
        ]
        
        account_summary = ib.accountSummary()
        net_liquidation = next((v.value for v in account_summary if v.tag == 'NetLiquidation'), 'N/A')

        return {"net_liquidation": net_liquidation, "positions": positions}
    except Exception as e:
        logging.error(f"Failed to get portfolio status: {e}")
        return {"error": str(e)}

