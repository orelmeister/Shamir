"""
Manual script to set up phase_state.json with existing full_market_data.json
This bypasses the aggregation phase and prepares for analyst phase.
"""
import json
from datetime import datetime
from shared_state.state_manager import write_state

# Load existing market data
with open('full_market_data.json', 'r') as f:
    stocks_data = json.load(f)

print(f"Loaded {len(stocks_data)} stocks from full_market_data.json")

# Write to phase_state
write_state('phase_state', {
    'current_phase': 'aggregation_complete',
    'stocks_for_analysis': stocks_data,
    'timestamp': datetime.now().isoformat()
})

print(f"✅ Phase state updated: {len(stocks_data)} stocks ready for Analyst")
print("You can now run: Option 3 (Analysis Only) in the orchestrator")
