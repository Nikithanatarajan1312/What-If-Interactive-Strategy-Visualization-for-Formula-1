"""
Compatibility shim.

Public import path stays ``backend.simulator.simulate_pit_strategy`` while
implementation now lives under ``backend.strategy.simulator``.
"""

from __future__ import annotations

try:
    from .strategy.simulator import simulate_pit_strategy
except ImportError:
    from strategy.simulator import simulate_pit_strategy
