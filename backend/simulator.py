"""
Rule-based pit what-if: adjust one pit lap + optional compound / pit loss.

Expected by ``POST /api/simulate`` / frontend ``simulateToViewModel``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _norm_driver(d: str) -> str:
    return str(d or "").strip().upper()


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Like float(v) but treats None / bad values as default."""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _pit_laps_from_stints(stints_clean: List[Dict[str, Any]], driver: str) -> List[int]:
    """First lap of each stint after the first (pit-in laps)."""
    code = _norm_driver(driver)
    rows = [r for r in stints_clean if _norm_driver(r.get("driver", "")) == code]
    by_stint: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        st = int(float(r.get("stint", 0) or 0))
        by_stint[st] = r
    out: List[int] = []
    for st in sorted(by_stint.keys()):
        if st <= 1:
            continue
        out.append(int(round(float(by_stint[st]["start_lap"]))))
    return sorted(out)


def simulate_pit_strategy(
    payload: Dict[str, Any],
    *,
    driver: str,
    new_pit_lap: int,
    new_compound: Optional[str] = None,
    pit_loss_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build ``actual_trace``, ``simulated_trace``, ``simulated_laps`` for one driver.

    Picks which original pit is being moved by closest lap to ``new_pit_lap``
    (matches frontend ``diffPitChange`` one-pit-at-a-time edits).
    """
    driver_u = _norm_driver(driver)
    if not driver_u:
        raise ValueError("driver is required")

    laps_clean = payload.get("laps_clean") or []
    race_trace = payload.get("race_trace") or []
    stints_clean = payload.get("stints_clean") or []

    driver_laps = sorted(
        (
            r
            for r in laps_clean
            if _norm_driver(r.get("driver", "")) == driver_u
        ),
        key=lambda r: float(r.get("lap", 0)),
    )
    if not driver_laps:
        raise ValueError(f"No laps for driver {driver_u}")

    gap_by_lap: Dict[int, float] = {}
    for r in race_trace:
        if _norm_driver(r.get("driver", "")) != driver_u:
            continue
        lap = int(round(float(r.get("lap", 0))))
        gap_by_lap[lap] = _safe_float(r.get("gap_to_leader"), 0.0)

    orig_pits = _pit_laps_from_stints(stints_clean, driver_u)
    if not orig_pits:
        raise ValueError(f"No pit stops in stints data for {driver_u}")

    pit_idx = min(range(len(orig_pits)), key=lambda j: abs(new_pit_lap - orig_pits[j]))
    old_pit_lap = orig_pits[pit_idx]

    loss = float(pit_loss_sec) if pit_loss_sec is not None else 22.0
    if loss <= 0:
        raise ValueError("pit_loss_sec must be positive")

    # Compound on the lap after original pit (first lap of next stint)
    compound_after_old = "MEDIUM"
    for r in driver_laps:
        lap = int(round(float(r.get("lap", 0))))
        if lap >= old_pit_lap:
            compound_after_old = str(r.get("compound") or "MEDIUM").upper()
            break
    compound_use = (new_compound or compound_after_old).strip().upper()

    actual_trace: List[Dict[str, Any]] = []
    simulated_trace: List[Dict[str, Any]] = []
    simulated_laps: List[Dict[str, Any]] = []

    shift = new_pit_lap - old_pit_lap
    # Simple deg model: seconds per lap "cost" when pit is delayed (extra laps on old rubber)
    deg_per_lap = 0.04

    for r in driver_laps:
        lap = int(round(float(r.get("lap", 0))))
        lt = _safe_float(r.get("lap_time_sec"), 0.0)
        comp = str(r.get("compound") or "MEDIUM").upper()
        tyre_age = int(round(float(r.get("tyre_age") or 1)))

        act_gap = gap_by_lap.get(lap, 0.0)
        actual_trace.append({"lap": lap, "gap_to_leader": act_gap})

        sim_lt = lt
        sim_comp = comp
        sim_age = tyre_age
        sim_gap = act_gap

        if lap == new_pit_lap:
            sim_lt = lt + loss
            sim_comp = compound_use
            sim_age = 1
            sim_gap = act_gap + loss
        elif lap > new_pit_lap:
            # After the new stop: nudge gap slightly vs actual based on early/late stop
            if shift != 0:
                sim_gap = act_gap + deg_per_lap * shift * min(lap - new_pit_lap, 15)

        simulated_trace.append({"lap": lap, "simulated_gap_to_leader": sim_gap})
        simulated_laps.append(
            {
                "lap": lap,
                "simulated_lap_time_sec": sim_lt,
                "compound": sim_comp,
                "simulated_tyre_age": sim_age,
            }
        )

    return {
        "driver": driver_u,
        "new_pit_lap": int(new_pit_lap),
        "old_pit_lap": old_pit_lap,
        "actual_trace": actual_trace,
        "simulated_trace": simulated_trace,
        "simulated_laps": simulated_laps,
    }
