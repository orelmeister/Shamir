#!/usr/bin/env python3
"""
Comprehensive Performance Analysis Script
Analyzes all trading history, positions, and generates detailed reports
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def analyze_trading_performance():
    """Main analysis function"""
    results = {
        "analysis_timestamp": datetime.now().isoformat(),
        "database_info": {},
        "position_history": [],
        "approved_positions_history": [],
        "exit_logs": [],
        "performance_summary": {},
        "best_performers": [],
        "worst_performers": [],
        "lessons_learned": []
    }
    
    # 1. Analyze Database
    db_path = 'databases/trading_history.db'
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get table info
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cur.fetchall()]
        results["database_info"]["tables"] = tables
        
        # Get trades if table exists
        if 'trades' in tables:
            cur.execute("SELECT * FROM trades ORDER BY timestamp DESC")
            trades = [dict(row) for row in cur.fetchall()]
            results["database_info"]["total_trades"] = len(trades)
            results["position_history"] = trades[:50]  # Last 50 trades
        
        # Get positions if table exists
        if 'positions' in tables:
            cur.execute("SELECT * FROM positions")
            positions = [dict(row) for row in cur.fetchall()]
            results["database_info"]["total_positions"] = len(positions)
        
        conn.close()
    
    # 2. Analyze Approved Positions Files
    reports_dir = Path('weekly_bot/form4_reports')
    if reports_dir.exists():
        approved_files = sorted(reports_dir.glob('approved_positions_*.json'))
        
        all_positions = []
        for f in approved_files:
            try:
                data = json.loads(f.read_text())
                file_date = f.stem.split('_')[2]  # YYYYMMDD
                for pos in data.get('approved_positions', []):
                    pos['file_date'] = file_date
                    pos['file_name'] = f.name
                    all_positions.append(pos)
            except Exception as e:
                print(f"Error reading {f}: {e}")
        
        results["approved_positions_history"] = all_positions
        results["database_info"]["approved_position_files"] = len(approved_files)
    
    # 3. Check exit logs
    exit_logs_dir = reports_dir / 'exit_logs' if reports_dir.exists() else None
    if exit_logs_dir and exit_logs_dir.exists():
        exit_files = sorted(exit_logs_dir.glob('*.json'))
        for f in exit_files[-30:]:  # Last 30
            try:
                data = json.loads(f.read_text())
                data['file_name'] = f.name
                results["exit_logs"].append(data)
            except:
                pass
    
    return results


def calculate_performance_metrics(results):
    """Calculate detailed performance metrics"""
    metrics = {
        "total_positions_analyzed": 0,
        "unique_symbols": set(),
        "position_by_symbol": defaultdict(list),
        "executed_trades": [],
        "pending_trades": []
    }
    
    for pos in results.get("approved_positions_history", []):
        symbol = pos.get('symbol', 'UNKNOWN')
        metrics["unique_symbols"].add(symbol)
        metrics["position_by_symbol"][symbol].append(pos)
        metrics["total_positions_analyzed"] += 1
        
        if pos.get('status', '').startswith('EXECUTED'):
            metrics["executed_trades"].append(pos)
        else:
            metrics["pending_trades"].append(pos)
    
    metrics["unique_symbols"] = list(metrics["unique_symbols"])
    metrics["position_by_symbol"] = dict(metrics["position_by_symbol"])
    
    return metrics


if __name__ == "__main__":
    print("=" * 80)
    print("COMPREHENSIVE TRADING PERFORMANCE ANALYSIS")
    print("=" * 80)
    
    # Run analysis
    results = analyze_trading_performance()
    metrics = calculate_performance_metrics(results)
    
    # Print summary
    print(f"\nDatabase Info:")
    print(f"  Tables: {results['database_info'].get('tables', [])}")
    print(f"  Total Trades: {results['database_info'].get('total_trades', 0)}")
    print(f"  Approved Position Files: {results['database_info'].get('approved_position_files', 0)}")
    
    print(f"\nPosition Analysis:")
    print(f"  Total Positions Analyzed: {metrics['total_positions_analyzed']}")
    print(f"  Unique Symbols: {len(metrics['unique_symbols'])}")
    print(f"  Symbols: {metrics['unique_symbols'][:20]}")
    
    print(f"\nRecent Approved Positions:")
    for pos in results['approved_positions_history'][-10:]:
        print(f"  {pos.get('file_date', '?')}: {pos.get('symbol', '?')} - {pos.get('shares', 0)} shares @ ${pos.get('price', 0):.2f} - Conf: {pos.get('confidence', 0):.0%}")
    
    # Save full results
    output_path = 'performance_analysis_full.json'
    with open(output_path, 'w') as f:
        json.dump({
            "results": results,
            "metrics": metrics
        }, f, indent=2, default=str)
    
    print(f"\nFull analysis saved to: {output_path}")
