"""Analyze the full analysis file to see all stocks and selection results"""
import json

# Load the full analysis
with open('weekly_bot/form4_reports/full_analysis_20251209_110445.json', 'r') as f:
    data = json.load(f)

print("\n" + "="*80)
print("FULL ANALYSIS RESULTS")
print("="*80)
print(f"Total stocks analyzed: {data['total_analyzed']}")
print(f"Min confidence threshold: {data['min_confidence']}")
print(f"Max positions: {data['max_positions']}\n")

# Sort by multi-criteria (same as the code fix)
analyzed = data['analyzed_stocks']
analyzed.sort(key=lambda x: (
    x['analysis']['confidence'],
    x['signal_data']['weighted_quality_score'],
    x['signal_data']['politician_count'],
    x['signal_data']['total_signals'],
    -x['timing_analysis']['days_ago']
), reverse=True)

print("TOP 10 STOCKS (Multi-Criteria Sorting):")
print("-" * 80)
for i, stock in enumerate(analyzed[:10], 1):
    conf = stock['analysis']['confidence']
    quality = stock['signal_data']['weighted_quality_score']
    politicians = stock['signal_data']['politician_count']
    total_signals = stock['signal_data']['total_signals']
    days_ago = stock['timing_analysis']['days_ago']
    symbol = stock['symbol']
    
    print(f"{i:2d}. {symbol:6s} | Conf: {conf:3.0%} | Quality: {quality:.2f}/3.0 | "
          f"Politicians: {politicians:2d} | Signals: {total_signals:3d} | Days: {days_ago:3d}")

print("\n" + "="*80)
print("COMPARISON: Did PayPal make the list?")
print("="*80)
paypal_found = False
for i, stock in enumerate(analyzed, 1):
    if stock['symbol'] == 'PYPL':
        paypal_found = True
        print(f"✓ PayPal found at position #{i}")
        print(f"  Confidence: {stock['analysis']['confidence']:.0%}")
        print(f"  Quality Score: {stock['signal_data']['weighted_quality_score']:.2f}/3.0")
        print(f"  Politicians: {stock['signal_data']['politician_count']}")
        print(f"  Total Signals: {stock['signal_data']['total_signals']}")
        print(f"  Days Ago: {stock['timing_analysis']['days_ago']}")
        break

if not paypal_found:
    print("✗ PayPal not in analyzed list (may have been filtered earlier)")

print("\n" + "="*80)
