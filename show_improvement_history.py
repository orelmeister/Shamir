"""Show autonomous improvement system history and impact"""
from observability import get_database
from pathlib import Path
import json

db = get_database()

print("="*80)
print("AUTONOMOUS IMPROVEMENT SYSTEM - IMPACT ANALYSIS")
print("="*80)
print()

# 1. Show parameter changes over time
print("1. PARAMETER EVOLUTION (Last 30 Days)")
print("-"*80)

# Query parameter changes directly from database
with db._get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, parameter_name, old_value, new_value, reason
        FROM parameter_changes
        WHERE timestamp >= date('now', '-30 days')
        ORDER BY timestamp DESC
    """)
    changes = [dict(row) for row in cursor.fetchall()]

if changes:
    print(f"Total parameter adjustments: {len(changes)}\n")
    for c in changes:
        old_val = float(c['old_value']) if c['old_value'] else 0
        new_val = float(c['new_value']) if c['new_value'] else 0
        print(f"{c['timestamp'][:10]} | {c['parameter_name']:20} | {old_val:6.2f} -> {new_val:6.2f}")
        print(f"  Reason: {c['reason']}")
        print()
else:
    print("No parameter changes recorded in database yet.\n")

# 2. Show improvement reports
print("\n2. IMPROVEMENT REPORTS (Recent)")
print("-"*80)
reports_dir = Path('reports/improvement')
if reports_dir.exists():
    reports = sorted(reports_dir.glob('*.json'), reverse=True)[:3]
    for report_file in reports:
        with open(report_file) as f:
            data = json.load(f)
        
        print(f"\nDate: {data['date']}")
        print(f"Market Regime: {data.get('market_regime', 'N/A')} (confidence: {data.get('regime_confidence', 0):.1%})")
        
        if data.get('parameter_changes'):
            print("Applied Changes:")
            for param, change in data['parameter_changes'].items():
                print(f"  • {param}: {change['old']} → {change['new']}")
                print(f"    Reason: {change['reason']}")
        else:
            print("Applied Changes: None (no high-priority suggestions)")
        
        if data.get('parameter_suggestions'):
            print("Suggestions Generated:")
            for sugg in data['parameter_suggestions']:
                status = "✓ APPLIED" if data.get('parameter_changes', {}).get(sugg['parameter']) else "⏸ PENDING"
                print(f"  {status} | {sugg['parameter']}: {sugg['current_value']} → {sugg['suggested_value']} ({sugg['priority']})")
        print()

# 3. Show current optimized parameters
print("\n3. CURRENT OPTIMIZED PARAMETERS")
print("-"*80)
latest_report = max(reports_dir.glob('*.json'), key=lambda p: p.stem.split('_')[-1])
with open(latest_report) as f:
    data = json.load(f)

if 'current_parameters' in data:
    print("Active trading parameters (auto-optimized):\n")
    for param, value in data['current_parameters'].items():
        print(f"  {param:25} = {value}")

# 4. Compare with baseline
print("\n\n4. IMPROVEMENT VS BASELINE")
print("-"*80)
print("Baseline parameters (Oct 22, 2025):")
baseline = {
    'profit_target_pct': 1.8,
    'stop_loss_pct': 0.9,
    'rsi_lower_bound': 40,
    'rsi_upper_bound': 60,
    'atr_threshold_pct': 0.3,  # Original 30-second bar threshold
    'max_position_size_pct': 5.0
}

current = data['current_parameters']
print()
for param in baseline:
    old = baseline[param]
    new = current.get(param, old)
    change = new - old
    pct_change = (change / old * 100) if old != 0 else 0
    symbol = "↑" if change > 0 else "↓" if change < 0 else "→"
    print(f"  {param:25} {old:6.2f} {symbol} {new:6.2f}  ({pct_change:+.1f}%)")

print("\n" + "="*80)
print("HOW IT HELPS:")
print("="*80)
print("""
✓ Adapts to market conditions automatically (trending vs ranging)
✓ Learns from losing trades and adjusts entry criteria
✓ Prevents overtrading by raising thresholds when seeing too many EOD positions
✓ Optimizes profit targets and stops based on actual win rates
✓ Generates LLM insights from performance patterns
✓ Runs every evening at 4:00 PM to prepare for next day

Example: On Nov 26, system saw 0% win rate and raised RSI lower bound from 40→45
to filter out weaker momentum signals and improve trade quality.
""")
