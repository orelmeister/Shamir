import yfinance as yf
import json
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IsraeliDataLoader:
    def __init__(self, universe_path: str = "universe.json"):
        self.universe_path = Path(__file__).parent / universe_path
        self.universe = self._load_universe()

    def _load_universe(self) -> Dict:
        """Load the target universe from JSON"""
        try:
            with open(self.universe_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load universe file: {e}")
            return {}

    def fetch_data(self) -> Dict[str, Dict]:
        """
        Fetch financial and market data for all sectors in the universe.
        Returns a dictionary structured by sector -> symbol -> data.
        """
        all_data = {}

        for bucket, companies in self.universe.items():
            logger.info(f"📥 Fetching data for bucket: {bucket.upper()}")
            sector_data = {}
            
            for company in companies:
                symbol = company['symbol']
                name = company['name']
                logger.info(f"   Processing {name} ({symbol})...")
                
                try:
                    ticker = yf.Ticker(symbol)
                    
                    # 1. Price History (Last 6 months for momentum)
                    history = ticker.history(period="6mo")
                    if history.empty:
                        logger.warning(f"   ⚠️ No price data for {symbol}")
                        continue
                        
                    current_price = history['Close'].iloc[-1]
                    start_price = history['Close'].iloc[0]
                    momentum_6m = ((current_price - start_price) / start_price) * 100
                    
                    # 2. Key Statistics (Valuation & Risk)
                    info = ticker.info

                    # yfinance sometimes reports TASE prices in agorot ("ILA").
                    # Normalize to ILS to make portfolio sizing meaningful.
                    raw_currency = (info.get('currency') or 'ILS').upper()
                    price = float(current_price)
                    currency = raw_currency
                    price_raw = None
                    currency_raw = None
                    if raw_currency == 'ILA':
                        price_raw = price
                        currency_raw = raw_currency
                        price = price / 100.0
                        currency = 'ILS'
                    
                    # 3. Financials (Balance Sheet / Income Stmt)
                    # Note: yfinance often returns empty dfs for TASE, handle gracefully
                    balance_sheet = ticker.balance_sheet
                    financials = ticker.financials
                    
                    # Extract specific metrics if available
                    total_debt = info.get('totalDebt')
                    total_cash = info.get('totalCash')
                    market_cap = info.get('marketCap')
                    
                    # Calculate Debt/Equity if not provided
                    debt_to_equity = info.get('debtToEquity')
                    
                    company_data = {
                        'symbol': symbol,
                        'name': name,
                        'sector': bucket,  # legacy field (used by some prompts)
                        'bucket': bucket,
                        'asset_type': company.get('asset_type', 'STOCK'),
                        'kosher': company.get('kosher', False),
                        'thesis': company.get('thesis', ''),
                        'price': price,
                        'currency': currency,
                        'price_raw': price_raw,
                        'currency_raw': currency_raw,
                        'momentum_6m_pct': round(momentum_6m, 2),
                        'market_cap': market_cap,
                        'metrics': {
                            'debt_to_equity': debt_to_equity,
                            'current_ratio': info.get('currentRatio'),
                            'quick_ratio': info.get('quickRatio'),
                            'trailing_pe': info.get('trailingPE'),
                            'beta': info.get('beta')
                        },
                        'financial_health': {
                            'total_debt': total_debt,
                            'total_cash': total_cash,
                            'revenue_growth': info.get('revenueGrowth')
                        }
                    }
                    
                    sector_data[symbol] = company_data
                    logger.info(f"   ✅ Fetched {symbol}: {price:.4g} {currency} | Mom: {momentum_6m:.1f}%")
                    
                except Exception as e:
                    logger.error(f"   ❌ Error fetching {symbol}: {e}")
            
            all_data[bucket] = sector_data
            
        return all_data

if __name__ == "__main__":
    # Test run
    loader = IsraeliDataLoader()
    data = loader.fetch_data()
    print(json.dumps(data, indent=2, default=str))
