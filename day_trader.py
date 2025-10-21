"""
Main entry point for the Day-Trading Bot.

This bot operates in FOUR phases:
0. Data Aggregation: Collect fresh market data if needed (skips if data is current)
1. Pre-Market Analysis: LLM-based agent analyzes market data to generate a watchlist.
2. Watchlist Creation: Filter and rank candidates to create final watchlist.
3. Intraday Trading: High-speed, algorithmic agent trades the stocks from the watchlist.
"""

import argparse
import logging
from datetime import datetime, time as dt_time, timedelta
import time
import pytz

from day_trading_agents import DataAggregatorAgent, WatchlistAnalystAgent, IntradayTraderAgent
from utils import setup_logging, is_market_open

class DayTraderOrchestrator:
    def __init__(self, allocation, paper_trade=True):
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f"logs/day_trader_run_{run_id}.json"
        self.logger = setup_logging(self.log_file, run_id)
        self.allocation = allocation
        self.paper_trade = paper_trade
        self.log_adapter = logging.LoggerAdapter(self.logger, {'agent': 'Orchestrator'})
        self.log(logging.INFO, f"Day Trader Orchestrator initialized with {self.allocation*100}% capital allocation.")

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
        
        # Define trading preparation start time (8:30 AM ET)
        prep_start_time = dt_time(8, 30)
        market_close_time = dt_time(16, 0)  # 4:00 PM ET
        
        # If it's after 4 PM today, wait until 8:30 AM tomorrow
        if current_time >= market_close_time:
            # Calculate tomorrow 8:30 AM ET
            tomorrow = now_et.date() + timedelta(days=1)
            target_datetime = et_tz.localize(datetime.combine(tomorrow, prep_start_time))
            
            seconds_until_start = (target_datetime - now_et).total_seconds()
            
            self.log(logging.INFO, f"[CLOCK] Current time: {now_et.strftime('%I:%M:%S %p ET on %B %d, %Y')}")
            self.log(logging.INFO, f"[CLOSED] Market is closed for today (closes at 4:00 PM ET)")
            self.log(logging.INFO, f"[SCHEDULED] Bot will start at: {target_datetime.strftime('%I:%M:%S %p ET on %B %d, %Y')}")
            
            # Show countdown
            hours_until = int(seconds_until_start // 3600)
            minutes_until = int((seconds_until_start % 3600) // 60)
            self.log(logging.INFO, f"[COUNTDOWN] Sleeping for {hours_until} hours and {minutes_until} minutes until 8:30 AM ET tomorrow...")
            self.log(logging.INFO, "[WAITING] The bot will automatically start when it's time. You can leave it running!")
            
            # Sleep with periodic updates every 10 minutes for better visibility
            update_interval = 600  # 10 minutes
            while seconds_until_start > 0:
                sleep_time = min(update_interval, seconds_until_start)
                time.sleep(sleep_time)
                seconds_until_start -= sleep_time
                
                if seconds_until_start > 0:
                    hours_left = int(seconds_until_start // 3600)
                    minutes_left = int((seconds_until_start % 3600) // 60)
                    self.log(logging.INFO, f"[COUNTDOWN] {hours_left}h {minutes_left}m remaining until 8:30 AM ET...")
            
            self.log(logging.INFO, "[MORNING] Good morning! It's 8:30 AM ET - starting the day trading workflow!")
        
        # If it's before 8:30 AM, wait until 8:30 AM today
        elif current_time < prep_start_time:
            today = now_et.date()
            target_datetime = et_tz.localize(datetime.combine(today, prep_start_time))
            seconds_until_start = (target_datetime - now_et).total_seconds()
            
            hours_until = int(seconds_until_start // 3600)
            minutes_until = int((seconds_until_start % 3600) // 60)
            
            self.log(logging.INFO, f"[CLOCK] Current time: {now_et.strftime('%I:%M:%S %p ET')}")
            self.log(logging.INFO, f"[COUNTDOWN] Waiting {hours_until}h {minutes_until}m until 8:30 AM ET to start...")
            time.sleep(seconds_until_start)
            self.log(logging.INFO, "[START] It's 8:30 AM ET - starting workflow!")
        else:
            # Between 8:30 AM and 4:00 PM - start immediately
            self.log(logging.INFO, f"[READY] Current time: {now_et.strftime('%I:%M:%S %p ET')} - starting immediately!")

        # --- Phase 0: Data Aggregation (skips if data is current) ---
        self.run_data_aggregation()

        # --- Phase 1: Pre-Market Analysis ---
        # We run this regardless of market hours to prepare the watchlist.
        self.run_pre_market_analysis()

        # --- Phase 2: Intraday Trading ---
        self.log(logging.INFO, "Checking market hours before starting Phase 2.")
        
        # Wait for the market to open if it's not already.
        # This loop will run once and exit if the market is open.
        # If the market is closed, it will wait and check every 5 minutes.
        while not is_market_open():
            self.log(logging.INFO, "Market is currently closed. Waiting for market open to begin trading...")
            time.sleep(300) # Wait for 5 minutes before checking again

        # Once the loop exits, the market is open.
        self.log(logging.INFO, "Market is open. Proceeding with intraday trading.")
        self.run_intraday_trading()
        
        self.log(logging.INFO, "Day trading bot workflow finished.")


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
    args = parser.parse_args()

    if args.allocation <= 0 or args.allocation > 1:
        raise ValueError("Allocation must be between 0 and 1.")

    orchestrator = DayTraderOrchestrator(
        allocation=args.allocation,
        paper_trade=not args.live
    )
    orchestrator.start()

if __name__ == "__main__":
    main()
