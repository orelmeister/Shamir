"""
Intraday Scanner - Get fresh stocks with momentum RIGHT NOW
Runs during market hours to find new opportunities based on current price action
"""

import json
import logging
from datetime import datetime, timedelta
from ib_insync import IB, Stock, util
import pandas as pd
import pandas_ta as ta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntradayScanner:
    def __init__(self):
        self.ib = IB()
        
    def connect_to_ibkr(self):
        """Connect to IBKR Gateway"""
        try:
            self.ib.connect('127.0.0.1', 4001, clientId=99)
            logger.info("✅ Connected to IBKR")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to IBKR: {e}")
            return False
    
    def get_current_movers(self):
        """Get stocks with high volume and volatility RIGHT NOW"""
        logger.info("📊 Scanning current market for high-momentum stocks...")
        
        # Load the base universe from your ticker list
        try:
            with open('us_tickers.json', 'r') as f:
                all_tickers = json.load(f)
            logger.info(f"Loaded {len(all_tickers)} tickers from universe")
        except:
            logger.error("Could not load us_tickers.json - run ticker_screener_fmp.py first")
            return []
        
        # Filter out mutual funds (typically 5 letters ending in X)
        stock_tickers = [t for t in all_tickers 
                        if not (isinstance(t, dict) and len(t.get('ticker', '')) == 5 and t.get('ticker', '')[-1] == 'X')]
        
        # Sample first 300 tickers for quick scan (adjust as needed)
        sample_tickers = stock_tickers[:300]
        
        movers = []
        
        for ticker_data in sample_tickers:
            ticker = ticker_data.get('ticker', ticker_data) if isinstance(ticker_data, dict) else ticker_data
            
            try:
                # Get current intraday data
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)
                
                # Get last 30 minutes of 1-min bars
                bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime='',
                    durationStr='30 min',
                    barSizeSetting='1 min',
                    whatToShow='TRADES',
                    useRTH=True,
                    formatDate=1
                )
                
                if not bars or len(bars) < 10:
                    continue
                
                df = util.df(bars)
                
                # Calculate current metrics
                current_price = df['close'].iloc[-1]
                volume = df['volume'].sum()
                price_change = ((current_price - df['open'].iloc[0]) / df['open'].iloc[0]) * 100
                
                # Calculate volatility (ATR)
                df_ta = df.copy()
                atr = ta.atr(df_ta['high'], df_ta['low'], df_ta['close'], length=14)
                if atr is not None and len(atr) > 0:
                    atr_pct = (atr.iloc[-1] / current_price) * 100
                else:
                    atr_pct = 0
                
                # Filter criteria: Relaxed for early market - any significant movement
                if volume > 50000 and abs(price_change) > 0.5 and atr_pct > 0.3:
                    movers.append({
                        'ticker': ticker,
                        'price': current_price,
                        'volume_30min': volume,
                        'price_change_pct': price_change,
                        'atr_pct': atr_pct,
                        'momentum_score': abs(price_change) * (volume / 50000)
                    })
                    logger.info(f"✅ {ticker}: ${current_price:.2f}, Vol={volume:,}, Change={price_change:+.2f}%, ATR={atr_pct:.2f}%")
                
            except Exception as e:
                logger.debug(f"Skip {ticker}: {e}")
                continue
        
        # Sort by momentum score
        movers.sort(key=lambda x: x['momentum_score'], reverse=True)
        
        return movers[:10]  # Top 10 movers
    
    def save_watchlist(self, movers):
        """Save fresh movers to watchlist"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        
        # Format for day trader
        watchlist = []
        for stock in movers:
            watchlist.append({
                'ticker': stock['ticker'],
                'primaryExchange': 'SMART',
                'confidence_score': min(0.9, 0.6 + (stock['momentum_score'] / 100)),
                'reasoning': f"LIVE INTRADAY SCAN ({timestamp}): {stock['price_change_pct']:+.2f}% move with {stock['volume_30min']:,} volume in last 30min. ATR {stock['atr_pct']:.2f}% confirms volatility. Momentum score: {stock['momentum_score']:.1f}",
                'model': 'IntradayScanner'
            })
        
        # Save to watchlist file
        with open('day_trading_watchlist.json', 'w') as f:
            json.dump(watchlist, f, indent=4)
        
        logger.info(f"💾 Saved {len(watchlist)} fresh stocks to day_trading_watchlist.json")
        
        # Also save detailed version
        with open(f'intraday_scan_{timestamp}.json', 'w') as f:
            json.dump(movers, f, indent=4)
        
        return watchlist

def main():
    scanner = IntradayScanner()
    
    if not scanner.connect_to_ibkr():
        logger.error("Cannot scan without IBKR connection")
        return
    
    try:
        # Scan for current movers
        movers = scanner.get_current_movers()
        
        if not movers:
            logger.warning("⚠️ No stocks found matching criteria")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔥 TOP MOVERS RIGHT NOW:")
        logger.info(f"{'='*60}")
        for i, stock in enumerate(movers, 1):
            logger.info(f"{i}. {stock['ticker']:6} | ${stock['price']:7.2f} | {stock['price_change_pct']:+6.2f}% | Vol: {stock['volume_30min']:>10,} | Score: {stock['momentum_score']:.1f}")
        
        # Save to watchlist
        watchlist = scanner.save_watchlist(movers)
        
        logger.info(f"\n✅ READY TO TRADE! Restart your bot to use the fresh watchlist.")
        
    finally:
        scanner.ib.disconnect()

if __name__ == '__main__':
    main()
