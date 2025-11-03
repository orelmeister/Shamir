# Shared State JSON Files

This directory contains the **single source of truth** for position and order coordination between the weekly bot and day trader.

## Files

### `positions_state.json`
Tracks all open positions with full metadata.

**Schema:**
```json
{
  "positions": [
    {
      "symbol": "AAPL",
      "quantity": 10,
      "entry_price": 150.25,
      "entry_date": "2025-11-03T09:30:00",
      "stop_loss": 135.23,
      "trailing_stop": null,
      "trailing_stop_trigger": 180.30,
      "source": "WEEKLY",
      "metadata": {
        "confidence_score": 0.85,
        "sector": "Technology",
        "last_sync": "2025-11-03T10:00:00"
      }
    }
  ],
  "last_updated": "2025-11-03T10:00:00"
}
```

**Fields:**
- `source`: "WEEKLY" or "DAY_TRADER" (determines which bot manages it)
- `stop_loss`: Hard stop loss price
- `trailing_stop`: Current trailing stop price (null if not activated)
- `trailing_stop_trigger`: Price that activates trailing stop

### `orders_state.json`
Tracks all pending orders (MOO, limit, bracket, etc).

**Schema:**
```json
{
  "pending_orders": [
    {
      "order_id": "12345",
      "symbol": "TSLA",
      "action": "BUY",
      "quantity": 5,
      "order_type": "MOO",
      "limit_price": null,
      "status": "PreSubmitted",
      "placed_at": "2025-11-03T09:00:00",
      "source": "WEEKLY",
      "parent_order_id": null
    }
  ],
  "last_updated": "2025-11-03T09:00:00"
}
```

### `phase_state.json`
Tracks current phase execution state (replaces trading_queue.json).

**Schema:**
```json
{
  "current_phase": "monitoring",
  "phase_history": [
    {"phase": "aggregation", "status": "completed", "timestamp": "2025-11-03T07:00:00"},
    {"phase": "analysis", "status": "completed", "timestamp": "2025-11-03T07:30:00"},
    {"phase": "portfolio_management", "status": "completed", "timestamp": "2025-11-03T09:30:00"},
    {"phase": "monitoring", "status": "running", "timestamp": "2025-11-03T09:35:00"}
  ],
  "last_error": null,
  "halt_requested": false,
  "last_updated": "2025-11-03T09:35:00"
}
```

## Usage

### Reading Positions (Both Bots)
```python
import json

def get_positions(source=None):
    with open("shared_state/positions_state.json", "r") as f:
        data = json.load(f)
    
    if source:
        return [p for p in data["positions"] if p["source"] == source]
    return data["positions"]

# Get only weekly positions
weekly_positions = get_positions(source="WEEKLY")
```

### Writing Positions (Thread-Safe)
```python
import json
import filelock

LOCK_FILE = "shared_state/.positions_state.lock"

def update_positions(new_positions):
    lock = filelock.FileLock(LOCK_FILE)
    with lock:
        with open("shared_state/positions_state.json", "r+") as f:
            data = json.load(f)
            data["positions"] = new_positions
            data["last_updated"] = datetime.now().isoformat()
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
```

### Syncing from IBKR
```python
# Run standalone utility to sync current IBKR positions
python sync_positions_from_ibkr.py
```

## Safety Guarantees

1. **File Locking**: Use `filelock` library to prevent concurrent writes
2. **Atomic Updates**: Always read → modify → write in locked section
3. **Validation**: Each script validates JSON schema before reading
4. **Backup**: Old state files moved to `shared_state/backup/` on each update
5. **Recovery**: If JSON is corrupted, restore from latest backup

## Dependencies

```bash
pip install filelock
```
