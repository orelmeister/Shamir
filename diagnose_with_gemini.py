"""
Final diagnostic with LLM analysis using Gemini 2.0 Flash
"""
import sys
from ib_insync import IB, util
import json
from pathlib import Path
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI

def get_all_data():
    """Collect all position data from all sources"""
    # IBKR
    ib = IB()
    util.run(ib.connectAsync('127.0.0.1', 4001, clientId=98))
    ib.reqMarketDataType(3)
    ibkr_positions = []
    for pos in ib.positions():
        ibkr_positions.append({
            'symbol': pos.contract.symbol,
            'quantity': pos.position,
            'avg_cost': pos.avgCost
        })
    ib.disconnect()
    
    # Exit Manager
    with open('weekly_bot/form4_reports/exit_analysis_20251215_080325.json') as f:
        exit_data = json.load(f)
    exit_positions = []
    for decision in exit_data.get('exit_decisions', []):
        pos = decision['position']
        exit_positions.append({
            'symbol': pos['symbol'],
            'quantity': pos['quantity'],
            'entry_price': pos['entry_price'],
            'entry_date': pos['entry_date']
        })
    
    # Approved Today
    with open('weekly_bot/form4_reports/approved_positions_20251215_080210.json') as f:
        approved_data = json.load(f)
    approved_positions = []
    for pos in approved_data.get('approved_positions', []):
        if pos.get('status') == 'EXECUTED':
            approved_positions.append({
                'symbol': pos['symbol'],
                'shares': pos.get('execution', {}).get('shares', pos['shares']),
                'fill_price': pos.get('execution', {}).get('fill_price', pos['price'])
            })
    
    return {
        'ibkr': ibkr_positions,
        'exit_manager': exit_positions,
        'approved_today': approved_positions
    }

def analyze_with_gemini(data):
    """Use Gemini to explain what's wrong in plain English"""
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0.1,
        max_retries=3
    )
    
    prompt = f"""You are analyzing a critical bug in an automated trading system's position tracking.

**IBKR ACTUAL POSITIONS** (Ground Truth - 16 positions):
{json.dumps(data['ibkr'], indent=2)}

**EXIT MANAGER TRACKED** (What the system thinks it has - 3 positions):
{json.dumps(data['exit_manager'], indent=2)}

**APPROVED/EXECUTED TODAY** (4 new positions bought this morning):
{json.dumps(data['approved_today'], indent=2)}

The exit manager is supposed to monitor positions and liquidate them when they hit profit targets (+15%) or stop losses (-8%).

**THE PROBLEM**: The exit manager can only see 3 old positions from November 15. It's completely blind to 13 other positions that actually exist in the IBKR account, including 4 that were bought TODAY.

Please explain in plain English:
1. What exactly is wrong here?
2. Why is this critical for the trading system?
3. What's the likely root cause?
4. What should be fixed to prevent this?

Be direct and clear - this is costing real money because positions can't be liquidated."""

    response = llm.invoke(prompt)
    return response.content

def main():
    print("="*80)
    print("FORM 4 STRATEGY - ROOT CAUSE ANALYSIS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    print("\nCollecting position data from all sources...")
    data = get_all_data()
    
    print(f"\n  IBKR: {len(data['ibkr'])} positions")
    print(f"  Exit Manager: {len(data['exit_manager'])} positions")
    print(f"  Approved Today: {len(data['approved_today'])} positions")
    
    print("\nAnalyzing with Gemini 2.0 Flash...")
    print("-" * 80)
    
    try:
        analysis = analyze_with_gemini(data)
        print(analysis)
    except Exception as e:
        print(f"\n[ERROR] Gemini analysis failed: {e}")
        print("\nManual Analysis:")
        print("The exit manager is out of sync with IBKR. It only sees 3 old positions")
        print("but IBKR has 16 total. This means 13 positions are orphaned and cannot")
        print("be managed or liquidated, tying up ~$2,700 of capital.")
    
    print("\n" + "="*80)
    print("ORPHANED POSITIONS (in IBKR but NOT tracked):")
    ibkr_symbols = {p['symbol'] for p in data['ibkr']}
    exit_symbols = {p['symbol'] for p in data['exit_manager']}
    approved_symbols = {p['symbol'] for p in data['approved_today']}
    
    orphaned = ibkr_symbols - exit_symbols - approved_symbols
    for symbol in sorted(orphaned):
        pos = next(p for p in data['ibkr'] if p['symbol'] == symbol)
        print(f"  {symbol}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f}")
    print("="*80)

if __name__ == '__main__':
    main()
