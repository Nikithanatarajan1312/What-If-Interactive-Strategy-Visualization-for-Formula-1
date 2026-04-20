"""Shared strategy visualization model driven by the simulator."""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

try:
    from .simulator import simulate_pit_strategy
except ImportError:
    from simulator import simulate_pit_strategy

def _norm_code(c: str) -> str:
    return str(c or "").strip().upper()


def _pit_laps_from_stints(stints_clean: List[Dict[str, Any]], driver: str) -> List[int]:
    code = _norm_code(driver)
    rows = [r for r in stints_clean if _norm_code(r.get("driver", "")) == code]
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


COLORS = {
    "pit": "#ff6b6b",
    "deg": "#ffbf40",
    "traffic": "#818cf8",
}


def _laps_driver(laps_clean: List[Dict[str, Any]], code: str) -> List[Dict[str, Any]]:
    u = _norm_code(code)
    rows = [r for r in laps_clean if _norm_code(r.get("driver", "")) == u]
    return sorted(rows, key=lambda r: float(r.get("lap", 0) or 0))


def _float(r: Any, default: float = 0.0) -> float:
    try:
        return float(r)
    except (TypeError, ValueError):
        return default


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    return float(statistics.median(xs))


def _estimate_pit_loss_sec(
    laps: List[Dict[str, Any]], pit_lap_nums: set
) -> Tuple[float, int]:
    """Mean pit-lap time minus median clean lap time; fallback 22. n_pits = len(pit_lap_nums)."""
    clean_times: List[float] = []
    pit_times: List[float] = []
    for r in laps:
        lap = int(round(_float(r.get("lap", 0))))
        raw_lt = r.get("lap_time_sec")
        if raw_lt is None:
            continue
        lt = _float(raw_lt)
        if lt <= 0:
            continue
        if 60 < lt < 200 and lap not in pit_lap_nums:
            clean_times.append(lt)
        if lap in pit_lap_nums:
            pit_times.append(lt)
    med_clean = _median(clean_times) if clean_times else 95.0
    if pit_times:
        excess = _median(pit_times) - med_clean
        avg_loss = max(18.0, min(38.0, excess))
    else:
        avg_loss = 22.0
    n_pits = len(pit_lap_nums)
    return avg_loss, n_pits


def _deg_slopes_from_clean_laps(
    clean_laps: List[Dict[str, Any]]
) -> Tuple[Dict[str, float], float]:
    """Linear slope lap_time vs tyre_age per compound (same as old PitHeatmap.vue)."""
    stints: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    for lap in clean_laps:
        if cur:
            prev = cur[-1]
            same = str(lap.get("compound", "")).upper() == str(prev.get("compound", "")).upper()
            ta = int(round(_float(lap.get("tyre_age", 1))))
            ta0 = int(round(_float(prev.get("tyre_age", 1))))
            if not same or ta <= ta0:
                if len(cur) >= 3:
                    stints.append(cur[:])
                cur = []
        cur.append(lap)
    if len(cur) >= 3:
        stints.append(cur)

    comp_rates: Dict[str, List[float]] = {}
    for stint in stints:
        comp = str(stint[0].get("compound", "MEDIUM") or "MEDIUM").upper()
        ages = [_float(x.get("tyre_age", 1)) for x in stint]
        times = [_float(x.get("lap_time_sec", 0)) for x in stint]
        if len(ages) < 3:
            continue
        mean_a = statistics.mean(ages)
        mean_t = statistics.mean(times)
        num = sum((ages[i] - mean_a) * (times[i] - mean_t) for i in range(len(ages)))
        den = sum((a - mean_a) ** 2 for a in ages)
        slope = max(0.0, num / den) if den > 0 else 0.0
        comp_rates.setdefault(comp, []).append(slope)

    deg_rate: Dict[str, float] = {}
    for comp, rates in comp_rates.items():
        deg_rate[comp] = float(statistics.median(rates))
    fallback = float(statistics.median(deg_rate.values())) if deg_rate else 0.04
    return deg_rate, fallback


def compute_pit_window_grid(
    raw_race: Dict[str, Any],
    driver: str,
    total_laps: int,
) -> List[Dict[str, Any]]:
    """
    Simulator-driven pit window:
    value(lap) = actual_final_gap - simulated_final_gap_at_candidate_lap

    Positive => better (green), negative => worse (red).
    """
    laps_clean = raw_race.get("laps_clean") or []
    stints_clean = raw_race.get("stints_clean") or []
    race_trace = raw_race.get("race_trace") or []
    code = _norm_code(driver)
    laps = _laps_driver(laps_clean, code)
    if len(laps) < 5:
        return []

    gap_by_lap: Dict[int, float] = {}
    for r in race_trace:
        if _norm_code(r.get("driver", "")) != code:
            continue
        lap = int(round(_float(r.get("lap", 0))))
        gap_by_lap[lap] = _float(r.get("gap_to_leader"), float("nan"))
    last_lap = max((int(round(_float(x.get("lap", 0)))) for x in laps), default=0)
    actual_final_gap = gap_by_lap.get(last_lap, float("nan"))
    if not (actual_final_gap == actual_final_gap):
        return []

    # Candidate laps: realistic stop range.
    min_lap = 3
    max_lap = max(min_lap, total_laps - 2)
    lap_set = {int(round(_float(r.get("lap", 0)))) for r in laps}

    out: List[Dict[str, Any]] = []
    for lap_num in range(min_lap, max_lap + 1):
        if lap_num not in lap_set:
            continue
        try:
            sim = simulate_pit_strategy(
                raw_race,
                driver=code,
                new_pit_lap=lap_num,
                new_compound=None,
                pit_loss_sec=None,
                monte_carlo_samples=1,
                random_seed=0,
                use_ml=True,
            )
        except Exception:
            continue
        sim_trace = sim.get("simulated_trace") or []
        sim_final = None
        for row in sim_trace:
            if int(round(_float(row.get("lap", 0)))) == last_lap:
                sim_final = _float(row.get("simulated_gap_to_leader"), float("nan"))
                break
        if sim_final is None or not (sim_final == sim_final):
            continue
        delta_gap = actual_final_gap - sim_final
        out.append(
            {
                "lap": lap_num,
                "value": round(delta_gap, 4),
                "actual_final_gap": round(actual_final_gap, 4),
                "simulated_final_gap": round(sim_final, 4),
                "delta_gap": round(delta_gap, 4),
            }
        )
    return out


