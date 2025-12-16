"""
FORM 4 POSITION DIAGNOSTIC TOOL
Comprehensive analysis of what positions exist vs what the system thinks
Connects to IBKR to get GROUND TRUTH
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from ib_insync import IB, util
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False
    print("⚠️  ib_insync not installed - cannot connect to IBKR")

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage, SystemMessage
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  Gemini not available")

print("="*80)
print("FORM 4 STRATEGY - COMPREHENSIVE POSITION DIAGNOSTIC")
print("="*80)
print()

# ============================================
# STEP 1: Get ACTUAL positions from IBKR
# ============================================

print("[STEP 1] Connecting to IBKR to get ACTUAL positions...")
print("-"*80)

actual_positions = {}
ibkr_connected = False

if IBKR_AVAILABLE:
    try:
        ib = IB()
        util.run(ib.connectAsync('127.0.0.1', 4001, clientId=99))
        ib.reqMarketDataType(3)  # Delayed data
        ibkr_connected = True
        
        positions = ib.positions()
        
        if positions:
            print(f"✅ Connected to IBKR - Found {len(positions)} total positions in account")
            print()
            
            # Filter for Form 4 positions (we need to identify them somehow)
            # For now, get ALL positions
            for pos in positions:
                symbol = pos.contract.symbol
                quantity = pos.position
                avg_cost = pos.avgCost
                
                actual_positions[symbol] = {
                    'quantity': quantity,
                    'avg_cost': avg_cost,
                    'symbol': symbol,
                    'exchange': pos.contract.exchange if hasattr(pos.contract, 'exchange') else 'Unknown',
                    'market_value': quantity * avg_cost  # Approximate
                }
                
                print(f"   {symbol}: {quantity} shares @ ${avg_cost:.2f} avg cost")
        else:
            print("⚠️  No positions found in IBKR account")
        
        ib.disconnect()
        print()
        
    except Exception as e:
        print(f"❌ Failed to connect to IBKR: {e}")
        print("   Make sure IBKR Gateway or TWS is running!")
        print()
        ibkr_connected = False
else:
    print("❌ ib_insync not installed - cannot connect to IBKR")
    print()

# ============================================
# STEP 2: Get what EXIT MANAGER thinks exists
# ============================================

print("[STEP 2] Checking what EXIT MANAGER thinks exists...")
print("-"*80)

form4_dir = Path('weekly_bot/form4_reports')
exit_files = sorted(form4_dir.glob('exit_analysis_*.json'))

exit_manager_positions = {}

if exit_files:
    latest_exit = exit_files[-1]
    print(f"Reading: {latest_exit.name}")
    
    with open(latest_exit, 'r') as f:
        exit_data = json.load(f)
    
    date = exit_data.get('date')
    timestamp = exit_data.get('timestamp')
    positions_count = exit_data.get('positions_analyzed', 0)
    
    print(f"Date: {date} at {timestamp}")
    print(f"Positions analyzed: {positions_count}")
    print()
    
    for decision in exit_data.get('exit_decisions', []):
        pos = decision.get('position', {})
        symbol = pos.get('symbol')
        quantity = pos.get('quantity')
        entry_price = pos.get('entry_price')
        entry_date = pos.get('entry_date')
        
        exit_manager_positions[symbol] = {
            'quantity': quantity,
            'entry_price': entry_price,
            'entry_date': entry_date,
            'cost_basis': pos.get('cost_basis'),
            'current_price': pos.get('current_price'),
            'pnl_pct': pos.get('pnl_pct')
        }
        
        print(f"   {symbol}: {quantity} shares from {entry_date} @ ${entry_price:.2f}")
    
    print()
else:
    print("❌ No exit analysis files found")
    print()

# ============================================
# STEP 3: Get what was APPROVED for execution
# ============================================

print("[STEP 3] Checking APPROVED positions (what was supposed to be bought)...")
print("-"*80)

approved_files = sorted(form4_dir.glob('approved_positions_*.json'))

all_approved_positions = defaultdict(list)  # symbol -> list of entries

for file in approved_files[-5:]:  # Last 5 approval sessions
    with open(file, 'r') as f:
        data = json.load(f)
    
    approved_at = data.get('approved_at')
    date_only = approved_at[:10] if approved_at else 'Unknown'
    
    for pos in data.get('approved_positions', []):
        if pos.get('status') == 'EXECUTED' and 'execution' in pos:
            symbol = pos['symbol']
            exec_data = pos['execution']
            
            all_approved_positions[symbol].append({
                'date': date_only,
                'shares': exec_data.get('shares'),
                'fill_price': exec_data.get('fill_price'),
                'total_cost': exec_data.get('total_cost'),
                'status': exec_data.get('status')
            })

print(f"Found {len(all_approved_positions)} unique symbols approved across last 5 sessions:")
print()

for symbol, entries in sorted(all_approved_positions.items()):
    total_shares = sum(e['shares'] for e in entries)
    latest_date = max(e['date'] for e in entries)
    
    print(f"   {symbol}: {len(entries)} entry(ies), {total_shares} total shares, latest: {latest_date}")
    for entry in entries:
        print(f"      - {entry['date']}: {entry['shares']} @ ${entry['fill_price']:.2f} = ${entry['total_cost']:.2f}")

print()

# ============================================
# STEP 4: COMPARISON & DISCREPANCY ANALYSIS
# ============================================

print("[STEP 4] DISCREPANCY ANALYSIS")
print("="*80)
print()

all_symbols = set(actual_positions.keys()) | set(exit_manager_positions.keys()) | set(all_approved_positions.keys())

discrepancies = []

for symbol in sorted(all_symbols):
    in_ibkr = symbol in actual_positions
    in_exit = symbol in exit_manager_positions
    in_approved = symbol in all_approved_positions
    
    status = []
    if in_ibkr:
        status.append(f"IBKR: {actual_positions[symbol]['quantity']} shares")
    else:
        status.append("IBKR: ❌ NOT FOUND")
    
    if in_exit:
        status.append(f"Exit Mgr: {exit_manager_positions[symbol]['quantity']} shares")
    else:
        status.append("Exit Mgr: ❌ NOT TRACKED")
    
    if in_approved:
        total_approved = sum(e['shares'] for e in all_approved_positions[symbol])
        status.append(f"Approved: {total_approved} shares")
    else:
        status.append("Approved: ❌ NEVER APPROVED")
    
    print(f"{symbol}:")
    for s in status:
        print(f"   {s}")
    
    # Identify discrepancy type
    if in_ibkr and not in_exit:
        discrepancies.append({
            'symbol': symbol,
            'type': 'ORPHANED_IN_IBKR',
            'description': f'{symbol} exists in IBKR but EXIT MANAGER does not track it',
            'severity': 'CRITICAL',
            'impact': 'Position cannot be monitored or sold by exit manager'
        })
    
    if in_exit and not in_ibkr:
        discrepancies.append({
            'symbol': symbol,
            'type': 'GHOST_POSITION',
            'description': f'{symbol} tracked by EXIT MANAGER but does not exist in IBKR',
            'severity': 'CRITICAL',
            'impact': 'System thinks it owns stock it doesnt have - data corruption'
        })
    
    if in_approved and not in_ibkr:
        discrepancies.append({
            'symbol': symbol,
            'type': 'FAILED_EXECUTION',
            'description': f'{symbol} was approved but never executed in IBKR',
            'severity': 'HIGH',
            'impact': 'Approved trade did not execute properly'
        })
    
    if in_ibkr and in_exit:
        ibkr_qty = actual_positions[symbol]['quantity']
        exit_qty = exit_manager_positions[symbol]['quantity']
        if abs(ibkr_qty - exit_qty) > 0.1:  # Allow for small float differences
            discrepancies.append({
                'symbol': symbol,
                'type': 'QUANTITY_MISMATCH',
                'description': f'{symbol} quantity mismatch: IBKR={ibkr_qty}, Exit Manager={exit_qty}',
                'severity': 'HIGH',
                'impact': 'Position size tracked incorrectly'
            })
    
    print()

# ============================================
# STEP 5: LLM ANALYSIS (if Gemini available)
# ============================================

if GEMINI_AVAILABLE and discrepancies:
    print("[STEP 5] LLM ANALYSIS OF DISCREPANCIES")
    print("="*80)
    print()
    
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp", temperature=0.1)
        
        analysis_prompt = f"""You are a financial trading system debugger. Analyze these position tracking discrepancies:

