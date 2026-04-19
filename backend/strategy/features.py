from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def norm_code(value: Any) -> str:
    return str(value or "").strip().upper()


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        n = float(value)
        if not math.isfinite(n):
            return default
        return n
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    f = to_float(value, None)
    if f is None:
        return default
    return int(round(f))


def map_driver_laps(laps_clean: List[Dict[str, Any]], driver: str) -> List[Dict[str, Any]]:
    code = norm_code(driver)
    rows = [r for r in laps_clean if norm_code(r.get("driver")) == code]
    return sorted(rows, key=lambda r: to_float(r.get("lap"), 0.0) or 0.0)


def map_driver_trace(race_trace: List[Dict[str, Any]], driver: str) -> Dict[int, float]:
    code = norm_code(driver)
    out: Dict[int, float] = {}
    for row in race_trace:
        if norm_code(row.get("driver")) != code:
            continue
        lap = to_int(row.get("lap"))
        gap = to_float(row.get("gap_to_leader"))
        if lap is None or gap is None:
            continue
        out[lap] = gap
    return out


def infer_pit_laps_from_stints(stints_clean: List[Dict[str, Any]], driver: str) -> List[int]:
    code = norm_code(driver)
    rows = [r for r in stints_clean if norm_code(r.get("driver")) == code]
    by_stint: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        stint = to_int(r.get("stint"), 0) or 0
        by_stint[stint] = r
    out: List[int] = []
    for stint in sorted(by_stint.keys()):
        if stint <= 1:
            continue
        start_lap = to_int(by_stint[stint].get("start_lap"))
        if start_lap is not None:
            out.append(start_lap)
    return sorted(out)


def infer_team_by_driver(laps_clean: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """
    Team is often unavailable in cached payloads; keep hook.
    """
    out: Dict[str, Optional[str]] = {}
    for row in laps_clean:
        code = norm_code(row.get("driver"))
        if not code:
            continue
        if code in out:
            continue
        team = row.get("team")
        out[code] = str(team) if team else None
    return out


def build_lap_features(
    *,
    meta: Dict[str, Any],
    driver: str,
    team: Optional[str],
    lap_number: int,
    total_laps: int,
    stint_number: int,
    tyre_compound: str,
    tyre_age: int,
    gap_to_leader: Optional[float],
    gap_ahead: Optional[float],
    gap_behind: Optional[float],
    position: Optional[int],
    pit_this_lap: bool,
    is_in_lap: bool,
    is_out_lap: bool,
    laps_since_pit: int,
    original_pit_lap: int,
    simulated_pit_lap: int,
    pit_shift: int,
    safety_car_flag: int,
    vsc_flag: int,
) -> Tuple[Dict[str, Any], List[float]]:
    """
    Returns (raw feature dict, model-ready numeric vector).

    Numeric vector keeps encoding simple and robust for lightweight tabular models.
    Categorical hashes are coarse placeholders until one-hot/target encoding is introduced.
    """
    year = to_int(meta.get("year"), 0) or 0
    race_name = str(meta.get("resolved_event_name") or meta.get("requested_grand_prix") or "")
    race_hash = float(abs(hash(race_name)) % 10000)
    driver_hash = float(abs(hash(norm_code(driver))) % 10000)
    team_hash = float(abs(hash(team)) % 10000) if team else 0.0
    comp = str(tyre_compound or "UNKNOWN").upper()
    comp_map = {"SOFT": 0.0, "MEDIUM": 1.0, "HARD": 2.0, "INTERMEDIATE": 3.0, "WET": 4.0}
    comp_val = comp_map.get(comp, 9.0)

    laps_remaining = max(0, total_laps - lap_number)
    phase_before_old = 1 if lap_number < original_pit_lap else 0
    phase_between = 1 if simulated_pit_lap <= lap_number < original_pit_lap else 0
    phase_after_new = 1 if lap_number >= simulated_pit_lap else 0

    raw = {
        "year": year,
        "race_name": race_name,
        "driver": norm_code(driver),
        "team": team,
        "lap_number": lap_number,
        "laps_remaining": laps_remaining,
        "stint_number": stint_number,
        "tyre_compound": comp,
        "tyre_age": tyre_age,
        "is_out_lap": int(bool(is_out_lap)),
        "is_in_lap": int(bool(is_in_lap)),
        "gap_to_leader": gap_to_leader,
        "gap_ahead": gap_ahead,
        "gap_behind": gap_behind,
        "position": position,
        "pit_this_lap": int(bool(pit_this_lap)),
        "laps_since_pit": laps_since_pit,
        "original_pit_lap": original_pit_lap,
        "simulated_pit_lap": simulated_pit_lap,
        "pit_shift": pit_shift,
        "safety_car_flag": safety_car_flag,
        "vsc_flag": vsc_flag,
        "phase_before_old_pit": phase_before_old,
        "phase_between_new_old": phase_between,
        "phase_after_new_pit": phase_after_new,
    }

    vector = [
        float(year),
        race_hash,
        driver_hash,
        team_hash,
        float(lap_number),
        float(laps_remaining),
        float(stint_number),
        comp_val,
        float(tyre_age),
        float(raw["is_out_lap"]),
        float(raw["is_in_lap"]),
        float(gap_to_leader if gap_to_leader is not None else 0.0),
        float(gap_ahead if gap_ahead is not None else 0.0),
        float(gap_behind if gap_behind is not None else 0.0),
        float(position if position is not None else 0.0),
        float(raw["pit_this_lap"]),
        float(laps_since_pit),
        float(original_pit_lap),
        float(simulated_pit_lap),
        float(pit_shift),
        float(safety_car_flag),
        float(vsc_flag),
        float(phase_before_old),
        float(phase_between),
        float(phase_after_new),
    ]
    return raw, vector
