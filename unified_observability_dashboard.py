"""
Unified Observability Dashboard - Cross-Bot Analytics
Compares performance and learning across all 3 trading bots:
- Day Trading Bot (intraday momentum)
- Form4 Bot (insider cluster signals)
- Weekly Bot (weekly portfolio rebalancing)

Provides comprehensive analysis to determine which strategy performs best
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import statistics

from observability import get_database
from continuous_improvement import ContinuousImprovementEngine

print("="*100)
print("🤖 UNIFIED AUTONOMOUS TRADING SYSTEM - CROSS-BOT ANALYTICS DASHBOARD")
print("="*100)
print()

db = get_database()

# Bot configurations
BOTS = {
    'day_trader': {
        'name': 'Day Trading Bot',
        'agent_names': ['day_trader', 'IntradayTraderAgent', 'VWAPMomentumAgent'],
        'strategy': 'Intraday VWAP momentum + ATR filtering',
        'frequency': 'Daily (6-10 trades/day)',
        'hold_time': '< 1 day (intraday exits)',
        'capital_allocation': '25% of portfolio'
    },
    'form4': {
        'name': 'Form4 Insider Bot',
        'agent_names': ['form4_strategy', 'PreFlightTest'],
        'strategy': 'Insider cluster signals (3+ Form4 filings)',
        'frequency': 'Weekly (0-2 trades/week)',
        'hold_time': '2-4 weeks (swing trading)',
        'capital_allocation': '$1,000 fixed'
    },
    'weekly': {
        'name': 'Weekly Portfolio Bot',
        'agent_names': ['weekly_portfolio_manager', 'PortfolioManager'],
        'strategy': 'LLM-scored portfolio rebalancing',
        'frequency': 'Weekly (Sunday rebalances)',
        'hold_time': '1-4 weeks',
        'capital_allocation': 'Remaining capital'
    }
}

def get_bot_trades(bot_key: str, days: int = 30) -> List[Dict]:
    """Get all trades for a bot across all its agent names"""
    agent_names = BOTS[bot_key]['agent_names']
    all_trades = []
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    for date in [(start_date + timedelta(days=x)).strftime('%Y-%m-%d') 
                 for x in range(days + 1)]:
        for agent_name in agent_names:
            trades = db.get_trades_by_date(date, agent_name)
            all_trades.extend(trades)
    
    return all_trades

def calculate_bot_metrics(trades: List[Dict]) -> Dict:
    """Calculate performance metrics from trades"""
    if not trades:
        return {
            'total_trades': 0,
            'buy_count': 0,
            'sell_count': 0,
            'realized_pnl': 0.0,
            'realized_pnl_pct': 0.0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'profit_factor': 0.0
        }
    
    buys = [t for t in trades if t['action'] == 'BUY']
    sells = [t for t in trades if t['action'] == 'SELL']
    
    # Calculate realized P&L from SELL orders
    realized_trades = [t for t in sells if t.get('profit_loss') is not None]
    wins = [t for t in realized_trades if t['profit_loss'] > 0]
    losses = [t for t in realized_trades if t['profit_loss'] < 0]
    
    total_pnl = sum(t['profit_loss'] for t in realized_trades)
    total_pnl_pct = sum(t.get('profit_loss_pct', 0) for t in realized_trades)
    
    win_rate = (len(wins) / len(realized_trades) * 100) if realized_trades else 0
    
    avg_win = statistics.mean([t['profit_loss'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['profit_loss'] for t in losses]) if losses else 0
    
    largest_win = max([t['profit_loss'] for t in wins]) if wins else 0
    largest_loss = min([t['profit_loss'] for t in losses]) if losses else 0
    
    gross_profit = sum([t['profit_loss'] for t in wins]) if wins else 0
    gross_loss = abs(sum([t['profit_loss'] for t in losses])) if losses else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
    
    return {
        'total_trades': len(trades),
        'buy_count': len(buys),
        'sell_count': len(sells),
        'realized_trades': len(realized_trades),
        'realized_pnl': total_pnl,
        'realized_pnl_pct': total_pnl_pct,
        'win_rate': win_rate,
        'wins': len(wins),
        'losses': len(losses),
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'largest_win': largest_win,
        'largest_loss': largest_loss,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor
    }

def get_bot_positions(bot_key: str) -> List[Dict]:
    """Get current active positions for a bot"""
    agent_names = BOTS[bot_key]['agent_names']
    all_positions = []
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        for agent_name in agent_names:
            cursor.execute("""
                SELECT * FROM active_positions 
                WHERE agent_name = ? AND status = 'OPEN'
            """, (agent_name,))
            positions = [dict(row) for row in cursor.fetchall()]
            all_positions.extend(positions)
    
    return all_positions

def get_parameter_evolution(bot_key: str, days: int = 30) -> List[Dict]:
    """Get parameter changes for a bot"""
    agent_names = BOTS[bot_key]['agent_names']
    all_changes = []
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        for agent_name in agent_names:
            cursor.execute("""
                SELECT * FROM parameter_changes
                WHERE agent_name = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (agent_name, start_date))
            changes = [dict(row) for row in cursor.fetchall()]
            all_changes.extend(changes)
    
    return all_changes

