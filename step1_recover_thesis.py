#!/usr/bin/env python3
"""
STEP 1: RECOVER MISSING THESIS DATA
Query trading_history.db for original entry information for all 14 current positions
"""

import sqlite3
import json
from pathlib import Path

# Database path
db_path = Path("databases/trading_history.db")

# The 14 positions from today's exit analysis
positions = ['AL', 'AMR', 'BBIO', 'CPRT', 'FCX', 'GEO', 'IEP', 'K', 'LHCG', 'NRG', 'PCAR', 'REXR', 'RLY', 'UMC']

print("\n" + "="*110)
print("STEP 1: THESIS DATA RECOVERY - DATABASE QUERY RESULTS")
print("="*110 + "\n")

try:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    recovered_data = {}
    
    # Query for each position
    for symbol in sorted(positions):
        print(f"[{symbol}] SEARCHING DATABASE...")
        
        # Look for trades with this symbol
        cursor.execute('''
            SELECT 
                id, symbol, action, quantity, price, timestamp, agent_name, metadata
            FROM trades
            WHERE symbol = ?
            ORDER BY timestamp ASC
        ''', (symbol,))
        
        trades = cursor.fetchall()
        
        if trades:
            print(f"   ✓ Found {len(trades)} trade record(s):")
            
            # Process all trades for this symbol
            position_data = []
            for trade in trades:
                trade_dict = {
                    'id': trade['id'],
                    'timestamp': trade['timestamp'],
                    'action': trade['action'],
                    'quantity': trade['quantity'],
                    'price': trade['price'],
                    'agent_name': trade['agent_name'],
                    'metadata': {}
                }
                
                # Parse metadata JSON
                if trade['metadata']:
                    try:
                        metadata = json.loads(trade['metadata'])
                        trade_dict['metadata'] = metadata
                        
                        # Display key fields
                        print(f"      [{trade['timestamp']}] {trade['action']} {trade['quantity']} @ ${trade['price']} | Agent: {trade['agent_name']}")
                        
                        if 'reasoning' in metadata:
                            reason = str(metadata['reasoning'])[:100]
                            print(f"         → Reasoning: {reason}")
                        
                        if 'confidence' in metadata:
                            print(f"         → Confidence: {metadata['confidence']}")
                        
                        if 'hold_period_days' in metadata:
                            print(f"         → Hold Period: {metadata['hold_period_days']} days")
                            
                    except json.JSONDecodeError as e:
                        print(f"      [{trade['timestamp']}] {trade['action']} {trade['quantity']} @ ${trade['price']} - Metadata parse error")
                else:
                    print(f"      [{trade['timestamp']}] {trade['action']} {trade['quantity']} @ ${trade['price']} - No metadata")
                
                position_data.append(trade_dict)
            
            recovered_data[symbol] = position_data
        else:
            print(f"   ❌ NO TRADES FOUND in database")
        
        print()
    
    conn.close()
    
    # Summary
    print("\n" + "="*110)
    print("SUMMARY - THESIS DATA RECOVERY")
    print("="*110 + "\n")
    
    recovered_count = sum(1 for data in recovered_data.values() if data)
    print(f"[RESULTS]")
    print(f"   Positions checked: {len(positions)}")
    print(f"   Positions with database records: {recovered_count}")
    print(f"   Positions with NO records: {len(positions) - recovered_count}")
    print(f"\n   Covered positions: {', '.join([k for k in sorted(recovered_data.keys()) if recovered_data[k]])}")
    print(f"   Missing positions: {', '.join([p for p in sorted(positions) if p not in recovered_data or not recovered_data[p]])}")
    
    # Show what data we recovered
    print(f"\n[DATA TYPES RECOVERED]")
    recovered_fields = set()
    for symbol_data in recovered_data.values():
        for trade in symbol_data:
            if trade['metadata']:
                recovered_fields.update(trade['metadata'].keys())
    
    if recovered_fields:
        print(f"   {', '.join(sorted(recovered_fields))}")
    else:
        print(f"   (No metadata fields found)")
    
    print("\n" + "="*110)
    
    # Save recovered data to JSON for reference
    output_file = Path("step1_recovered_thesis_data.json")
    with open(output_file, 'w') as f:
        # Convert for JSON serialization
        json_data = {}
        for symbol, trades in recovered_data.items():
            json_data[symbol] = [
                {
                    'id': t['id'],
                    'timestamp': t['timestamp'],
                    'action': t['action'],
                    'quantity': t['quantity'],
                    'price': t['price'],
                    'agent_name': t['agent_name'],
                    'metadata': t['metadata']
                }
                for t in trades
            ]
        json.dump(json_data, f, indent=2)
    
    print(f"\n✓ Recovered data saved to: {output_file}")
    print()

except sqlite3.Error as e:
    print(f"\n❌ DATABASE ERROR: {e}\n")
except Exception as e:
    print(f"\n❌ ERROR: {e}\n")
