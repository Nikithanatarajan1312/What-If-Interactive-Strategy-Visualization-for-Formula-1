from __future__ import annotations

import random
from typing import Any, Dict, Optional


def sample_pit_loss_fallback(
    rng: random.Random, mean_loss: float = 22.0, user_override: Optional[float] = None
) -> float:
    base = float(user_override) if user_override is not None else float(mean_loss)
    sigma = max(0.8, base * 0.13)
    for _ in range(40):
        x = rng.gauss(base, sigma)
        if 5.5 <= x <= 50.0:
            return float(x)
    return float(max(5.5, min(50.0, base)))


def heuristic_pace_delta_adjustment(
    *,
    pit_shift: int,
    laps_since_new_pit: int,
    tyre_age_sim: int,
    tyre_age_actual: int,
    compound_sim: str,
    compound_actual: str,
) -> float:
    """
    Residual-style adjustment (seconds on gap delta).

    Negative => improves gap (faster than actual).
    Positive => worsens gap.
    """
    age_term = 0.03 * max(-25, min(25, tyre_age_sim - tyre_age_actual))
    shift_term = 0.02 * max(-20, min(20, pit_shift))
    recover_term = -0.01 * max(0, min(20, laps_since_new_pit))
    comp_bonus = 0.0
    c_sim = str(compound_sim or "").upper()
    c_act = str(compound_actual or "").upper()
    if c_sim == "SOFT" and c_act in {"MEDIUM", "HARD"}:
        comp_bonus -= 0.08
    elif c_sim == "HARD" and c_act == "SOFT":
        comp_bonus += 0.08
    raw = age_term + shift_term + recover_term + comp_bonus
    return max(-1.2, min(1.2, raw))


def estimate_rejoin_penalty(
    *,
    gap_to_leader: Optional[float],
    gap_ahead: Optional[float],
    gap_behind: Optional[float],
    lap_offset_after_pit: int,
) -> float:
    """
    Heuristic traffic/rejoin penalty hook.

    Positive => worse gap for a few laps after rejoin when in tight traffic.
    """
    if lap_offset_after_pit < 0 or lap_offset_after_pit > 4:
        return 0.0
    close_ahead = gap_ahead is not None and abs(gap_ahead) < 1.6
    close_behind = gap_behind is not None and abs(gap_behind) < 1.6
    if close_ahead or close_behind:
        return 0.12 * (4 - lap_offset_after_pit)
    return 0.0


def sample_rollout_noise(rng: random.Random, scale: float = 0.08) -> float:
    return rng.gauss(0.0, max(0.0, scale))