ACTUAL POSITIONS IN IBKR:
{json.dumps(actual_positions, indent=2)}

EXIT MANAGER TRACKED POSITIONS:
{json.dumps(exit_manager_positions, indent=2)}

APPROVED POSITIONS (last 5 sessions):
{json.dumps(dict(all_approved_positions), indent=2)}

IDENTIFIED DISCREPANCIES:
{json.dumps(discrepancies, indent=2)}

Provide a comprehensive analysis in plain English:
1. What is the root cause of these discrepancies?
2. What specific bug or system failure caused this?
3. What is the immediate risk to the trading strategy?
4. What are the exact steps to fix this (be very specific)?
5. How can we prevent this from happening again?

Be direct and actionable. This is causing real money risk."""

        messages = [HumanMessage(content=analysis_prompt)]
        response = llm.invoke(messages)
        
        print("GEMINI ANALYSIS:")
        print("-"*80)
        print(response.content)
        print()
        
    except Exception as e:
        print(f"⚠️  Gemini analysis failed: {e}")
        print()

# ============================================
# STEP 6: SUMMARY & RECOMMENDATIONS
# ============================================

print("[STEP 6] SUMMARY & ACTIONABLE RECOMMENDATIONS")
print("="*80)
print()

if not ibkr_connected:
    print("❌ CRITICAL: Could not connect to IBKR!")
    print("   RECOMMENDATION: Start IBKR Gateway/TWS and run this script again")
    print()

if discrepancies:
    print(f"⚠️  FOUND {len(discrepancies)} DISCREPANCIES:")
    print()
    
    critical = [d for d in discrepancies if d['severity'] == 'CRITICAL']
    high = [d for d in discrepancies if d['severity'] == 'HIGH']
    
    if critical:
        print(f"🚨 CRITICAL ISSUES ({len(critical)}):")
        for d in critical:
            print(f"   - {d['description']}")
            print(f"     Impact: {d['impact']}")
        print()
    
    if high:
        print(f"⚠️  HIGH PRIORITY ({len(high)}):")
        for d in high:
            print(f"   - {d['description']}")
            print(f"     Impact: {d['impact']}")
        print()
    
    print("RECOMMENDED ACTIONS:")
    print("1. DO NOT place new trades until discrepancies are resolved")
    print("2. Create a position reconciliation script to sync IBKR -> Exit Manager")
    print("3. Add position sync check at start of every exit analysis")
    print("4. Investigate why approved positions didn't appear in exit manager")
    print("5. Check if there's a timing issue (exit runs before new positions settle)")
    print()

else:
    print("✅ No discrepancies found - all systems in sync")
    print()

print("="*80)

# Save to file
output = {
    'timestamp': datetime.now().isoformat(),
    'ibkr_connected': ibkr_connected,
    'actual_positions': actual_positions,
    'exit_manager_positions': exit_manager_positions,
    'approved_positions': dict(all_approved_positions),
    'discrepancies': discrepancies
}

output_file = Path('weekly_bot/form4_reports/position_diagnostic.json')
with open(output_file, 'w') as f:
    json.dump(output, f, indent=2)

print(f"✅ Full diagnostic saved to: {output_file}")
