"""Add VMD position to database for Exit Manager monitoring"""
from observability import get_database

db = get_database()

# Add VMD with current price and reasonable profit/stop levels
success = db.add_active_position(
    symbol='VMD',
    quantity=35,
    entry_price=6.84,
    agent_name='day_trader',
    profit_target=6.96,  # +1.8% profit target
    stop_loss=6.78       # -0.9% stop loss
)

print(f"VMD added to database: {success}")
print("\n=== Active Positions Now ===")
for pos in db.get_active_positions():
    print(f"  {pos['symbol']}: {pos['quantity']} shares @ ${pos['entry_price']:.2f}")
    print(f"    TP: ${pos['profit_target_price']:.2f}, SL: ${pos['stop_loss_price']:.2f}")
