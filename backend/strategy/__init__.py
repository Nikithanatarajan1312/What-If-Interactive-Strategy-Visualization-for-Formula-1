"""
Hybrid strategy simulation package.

This package separates:
- feature building
- ML model wrappers
- heuristic fallbacks
- rollout simulation engine
- training-data utilities
"""

from .simulator import simulate_pit_strategy

__all__ = ["simulate_pit_strategy"]
