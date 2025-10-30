"""
Main entry point for the Day-Trading Bot.

This bot operates in FIVE phases (optimized October 23, 2025):
0. Data Aggregation (7:00 AM): Collect fresh market data with ATR > 1.0% filter
1. Pre-Market Analysis (7:30 AM): Deep LLM analysis of volatile candidates
1.5. Ticker Validation (8:15 AM): Verify IBKR can trade these stocks
1.75. Pre-Market Momentum (9:00 AM): Analyze which stocks are moving in pre-market
2. Intraday Trading (9:30 AM-4:00 PM): High-speed algorithmic trading

REMOVED Phase 0.5 (ATR Prediction): Was too slow - DeepSeek calls for 27 stocks took forever.
Data aggregator already filters by ATR > 1.0%, so LLM prediction was redundant.
"""

import argparse
import logging
from datetime import datetime, time as dt_time, timedelta
import time
import pytz
import json
import os

from day_trading_agents import (
    DataAggregatorAgent, 
    ATRPredictorAgent,
    WatchlistAnalystAgent, 
    TickerValidatorAgent,
    PreMarketMomentumAgent,
    IntradayTraderAgent
)
from utils import setup_logging, is_market_open
from observability import get_tracer, get_database
# Removed deprecated imports - using observability module now

class DayTraderOrchestrator:
    def __init__(self, allocation, paper_trade=True):
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f"logs/day_trader_run_{run_id}.json"
        self.logger = setup_logging(self.log_file, run_id)
        self.allocation = allocation
        self.paper_trade = paper_trade
        self.log_adapter = logging.LoggerAdapter(self.logger, {'agent': 'Orchestrator'})
        
        # Initialize observability (tracing handled by agents)
        self.database = get_database()
        self.tracer = get_tracer()
        
        self.log(logging.INFO, f"Day Trader Orchestrator initialized with {self.allocation*100}% capital allocation.")
        self.log(logging.INFO, "[OK] Observability system enabled")

    def log(self, level, message, **kwargs):
        self.log_adapter.log(level, message, **kwargs)

    def run_data_aggregation(self):
        """
        Phase 0: Collect fresh market data if needed.
        Skips if data file is already current for today.
        """
        self.log(logging.INFO, "Starting Phase 0: Data Aggregation.")
        
        aggregator_agent = DataAggregatorAgent(self)
        aggregator_agent.run()
        
        self.log(logging.INFO, "Data Aggregation complete.")

    def run_pre_market_analysis(self):
        """
        Phase 1: Run the LLM-based agent to generate the watchlist.
        """
        self.log(logging.INFO, "Starting Phase 1: Pre-Market Analysis.")
        
        watchlist_agent = WatchlistAnalystAgent(self)
        watchlist_agent.run()
        
        self.log(logging.INFO, "Pre-Market Analysis complete. Watchlist generated.")

    def _run_atr_prediction(self):
        """Helper method to run ATR prediction."""
        try:
            with open('full_market_data.json', 'r') as f:
                market_data = json.load(f)
            
            atr_predictor = ATRPredictorAgent(self)
            predicted_stocks = atr_predictor.run(market_data)
            
            # Save predictions for next phase
            with open('atr_predictions.json', 'w') as f:
                json.dump(predicted_stocks, f, indent=2)
            
            self.log(logging.INFO, f"ATR Prediction complete. {len(predicted_stocks)} stocks predicted to have ATR > 1.5%")
            return predicted_stocks
            
        except Exception as e:
            self.log(logging.ERROR, f"ATR Prediction failed: {e}. Proceeding with all stocks.")
            return market_data
    
    def _run_ticker_screener(self):
        """Run the ticker screener to refresh the universe of stocks daily."""
        try:
            import subprocess
            
            # Check if us_tickers.json exists and is from today
            if os.path.exists('us_tickers.json'):
                file_mod_time = datetime.fromtimestamp(os.path.getmtime('us_tickers.json'))
                if file_mod_time.date() == datetime.now().date():
                    with open('us_tickers.json', 'r') as f:
                        tickers = json.load(f)
                    self.log(logging.INFO, f"Ticker universe is fresh for today with {len(tickers)} tickers. Skipping screener.")
                    return
            
            # Run the ticker screener
            self.log(logging.INFO, "Running ticker screener to refresh stock universe...")
            result = subprocess.run(['python', 'ticker_screener_fmp.py'], 
                                  capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                with open('us_tickers.json', 'r') as f:
                    tickers = json.load(f)
                self.log(logging.INFO, f"Ticker screener complete. {len(tickers)} tickers loaded.")
            else:
                self.log(logging.ERROR, f"Ticker screener failed: {result.stderr}")
                
        except Exception as e:
            self.log(logging.ERROR, f"Failed to run ticker screener: {e}")
    
    def _run_ticker_validation(self):
        """Helper method to run ticker validation."""
        try:
            # Load watchlist
            with open('day_trading_watchlist.json', 'r') as f:
                watchlist = json.load(f)
            
            validator = TickerValidatorAgent(self)
            validated_tickers = validator.run(watchlist)
            
            # Save validated tickers
            with open('validated_tickers.json', 'w') as f:
                json.dump(validated_tickers, f, indent=2)
            
            self.log(logging.INFO, f"Validation complete. {len(validated_tickers)} tickers are tradeable.")
            return validated_tickers
            
        except Exception as e:
            self.log(logging.ERROR, f"Validation failed: {e}")
            return []

    def run_intraday_trading(self):
        """
        Phase 2: Run the high-speed algorithmic trading agent.
        """
        self.log(logging.INFO, "Starting Phase 2: Intraday Trading.")
        
        trader_agent = IntradayTraderAgent(self, self.allocation, self.paper_trade)
        trader_agent.run()
        
        self.log(logging.INFO, "Intraday Trading complete. All positions liquidated.")

    def start(self):
        """
        Starts the full day-trading workflow.
        Waits until 8:30 AM ET if started after market hours.
        """
        self.log(logging.INFO, "Starting the day trading bot workflow.")
        
        # Check current time in ET
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        current_time = now_et.time()
        
        # Define trading preparation start time (7:00 AM ET - changed from 8:30 AM)
        prep_start_time = dt_time(7, 0)
        market_close_time = dt_time(16, 0)  # 4:00 PM ET
        
        # If it's after 4 PM today, wait until 7:00 AM tomorrow
        if current_time >= market_close_time:
            # Calculate tomorrow 7:00 AM ET
            tomorrow = now_et.date() + timedelta(days=1)
            target_datetime = et_tz.localize(datetime.combine(tomorrow, prep_start_time))
            
            seconds_until_start = (target_datetime - now_et).total_seconds()
            
            self.log(logging.INFO, f"[CLOCK] Current time: {now_et.strftime('%I:%M:%S %p ET on %B %d, %Y')}")
            self.log(logging.INFO, f"[CLOSED] Market is closed for today (closes at 4:00 PM ET)")
            self.log(logging.INFO, f"[SCHEDULED] Bot will start at: {target_datetime.strftime('%I:%M:%S %p ET on %B %d, %Y')}")
            
            # Show countdown
            hours_until = int(seconds_until_start // 3600)
            minutes_until = int((seconds_until_start % 3600) // 60)
            self.log(logging.INFO, f"[COUNTDOWN] Sleeping for {hours_until} hours and {minutes_until} minutes until 7:00 AM ET tomorrow...")
            self.log(logging.INFO, "[WAITING] The bot will automatically start when it's time. You can leave it running!")
            
            # Sleep with visible countdown updates every 5 seconds
            import sys
            
            while seconds_until_start > 0:
                hours_left = int(seconds_until_start // 3600)
                minutes_left = int((seconds_until_start % 3600) // 60)
                seconds_left = int(seconds_until_start % 60)
                
                # Print countdown on same line (overwrites)
                print(f"\r[COUNTDOWN] {hours_left:02d}h {minutes_left:02d}m {seconds_left:02d}s remaining until 8:30 AM ET...", end='', flush=True)
                
                time.sleep(5)  # Update every 5 seconds
                seconds_until_start -= 5
            
            print()  # New line after countdown finishes
            self.log(logging.INFO, "[MORNING] Good morning! It's 7:00 AM ET - starting the day trading workflow!")
        
        # If it's before 7:00 AM, wait until 7:00 AM today
        elif current_time < prep_start_time:
            today = now_et.date()
            target_datetime = et_tz.localize(datetime.combine(today, prep_start_time))
            seconds_until_start = (target_datetime - now_et).total_seconds()
            
            hours_until = int(seconds_until_start // 3600)
            minutes_until = int((seconds_until_start % 3600) // 60)
            
            self.log(logging.INFO, f"[CLOCK] Current time: {now_et.strftime('%I:%M:%S %p ET')}")
            self.log(logging.INFO, f"[COUNTDOWN] Waiting {hours_until}h {minutes_until}m until 7:00 AM ET to start...")
            time.sleep(seconds_until_start)
            self.log(logging.INFO, "[START] It's 7:00 AM ET - starting workflow!")
        else:
            # Between 7:00 AM and 4:00 PM - start immediately
            self.log(logging.INFO, f"[READY] Current time: {now_et.strftime('%I:%M:%S %p ET')} - starting immediately!")

        # --- Phase -1: Ticker Screening (runs before Phase 0) ---
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "PHASE -1: Ticker Universe Refresh (6:55 AM)")
        self.log(logging.INFO, "=" * 60)
        self._run_ticker_screener()

        # --- Phase 0: Data Aggregation (7:00 AM - with ATR filtering) ---
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "PHASE 0: Data Collection (7:00 AM)")
        self.log(logging.INFO, "=" * 60)
        self.run_data_aggregation()

        # Phase 0.5 is REMOVED - ATR prediction is redundant since data aggregator
        # already filters by ATR > 1.0%. LLM prediction was too slow (27 stocks * DeepSeek calls)
        # and didn't add enough value to justify the time cost.

        # --- Phase 1: Pre-Market Analysis (7:30 AM) ---
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "PHASE 1: LLM Watchlist Analysis (7:30 AM)")
        self.log(logging.INFO, "=" * 60)
        self.run_pre_market_analysis()
        
        # --- Phase 1.5: Ticker Validation (8:15 AM) ---
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "PHASE 1.5: Ticker Validation (8:15 AM)")
        self.log(logging.INFO, "=" * 60)
        
        # Check if validation already done today AND is complete
        validated_path = 'validated_tickers.json'
        if os.path.exists(validated_path):
            val_mtime = datetime.fromtimestamp(os.path.getmtime(validated_path))
            if val_mtime.date() == datetime.now().date():
                try:
                    with open(validated_path, 'r') as f:
                        validated_tickers = json.load(f)
                    # Validation is fresh and has data
                    if len(validated_tickers) > 0:
                        self.log(logging.INFO, f"Ticker validation fresh for today with {len(validated_tickers)} tickers. Using cached validation.")
                    else:
                        # Empty validation, re-run
                        self.log(logging.INFO, "Validation file is empty. Re-running validation.")
                        validated_tickers = self._run_ticker_validation()
                except:
                    # Corrupted file, re-run
                    validated_tickers = self._run_ticker_validation()
            else:
                # Validation is old, re-run
                validated_tickers = self._run_ticker_validation()
        else:
            # No validation file, run validation
            validated_tickers = self._run_ticker_validation()
        
        # Check if we have any tradeable tickers
        if not validated_tickers or len(validated_tickers) == 0:
            self.log(logging.ERROR, "CRITICAL: No tickers passed validation. Cannot proceed with trading.")
            self.log(logging.ERROR, "This usually means:")
            self.log(logging.ERROR, "  1. IBKR connection issue")
            self.log(logging.ERROR, "  2. Tickers not available for trading")
            self.log(logging.ERROR, "  3. Data subscription issue with IBKR")
            self.log(logging.ERROR, "Stopping bot to prevent trading invalid contracts.")
            return
        
        self.log(logging.INFO, f"Validation successful: {len(validated_tickers)} tickers ready for trading.")
        
        # --- Phase 1.75: Dynamic Pre-Market Momentum + MOO Management ---
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "PHASE 1.75: Dynamic Pre-Market Momentum + MOO Management")
        self.log(logging.INFO, "=" * 60)
        
        # CRITICAL: Skip MOO phase if market is already open (restart after 9:30 AM)
        if is_market_open():
            self.log(logging.WARNING, "⚠️  Market is ALREADY OPEN - skipping MOO placement phase!")
            self.log(logging.INFO, "Bot will proceed directly to intraday trading and sync existing positions.")
            # Jump straight to Phase 2
        else:
            self.log(logging.INFO, "Strategy: Run momentum analysis NOW, then every 15 minutes until 9:22 AM")
            self.log(logging.INFO, "MOO orders will be dynamically adjusted based on changing pre-market momentum")
            
            # Initialize intraday agent once (reuse for all MOO operations)
            from day_trading_agents import IntradayTraderAgent
            intraday_agent = IntradayTraderAgent(
                orchestrator=self,
                allocation=self.allocation,
                paper_trade=self.paper_trade
            )
            intraday_agent._connect_to_brokerage()
            
            # Dynamic momentum loop: Run now, then every 15 min until 9:22 AM
            momentum_check_interval = 15 * 60  # 15 minutes in seconds
            final_check_time = dt_time(9, 22)  # Last check at 9:22 AM (6 min before cutoff)
            
            iteration = 0
            while True:
                iteration += 1
                now_et = datetime.now(et_tz)
                current_time = now_et.time()
                
                self.log(logging.INFO, f"\n--- Momentum Check #{iteration} at {now_et.strftime('%I:%M:%S %p ET')} ---")
                
                # Run momentum analysis
                try:
                    momentum_agent = PreMarketMomentumAgent(self)
                    ranked_tickers = momentum_agent.run(validated_tickers)
                    
                    # Save ranked tickers
                    with open('ranked_tickers.json', 'w') as f:
                        json.dump(ranked_tickers, f, indent=2)
                    
                    self.log(logging.INFO, f"Momentum analysis complete. Top 5 stocks: {[t['ticker'] for t in ranked_tickers[:5]]}")
                    
                except Exception as e:
                    self.log(logging.ERROR, f"Momentum analysis failed: {e}. Keeping previous rankings.")
                    # Load previous rankings if they exist
                    try:
                        with open('ranked_tickers.json', 'r') as f:
                            ranked_tickers = json.load(f)
                    except:
                        ranked_tickers = validated_tickers
                
                # Update MOO orders based on latest momentum
                try:
                    intraday_agent._load_watchlist()  # Reload with updated rankings
                    intraday_agent._calculate_capital()
                    
                    # Get current order symbols
                    current_symbols = [moo['symbol'] for moo in intraday_agent.moo_trades] if hasattr(intraday_agent, 'moo_trades') else []
                    
                    # Get new top stocks from updated rankings - FILTER OUT NEGATIVE PRE-MARKET MOVEMENT
                    max_moo_orders = min(5, 4 - len(intraday_agent.positions))
                    
                    # Filter: Only stocks with POSITIVE pre-market movement (>= 0%)
                    filtered_stocks = []
                    for item in intraday_agent.watchlist_data:
                        ticker = item.get('ticker')
                        premarket_change = item.get('premarket_change', 0)  # Default to 0 if missing
                        
                        # Accept stocks with >= 0% pre-market change (positive momentum only)
                        if premarket_change >= 0:
                            filtered_stocks.append(ticker)
                            if len(filtered_stocks) >= max_moo_orders:
                                break
                        else:
                            # Log rejected stocks for visibility
                            self.log(logging.INFO, f"REJECTED {ticker}: Pre-market {premarket_change:+.2f}% (negative momentum)")
                    
                    new_top_stocks = filtered_stocks
                    
                    # Determine which orders to cancel (no longer in top rankings)
                    to_cancel = [symbol for symbol in current_symbols if symbol not in new_top_stocks]
                    to_keep = [symbol for symbol in current_symbols if symbol in new_top_stocks]
                    to_add = [symbol for symbol in new_top_stocks if symbol not in current_symbols]
                    
                    if to_cancel:
                        self.log(logging.INFO, f"Cancelling orders for stocks that dropped in rankings: {', '.join(to_cancel)}")
                        for moo in intraday_agent.moo_trades[:]:  # Copy list to avoid modification during iteration
                            if moo['symbol'] in to_cancel:
                                intraday_agent.ib.cancelOrder(moo['trade'].order)
                                intraday_agent.moo_trades.remove(moo)
                    
                    if to_keep:
                        self.log(logging.INFO, f"Keeping orders for stocks still in top rankings: {', '.join(to_keep)}")
                    
                    if to_add:
                        self.log(logging.INFO, f"Adding new orders for stocks in top rankings (with positive momentum): {', '.join(to_add)}")
                        # Place new MOO orders (will only place for stocks not already ordered)
                        intraday_agent._place_moo_orders()
                    
                    self.log(logging.INFO, f"MOO orders after update: {len(intraday_agent.moo_trades)} orders queued for 9:30 AM")
                    
                    # Log current order symbols
                    if intraday_agent.moo_trades:
                        symbols = [moo['symbol'] for moo in intraday_agent.moo_trades]
                        self.log(logging.INFO, f"Current MOO orders: {', '.join(symbols)}")
                    
                except Exception as e:
                    self.log(logging.ERROR, f"MOO order update failed: {e}")
                
                # Check if this was the final iteration
                if current_time >= final_check_time:
                    self.log(logging.INFO, f"\nFINAL momentum check complete at {now_et.strftime('%I:%M:%S %p ET')}")
                    self.log(logging.INFO, f"MOO orders LOCKED. No more changes until 9:30 AM execution.")
                    break
                
                # Calculate next check time
                next_check = now_et + timedelta(seconds=momentum_check_interval)
                
                # If next check would be after 9:22 AM, schedule final check at 9:22 AM instead
                if next_check.time() > final_check_time:
                    next_check = et_tz.localize(datetime.combine(now_et.date(), final_check_time))
                
                wait_seconds = (next_check - now_et).total_seconds()
                
                if wait_seconds > 0:
                    self.log(logging.INFO, f"Next momentum check at {next_check.strftime('%I:%M:%S %p ET')} ({int(wait_seconds/60)} minutes)")
                    time.sleep(wait_seconds)


        # --- Phase 2: Intraday Trading ---
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "PHASE 2: Intraday Trading (9:30 AM - 3:45 PM)")
        self.log(logging.INFO, "=" * 60)
        
        # Wait for the market to open if it's not already.
        # This loop will run once and exit if the market is open.
        # If the market is closed, it will wait and check every 5 minutes.
        while not is_market_open():
            self.log(logging.INFO, "Market is currently closed. Waiting for market open to begin trading...")
            time.sleep(300) # Wait for 5 minutes before checking again

        # Once the loop exits, the market is open.
        self.log(logging.INFO, "Market is open. Proceeding with intraday trading.")
        self.run_intraday_trading()
        
        # Performance analysis is handled by autonomous system (continuous_improvement.py)
        self.log(logging.INFO, "Day trading bot workflow finished.")

    def run_backtest(self, target_date: str):
        """
        Run backtest mode to analyze what would have happened if we ran the system
        at 7:00 AM on the target date.
        
        Args:
            target_date: Date in YYYY-MM-DD format
        """
        self.log(logging.INFO, "=" * 80)
        self.log(logging.INFO, f"BACKTEST MODE: Analyzing {target_date}")
        self.log(logging.INFO, "=" * 80)
        
        # Parse target date
        from datetime import datetime
        test_date = datetime.strptime(target_date, '%Y-%m-%d')
        
        self.log(logging.INFO, f"Simulating as if we ran the system at 7:00 AM ET on {target_date}")
        self.log(logging.INFO, "This will show what stocks we would have picked and how they performed.")
        
        # Phase 0: Data Collection (simulated at 7:00 AM)
        self.log(logging.INFO, "\n" + "=" * 60)
        self.log(logging.INFO, "PHASE 0: Data Collection (7:00 AM)")
        self.log(logging.INFO, "=" * 60)
        self.log(logging.INFO, "In backtest mode, we'll use actual data from that morning...")
        
        # For now, just run the actual data collection
        # In a full implementation, you'd filter news to only 6-7 AM
        self.run_data_aggregation()
        
        # Phase 0.5: ATR Prediction
        self.log(logging.INFO, "\n" + "=" * 60)
        self.log(logging.INFO, "PHASE 0.5: ATR Prediction (7:15 AM)")
        self.log(logging.INFO, "=" * 60)
        
        try:
            with open('full_market_data.json', 'r') as f:
                market_data = json.load(f)
            
            atr_predictor = ATRPredictorAgent(self)
            predicted_stocks = atr_predictor.run(market_data)
            
            self.log(logging.INFO, f"Predicted {len(predicted_stocks)} stocks would have ATR > 1.5%")
            
        except Exception as e:
            self.log(logging.ERROR, f"ATR Prediction failed: {e}")
            return
        
        # Phase 1: Watchlist Analysis
        self.log(logging.INFO, "\n" + "=" * 60)
        self.log(logging.INFO, "PHASE 1: LLM Watchlist Analysis (7:30 AM)")
        self.log(logging.INFO, "=" * 60)
        
        self.run_pre_market_analysis()
        
        # Phase 1.5: Ticker Validation
        self.log(logging.INFO, "\n" + "=" * 60)
        self.log(logging.INFO, "PHASE 1.5: Ticker Validation (8:15 AM)")
        self.log(logging.INFO, "=" * 60)
        
        try:
            with open('day_trading_watchlist.json', 'r') as f:
                watchlist = json.load(f)
            
            validator = TickerValidatorAgent(self)
            validated_tickers = validator.run(watchlist)
            
            self.log(logging.INFO, f"Validated {len(validated_tickers)} tickers as tradeable")
            
        except Exception as e:
            self.log(logging.ERROR, f"Validation failed: {e}")
            return
        
        # Now analyze actual performance
        self.log(logging.INFO, "\n" + "=" * 80)
        self.log(logging.INFO, "PERFORMANCE ANALYSIS: What actually happened?")
        self.log(logging.INFO, "=" * 80)
        
        self._analyze_backtest_performance(validated_tickers, predicted_stocks, test_date)
        
        self.log(logging.INFO, "\n" + "=" * 80)
        self.log(logging.INFO, "BACKTEST COMPLETE")
        self.log(logging.INFO, "=" * 80)
    
    def _analyze_backtest_performance(self, validated_tickers: list, predictions: list, test_date):
        """Analyze how the predicted stocks actually performed."""
        import yfinance as yf
        import pandas as pd
        
        self.log(logging.INFO, f"\nAnalyzing actual performance of {len(validated_tickers)} validated tickers...")
        
        results = []
        
        for item in validated_tickers[:10]:  # Top 10 only
            ticker = item['ticker'] if isinstance(item, dict) else item
            
            try:
                stock = yf.Ticker(ticker)
                
                # Get intraday data for that day
                hist = stock.history(start=test_date, period="1d", interval="1m")
                
                if hist.empty:
                    self.log(logging.WARNING, f"{ticker}: No intraday data available")
                    continue
                
                # Get open and close
                open_price = hist['Open'].iloc[0]
                high_price = hist['High'].max()
                low_price = hist['Low'].min()
                close_price = hist['Close'].iloc[-1]
                
                # Calculate metrics
                intraday_high_pct = ((high_price - open_price) / open_price) * 100
                intraday_low_pct = ((low_price - open_price) / open_price) * 100
                close_pct = ((close_price - open_price) / open_price) * 100
                
                # Calculate actual ATR
                high_low = hist['High'] - hist['Low']
                high_close = abs(hist['High'] - hist['Close'].shift())
                low_close = abs(hist['Low'] - hist['Close'].shift())
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.mean()
                atr_pct = (atr / open_price) * 100
                
                # Find prediction for this ticker
                pred = next((p for p in predictions if p['ticker'] == ticker), None)
                predicted_atr = pred['predicted_atr'] if pred else 0.0
                
                # Check if would have hit profit target (+1.8%) or stop loss (-0.9%)
                hit_profit = intraday_high_pct >= 1.8
                hit_stop = intraday_low_pct <= -0.9
                
                result = {
                    'ticker': ticker,
                    'open': open_price,
                    'high_pct': intraday_high_pct,
                    'low_pct': intraday_low_pct,
                    'close_pct': close_pct,
                    'actual_atr': atr_pct,
                    'predicted_atr': predicted_atr,
                    'hit_profit': hit_profit,
                    'hit_stop': hit_stop
                }
                
                results.append(result)
                
                # Log result
                status = "PROFIT" if hit_profit else ("STOP" if hit_stop else "HOLD")
                self.log(logging.INFO,
                        f"{ticker}: {status} | "
                        f"High: +{intraday_high_pct:.2f}%, Low: {intraday_low_pct:.2f}%, "
                        f"Close: {close_pct:+.2f}% | "
                        f"ATR: {atr_pct:.2f}% (pred: {predicted_atr:.2f}%)")
                
            except Exception as e:
                self.log(logging.WARNING, f"{ticker}: Error analyzing performance: {e}")
        
        # Summary statistics
        if results:
            self.log(logging.INFO, "\n" + "=" * 60)
            self.log(logging.INFO, "SUMMARY STATISTICS")
            self.log(logging.INFO, "=" * 60)
            
            total = len(results)
            winners = sum(1 for r in results if r['hit_profit'])
            losers = sum(1 for r in results if r['hit_stop'])
            holds = total - winners - losers
            
            win_rate = (winners / total * 100) if total > 0 else 0
            avg_atr = sum(r['actual_atr'] for r in results) / total if total > 0 else 0
            avg_pred_atr = sum(r['predicted_atr'] for r in results) / total if total > 0 else 0
            
            # ATR prediction accuracy
            atr_errors = [abs(r['actual_atr'] - r['predicted_atr']) for r in results]
            avg_error = sum(atr_errors) / len(atr_errors) if atr_errors else 0
            accuracy = max(0, 100 - (avg_error / avg_pred_atr * 100)) if avg_pred_atr > 0 else 0
            
            self.log(logging.INFO, f"Total Tickers Analyzed: {total}")
            self.log(logging.INFO, f"Hit Profit Target (+1.8%): {winners} ({win_rate:.1f}%)")
            self.log(logging.INFO, f"Hit Stop Loss (-0.9%): {losers}")
            self.log(logging.INFO, f"Still Holding: {holds}")
            self.log(logging.INFO, f"Average Actual ATR: {avg_atr:.2f}%")
            self.log(logging.INFO, f"Average Predicted ATR: {avg_pred_atr:.2f}%")
            self.log(logging.INFO, f"ATR Prediction Accuracy: {accuracy:.1f}%")
            
            # Save detailed results
            results_file = f"backtest_results_{test_date.strftime('%Y%m%d')}.json"
            with open(results_file, 'w') as f:
                json.dump({
                    'date': test_date.strftime('%Y-%m-%d'),
                    'summary': {
                        'total': total,
                        'winners': winners,
                        'losers': losers,
                        'win_rate': win_rate,
                        'avg_actual_atr': avg_atr,
                        'avg_predicted_atr': avg_pred_atr,
                        'prediction_accuracy': accuracy
                    },
                    'results': results
                }, f, indent=2)
            
            self.log(logging.INFO, f"\nDetailed results saved to: {results_file}")


def main():
    """Main entry point to start the day trader orchestrator."""
    parser = argparse.ArgumentParser(description="Autonomous Day-Trading Bot")
    parser.add_argument(
        '--allocation',
        type=float,
        required=True,
        help="The percentage of total capital to allocate to day trading (e.g., 0.2 for 20%)."
    )
    parser.add_argument(
        '--live',
        action='store_true',
        help="If set, runs in live trading mode. Default is paper trading."
    )
    parser.add_argument(
        '--backtest',
        action='store_true',
        help="If set, runs in backtest mode to analyze today's performance retrospectively."
    )
    parser.add_argument(
        '--date',
        type=str,
        default=datetime.now().strftime('%Y-%m-%d'),
        help="Date for backtest in YYYY-MM-DD format. Default is today."
    )
    args = parser.parse_args()

    if args.allocation <= 0 or args.allocation > 1:
        raise ValueError("Allocation must be between 0 and 1.")

    orchestrator = DayTraderOrchestrator(
        allocation=args.allocation,
        paper_trade=not args.live
    )
    
    if args.backtest:
        orchestrator.run_backtest(args.date)
    else:
        orchestrator.start()

if __name__ == "__main__":
    main()
