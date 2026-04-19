from __future__ import annotations

import random
import statistics
from typing import Any, Dict, List, Optional, Tuple

from .features import (
    build_lap_features,
    infer_pit_laps_from_stints,
    infer_team_by_driver,
    map_driver_laps,
    map_driver_trace,
    norm_code,
    to_float,
    to_int,
)
from .heuristics import (
    estimate_rejoin_penalty,
    heuristic_pace_delta_adjustment,
    sample_pit_loss_fallback,
    sample_rollout_noise,
)
from .ml_models import (
    load_pace_model,
    load_pit_loss_model,
    model_available,
    predict_pace_delta,
    predict_pit_loss,
)


def _linear_percentile(sorted_vals: List[float], p: float) -> float:
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_vals[0])
    k = (n - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, n - 1)
    return float(sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f]))


def _stats(samples: List[float]) -> Tuple[float, float, float, float, float]:
    if not samples:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    s = sorted(samples)
    med = float(statistics.median(s))
    return (
        med,
        _linear_percentile(s, 5.0),
        _linear_percentile(s, 25.0),
        _linear_percentile(s, 75.0),
        _linear_percentile(s, 95.0),
    )


def _select_original_pit(orig_pits: List[int], new_pit_lap: int) -> int:
    if not orig_pits:
        return int(new_pit_lap)
    idx = min(range(len(orig_pits)), key=lambda j: abs(new_pit_lap - orig_pits[j]))
    return int(orig_pits[idx])


def _build_actual_driver_series(
    payload: Dict[str, Any], driver: str
) -> Dict[str, Any]:
    laps_clean = payload.get("laps_clean") or []
    race_trace = payload.get("race_trace") or []
    stints_clean = payload.get("stints_clean") or []
    code = norm_code(driver)
    driver_laps = map_driver_laps(laps_clean, code)
    if not driver_laps:
        raise ValueError(f"No laps for driver {code}")

    lap_nums: List[int] = []
    lap_time: Dict[int, float] = {}
    compound: Dict[int, str] = {}
    tyre_age: Dict[int, int] = {}
    stint: Dict[int, int] = {}
    position: Dict[int, Optional[int]] = {}

    for row in driver_laps:
        lap = to_int(row.get("lap"))
        lt = to_float(row.get("lap_time_sec"))
        if lap is None or lt is None:
            continue
        lap_nums.append(lap)
        lap_time[lap] = float(lt)
        compound[lap] = str(row.get("compound") or "MEDIUM").upper()
        tyre_age[lap] = to_int(row.get("tyre_age"), 1) or 1
        stint[lap] = to_int(row.get("stint"), 1) or 1
        position[lap] = to_int(row.get("position"))

    if not lap_nums:
        raise ValueError(f"No valid lap_time rows for driver {code}")
    lap_nums = sorted(set(lap_nums))

    actual_gap = map_driver_trace(race_trace, code)
    if not actual_gap:
        raise ValueError(f"No race_trace rows for driver {code}")
    # Keep only aligned laps.
    actual_gap = {lap: actual_gap.get(lap, 0.0) for lap in lap_nums}

    pit_laps = infer_pit_laps_from_stints(stints_clean, code)
    return {
        "driver_code": code,
        "lap_nums": lap_nums,
        "actual_lap_time_by_lap": lap_time,
        "actual_compound_by_lap": compound,
        "actual_tyre_age_by_lap": tyre_age,
        "actual_stint_by_lap": stint,
        "actual_position_by_lap": position,
        "actual_gap_by_lap": actual_gap,
        "actual_pit_laps": pit_laps,
        "driver_laps_raw": driver_laps,
    }


def _infer_outgoing_compound_at_old_pit(
    actual_compound_by_lap: Dict[int, str], old_pit_lap: int
) -> str:
    if old_pit_lap in actual_compound_by_lap:
        return actual_compound_by_lap[old_pit_lap]
    return "MEDIUM"


