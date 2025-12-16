import json

# Check exit analysis structure
with open('weekly_bot/form4_reports/exit_analysis_20251215_080325.json') as f:
    exit_data = json.load(f)

print("Exit Analysis Structure:")
print(f"  positions_analyzed: {exit_data.get('positions_analyzed')}")
print(f"  exit_decisions count: {len(exit_data.get('exit_decisions', []))}")

print("\nExit Manager sees these positions:")
for decision in exit_data.get('exit_decisions', []):
    pos = decision['position']
    print(f"  {pos['symbol']}: {pos['quantity']} shares @ ${pos['entry_price']:.2f}")
    print(f"    Entry: {pos['entry_date']}, P&L: {pos['pnl_pct']:.2f}%")
    print(f"    Decision: {decision['decision']['decision']}")
