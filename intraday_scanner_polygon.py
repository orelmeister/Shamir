"""
Intraday Stock Scanner using Polygon.io API
Finds stocks with momentum in the last 30 minutes of trading
Uses Polygon unlimited tier for fast, reliable scanning
"""
import os
import json
import logging
from datetime import datetime, timedelta
from polygon import RESTClient
import pandas as pd
import pandas_ta as ta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PolygonIntradayScanner:
    """Scanner using Polygon.io to find intraday momentum stocks"""
    
    def __init__(self):
        self.polygon = RESTClient(POLYGON_API_KEY)
        logger.info("✅ Polygon.io scanner initialized")
    
    def get_current_movers(self, sample_size=300):
        """
        Scan stocks for momentum in last 30 minutes using Polygon.io
        
        Returns:
            list: Top momentum stocks with metrics
        """
        logger.info("📊 Scanning stocks for momentum using Polygon.io...")
        
        # Load tickers from us_tickers.json
        try:
            with open('us_tickers.json', 'r') as f:
                all_tickers_data = json.load(f)
        except FileNotFoundError:
            logger.error("❌ us_tickers.json not found. Run ticker_screener_fmp.py first.")
            return []
        
        # Filter to ONLY common stocks (exclude ETFs, mutual funds, warrants, etc.)
        stock_tickers = []
        for item in all_tickers_data:
            if isinstance(item, dict):
                ticker = item.get('ticker', '')
            else:
                ticker = item
            
            # STRICT filtering for common stocks only
            if ticker and self._is_common_stock(ticker):
                stock_tickers.append(ticker)
        
        logger.info(f"Loaded {len(stock_tickers)} common stocks (filtered out ETFs/funds/warrants)")
        
        # Sample stocks to scan (Polygon unlimited = fast, but still be reasonable)
        import random
        if len(stock_tickers) > sample_size:
            stock_tickers = random.sample(stock_tickers, sample_size)
        
        logger.info(f"Scanning {len(stock_tickers)} stocks...")
        
        movers = []
        
        # Calculate time range (last 30 minutes of trading)
        now = datetime.now()
        # For market hours: get last 30 minutes
        end_time = now - timedelta(minutes=5)  # 5 min delay for data availability
        start_time = end_time - timedelta(minutes=30)
        
        from_date = start_time.strftime('%Y-%m-%d')
        to_date = end_time.strftime('%Y-%m-%d')
        
        for ticker in stock_tickers:
            try:
                # Get 1-minute aggregates for last 30 minutes
                aggs = self.polygon.get_aggs(
                    ticker=ticker,
                    multiplier=1,
                    timespan='minute',
                    from_=from_date,
                    to=to_date,
                    limit=50  # Last 30-50 minutes
                )
                
                if not aggs or len(aggs) < 10:
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame([{
                    'time': datetime.fromtimestamp(bar.timestamp / 1000),
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume
                } for bar in aggs])
                
                # Calculate metrics
                current_price = df['close'].iloc[-1]
                volume_30min = df['volume'].sum()
                price_change_pct = ((current_price - df['open'].iloc[0]) / df['open'].iloc[0]) * 100
                
                # Calculate ATR for volatility
                atr_series = ta.atr(df['high'], df['low'], df['close'], length=14)
                if atr_series is None or len(atr_series) == 0 or pd.isna(atr_series.iloc[-1]):
                    continue
                
                atr = atr_series.iloc[-1]
                atr_pct = (atr / current_price) * 100
                
                # RELAXED filters for early market (30 min after open)
                if volume_30min > 50000 and abs(price_change_pct) > 0.5 and atr_pct > 0.3:
                    momentum_score = abs(price_change_pct) * (volume_30min / 50000)
                    
                    movers.append({
                        'ticker': ticker,
                        'price': current_price,
                        'volume_30min': int(volume_30min),
                        'price_change_pct': round(price_change_pct, 2),
                        'atr_pct': round(atr_pct, 2),
                        'momentum_score': round(momentum_score, 2)
                    })
                    
                    logger.info(f"✅ {ticker}: {price_change_pct:+.2f}% on {volume_30min:,} vol")
            
            except Exception as e:
                logger.debug(f"⚠️ {ticker}: {str(e)}")
                continue
        
        # Sort by momentum score (highest first)
        movers.sort(key=lambda x: x['momentum_score'], reverse=True)
        
        logger.info(f"✅ Found {len(movers)} stocks with momentum")
        
        return movers[:10]  # Return top 10
    
    def _is_common_stock(self, ticker):
        """
        Filter to ONLY common stocks (exclude ETFs, mutual funds, warrants, ADRs)
        
        Common patterns to EXCLUDE:
        - 5-letter tickers ending in X (mutual funds: VFINX, MIAWX)
        - Tickers ending in W (warrants: AAPLW, TSLAWW)
        - Tickers ending in U (units: AACQU)
        - Tickers ending in R (rights: AAPLR)
        - Known ETF patterns (QQQ, SPY, etc.)
        - ADRs (American Depositary Receipts)
        """
        if not ticker or len(ticker) < 1:
            return False
        
        # Blacklist: Known problematic ADRs and foreign stocks
        BLACKLIST = {'BBAR', 'YPF', 'VALE', 'PAM', 'TX', 'BBD', 'ITUB', 'PBR', 'SID'}
        if ticker in BLACKLIST:
            return False
        
        # Exclude mutual funds (5 letters ending in X)
        if len(ticker) == 5 and ticker[-1] == 'X':
            return False
        
        # Exclude warrants (ending in W or WW)
        if ticker.endswith('W') or ticker.endswith('WW'):
            return False
        
        # Exclude units (ending in U)
        if ticker.endswith('U') and len(ticker) > 2:
            return False
        
        # Exclude rights (ending in R)
        if ticker.endswith('R') and len(ticker) > 2:
            return False
        
        # Exclude preferred shares (ending in -P, -PR, etc.)
        if '-' in ticker:
            return False
        
        # Exclude common ADR suffixes (.A, .B, .C)
        if ticker.endswith('.A') or ticker.endswith('.B') or ticker.endswith('.C'):
            return False
        
        # Exclude common ETF patterns (3-4 letters, all uppercase, common names)
        etf_patterns = ['QQQ', 'SPY', 'DIA', 'IWM', 'VOO', 'VTI', 'AGG', 'BND', 
                       'GLD', 'SLV', 'USO', 'TLT', 'HYG', 'LQD', 'EEM', 'VWO',
                       'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLRE', 'XLU']
        if ticker in etf_patterns:
            return False
        
        return True
    
    def save_watchlist(self, movers):
        """
        Save top movers to day_trading_watchlist.json
        """
        if not movers:
            logger.warning("⚠️ No movers to save")
            return
        
        # Format for day trader
        formatted_watchlist = []
        for mover in movers:
            confidence = min(95, 70 + (mover['momentum_score'] / 10))
            
            formatted_watchlist.append({
                'ticker': mover['ticker'],
                'confidence_score': round(confidence, 1),
                'reasoning': (
                    f"Polygon intraday scan: {mover['price_change_pct']:+.2f}% move "
                    f"on {mover['volume_30min']:,} volume in last 30 min. "
                    f"ATR: {mover['atr_pct']:.2f}%. "
                    f"Momentum score: {mover['momentum_score']:.1f}. "
                    f"Scanned at {datetime.now().strftime('%H:%M:%S')}"
                )
            })
        
        # Save to main watchlist file
        with open('day_trading_watchlist.json', 'w') as f:
            json.dump(formatted_watchlist, f, indent=2)
        
        logger.info(f"✅ Saved {len(formatted_watchlist)} stocks to day_trading_watchlist.json")
        
        # Save detailed backup
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        backup_file = f"intraday_scan_polygon_{timestamp}.json"
        with open(backup_file, 'w') as f:
            json.dump(movers, f, indent=2)
        
        logger.info(f"✅ Backup saved to {backup_file}")
        
        # Print summary
        print("\n" + "="*60)
        print("TOP MOMENTUM STOCKS (Last 30 Minutes)")
        print("="*60)
        for i, mover in enumerate(movers, 1):
            print(f"{i}. {mover['ticker']:6s} | "
                  f"{mover['price_change_pct']:+6.2f}% | "
                  f"Vol: {mover['volume_30min']:>10,} | "
                  f"Price: ${mover['price']:>7.2f} | "
                  f"Score: {mover['momentum_score']:>6.1f}")
        print("="*60 + "\n")


def main():
    """Main execution"""
    scanner = PolygonIntradayScanner()
    
    # Scan for current movers
    movers = scanner.get_current_movers(sample_size=300)
    
    if movers:
        scanner.save_watchlist(movers)
        logger.info("✅ Scan complete!")
    else:
        logger.warning("⚠️ No stocks found matching criteria")


if __name__ == "__main__":
    main()
