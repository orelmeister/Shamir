"""
Form4 Exit Analysis Runner
Checks existing positions and determines HOLD/SELL decisions

Features:
- Smart caching: Loads today's analysis if already ran (avoids redundant AI calls)
- Multi-agent AI debate: DeepSeek + Gemini consensus
- Automatic execution: Sells positions with AI approval (optional)
- Cost-efficient: Run once per week, reuse analysis if needed

Usage:
    python run_exit_analysis.py                 # Check for existing analysis, run if needed
    python run_exit_analysis.py --force         # Force re-analysis (ignore cache)
    python run_exit_analysis.py --dry-run       # Analyze but don't execute sells
    python run_exit_analysis.py --display-only  # Just show existing analysis (no new run)
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add weekly_bot to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'weekly_bot'))

from form4_exit_manager import Form4ExitManager


def display_analysis(analysis_data: dict, title: str = "EXIT ANALYSIS"):
    """Display exit analysis in readable format"""
    print("\n" + "="*80)
    print(f"{title}")
    print("="*80)
    print(f"Date: {analysis_data['date']}")
    print(f"Analyzed: {analysis_data['timestamp']}")
    print(f"Positions: {analysis_data['positions_analyzed']}")
    print(f"Sell Decisions: {analysis_data['sell_decisions']}")
    print(f"Hold Decisions: {analysis_data['hold_decisions']}")
    
    if analysis_data['total_realized_pnl'] != 0:
        print(f"Realized P&L: ${analysis_data['total_realized_pnl']:.2f}")
    
    print("="*80 + "\n")
    
    # Show individual position decisions
    for i, decision in enumerate(analysis_data['exit_decisions'], 1):
        position = decision['position']
        dec = decision['decision']
        execution = decision['execution']
        
        print(f"[{i}] {position['symbol']} - {dec['decision']}")
        print(f"    Entry: ${position['entry_price']:.2f} | Current: ${position['current_price']:.2f}")
        print(f"    P&L: ${position['pnl_dollars']:.2f} ({position['pnl_pct']:+.1f}%)")
        print(f"    Days Held: {position['days_held']} / {position['recommended_hold_days']}")
        print(f"    Confidence: {dec['confidence']:.0%}")
        print(f"    Reasoning: {dec['reasoning']}")
        
        if execution['status'] == 'FILLED':
            print(f"    ✅ EXECUTED: Sold {execution['shares']} shares @ ${execution['price']:.2f}")
            print(f"       P&L: ${execution['pnl_dollars']:.2f} ({execution['pnl_pct']:+.1f}%)")
        elif execution['status'] == 'DRY_RUN':
            print(f"    🔸 DRY RUN: Would sell {position['shares']} shares")
        elif execution['status'] == 'SKIPPED':
            print(f"    ⏭️  SKIPPED: {execution.get('reason', 'HOLD decision')}")
        
        print()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Form4 Exit Analysis Runner")
    parser.add_argument('--force', action='store_true', 
                       help="Force re-analysis even if today's analysis exists")
    parser.add_argument('--dry-run', action='store_true', 
                       help="Analyze but don't execute trades")
    parser.add_argument('--display-only', action='store_true',
                       help="Only display existing analysis (don't run if missing)")
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("FORM4 EXIT ANALYSIS RUNNER")
    print("="*80)
    print(f"Mode: {'FORCE RE-ANALYSIS' if args.force else 'DRY RUN' if args.dry_run else 'DISPLAY ONLY' if args.display_only else 'SMART CACHE'}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    
    # Initialize exit manager
    manager = Form4ExitManager()
    
    # Check for existing analysis (unless --force)
    if not args.force:
        print("[CHECKING] Looking for existing exit analysis today...")
        existing_analysis = manager.load_todays_analysis()
        
        if existing_analysis:
            print(f"✅ Found existing analysis from {existing_analysis['timestamp']}")
            print("💡 Using cached results (saves AI API costs)")
            print("   Run with --force to re-analyze\n")
            
            display_analysis(existing_analysis, "CACHED EXIT ANALYSIS")
            
            # Summary recommendations
            sell_positions = [
                d for d in existing_analysis['exit_decisions'] 
                if d['decision']['decision'] == 'SELL'
            ]
            
            if sell_positions:
                print("\n" + "="*80)
                print("📋 RECOMMENDED ACTIONS:")
                print("="*80)
                for d in sell_positions:
                    symbol = d['position']['symbol']
                    pnl = d['position']['pnl_dollars']
                    pnl_pct = d['position']['pnl_pct']
                    print(f"   SELL {symbol}: ${pnl:.2f} ({pnl_pct:+.1f}%) - {d['decision']['reasoning'][:80]}...")
                print("="*80 + "\n")
            else:
                print("✅ No sells recommended - all positions should HOLD\n")
            
            return
        else:
            print("ℹ️  No existing analysis found for today")
            
            if args.display_only:
                print("❌ --display-only specified but no analysis exists")
                print("   Run without --display-only to create new analysis\n")
                return
            
            print("🔄 Running fresh exit analysis...\n")
    else:
        print("🔄 FORCE mode: Running fresh exit analysis (ignoring cache)...\n")
    
    # Run exit manager
    try:
        results = manager.run(dry_run=args.dry_run)
        
        if results.get('error'):
            print(f"\n❌ ERROR: {results['error']}")
            return
        
        if results.get('status') == 'no_positions':
            print("\n✅ Portfolio is empty - no positions to analyze")
            return
        
        # Display results
        if results.get('exit_decisions'):
            analysis_data = {
                'date': datetime.now().strftime("%Y-%m-%d"),
                'timestamp': results['timestamp'],
                'positions_analyzed': results['positions_analyzed'],
                'sell_decisions': sum(1 for d in results['exit_decisions'] if d['decision']['decision'] == 'SELL'),
                'hold_decisions': sum(1 for d in results['exit_decisions'] if d['decision']['decision'] == 'HOLD'),
                'total_realized_pnl': results['total_realized_pnl'],
                'exit_decisions': results['exit_decisions']
            }
            
            title = "FRESH EXIT ANALYSIS" if not args.dry_run else "EXIT ANALYSIS (DRY RUN)"
            display_analysis(analysis_data, title)
            
            # Summary recommendations
            sell_positions = [
                d for d in results['exit_decisions'] 
                if d['decision']['decision'] == 'SELL'
            ]
            
            if sell_positions:
                print("\n" + "="*80)
                print("📋 RECOMMENDED ACTIONS:")
                print("="*80)
                for d in sell_positions:
                    symbol = d['position']['symbol']
                    pnl = d['position']['pnl_dollars']
                    pnl_pct = d['position']['pnl_pct']
                    status = d['execution']['status']
                    
                    if status == 'FILLED':
                        print(f"   ✅ SOLD {symbol}: ${pnl:.2f} ({pnl_pct:+.1f}%)")
                    elif status == 'DRY_RUN':
                        print(f"   🔸 WOULD SELL {symbol}: ${pnl:.2f} ({pnl_pct:+.1f}%) - {d['decision']['reasoning'][:60]}...")
                    else:
                        print(f"   ⚠️  {symbol}: SELL recommended but not executed ({status})")
                
                print("="*80 + "\n")
                
                if args.dry_run:
                    print("💡 Run without --dry-run to execute sells\n")
            else:
                print("✅ No sells recommended - all positions should HOLD\n")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
