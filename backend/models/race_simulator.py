"""
Race simulator engine — delta-anchored approach.

Instead of predicting absolute lap times from a model (which accumulates
systematic errors), this simulator works relative to actual race data:

  sim_time = actual_time + (model_sim_conditions − model_actual_conditions)

This guarantees:
  • Unchanged strategy  → result ≈ actual race  (delta ≈ 0)
  • Modified strategy   → realistic estimate anchored to real performance

Five cases per lap depending on whether the lap was / will be a pit stop:
  A  clean→clean    delta-based (most laps)
  B  pit→pit        delta + pit-cost difference
  C  clean→pit      actual + delta + new pit cost
  D  pit→clean      model-only (actual includes pit time, unusable)
  E  no actual data  model-only fallback

Public API:
    simulate(race_data, tyre_model, strategy, rng=None) -> dict
"""
import copy
import logging

import numpy as np

logger = logging.getLogger(__name__)


def simulate(race_data, tyre_model, strategy, rng=None):
    if rng is None:
        rng = np.random.default_rng(42)

    total_laps = race_data['race']['totalLaps']
    target_code = strategy['driverCode']
    new_pits = sorted(strategy['pitStops'], key=lambda p: p['lap'])

    sim_data = copy.deepcopy(race_data)

    target_driver = None
    for d in sim_data['drivers']:
        if d['code'] == target_code:
            target_driver = d
            break

    if not target_driver:
        logger.warning("Driver %s not found in race data", target_code)
        return sim_data

    original_laps = target_driver.get('laps', [])
    original_pits = target_driver.get('pitStops', [])

    if _strategy_unchanged(original_pits, new_pits):
        logger.info("Strategy unchanged for %s — returning actual data",
                     target_code)
        for lap in target_driver['laps']:
            lap['isSimulated'] = True
        return sim_data

    # ---- lookups ----
    actual_by_lap = {l['lap']: l for l in original_laps}
    orig_pit_set = {p['lap'] for p in original_pits}
    orig_pit_map = {p['lap']: p for p in original_pits}
    new_pit_set = {p['lap'] for p in new_pits}
    new_pit_map = {p['lap']: p for p in new_pits}

    avg_pit_loss = (
        float(np.mean([p['duration_s'] for p in original_pits]))
        if original_pits else 22.0
    )

    # Per-compound calibration for model-only fallback (cases D, E)
    comp_cal = _compound_calibration(
        original_laps, orig_pit_set, tyre_model, total_laps)
    global_cal = (float(np.median(list(comp_cal.values())))
                  if comp_cal else 0.0)

    # Starting state
    if new_pits:
        current_compound = new_pits[0]['fromCompound']
    elif original_laps:
        current_compound = original_laps[0].get('compound', 'MEDIUM')
    else:
        current_compound = 'MEDIUM'

    tyre_age = (original_laps[0].get('tyreAge', 1) - 1
                if original_laps else 0)

    new_lap_list = []

    for lap_num in range(1, total_laps + 1):
        tyre_age += 1
        fuel = 1.0 - (lap_num / total_laps)
        is_new_pit = lap_num in new_pit_set
        was_old_pit = lap_num in orig_pit_set

        actual = actual_by_lap.get(lap_num)
        actual_t = (actual['time_s']
                    if actual and actual.get('time_s')
                    and actual['time_s'] > 60 else None)
        noise_std = tyre_model.residual_std(current_compound)

        # ---- determine lap time ----
        if actual_t and not was_old_pit and not is_new_pit:
            # Case A: clean in both → delta-based
            lap_time = _delta_time(
                actual, actual_t, current_compound, tyre_age, fuel,
                tyre_model, rng, noise_std * 0.15)

        elif actual_t and was_old_pit and is_new_pit:
            # Case B: pit in both → delta + pit cost diff
            base = _delta_time(
                actual, actual_t, current_compound, tyre_age, fuel,
                tyre_model, rng, noise_std * 0.15)
            old_cost = orig_pit_map[lap_num].get('duration_s', avg_pit_loss)
            new_cost = new_pit_map[lap_num].get('duration_s', avg_pit_loss)
            lap_time = base + (new_cost - old_cost)

        elif actual_t and not was_old_pit and is_new_pit:
            # Case C: adding a pit where there wasn't one
            base = _delta_time(
                actual, actual_t, current_compound, tyre_age, fuel,
                tyre_model, rng, noise_std * 0.15)
            pit_cost = new_pit_map[lap_num].get('duration_s', avg_pit_loss)
            lap_time = base + pit_cost

        elif was_old_pit and not is_new_pit:
            # Case D: removing a pit — actual time includes pit cost,
            # so we must fall back to model + compound calibration
            cal = comp_cal.get(current_compound, global_cal)
            lap_time = (tyre_model.predict(current_compound, tyre_age, fuel)
                        + cal + rng.normal(0, noise_std * 0.5))

        else:
            # Case E: no usable actual data
            cal = comp_cal.get(current_compound, global_cal)
            lap_time = (tyre_model.predict(current_compound, tyre_age, fuel)
                        + cal + rng.normal(0, noise_std * 0.5))

        # ---- compound/age change on pit ----
        if is_new_pit:
            current_compound = new_pit_map[lap_num].get(
                'toCompound', current_compound)
            tyre_age = 0

        entry = {
            'lap': lap_num,
            'time_s': round(float(lap_time), 3),
            'compound': current_compound,
            'tyreAge': tyre_age,
            'gapToLeader': 0.0,
            'position': 0,
            'isSimulated': True,
        }
        if is_new_pit:
            entry['isPitLap'] = True

        new_lap_list.append(entry)

    target_driver['laps'] = new_lap_list
    target_driver['pitStops'] = new_pits

    _recompute_gaps_and_positions(sim_data, total_laps)
    return sim_data


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _strategy_unchanged(original_pits, new_pits):
    """True when pit lap numbers AND compounds are identical."""
    if len(original_pits) != len(new_pits):
        return False
    o = sorted(original_pits, key=lambda p: p['lap'])
    n = sorted(new_pits, key=lambda p: p['lap'])
    return all(
        a['lap'] == b['lap'] and a.get('toCompound') == b.get('toCompound')
        for a, b in zip(o, n)
    )


