"""
shared_state package

Thread-safe state management for weekly bot and day trader coordination.
"""

from .state_manager import (
    StateManager,
    get_positions,
    update_positions,
    add_position,
    remove_position,
    get_orders,
    update_orders,
    add_order,
    remove_order,
    get_phase_state,
    update_phase_state
)

__all__ = [
    'StateManager',
    'get_positions',
    'update_positions',
    'add_position',
    'remove_position',
    'get_orders',
    'update_orders',
    'add_order',
    'remove_order',
    'get_phase_state',
    'update_phase_state'
]
