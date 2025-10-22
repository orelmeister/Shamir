# Trading Bot Agent Instructions

This document outlines the specific instructions and configurations for the AI agent working on this trading bot.

## Language Models

For the pre-market analysis, the following models must be used in this order of priority:

1.  **Primary:** `deepseek-reasoner` (via the DeepSeek API)
2.  **Fallback:** `gemini-2.5-flash` (via the Google Generative AI API)

Do not use local models like Ollama or other versions of Gemini (e.g., `gemini-1.5-flash`) for the pre-market analysis phase unless explicitly instructed to. The goal is to use the fastest and most capable models for timely and accurate information before the market opens.

## Trading Logic & Configuration

- **Confidence Score Threshold**: When generating the pre-market watchlist, only include stocks that receive a `confidence_score` strictly greater than `0.7`. Do not include stocks with a score of `0.7`.
- **Interactive Brokers (IBKR) Port**: For paper trading, the connection to TWS or IB Gateway must use port `4001`.

## Exchange Routing Strategy

The bot uses a **dual-exchange strategy** for optimal performance:

### Ticker Validation (Pre-Market Phase)
- **Method**: Parallel validation using `ThreadPoolExecutor` with 20 workers
- **Exchanges Checked**: `NASDAQ` and `NYSE` (in that priority order)
- **Process**: Each ticker is validated against specific exchanges to ensure it's a tradable stock (`secType == 'STK'`)
- **Output**: The `primaryExchange` for each validated ticker is saved in `day_trading_watchlist.json`
- **Why**: Using specific exchanges prevents ambiguity and ensures we only trade valid, individual stocks (not ETFs or other securities)

### Data Retrieval (Intraday Phase)
- **For Market Data & Historical Bars**: Use the specific `primaryExchange` from the watchlist (e.g., `Stock('AAPL', 'NASDAQ', 'USD')`)
- **Why**: Requesting data from the specific exchange ensures accuracy and reduces errors related to "No security definition found"

### Order Execution (Intraday Phase)
- **For Buy/Sell Orders**: Use `'SMART'` routing (e.g., `Stock('AAPL', 'SMART', 'USD')`)
- **Why**: SMART routing allows Interactive Brokers to find the best available price across all exchanges, ensuring optimal execution

## Parallel Processing

- **Ticker Validation**: Uses up to 20 parallel workers, each with a unique IBKR client ID (starting from 100)
- **LLM Analysis**: Uses up to 10 parallel workers for concurrent stock analysis with DeepSeek/Gemini