def _build_simulated_stint_plan(
    *,
    lap_nums: List[int],
    actual_pit_laps: List[int],
    old_pit_lap: int,
    new_pit_lap: int,
    actual_compound_by_lap: Dict[int, str],
    new_compound: Optional[str],
) -> Dict[str, Any]:
    """
    Move one selected pit event from old->new and rebuild per-lap stint/compound/age.

    Later pit events are preserved at their original laps.
    """
    pits = sorted(actual_pit_laps)
    if not pits:
        pits = [old_pit_lap]
    old_idx = min(range(len(pits)), key=lambda i: abs(pits[i] - old_pit_lap))
    moved_from = pits[old_idx]
    pits[old_idx] = int(new_pit_lap)
    pits = sorted(set(pits))

    # Actual stint compounds in sequence.
    actual_stint_starts = [min(lap_nums)] + sorted(actual_pit_laps)
    compounds_seq: List[str] = []
    for s in actual_stint_starts:
        compounds_seq.append(actual_compound_by_lap.get(s, "MEDIUM"))
    if not compounds_seq:
        compounds_seq = ["MEDIUM"]

    # Apply override on moved pit outgoing stint compound.
    moved_outgoing_idx = min(old_idx + 1, len(compounds_seq) - 1)
    if new_compound:
        compounds_seq[moved_outgoing_idx] = str(new_compound).upper().strip()

    # Sim starts: first lap + simulated pit laps.
    sim_starts = [min(lap_nums)] + pits
    # Ensure compounds length covers all simulated stints.
    while len(compounds_seq) < len(sim_starts):
        compounds_seq.append(compounds_seq[-1])
    compounds_seq = compounds_seq[: len(sim_starts)]

    sim_stint_by_lap: Dict[int, int] = {}
    sim_compound_by_lap: Dict[int, str] = {}
    sim_tyre_age_by_lap: Dict[int, int] = {}
    pit_this_lap: Dict[int, bool] = {lap: False for lap in lap_nums}
    out_lap: Dict[int, bool] = {lap: False for lap in lap_nums}
    laps_since_pit: Dict[int, int] = {}

    pit_set = set(pits)
    for lap in lap_nums:
        if lap in pit_set:
            pit_this_lap[lap] = True
        if lap - 1 in pit_set:
            out_lap[lap] = True
        idx = 0
        for j, st in enumerate(sim_starts):
            if lap >= st:
                idx = j
            else:
                break
        start_lap = sim_starts[idx]
        sim_stint_by_lap[lap] = idx + 1
        sim_compound_by_lap[lap] = compounds_seq[idx]
        sim_tyre_age_by_lap[lap] = max(1, lap - start_lap + 1)
        laps_since_pit[lap] = 0 if pit_this_lap[lap] else max(0, lap - start_lap)

    return {
        "sim_pit_laps": sorted(pits),
        "sim_stint_by_lap": sim_stint_by_lap,
        "sim_compound_by_lap": sim_compound_by_lap,
        "sim_tyre_age_by_lap": sim_tyre_age_by_lap,
        "pit_this_lap": pit_this_lap,
        "out_lap": out_lap,
        "laps_since_pit": laps_since_pit,
        "moved_from_pit_lap": moved_from,
    }


def _build_gap_neighbors(actual_gap_by_lap: Dict[int, float], lap_nums: List[int]) -> Dict[int, Dict[str, float]]:
    out: Dict[int, Dict[str, float]] = {}
    prev = None
    for lap in lap_nums:
        g = actual_gap_by_lap.get(lap)
        if g is None:
            continue
        if prev is None:
            out[lap] = {"gap_ahead": 2.5, "gap_behind": 2.5}
        else:
            out[lap] = {
                "gap_ahead": max(0.0, prev - g),
                "gap_behind": max(0.0, g - prev),
            }
        prev = g
    return out


def _compute_original_pit_loss(
    old_pit_lap: int, actual_lap_time_by_lap: Dict[int, float]
) -> float:
    """
    Compute pit loss once from original pit lap:
    pit_loss = pit_lap_time - median(nearby clean laps).
    """
    pit_lt = actual_lap_time_by_lap.get(old_pit_lap)
    if pit_lt is None:
        return 22.0

    cand_offsets = (-2, -1, +2, +3)
    nearby: List[float] = []
    for off in cand_offsets:
        lap = old_pit_lap + off
        lt = actual_lap_time_by_lap.get(lap)
        if lt is None:
            continue
        if lt <= 0:
            continue
        nearby.append(lt)

    if len(nearby) < 2:
        return 22.0

    med_clean = float(statistics.median(sorted(nearby)))
    est = pit_lt - med_clean
    return max(15.0, min(35.0, float(est)))