# ============================================================================
# SECTION 1: PERFORMANCE COMPARISON (Last 30 Days)
# ============================================================================

print("\n📊 SECTION 1: PERFORMANCE COMPARISON (Last 30 Days)")
print("-" * 100)
print()

comparison_data = {}

for bot_key, bot_info in BOTS.items():
    trades = get_bot_trades(bot_key, days=30)
    metrics = calculate_bot_metrics(trades)
    positions = get_bot_positions(bot_key)
    
    comparison_data[bot_key] = {
        'info': bot_info,
        'trades': trades,
        'metrics': metrics,
        'positions': positions
    }
    
    print(f"🤖 {bot_info['name'].upper()}")
    print(f"   Strategy: {bot_info['strategy']}")
    print(f"   Frequency: {bot_info['frequency']}")
    print(f"   Hold Time: {bot_info['hold_time']}")
    print()
    
    if metrics['total_trades'] == 0:
        print(f"   📈 Performance Metrics:")
        print(f"      ⚠️  No trading activity detected in last 30 days")
        print(f"      Active Positions: {len(positions)}")
        print()
        continue
    
    print(f"   📈 Performance Metrics:")
    print(f"      Total Trades: {metrics['total_trades']} ({metrics['buy_count']} BUY, {metrics['sell_count']} SELL)")
    print(f"      Completed Trades: {metrics['realized_trades']}")
    print(f"      Win Rate: {metrics['win_rate']:.1f}% ({metrics['wins']}W / {metrics['losses']}L)")
    print(f"      Realized P&L: ${metrics['realized_pnl']:.2f} ({metrics['realized_pnl_pct']:.2f}%)")
    print(f"      Avg Win/Loss: ${metrics['avg_win']:.2f} / ${metrics['avg_loss']:.2f}")
    print(f"      Largest Win/Loss: ${metrics['largest_win']:.2f} / ${metrics['largest_loss']:.2f}")
    print(f"      Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"      Active Positions: {len(positions)}")
    print()

# ============================================================================
# SECTION 2: SIDE-BY-SIDE COMPARISON
# ============================================================================

print("\n📊 SECTION 2: HEAD-TO-HEAD COMPARISON")
print("-" * 100)
print()

print(f"{'Metric':<25} | {'Day Trader':>15} | {'Form4 Bot':>15} | {'Weekly Bot':>15}")
print("-" * 100)

metrics_to_compare = [
    ('Total Trades', 'total_trades', ''),
    ('Completed Trades', 'realized_trades', ''),
    ('Win Rate', 'win_rate', '%'),
    ('Realized P&L', 'realized_pnl', '$'),
    ('Avg Win', 'avg_win', '$'),
    ('Avg Loss', 'avg_loss', '$'),
    ('Profit Factor', 'profit_factor', 'x'),
    ('Active Positions', 'positions', '')
]

for label, key, suffix in metrics_to_compare:
    day_val = comparison_data['day_trader']['metrics'].get(key, 0) if key != 'positions' else len(comparison_data['day_trader']['positions'])
    form4_val = comparison_data['form4']['metrics'].get(key, 0) if key != 'positions' else len(comparison_data['form4']['positions'])
    weekly_val = comparison_data['weekly']['metrics'].get(key, 0) if key != 'positions' else len(comparison_data['weekly']['positions'])
    
    if suffix == '$':
        print(f"{label:<25} | ${day_val:>14.2f} | ${form4_val:>14.2f} | ${weekly_val:>14.2f}")
    elif suffix == '%':
        print(f"{label:<25} | {day_val:>14.1f}% | {form4_val:>14.1f}% | {weekly_val:>14.1f}%")
    elif suffix == 'x':
        print(f"{label:<25} | {day_val:>14.2f}x | {form4_val:>14.2f}x | {weekly_val:>14.2f}x")
    else:
        print(f"{label:<25} | {day_val:>15.0f} | {form4_val:>15.0f} | {weekly_val:>15.0f}")

# ============================================================================
# SECTION 3: PARAMETER EVOLUTION (Autonomous Learning)
# ============================================================================

print("\n\n🧠 SECTION 3: AUTONOMOUS LEARNING & PARAMETER EVOLUTION")
print("-" * 100)
print()

for bot_key, bot_info in BOTS.items():
    changes = get_parameter_evolution(bot_key, days=30)
    
    print(f"🤖 {bot_info['name'].upper()}")
    
    if changes:
        print(f"   Total Parameter Adjustments: {len(changes)}")
        print()
        for change in changes[:5]:  # Show last 5 changes
            print(f"   {change['timestamp'][:10]} | {change['parameter_name']:25} | {change['old_value']:>8} → {change['new_value']:>8}")
            print(f"      Reason: {change['reason']}")
            print()
    else:
        print("   ⚠️  No autonomous parameter changes yet")
        print("   💡 System will start learning after more trading data is collected")
        print()

# ============================================================================
# SECTION 4: IMPROVEMENT REPORTS
# ============================================================================

print("\n📈 SECTION 4: LATEST IMPROVEMENT REPORTS")
print("-" * 100)
print()

reports_dir = Path('reports/improvement')
if reports_dir.exists():
    for bot_key, bot_info in BOTS.items():
        print(f"🤖 {bot_info['name'].upper()}")
        
        # Find latest report for this bot
        reports = sorted(reports_dir.glob('*.json'), reverse=True)
        bot_report = None
        
        for report_file in reports:
            with open(report_file) as f:
                data = json.load(f)
                # Check if report matches bot's agent names
                if any(agent in str(data) for agent in bot_info['agent_names']):
                    bot_report = data
                    break
        
        if bot_report:
            print(f"   Latest Report: {bot_report['date']}")
            print(f"   Market Regime: {bot_report.get('market_regime', 'N/A')}")
            
            if bot_report.get('parameter_changes'):
                print(f"   ✅ Parameters Updated:")
                for param, change in bot_report['parameter_changes'].items():
                    print(f"      • {param}: {change['old']} → {change['new']}")
            else:
                print(f"   ⏸  No parameter changes (monitoring)")
            
            if bot_report.get('parameter_suggestions'):
                print(f"   💡 Pending Suggestions: {len(bot_report['parameter_suggestions'])}")
        else:
            print(f"   ⚠️  No improvement reports found yet")
        
        print()

# ============================================================================
# SECTION 5: WINNER DETERMINATION & RECOMMENDATIONS
# ============================================================================

print("\n🏆 SECTION 5: WINNER ANALYSIS & STRATEGIC RECOMMENDATIONS")
print("-" * 100)
print()

# Rank bots by realized P&L
rankings = sorted(
    [(bot_key, data['metrics']['realized_pnl']) for bot_key, data in comparison_data.items()],
    key=lambda x: x[1],
    reverse=True
)

print("📊 OVERALL RANKINGS (by Realized P&L):")
print()

for rank, (bot_key, pnl) in enumerate(rankings, 1):
    bot_info = BOTS[bot_key]
    metrics = comparison_data[bot_key]['metrics']
    
    medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉"
    print(f"{medal} #{rank}. {bot_info['name']}")
    print(f"   Realized P&L: ${pnl:.2f}")
    print(f"   Win Rate: {metrics['win_rate']:.1f}%")
    print(f"   Profit Factor: {metrics['profit_factor']:.2f}x")
    print(f"   Active Trades: {len(comparison_data[bot_key]['positions'])}")
    print()

# Strategic recommendations
print("\n💡 STRATEGIC RECOMMENDATIONS:")
print("-" * 100)
print()

winner_key = rankings[0][0]
winner_info = BOTS[winner_key]
winner_metrics = comparison_data[winner_key]['metrics']

print(f"🏆 CURRENT CHAMPION: {winner_info['name']}")
print()
print(f"✅ STRENGTHS:")
print(f"   • Highest realized P&L: ${winner_metrics['realized_pnl']:.2f}")
print(f"   • Strategy: {winner_info['strategy']}")
print(f"   • Win rate: {winner_metrics['win_rate']:.1f}%")
print()

# Analyze each bot
print(f"📊 BOT-SPECIFIC INSIGHTS:")
print()

for bot_key, bot_info in BOTS.items():
    metrics = comparison_data[bot_key]['metrics']
    positions = comparison_data[bot_key]['positions']
    
    print(f"🤖 {bot_info['name']}:")
    
    # Provide specific recommendations
    if metrics['total_trades'] == 0:
        print(f"   ⚠️  STATUS: No trading activity detected")
        print(f"   💡 ACTION: Ensure bot is running on schedule, check logs for errors")
    
    elif metrics['realized_trades'] < 5:
        print(f"   ⚠️  STATUS: Insufficient data (only {metrics['realized_trades']} completed trades)")
        print(f"   💡 ACTION: Continue collecting data for 1-2 more weeks before optimization")
    
    elif metrics['win_rate'] < 40:
        print(f"   ⚠️  STATUS: Low win rate ({metrics['win_rate']:.1f}%)")
        print(f"   💡 ACTION: Autonomous system will tighten entry criteria")
        print(f"   💡 MANUAL: Consider reducing position sizes until performance improves")
    
    elif metrics['win_rate'] > 60:
        print(f"   ✅ STATUS: Strong performance ({metrics['win_rate']:.1f}% win rate)")
        print(f"   💡 ACTION: Consider increasing capital allocation to this strategy")
    
    elif metrics['profit_factor'] < 1.5:
        print(f"   ⚠️  STATUS: Low profit factor ({metrics['profit_factor']:.2f}x)")
        print(f"   💡 ACTION: Exit strategy needs improvement - losses too large relative to wins")
    
    else:
        print(f"   ✅ STATUS: Healthy performance")
        print(f"   💡 ACTION: Continue monitoring, autonomous system optimizing parameters")
    
    print()

# Portfolio recommendations
print("\n🎯 PORTFOLIO ALLOCATION RECOMMENDATIONS:")
print("-" * 100)
print()

total_pnl = sum(data['metrics']['realized_pnl'] for data in comparison_data.values())

if total_pnl > 0:
    print("✅ OVERALL PORTFOLIO: PROFITABLE")
    print()
    print("Suggested capital allocation based on performance:")
    print()
    
    for bot_key, data in comparison_data.items():
        bot_info = BOTS[bot_key]
        metrics = data['metrics']
        
        if metrics['realized_pnl'] > 0:
            allocation_pct = (metrics['realized_pnl'] / total_pnl) * 100
            print(f"   {bot_info['name']:25} : {allocation_pct:>5.1f}% of capital")
    
    print()
    print("💡 Adjust allocations quarterly based on 3-month performance")
    
else:
    print("⚠️  OVERALL PORTFOLIO: BREAK-EVEN OR NEGATIVE")
    print()
    print("💡 IMMEDIATE ACTIONS:")
    print("   1. Review autonomous parameter changes in Section 3")
    print("   2. Let systems learn for 2-4 more weeks with current settings")
    print("   3. Consider reducing overall capital deployment by 50%")
    print("   4. Focus on the best-performing bot and pause others temporarily")

print()
print("="*100)
print("✅ CROSS-BOT ANALYSIS COMPLETE")
print("="*100)
print()
print(f"📁 Full trade data available in: trading_history.db")
print(f"📊 Individual bot reports in: reports/improvement/")
print(f"🔄 Dashboard updates automatically with each trade")
print()