def _delta_time(actual_lap, actual_t, sim_compound, sim_age, fuel,
                tyre_model, rng, noise_scale):
    """
    actual_time + (model_sim − model_actual) + noise

    When the compound and age are the same, delta ≈ 0 → result ≈ actual.
    """
    actual_comp = actual_lap.get('compound', sim_compound)
    actual_age = actual_lap.get('tyreAge', sim_age)
    model_actual = tyre_model.predict(actual_comp, actual_age, fuel)
    model_sim = tyre_model.predict(sim_compound, sim_age, fuel)
    delta = model_sim - model_actual
    return actual_t + delta + rng.normal(0, noise_scale)


def _compound_calibration(laps, pit_laps, tyre_model, total_laps):
    """median(actual − model) per compound, from clean laps only."""
    by_comp = {}
    for l in laps:
        t = l.get('time_s')
        if t and 60 < t < 200 and l['lap'] not in pit_laps:
            comp = l.get('compound', 'MEDIUM')
            fuel = 1.0 - (l['lap'] / total_laps)
            pred = tyre_model.predict(comp, l.get('tyreAge', 1), fuel)
            by_comp.setdefault(comp, []).append(t - pred)
    return {c: float(np.median(r)) for c, r in by_comp.items()}


def _recompute_gaps_and_positions(sim_data, total_laps):
    """Recompute gap-to-leader and positions from cumulative times."""
    drivers = sim_data['drivers']

    cum_times = {}
    for d in drivers:
        cum = 0.0
        ct = {}
        for lap_entry in d['laps']:
            cum += lap_entry.get('time_s') or 0
            ct[lap_entry['lap']] = cum
        cum_times[d['code']] = ct

    for lap_num in range(1, total_laps + 1):
        times_at_lap = []
        for d in drivers:
            ct = cum_times[d['code']]
            if lap_num in ct:
                times_at_lap.append((d['code'], ct[lap_num]))

        if not times_at_lap:
            continue

        times_at_lap.sort(key=lambda x: x[1])
        leader_time = times_at_lap[0][1]

        position_map = {
            code: pos + 1 for pos, (code, _) in enumerate(times_at_lap)
        }
        gap_map = {
            code: round(max(0.0, t - leader_time), 1)
            for code, t in times_at_lap
        }

        for d in drivers:
            lap_entry = next(
                (l for l in d['laps'] if l['lap'] == lap_num), None)
            if lap_entry:
                lap_entry['gapToLeader'] = gap_map.get(d['code'], 0.0)
                lap_entry['position'] = position_map.get(d['code'], 0)
