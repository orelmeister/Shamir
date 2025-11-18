"""
shared_state/state_manager.py

Utility module for thread-safe reading and writing of shared state JSON files.
All weekly bot phases and the day trader use these functions to coordinate.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
import filelock

# File paths
STATE_DIR = Path(__file__).parent
POSITIONS_FILE = STATE_DIR / "positions_state.json"
ORDERS_FILE = STATE_DIR / "orders_state.json"
PHASE_FILE = STATE_DIR / "phase_state.json"
BACKUP_DIR = STATE_DIR / "backup"

# Lock files
POSITIONS_LOCK = STATE_DIR / ".positions_state.lock"
ORDERS_LOCK = STATE_DIR / ".orders_state.lock"
PHASE_LOCK = STATE_DIR / ".phase_state.lock"

LOCK_TIMEOUT = 10  # seconds


class StateManager:
    """Thread-safe manager for shared state JSON files"""
    
    def __init__(self):
        # Ensure backup directory exists
        BACKUP_DIR.mkdir(exist_ok=True)
    
    def _backup_file(self, file_path):
        """Create timestamped backup of state file"""
        if file_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.stem}_{timestamp}.json"
            backup_path = BACKUP_DIR / backup_name
            shutil.copy2(file_path, backup_path)
            
            # Keep only last 10 backups per file
            backups = sorted(BACKUP_DIR.glob(f"{file_path.stem}_*.json"))
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_backup.unlink()
    
    # --- Positions State ---
    
    def get_positions(self, source=None):
        """
        Get all positions, optionally filtered by source.
        
        Args:
            source: "WEEKLY" or "DAY_TRADER" (None = all positions)
        
        Returns:
            list: List of position dicts
        """
        lock = filelock.FileLock(POSITIONS_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                if not POSITIONS_FILE.exists():
                    return []
                
                with open(POSITIONS_FILE, "r") as f:
                    data = json.load(f)
                
                positions = data.get("positions", [])
                
                if source:
                    return [p for p in positions if p.get("source") == source]
                return positions
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {POSITIONS_FILE} (timeout)")
    
    def update_positions(self, positions):
        """
        Update all positions (replaces entire positions array).
        
        Args:
            positions: List of position dicts
        """
        lock = filelock.FileLock(POSITIONS_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                self._backup_file(POSITIONS_FILE)
                
                data = {
                    "positions": positions,
                    "last_updated": datetime.now().isoformat()
                }
                
                with open(POSITIONS_FILE, "w") as f:
                    json.dump(data, f, indent=2)
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {POSITIONS_FILE} (timeout)")
    
    def add_position(self, position):
        """Add a single position to the state"""
        positions = self.get_positions()
        
        # Check if position already exists (by symbol and source)
        existing = next((p for p in positions if p["symbol"] == position["symbol"] and p["source"] == position["source"]), None)
        
        if existing:
            # Update existing position
            positions = [p if not (p["symbol"] == position["symbol"] and p["source"] == position["source"]) else position for p in positions]
        else:
            # Add new position
            positions.append(position)
        
        self.update_positions(positions)
    
    def remove_position(self, symbol, source):
        """Remove a position by symbol and source"""
        positions = self.get_positions()
        positions = [p for p in positions if not (p["symbol"] == symbol and p["source"] == source)]
        self.update_positions(positions)
    
    # --- Orders State ---
    
    def get_orders(self, source=None):
        """Get all pending orders, optionally filtered by source"""
        lock = filelock.FileLock(ORDERS_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                if not ORDERS_FILE.exists():
                    return []
                
                with open(ORDERS_FILE, "r") as f:
                    data = json.load(f)
                
                orders = data.get("pending_orders", [])
                
                if source:
                    return [o for o in orders if o.get("source") == source]
                return orders
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {ORDERS_FILE} (timeout)")
    
    def update_orders(self, orders):
        """Update all orders (replaces entire orders array)"""
        lock = filelock.FileLock(ORDERS_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                self._backup_file(ORDERS_FILE)
                
                data = {
                    "pending_orders": orders,
                    "last_updated": datetime.now().isoformat()
                }
                
                with open(ORDERS_FILE, "w") as f:
                    json.dump(data, f, indent=2)
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {ORDERS_FILE} (timeout)")
    
    def add_order(self, order):
        """Add a single order to the state"""
        orders = self.get_orders()
        
        # Check if order already exists (by order_id)
        existing = next((o for o in orders if o["order_id"] == order["order_id"]), None)
        
        if existing:
            # Update existing order
            orders = [o if o["order_id"] != order["order_id"] else order for o in orders]
        else:
            # Add new order
            orders.append(order)
        
        self.update_orders(orders)
    
    def remove_order(self, order_id):
        """Remove an order by order_id"""
        orders = self.get_orders()
        orders = [o for o in orders if o["order_id"] != order_id]
        self.update_orders(orders)
    
    # --- Phase State ---
    
    def get_phase_state(self):
        """Get current phase state"""
        lock = filelock.FileLock(PHASE_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                if not PHASE_FILE.exists():
                    return {
                        "current_phase": "idle",
                        "phase_history": [],
                        "last_error": None,
                        "halt_requested": False,
                        "last_updated": datetime.now().isoformat()
                    }
                
                with open(PHASE_FILE, "r") as f:
                    return json.load(f)
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {PHASE_FILE} (timeout)")
    
    def update_phase_state(self, current_phase, status, error=None):
        """
        Update phase state.
        
        Args:
            current_phase: Phase name (e.g., "aggregation", "analysis")
            status: "running", "completed", "failed"
            error: Error message if status is "failed"
        """
        lock = filelock.FileLock(PHASE_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                # Read state directly (don't call self.get_phase_state() - would deadlock!)
                if not PHASE_FILE.exists():
                    state = {
                        "current_phase": "idle",
                        "phase_history": [],
                        "last_error": None,
                        "halt_requested": False,
                        "last_updated": datetime.now().isoformat()
                    }
                else:
                    with open(PHASE_FILE, "r") as f:
                        state = json.load(f)
                
                # Add to history
                history_entry = {
                    "phase": current_phase,
                    "status": status,
                    "timestamp": datetime.now().isoformat()
                }
                if error:
                    history_entry["error"] = error
                
                state["phase_history"].append(history_entry)
                state["current_phase"] = current_phase
                state["last_error"] = error
                state["last_updated"] = datetime.now().isoformat()
                
                with open(PHASE_FILE, "w") as f:
                    json.dump(state, f, indent=2)
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {PHASE_FILE} (timeout)")


# --- Convenience Functions (can be imported directly) ---

_state_manager = StateManager()

def get_positions(source=None):
    """Get positions (convenience function)"""
    return _state_manager.get_positions(source)

def update_positions(positions):
    """Update positions (convenience function)"""
    _state_manager.update_positions(positions)

def add_position(position):
    """Add position (convenience function)"""
    _state_manager.add_position(position)

def remove_position(symbol, source):
    """Remove position (convenience function)"""
    _state_manager.remove_position(symbol, source)

def get_orders(source=None):
    """Get orders (convenience function)"""
    return _state_manager.get_orders(source)

def update_orders(orders):
    """Update orders (convenience function)"""
    _state_manager.update_orders(orders)

def add_order(order):
    """Add order (convenience function)"""
    _state_manager.add_order(order)

def remove_order(order_id):
    """Remove order (convenience function)"""
    _state_manager.remove_order(order_id)

def get_phase_state():
    """Get phase state (convenience function)"""
    return _state_manager.get_phase_state()

def update_phase_state(current_phase, status, error=None):
    """Update phase state (convenience function)"""
    _state_manager.update_phase_state(current_phase, status, error)

# Generic read/write functions for backward compatibility
def read_state(filename):
    """
    Generic read function for state files.
    Args:
        filename: 'phase_state', 'positions_state', or 'orders_state'
    Returns:
        dict: State data
    """
    if filename == 'phase_state':
        return get_phase_state()
    elif filename == 'positions_state':
        positions = get_positions()
        return {'positions': positions, 'last_updated': datetime.now().isoformat()}
    elif filename == 'orders_state':
        orders = get_orders()
        return {'orders': orders, 'last_updated': datetime.now().isoformat()}
    else:
        raise ValueError(f"Unknown state file: {filename}")

def write_state(filename, data):
    """
    Generic write function for state files.
    Args:
        filename: 'phase_state', 'positions_state', or 'orders_state'
        data: dict with state data (for phase_state, can include custom keys like stocks_for_analysis)
    """
    if filename == 'phase_state':
        # For phase_state, write custom data directly (like stocks_for_analysis)
        lock = filelock.FileLock(PHASE_LOCK, timeout=LOCK_TIMEOUT)
        try:
            with lock:
                # Read existing state to preserve history
                if PHASE_FILE.exists():
                    with open(PHASE_FILE, "r") as f:
                        state = json.load(f)
                else:
                    state = {
                        "current_phase": "idle",
                        "phase_history": [],
                        "last_error": None,
                        "halt_requested": False
                    }
                
                # Merge new data (allows custom keys like stocks_for_analysis)
                state.update(data)
                state["last_updated"] = datetime.now().isoformat()
                
                # Backup and write
                _state_manager._backup_file(PHASE_FILE)
                with open(PHASE_FILE, "w") as f:
                    json.dump(state, f, indent=2)
        except filelock.Timeout:
            raise RuntimeError(f"Failed to acquire lock on {PHASE_FILE} (timeout)")
    elif filename == 'positions_state':
        positions = data.get('positions', [])
        update_positions(positions)
    elif filename == 'orders_state':
        orders = data.get('orders', [])
        update_orders(orders)
    else:
        raise ValueError(f"Unknown state file: {filename}")
