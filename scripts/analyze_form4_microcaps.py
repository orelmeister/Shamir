"""
Analyze Form 4 Filing Patterns for Microcap Strategy
Tests different lookback periods and validates strategy fit
"""
import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter

# FMP API key
API_KEY = "Q0MEUK8wi0TxCWR036LRxP8jSRdxZbhg"

# Your microcap strategy parameters
MIN_MARKET_CAP = 300_000_000  # $300M
MAX_MARKET_CAP = 20_000_000_000  # $20B
MIN_PRICE = 1.0
MAX_PRICE = 18.0

def fetch_form4_filings(days_back):
    """Fetch Form 4 filings for specified lookback period"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    url = "https://financialmodelingprep.com/stable/sec-filings-search/form-type"
    params = {
        "formType": "4",
        "from": start_date.strftime("%Y-%m-%d"),
        "to": end_date.strftime("%Y-%m-%d"),
        "apikey": API_KEY
    }
    
    response = requests.get(url, params=params, timeout=30)
    if response.status_code == 200:
        return response.json() if isinstance(response.json(), list) else []
    return []

def get_stock_profile(symbol):
    """Fetch stock profile to check market cap and price"""
    url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
    params = {"apikey": API_KEY}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0]
    except:
        pass
    return None

def analyze_lookback_periods():
    """Test different lookback periods to find optimal signal quality"""
    
    print("\n" + "=" * 80)
    print("FORM 4 LOOKBACK PERIOD ANALYSIS FOR MICROCAP STRATEGY")
    print("=" * 80)
    print(f"\nYour Strategy: Market Cap ${MIN_MARKET_CAP/1_000_000:.0f}M - ${MAX_MARKET_CAP/1_000_000_000:.0f}B")
    print(f"              Price ${MIN_PRICE} - ${MAX_PRICE}")
    
    lookback_periods = [3, 5, 7, 10, 14, 21, 30]
    
    results = {}
    
    for days in lookback_periods:
        print(f"\n{'─' * 80}")
        print(f"Testing {days}-day lookback period...")
        print(f"{'─' * 80}")
        
        filings = fetch_form4_filings(days)
        print(f"   Total Form 4 filings: {len(filings)}")
        
        # Group by symbol
        symbol_counts = Counter()
        valid_symbols = set()
        
        for filing in filings:
            symbol = filing.get('symbol')
            if symbol and symbol != 'None':
                symbol_counts[symbol] += 1
                valid_symbols.add(symbol)
        
        print(f"   Unique symbols: {len(valid_symbols)}")
        
        # Find clusters (3+ filings)
        clusters = {sym: count for sym, count in symbol_counts.items() if count >= 3}
        print(f"   Cluster symbols (3+ filings): {len(clusters)}")
        
        if clusters:
            print(f"\n   Top clusters:")
            for sym, count in sorted(clusters.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"      {sym}: {count} filings")
        
        # Check how many align with your microcap strategy
        print(f"\n   Validating against your microcap criteria...")
        print(f"   (This may take a moment - checking market cap/price for top clusters)")
        
        matching_clusters = []
        checked = 0
        
        for sym, count in sorted(clusters.items(), key=lambda x: x[1], reverse=True)[:20]:  # Check top 20
            profile = get_stock_profile(sym)
            checked += 1
            
            if profile:
                market_cap = profile.get('mktCap', 0)
                price = profile.get('price', 0)
                
                if market_cap and price:
                    if (MIN_MARKET_CAP <= market_cap <= MAX_MARKET_CAP and 
                        MIN_PRICE <= price <= MAX_PRICE):
                        matching_clusters.append({
                            'symbol': sym,
                            'filings': count,
                            'market_cap': market_cap,
                            'price': price,
                            'name': profile.get('companyName', 'N/A')
                        })
                        print(f"      ✓ {sym}: ${market_cap/1_000_000:.0f}M cap, ${price:.2f} price ({count} filings)")
                    else:
                        reason = []
                        if market_cap < MIN_MARKET_CAP:
                            reason.append(f"too small ${market_cap/1_000_000:.0f}M")
                        elif market_cap > MAX_MARKET_CAP:
                            reason.append(f"too large ${market_cap/1_000_000_000:.1f}B")
                        if price < MIN_PRICE:
                            reason.append(f"price ${price:.2f} too low")
                        elif price > MAX_PRICE:
                            reason.append(f"price ${price:.2f} too high")
                        print(f"      ✗ {sym}: {', '.join(reason)} ({count} filings)")
            
            if checked >= 20:
                break
        
        results[days] = {
            'total_filings': len(filings),
            'unique_symbols': len(valid_symbols),
            'clusters': len(clusters),
            'matching_clusters': len(matching_clusters),
            'matches': matching_clusters
        }
        
        print(f"\n   📊 RESULT: {len(matching_clusters)}/{len(clusters)} clusters match your strategy")
        print(f"   Match rate: {len(matching_clusters)/max(len(clusters), 1)*100:.1f}%")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: OPTIMAL LOOKBACK PERIOD")
    print("=" * 80)
    
    print("\n┌─────────┬──────────────┬─────────────┬──────────┬─────────────────┬─────────────┐")
    print("│  Days   │ Total Form 4 │   Symbols   │ Clusters │ Microcap Match  │ Match Rate  │")
    print("├─────────┼──────────────┼─────────────┼──────────┼─────────────────┼─────────────┤")
    
    for days in lookback_periods:
        r = results[days]
        match_rate = r['matching_clusters']/max(r['clusters'], 1)*100 if r['clusters'] > 0 else 0
        print(f"│  {days:>2} days │   {r['total_filings']:>6}     │    {r['unique_symbols']:>4}     │   {r['clusters']:>3}    │      {r['matching_clusters']:>2}/{r['clusters']:<2}       │   {match_rate:>5.1f}%   │")
    
    print("└─────────┴──────────────┴─────────────┴──────────┴─────────────────┴─────────────┘")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("ANALYSIS & RECOMMENDATIONS")
    print("=" * 80)
    
    # Find best match rate
    best_days = max(results.items(), key=lambda x: x[1]['matching_clusters'])
    best_rate = max(results.items(), key=lambda x: x[1]['matching_clusters']/max(x[1]['clusters'], 1))
    
    print(f"\n📈 BEST ABSOLUTE MATCHES: {best_days[0]} days ({best_days[1]['matching_clusters']} matches)")
    print(f"📊 BEST MATCH RATE: {best_rate[0]} days ({best_rate[1]['matching_clusters']/max(best_rate[1]['clusters'], 1)*100:.1f}%)")
    
    # Strategy fit analysis
    total_checked = sum(len(r['matches']) for r in results.values())
    
    print(f"\n🎯 STRATEGY FIT ANALYSIS:")
    
    if total_checked == 0:
        print("   ❌ NO MATCHES FOUND - Your microcap strategy may be TOO RESTRICTIVE")
        print("   💡 Consider adjusting parameters:")
        print(f"      - Increase MAX_PRICE from ${MAX_PRICE} to $25-30")
        print(f"      - Increase MIN_MARKET_CAP from ${MIN_MARKET_CAP/1_000_000:.0f}M to $500M-1B")
        print("   ⚠️  Form 4 filings are more common in:")
        print("      - Mid-cap stocks ($1B-10B market cap)")
        print("      - Higher priced stocks ($15-50 range)")
        print("      - More established companies with insider compensation plans")
    else:
        # Calculate overall match rate
        total_clusters = sum(r['clusters'] for r in results.values())
        total_matches = sum(r['matching_clusters'] for r in results.values())
        overall_rate = total_matches / max(total_clusters, 1) * 100
        
        if overall_rate >= 20:
            print(f"   ✅ GOOD FIT: {overall_rate:.1f}% of clusters match your strategy")
            print(f"   📊 Found {total_matches} matching opportunities across all periods")
        elif overall_rate >= 10:
            print(f"   ⚠️  MODERATE FIT: {overall_rate:.1f}% of clusters match")
            print(f"   💡 Form 4 signal will work but coverage is limited")
        else:
            print(f"   ❌ POOR FIT: Only {overall_rate:.1f}% of clusters match")
            print(f"   💡 Consider strategy adjustments for better coverage")
        
        # Show example matches
        if best_days[1]['matches']:
            print(f"\n   📋 EXAMPLE MATCHES ({best_days[0]}-day period):")
            for match in best_days[1]['matches'][:5]:
                print(f"      {match['symbol']}: {match['name'][:40]}")
                print(f"         Market Cap: ${match['market_cap']/1_000_000:.0f}M | Price: ${match['price']:.2f} | {match['filings']} filings")
    
    # Optimal recommendation
    print(f"\n💡 RECOMMENDATION:")
    
    if total_checked > 0:
        if best_days[0] <= 7:
            print(f"   ✅ Use {best_days[0]}-day lookback (fresh signals, high relevance)")
            print(f"   ⏰ Run daily before market open to catch recent insider activity")
        else:
            print(f"   ⚠️  {best_days[0]}-day lookback gives most matches BUT signals may be stale")
            print(f"   ✅ RECOMMENDED: Use 7-day lookback as balance of freshness vs coverage")
        
        print(f"\n   📊 INTEGRATION APPROACH:")
        print(f"      1. Fetch Form 4s for past 7 days")
        print(f"      2. Filter to symbols with 3+ filings (clusters)")
        print(f"      3. Cross-reference with your watchlist from ticker_screener_fmp.py")
        print(f"      4. Boost LLM confidence by 10-15% for matches")
        print(f"      5. Add to prompt: 'Recent insider cluster activity (X filings)'")
    else:
        print(f"   ⚠️  FORM 4 SIGNAL MAY NOT BE OPTIMAL FOR YOUR CURRENT MICROCAP STRATEGY")
        print(f"   💡 ALTERNATIVES:")
        print(f"      1. Focus on other signals (news, momentum, volume)")
        print(f"      2. Adjust strategy to capture mid-cap stocks ($1B-10B)")
        print(f"      3. Use Form 4 as secondary confirmation only")

def main():
    analyze_lookback_periods()

if __name__ == "__main__":
    main()
