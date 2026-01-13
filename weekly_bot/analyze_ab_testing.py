"""
A/B Testing Analysis for Signal Weight Optimization
Compares performance of V1 (current) vs V2 (optimized) weight systems
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from collections import defaultdict

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from observability import get_database

def analyze_ab_testing():
    """Analyze A/B testing results and generate comparison report"""
    
    # Get database
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(parent_dir, "databases", "trading_history.db")
    db = get_database(db_path)
    
    print("="*80)
    print("A/B TESTING ANALYSIS: Signal Weight Optimization")
    print("="*80)
    print()
    
    # Check if A/B testing table exists
    try:
        result = db.execute_query("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='ab_test_log'
        """)
        
        if not result:
            print("❌ A/B testing table not found.")
            print("   The system hasn't logged any A/B test data yet.")
            print()
            print("To enable A/B testing:")
            print("   1. Set environment variable: $env:ENABLE_AB_TESTING='true'")
            print("   2. Run Form 4 strategy: python weekly_bot/05_form4_strategy.py")
            print()
            return
            
    except Exception as e:
        print(f"[ERROR] Error checking database: {e}")
        return
    
    # Get all A/B test logs
    logs = db.execute_query("""
        SELECT * FROM ab_test_log 
        ORDER BY timestamp DESC
    """)
    
    if not logs:
        print("[INFO] No A/B test data collected yet.")
        print("   Run the Form 4 strategy with A/B testing enabled to collect data.")
        return
    
    print(f"[INFO] Total A/B test logs: {len(logs)}")
    print()
    
    # Group by action type
    action_counts = defaultdict(int)
    for log in logs:
        action_counts[log['action']] += 1
    
    print("[ACTIONS LOGGED]")
    for action, count in sorted(action_counts.items()):
        print(f"   {action}: {count}")
    print()
    
    # Analyze BUY decisions
    buy_logs = [log for log in logs if log['action'] == 'BUY']
    
    if not buy_logs:
        print("⚠️  No BUY decisions logged yet.")
        print("   Candidates found but none executed. Check approval logs.")
        return
    
    print("="*80)
    print(f"[BUY ANALYSIS] {len(buy_logs)} purchases logged")
    print("="*80)
    print()
    
    # Compare weight system decisions
    print("[WEIGHT SYSTEM COMPARISON]")
    print()
    print(f"{'Symbol':<8} {'Active':<8} {'V1 Score':<10} {'V2 Score':<10} {'Delta':<10} {'Entry $':<10}")
    print("-"*80)
    
    v1_total_score = 0
    v2_total_score = 0
    
    for log in buy_logs:
        symbol = log['symbol']
        active = log['active_version']
        v1_score = log['weight_v1_score']
        v2_score = log['weight_v2_score']
        delta = v2_score - v1_score
        entry = log['entry_price'] or 0
        
        v1_total_score += v1_score
        v2_total_score += v2_score
        
        delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
        active_marker = "✓" if active == 'v2' else ""
        
        print(f"{symbol:<8} {active:<8} {v1_score:<10.2f} {v2_score:<10.2f} {delta_str:<10} ${entry:<9.2f} {active_marker}")
    
    print("-"*80)
    print(f"{'TOTALS':<8} {'':<8} {v1_total_score:<10.2f} {v2_total_score:<10.2f} {v2_total_score - v1_total_score:+.2f}")
    print()
    
    avg_v1 = v1_total_score / len(buy_logs)
    avg_v2 = v2_total_score / len(buy_logs)
    
    print(f"[AVERAGE SCORES]")
    print(f"   V1 (Current):  {avg_v1:.2f}")
    print(f"   V2 (Optimized): {avg_v2:.2f}")
    print(f"   Improvement:   {avg_v2 - avg_v1:+.2f} ({((avg_v2 - avg_v1) / avg_v1 * 100):+.1f}%)")
    print()
    
    # Analyze insider type distribution
    print("="*80)
    print("[INSIDER TYPE ANALYSIS]")
    print("="*80)
    print()
    
    total_politicians = sum(log['politician_count'] for log in buy_logs)
    total_directors = sum(log['director_count'] for log in buy_logs)
    total_officers = sum(log['officer_count'] for log in buy_logs)
    total_signals = sum(log['total_signals'] for log in buy_logs)
    
    print(f"Total Signals: {total_signals}")
    print(f"   Politicians: {total_politicians} ({total_politicians/total_signals*100:.1f}%)")
    print(f"   Directors:   {total_directors} ({total_directors/total_signals*100:.1f}%)")
    print(f"   Officers:    {total_officers} ({total_officers/total_signals*100:.1f}%)")
    print()
    
    # Check for positions with exit data
    exits_tracked = sum(1 for log in buy_logs if log['exit_price'])
    
    if exits_tracked > 0:
        print("="*80)
        print(f"[PERFORMANCE TRACKING] {exits_tracked} positions closed")
        print("="*80)
        print()
        
        for log in buy_logs:
            if log['exit_price']:
                entry = log['entry_price']
                exit_price = log['exit_price']
                pnl = log['pnl'] or ((exit_price - entry) / entry * 100)
                outcome = log['outcome'] or ("WIN" if pnl > 0 else "LOSS")
                
                print(f"{log['symbol']:<8} Entry: ${entry:.2f} → Exit: ${exit_price:.2f} | "
                      f"P&L: {pnl:+.2f}% | {outcome}")
        
        # Calculate win rate
        wins = sum(1 for log in buy_logs if log['outcome'] == 'WIN')
        win_rate = wins / exits_tracked * 100
        
        print()
        print(f"Win Rate: {wins}/{exits_tracked} ({win_rate:.1f}%)")
        print()
    else:
        print("⏳ Waiting for position exits to calculate performance...")
        print("   P&L tracking will be available once positions are closed.")
        print()
    
    # Recommendation
    print("="*80)
    print("[RECOMMENDATION]")
    print("="*80)
    print()
    
    if len(buy_logs) < 10:
        print(f"⚠️  INSUFFICIENT DATA ({len(buy_logs)} trades)")
        print(f"   Need at least 10 trades to make statistical conclusions.")
        print(f"   Continue A/B testing for {10 - len(buy_logs)} more trades.")
    elif exits_tracked < 5:
        print(f"⏳ WAITING FOR EXITS ({exits_tracked} closed)")
        print(f"   Need at least 5 closed positions to evaluate performance.")
        print(f"   Current data shows score differences but no P&L validation.")
    else:
        # Calculate if V2 would have improved decisions
        improvement = avg_v2 - avg_v1
        
        if improvement > 0.2:
            print(f"[RECOMMEND] STRONG SIGNAL: Switch to V2 weights")
            print(f"   V2 scores are {improvement:.2f} higher on average")
            print(f"   This represents a {((improvement / avg_v1) * 100):.1f}% improvement")
            print()
            print(f"To activate V2 weights:")
            print(f"   $env:USE_NEW_WEIGHTS='true'")
        elif improvement > 0:
            print(f"🟡 WEAK SIGNAL: V2 slightly better")
            print(f"   V2 scores are {improvement:.2f} higher but margin is small")
            print(f"   Recommend collecting more data before switching")
        else:
            print(f"[CAUTION] V1 PERFORMING BETTER")
            print(f"   Current weights are outperforming optimized weights")
            print(f"   This is unexpected - may need to re-analyze historical data")
    
    print()
    print("="*80)

if __name__ == "__main__":
    analyze_ab_testing()