def _default_pit_lap_for_delta_breakdown(
    pit_window_rows: List[Dict[str, Any]], old_pit: int
) -> Optional[int]:
    """
    When the UI has not picked a what-if lap yet, choose a single counterfactual lap so the
    delta breakdown chart can render: best pit-window gain among laps that differ from the
    actual first stop (same ordering as the heatmap's ``value`` field).
    """
    old = int(old_pit)
    candidates: List[Dict[str, Any]] = []
    for r in pit_window_rows or []:
        try:
            lap = int(round(_float(r.get("lap", 0))))
        except (TypeError, ValueError):
            continue
        if lap == old:
            continue
        candidates.append(r)
    if not candidates:
        return None
    # Max gain (value); tie-break toward earlier lap for stable UI.
    best_row = max(
        candidates,
        key=lambda r: (_float(r.get("value", 0)), -float(r.get("lap", 0))),
    )
    try:
        return int(round(_float(best_row.get("lap", 0))))
    except (TypeError, ValueError):
        return None


def compute_delta_breakdown(
    raw_race: Dict[str, Any],
    driver: str,
    total_laps: int,
    selected_new_pit_lap: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Simulator-based breakdown for the explicitly selected what-if pit lap."""
    laps_clean = raw_race.get("laps_clean") or []
    race_trace = raw_race.get("race_trace") or []
    stints_clean = raw_race.get("stints_clean") or []
    code = _norm_code(driver)
    laps = _laps_driver(laps_clean, code)
    if not laps:
        return None

    gap_by_lap: Dict[int, float] = {}
    for r in race_trace:
        if _norm_code(r.get("driver", "")) != code:
            continue
        lap = int(round(_float(r.get("lap", 0))))
        gap_by_lap[lap] = _float(r.get("gap_to_leader"), float("nan"))
    last_lap = max((int(round(_float(x.get("lap", 0)))) for x in laps), default=0)
    final_gap = gap_by_lap.get(last_lap, float("nan"))
    if not (final_gap == final_gap):
        return None

    if selected_new_pit_lap is None:
        return None
    pit_laps = _pit_laps_from_stints(stints_clean, code)
    if not pit_laps:
        return None
    old_pit = pit_laps[0]
    lap_set = {int(round(_float(r.get("lap", 0)))) for r in laps}
    new_pit = int(selected_new_pit_lap)
    if new_pit == old_pit:
        return None
    if new_pit < 3 or new_pit > (total_laps - 2):
        return None
    if new_pit not in lap_set:
        return None

    try:
        sim = simulate_pit_strategy(
            raw_race,
            driver=code,
            new_pit_lap=int(new_pit),
            new_compound=None,
            pit_loss_sec=None,
            monte_carlo_samples=1,
            random_seed=0,
            use_ml=True,
        )
    except Exception:
        return None

    breakdown = sim.get("delta_breakdown") or {}
    comps = breakdown.get("components") or []
    if not comps:
        return None
    total = _float(breakdown.get("total"), 0.0)
    return {
        "total": round(total, 3),
        "actual_final_gap": round(final_gap, 3),
        "simulated_final_gap": round(_float(sim.get("simulated_final_gap"), final_gap), 3),
        "delta_gap": round(_float(sim.get("delta_gap"), total), 3),
        "components": comps,
    }


def build_strategy_viz_payload(
    raw_race: Dict[str, Any],
    driver_codes: List[str],
    selected_pit_laps: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """pit_window and delta_breakdown per driver."""
    laps_clean = raw_race.get("laps_clean") or []

    total_laps = 0
    for r in laps_clean:
        total_laps = max(total_laps, int(round(_float(r.get("lap", 0)))))

    pit_window: Dict[str, List[Dict[str, Any]]] = {}
    delta_breakdown: Dict[str, Any] = {}
    stints_clean = raw_race.get("stints_clean") or []

    for code in driver_codes:
        c = _norm_code(code)
        pit_window[c] = compute_pit_window_grid(
            raw_race, c, total_laps
        )
        selected_lap = None
        if selected_pit_laps:
            selected_lap = selected_pit_laps.get(c)
            if selected_lap is None:
                selected_lap = selected_pit_laps.get(code)
        if selected_lap is None:
            pit_laps = _pit_laps_from_stints(stints_clean, c)
            if pit_laps:
                selected_lap = _default_pit_lap_for_delta_breakdown(
                    pit_window[c], pit_laps[0]
                )
        db = compute_delta_breakdown(raw_race, c, total_laps, selected_lap)
        if db:
            delta_breakdown[c] = db

    return {"pit_window": pit_window, "delta_breakdown": delta_breakdown}
