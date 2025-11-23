"""
Position Analysis Tool - Test Mode (No IBKR Connection Required)

This script tests the database query logic without requiring IBKR connection.
Useful for verifying the tool works with your database structure.
"""

import sqlite3
from datetime import datetime
from typing import Dict
import json


def get_database_entry_data(db_path: str = "trading_history.db") -> Dict[str, Dict]:
    """Get entry data for all positions from database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    entry_data = {}
    
    print("=" * 80)
    print("DATABASE ENTRY DATA TEST")
    print("=" * 80)
    print()
    
    # Get entry data from trades table (first BUY for each symbol)
    print("[1] Checking first entries from trades table...")
    cursor.execute("""
        SELECT symbol, MIN(timestamp) as first_entry, price as entry_price, quantity, agent_name
        FROM trades
        WHERE action = 'BUY'
        GROUP BY symbol
    """)
    
    first_entries = cursor.fetchall()
    print(f"    Found {len(first_entries)} symbols with BUY entries\n")
    
    for row in first_entries:
        symbol = row['symbol']
        entry_data[symbol] = {
            'first_entry_date': row['first_entry'],
            'first_entry_price': row['entry_price'],
            'quantity': row['quantity'],
            'agent_name': row['agent_name']
        }
    
    # Get most recent entry price for each symbol
    print("[2] Checking latest entries from trades table...")
    cursor.execute("""
        SELECT symbol, timestamp, price, quantity
        FROM trades
        WHERE action = 'BUY'
        AND (symbol, timestamp) IN (
            SELECT symbol, MAX(timestamp)
            FROM trades
            WHERE action = 'BUY'
            GROUP BY symbol
        )
    """)
    
    latest_entries = cursor.fetchall()
    print(f"    Found {len(latest_entries)} latest BUY entries\n")
    
    for row in latest_entries:
        symbol = row['symbol']
        if symbol in entry_data:
            entry_data[symbol]['latest_entry_date'] = row['timestamp']
            entry_data[symbol]['latest_entry_price'] = row['price']
            entry_data[symbol]['latest_quantity'] = row['quantity']
    
    # Get active position data from active_positions table
    print("[3] Checking active positions table...")
    cursor.execute("""
        SELECT symbol, entry_price, entry_timestamp, quantity, profit_target_price, stop_loss_price, status
        FROM active_positions
        WHERE status = 'OPEN'
    """)
    
    active_positions = cursor.fetchall()
    print(f"    Found {len(active_positions)} OPEN positions\n")
    
    for row in active_positions:
        symbol = row['symbol']
        if symbol not in entry_data:
            entry_data[symbol] = {}
        entry_data[symbol].update({
            'active_entry_price': row['entry_price'],
            'active_entry_date': row['entry_timestamp'],
            'active_quantity': row['quantity'],
            'profit_target': row['profit_target_price'],
            'stop_loss': row['stop_loss_price']
        })
    
    conn.close()
    return entry_data


def display_entry_data(entry_data: Dict[str, Dict]):
    """Display the entry data in a readable format"""
    print("=" * 80)
    print("ENTRY DATA SUMMARY")
    print("=" * 80)
    print()
    
    if not entry_data:
        print("[INFO] No entry data found in database")
        return
    
    print(f"Total symbols tracked: {len(entry_data)}\n")
    
    for symbol, data in sorted(entry_data.items()):
        print(f"{'─' * 80}")
        print(f"Symbol: {symbol}")
        print(f"{'─' * 80}")
        
        if 'first_entry_date' in data:
            print(f"  First Entry:")
            print(f"    Date:     {data['first_entry_date'][:19]}")
            print(f"    Price:    ${data['first_entry_price']:.2f}")
            print(f"    Quantity: {int(data['quantity'])} shares")
            print(f"    Agent:    {data.get('agent_name', 'N/A')}")
        
        if 'latest_entry_date' in data and data.get('latest_entry_date') != data.get('first_entry_date'):
            print(f"\n  Latest Entry:")
            print(f"    Date:     {data['latest_entry_date'][:19]}")
            print(f"    Price:    ${data['latest_entry_price']:.2f}")
            print(f"    Quantity: {int(data['latest_quantity'])} shares")
        
        if 'active_entry_price' in data:
            print(f"\n  Active Position (from active_positions table):")
            print(f"    Entry Date:   {data['active_entry_date'][:19]}")
            print(f"    Entry Price:  ${data['active_entry_price']:.2f}")
            print(f"    Quantity:     {int(data['active_quantity'])} shares")
            if data.get('profit_target'):
                print(f"    Target:       ${data['profit_target']:.2f}")
            if data.get('stop_loss'):
                print(f"    Stop Loss:    ${data['stop_loss']:.2f}")
        
        print()
    
    print("=" * 80)


def test_database_queries():
    """Test all database queries without IBKR connection"""
    try:
        print("\n" + "=" * 80)
        print("POSITION ANALYSIS - DATABASE TEST MODE")
        print("=" * 80)
        print()
        print("[INFO] This test runs without IBKR connection")
        print("[INFO] It verifies database query logic only")
        print()
        
        entry_data = get_database_entry_data()
        display_entry_data(entry_data)
        
        print("\n✓ Database queries completed successfully")
        print("\nTo run full analysis with IBKR connection, use: analyze_positions.py")
        print()
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_database_queries()