def _simulate_lap_times_for_run(
    *,
    meta: Dict[str, Any],
    team: Optional[str],
    code: str,
    lap_nums: List[int],
    total_laps: int,
    old_pit_lap: int,
    new_pit_lap: int,
    pit_shift: int,
    actual_lap_time_by_lap: Dict[int, float],
    actual_compound_by_lap: Dict[int, str],
    actual_tyre_age_by_lap: Dict[int, int],
    actual_stint_by_lap: Dict[int, int],
    actual_position_by_lap: Dict[int, Optional[int]],
    actual_gap_by_lap: Dict[int, float],
    sim_plan: Dict[str, Any],
    pace_model: Any,
    model_is_available: bool,
    pit_loss_draw: float,
    out_lap_penalty_draw: float,
    rng: random.Random,
    n_mc: int,
) -> Dict[str, Any]:
    """
    Simulate lap times directly.

    sim_lap_time = actual_lap_time
                 + pit_penalty
                 + out_lap_penalty
                 + tyre_state_delta
                 + traffic_penalty
                 + stochastic_noise
    """
    neighbors = _build_gap_neighbors(actual_gap_by_lap, lap_nums)
    sim_lap_time_by_lap: Dict[int, float] = {}
    lap_delta_by_lap: Dict[int, float] = {}
    pit_component_by_lap: Dict[int, float] = {}
    pace_component_by_lap: Dict[int, float] = {}
    traffic_component_by_lap: Dict[int, float] = {}

    for lap in lap_nums:
        actual_lt = actual_lap_time_by_lap[lap]
        actual_comp = actual_compound_by_lap[lap]
        actual_age = actual_tyre_age_by_lap[lap]
        actual_stint = actual_stint_by_lap[lap]
        actual_gap = actual_gap_by_lap.get(lap, 0.0)

        sim_comp = sim_plan["sim_compound_by_lap"][lap]
        sim_age = sim_plan["sim_tyre_age_by_lap"][lap]
        sim_stint = sim_plan["sim_stint_by_lap"][lap]
        pit_this_lap = bool(sim_plan["pit_this_lap"][lap])
        out_lap = bool(sim_plan["out_lap"][lap])
        laps_since_pit = int(sim_plan["laps_since_pit"][lap])

        # Gate strategy-effect interval:
        # - later stop: effects begin at old pit lap (when actual had stopped but sim did not)
        # - earlier stop: effects begin at new pit lap (when sim stops before actual)
        if pit_shift > 0:
            strategy_effect_active = lap >= old_pit_lap
        elif pit_shift < 0:
            strategy_effect_active = lap >= new_pit_lap
        else:
            strategy_effect_active = False

        # Hard clamp: before divergence window, keep simulation identical to actual.
        if not strategy_effect_active:
            lap_delta_by_lap[lap] = 0.0
            sim_lap_time_by_lap[lap] = actual_lt
            pit_component_by_lap[lap] = 0.0
            pace_component_by_lap[lap] = 0.0
            traffic_component_by_lap[lap] = 0.0
            continue

        gap_ahead = neighbors.get(lap, {}).get("gap_ahead", 2.5)
        gap_behind = neighbors.get(lap, {}).get("gap_behind", 2.5)
        position = actual_position_by_lap.get(lap)

        _, sim_vec = build_lap_features(
            meta=meta,
            driver=code,
            team=team,
            lap_number=lap,
            total_laps=total_laps,
            stint_number=sim_stint,
            tyre_compound=sim_comp,
            tyre_age=sim_age,
            gap_to_leader=actual_gap,
            gap_ahead=gap_ahead,
            gap_behind=gap_behind,
            position=position,
            pit_this_lap=pit_this_lap,
            is_in_lap=pit_this_lap,
            is_out_lap=out_lap,
            laps_since_pit=laps_since_pit,
            original_pit_lap=old_pit_lap,
            simulated_pit_lap=new_pit_lap,
            pit_shift=pit_shift,
            safety_car_flag=0,
            vsc_flag=0,
        )
        _, act_vec = build_lap_features(
            meta=meta,
            driver=code,
            team=team,
            lap_number=lap,
            total_laps=total_laps,
            stint_number=actual_stint,
            tyre_compound=actual_comp,
            tyre_age=actual_age,
            gap_to_leader=actual_gap,
            gap_ahead=gap_ahead,
            gap_behind=gap_behind,
            position=position,
            pit_this_lap=(lap == old_pit_lap),
            is_in_lap=(lap == old_pit_lap),
            is_out_lap=(lap == old_pit_lap + 1),
            laps_since_pit=actual_age,
            original_pit_lap=old_pit_lap,
            simulated_pit_lap=old_pit_lap,
            pit_shift=0,
            safety_car_flag=0,
            vsc_flag=0,
        )

        pit_penalty = 0.0
        if strategy_effect_active and new_pit_lap != old_pit_lap:
            if lap == new_pit_lap:
                pit_penalty += pit_loss_draw
            if lap == old_pit_lap:
                pit_penalty -= pit_loss_draw
            if lap == new_pit_lap + 1:
                pit_penalty += out_lap_penalty_draw
            if lap == old_pit_lap + 1:
                pit_penalty -= out_lap_penalty_draw

        if strategy_effect_active:
            if model_is_available:
                pred_sim = predict_pace_delta(pace_model, sim_vec)
                pred_act = predict_pace_delta(pace_model, act_vec)
                if pred_sim is not None and pred_act is not None:
                    tyre_state_delta = pred_sim - pred_act
                else:
                    tyre_state_delta = heuristic_pace_delta_adjustment(
                        pit_shift=pit_shift,
                        laps_since_new_pit=max(0, lap - new_pit_lap),
                        tyre_age_sim=sim_age,
                        tyre_age_actual=actual_age,
                        compound_sim=sim_comp,
                        compound_actual=actual_comp,
                    )
            else:
                tyre_state_delta = heuristic_pace_delta_adjustment(
                    pit_shift=pit_shift,
                    laps_since_new_pit=max(0, lap - new_pit_lap),
                    tyre_age_sim=sim_age,
                    tyre_age_actual=actual_age,
                    compound_sim=sim_comp,
                    compound_actual=actual_comp,
                )
        else:
            tyre_state_delta = 0.0

        if n_mc > 1 and strategy_effect_active:
            tyre_state_delta *= rng.uniform(0.9, 1.1)
        tyre_state_delta *= 0.5
        tyre_state_delta = max(-1.0, min(1.0, tyre_state_delta))

        # Temporary rejoin effect around moved pit only, and remove old rejoin effect.
        traffic_pen = 0.0
        if strategy_effect_active:
            traffic_pen = estimate_rejoin_penalty(
                gap_to_leader=actual_gap,
                gap_ahead=gap_ahead,
                gap_behind=gap_behind,
                lap_offset_after_pit=max(0, lap - new_pit_lap),
            )
            if new_pit_lap != old_pit_lap:
                traffic_pen -= estimate_rejoin_penalty(
                    gap_to_leader=actual_gap,
                    gap_ahead=gap_ahead,
                    gap_behind=gap_behind,
                    lap_offset_after_pit=max(0, lap - old_pit_lap),
                )

        noise = 0.0 if (n_mc == 1 or not strategy_effect_active) else sample_rollout_noise(rng, scale=0.08)
        sim_lt = actual_lt + pit_penalty + tyre_state_delta + traffic_pen + noise
        sim_lt = max(55.0, sim_lt)
        sim_lap_time_by_lap[lap] = sim_lt
        lap_delta_by_lap[lap] = sim_lt - actual_lt
        pit_component_by_lap[lap] = pit_penalty
        pace_component_by_lap[lap] = tyre_state_delta
        traffic_component_by_lap[lap] = traffic_pen

    return {
        "sim_lap_time_by_lap": sim_lap_time_by_lap,
        "lap_delta_by_lap": lap_delta_by_lap,
        "pit_component_by_lap": pit_component_by_lap,
        "pace_component_by_lap": pace_component_by_lap,
        "traffic_component_by_lap": traffic_component_by_lap,
    }


def _reconstruct_gap_trace_from_lap_deltas(
    *,
    lap_nums: List[int],
    actual_gap_by_lap: Dict[int, float],
    lap_delta_by_lap: Dict[int, float],
) -> Dict[int, float]:
    cumulative_delta = 0.0
    sim_gap_by_lap: Dict[int, float] = {}
    for lap in lap_nums:
        cumulative_delta += lap_delta_by_lap.get(lap, 0.0)
        sim_gap_by_lap[lap] = actual_gap_by_lap.get(lap, 0.0) + cumulative_delta
    return sim_gap_by_lap


def _build_simulated_lap_rows(
    *,
    lap_nums: List[int],
    actual_lap_time_by_lap: Dict[int, float],
    sim_lap_time_by_lap: Dict[int, float],
    actual_compound_by_lap: Dict[int, str],
    actual_tyre_age_by_lap: Dict[int, int],
    sim_plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for lap in lap_nums:
        actual_lt = actual_lap_time_by_lap[lap]
        sim_lt = sim_lap_time_by_lap[lap]
        out.append(
            {
                "lap": lap,
                "actual_lap_time_sec": actual_lt,
                "simulated_lap_time_sec": sim_lt,
                "actual_compound": actual_compound_by_lap[lap],
                "simulated_compound": sim_plan["sim_compound_by_lap"][lap],
                "actual_tyre_age": actual_tyre_age_by_lap[lap],
                "simulated_tyre_age": sim_plan["sim_tyre_age_by_lap"][lap],
                "pit_this_lap": bool(sim_plan["pit_this_lap"][lap]),
                "out_lap": bool(sim_plan["out_lap"][lap]),
                "lap_delta_sec": sim_lt - actual_lt,
                # Backward compatibility fields consumed by adapter.
                "compound": sim_plan["sim_compound_by_lap"][lap],
                "simulated_tyre_age": sim_plan["sim_tyre_age_by_lap"][lap],
            }
        )
    return out


def simulate_gap_trace_hybrid(
    *,
    payload: Dict[str, Any],
    driver: str,
    new_pit_lap: int,
    new_compound: Optional[str],
    pit_loss_sec: Optional[float],
    monte_carlo_samples: int,
    random_seed: Optional[int],
    use_ml: bool,
) -> Dict[str, Any]:
    """
    Hybrid simulator with LAP-TIME-FIRST rollout.

    Core:
      lap_delta[lap] = sim_lap_time[lap] - actual_lap_time[lap]
      sim_gap[lap] = actual_gap[lap] + cumulative_sum(lap_delta[:lap])
    """
    meta = payload.get("meta") or {}
    series = _build_actual_driver_series(payload, driver)
    code = series["driver_code"]
    lap_nums = series["lap_nums"]
    total_laps = max(lap_nums)
    actual_lap_time_by_lap = series["actual_lap_time_by_lap"]
    actual_compound_by_lap = series["actual_compound_by_lap"]
    actual_tyre_age_by_lap = series["actual_tyre_age_by_lap"]
    actual_stint_by_lap = series["actual_stint_by_lap"]
    actual_position_by_lap = series["actual_position_by_lap"]
    actual_gap_by_lap = series["actual_gap_by_lap"]
    actual_pit_laps = series["actual_pit_laps"]

    if not actual_pit_laps:
        raise ValueError(f"No pit stops in stints data for {code}")

    old_pit_lap = _select_original_pit(actual_pit_laps, int(new_pit_lap))
    pit_shift = int(new_pit_lap - old_pit_lap)
    chosen_compound = (
        str(new_compound).upper().strip()
        if new_compound
        else _infer_outgoing_compound_at_old_pit(actual_compound_by_lap, old_pit_lap)
    )

    sim_plan = _build_simulated_stint_plan(
        lap_nums=lap_nums,
        actual_pit_laps=actual_pit_laps,
        old_pit_lap=old_pit_lap,
        new_pit_lap=int(new_pit_lap),
        actual_compound_by_lap=actual_compound_by_lap,
        new_compound=chosen_compound,
    )

    n_mc = int(monte_carlo_samples)
    if n_mc < 1:
        raise ValueError("monte_carlo_samples must be >= 1")
    if n_mc > 500:
        raise ValueError("monte_carlo_samples must be <= 500")

    teams = infer_team_by_driver(payload.get("laps_clean") or [])
    team = teams.get(code)

    pace_model = load_pace_model() if use_ml else None
    pit_model = load_pit_loss_model() if use_ml else None
    pace_model_available = model_available(pace_model)
    pit_model_available = model_available(pit_model)
    rng = random.Random(random_seed)
    base_pit_loss = _compute_original_pit_loss(old_pit_lap, actual_lap_time_by_lap)

    gap_samples_by_lap: Dict[int, List[float]] = {lap: [] for lap in lap_nums}
    lap_time_samples_by_lap: Dict[int, List[float]] = {lap: [] for lap in lap_nums}
    pit_component_totals: List[float] = []
    pace_component_totals: List[float] = []
    traffic_component_totals: List[float] = []

    for _ in range(n_mc):
        # Pit-loss prediction hook (new pit lap context) with fallback.
        _, pit_vec = build_lap_features(
            meta=meta,
            driver=code,
            team=team,
            lap_number=int(new_pit_lap),
            total_laps=total_laps,
            stint_number=sim_plan["sim_stint_by_lap"].get(int(new_pit_lap), 2),
            tyre_compound=sim_plan["sim_compound_by_lap"].get(int(new_pit_lap), chosen_compound),
            tyre_age=sim_plan["sim_tyre_age_by_lap"].get(int(new_pit_lap), 1),
            gap_to_leader=actual_gap_by_lap.get(int(new_pit_lap), 0.0),
            gap_ahead=2.5,
            gap_behind=2.5,
            position=actual_position_by_lap.get(int(new_pit_lap)),
            pit_this_lap=True,
            is_in_lap=True,
            is_out_lap=False,
            laps_since_pit=0,
            original_pit_lap=old_pit_lap,
            simulated_pit_lap=int(new_pit_lap),
            pit_shift=pit_shift,
            safety_car_flag=0,
            vsc_flag=0,
        )
        # Use one stable pit-loss basis from original pit event.
        # User override still takes precedence.
        if pit_loss_sec is not None:
            pit_loss_draw = float(pit_loss_sec)
        else:
            pit_loss_draw = float(base_pit_loss)
            if n_mc > 1:
                # ±10% Monte Carlo spread around original pit-loss basis.
                pit_loss_draw *= rng.uniform(0.9, 1.1)
        out_lap_penalty_draw = 0.0 if n_mc == 1 else rng.uniform(0.8, 2.2)
        if pit_loss_sec is not None and n_mc == 1:
            out_lap_penalty_draw = min(3.0, max(0.8, 0.08 * pit_loss_sec))

        run = _simulate_lap_times_for_run(
            meta=meta,
            team=team,
            code=code,
            lap_nums=lap_nums,
            total_laps=total_laps,
            old_pit_lap=old_pit_lap,
            new_pit_lap=int(new_pit_lap),
            pit_shift=pit_shift,
            actual_lap_time_by_lap=actual_lap_time_by_lap,
            actual_compound_by_lap=actual_compound_by_lap,
            actual_tyre_age_by_lap=actual_tyre_age_by_lap,
            actual_stint_by_lap=actual_stint_by_lap,
            actual_position_by_lap=actual_position_by_lap,
            actual_gap_by_lap=actual_gap_by_lap,
            sim_plan=sim_plan,
            pace_model=pace_model,
            model_is_available=pace_model_available and bool(use_ml),
            pit_loss_draw=pit_loss_draw,
            out_lap_penalty_draw=out_lap_penalty_draw,
            rng=rng,
            n_mc=n_mc,
        )
        run_sim_gap = _reconstruct_gap_trace_from_lap_deltas(
            lap_nums=lap_nums,
            actual_gap_by_lap=actual_gap_by_lap,
            lap_delta_by_lap=run["lap_delta_by_lap"],
        )
        for lap in lap_nums:
            gap_samples_by_lap[lap].append(run_sim_gap[lap])
            lap_time_samples_by_lap[lap].append(run["sim_lap_time_by_lap"][lap])
        pit_component_totals.append(sum(run["pit_component_by_lap"].values()))
        pace_component_totals.append(sum(run["pace_component_by_lap"].values()))
        traffic_component_totals.append(sum(run["traffic_component_by_lap"].values()))

    # Aggregate MC gap percentiles (main line = median).
    simulated_trace: List[Dict[str, Any]] = []
    median_gap_by_lap: Dict[int, float] = {}
    for lap in lap_nums:
        med, p5, p25, p75, p95 = _stats(gap_samples_by_lap[lap])
        if n_mc == 1:
            p5 = p25 = p75 = p95 = med
        simulated_trace.append(
            {
                "lap": lap,
                "simulated_gap_to_leader": med,
                "p5": p5,
                "p25": p25,
                "p75": p75,
                "p95": p95,
            }
        )
        median_gap_by_lap[lap] = med

    # Build one lap-time rollout consistent with the published median gap line.
    # cumulative_delta = sim_gap - actual_gap => lap_delta from cumulative differences.
    median_lap_delta_by_lap: Dict[int, float] = {}
    prev_cum = 0.0
    for lap in lap_nums:
        cum = median_gap_by_lap[lap] - actual_gap_by_lap.get(lap, 0.0)
        median_lap_delta_by_lap[lap] = cum - prev_cum
        prev_cum = cum
    median_sim_lap_time_by_lap = {
        lap: actual_lap_time_by_lap[lap] + median_lap_delta_by_lap[lap]
        for lap in lap_nums
    }

    simulated_laps = _build_simulated_lap_rows(
        lap_nums=lap_nums,
        actual_lap_time_by_lap=actual_lap_time_by_lap,
        sim_lap_time_by_lap=median_sim_lap_time_by_lap,
        actual_compound_by_lap=actual_compound_by_lap,
        actual_tyre_age_by_lap=actual_tyre_age_by_lap,
        sim_plan=sim_plan,
    )

    actual_trace = [
        {"lap": lap, "gap_to_leader": actual_gap_by_lap.get(lap, 0.0)}
        for lap in lap_nums
    ]

    ml_used = bool(use_ml and pace_model_available)
    simulation_mode = "hybrid_ml" if ml_used else "heuristic"
    last_lap_num = lap_nums[-1]
    actual_final_gap = actual_gap_by_lap.get(last_lap_num, 0.0)
    simulated_final_gap = median_gap_by_lap.get(last_lap_num, actual_final_gap)
    # + = better (closer to leader): smaller simulated gap behind the leader.
    delta_gap = actual_final_gap - simulated_final_gap

    # Internal rollout sums lap-time deltas (+ => slower lap => worse gap). For the same
    # convention as the pit-window heatmap, flip to gap *gain* seconds: gain = -lap_time_effect.
    gain_pit_samples = [-float(x) for x in pit_component_totals]
    gain_pace_samples = [-float(x) for x in pace_component_totals]
    gain_traffic_samples = [-float(x) for x in traffic_component_totals]

    pit_gain_med = float(statistics.median(gain_pit_samples)) if gain_pit_samples else 0.0
    pace_gain_med = float(statistics.median(gain_pace_samples)) if gain_pace_samples else 0.0
    traffic_gain_med = (
        float(statistics.median(gain_traffic_samples)) if gain_traffic_samples else 0.0
    )
    # Median-of-gains can disagree slightly with median(sim gap); absorb in pace so bars sum to total.
    residual = float(delta_gap) - (pit_gain_med + pace_gain_med + traffic_gain_med)
    pace_gain_med += residual
    return {
        "driver": code,
        "new_pit_lap": int(new_pit_lap),
        "old_pit_lap": int(old_pit_lap),
        "pit_shift": int(pit_shift),
        "monte_carlo_samples": int(n_mc),
        "simulation_mode": simulation_mode,
        "model_available": pace_model_available,
        "pit_loss_model_available": pit_model_available,
        "fallback_used": not ml_used,
        "simulation_basis": "lap_time_reconstruction",
        "actual_final_gap": actual_final_gap,
        "simulated_final_gap": simulated_final_gap,
        "delta_gap": delta_gap,
        "delta_breakdown": {
            "total": delta_gap,
            "components": [
                {"label": "Pit stop effect", "value": pit_gain_med, "color": "#ff6b6b"},
                {"label": "Pace / tyre effect", "value": pace_gain_med, "color": "#ffbf40"},
                {"label": "Traffic / rejoin effect", "value": traffic_gain_med, "color": "#818cf8"},
            ],
        },
        "actual_trace": actual_trace,
        "simulated_trace": simulated_trace,
        "simulated_laps": simulated_laps,
    }


def simulate_pit_strategy(
    payload: Dict[str, Any],
    *,
    driver: str,
    new_pit_lap: int,
    new_compound: Optional[str] = None,
    pit_loss_sec: Optional[float] = None,
    monte_carlo_samples: int = 100,
    random_seed: Optional[int] = None,
    use_ml: bool = True,
) -> Dict[str, Any]:
    """
    Backward-compatible entrypoint used by API.
    """
    return simulate_gap_trace_hybrid(
        payload=payload,
        driver=driver,
        new_pit_lap=new_pit_lap,
        new_compound=new_compound,
        pit_loss_sec=pit_loss_sec,
        monte_carlo_samples=monte_carlo_samples,
        random_seed=random_seed,
        use_ml=use_ml,
    )
