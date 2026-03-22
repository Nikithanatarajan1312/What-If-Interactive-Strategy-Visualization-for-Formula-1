"""
Uncertainty estimation via Monte Carlo sampling.

Perturbs the tyre degradation model parameters using their residual
distributions, runs N independent simulations, and aggregates results
into percentile bands (5th, 25th, 50th, 75th, 95th) for gap-to-leader
and position at each lap.

Public API:
    run_monte_carlo(race_data, strategy, tyre_model, n_samples=200)
        -> dict with the median simulation result plus percentile bands
"""
import copy
import logging

import numpy as np

from models.race_simulator import simulate, _strategy_unchanged

logger = logging.getLogger(__name__)

DEFAULT_N_SAMPLES = 200
PERCENTILES = [5, 25, 50, 75, 95]


def run_monte_carlo(race_data, strategy, tyre_model, n_samples=DEFAULT_N_SAMPLES):
    """
    Run Monte Carlo simulation and return median result with percentile
    bands for gap-to-leader and position at every lap.
    """
    target_code = strategy['driverCode']
    total_laps = race_data['race']['totalLaps']

    # ---- fast path: strategy unchanged → zero uncertainty ----
    target_driver = next(
        (d for d in race_data['drivers'] if d['code'] == target_code), None)
    if target_driver and _strategy_unchanged(
            target_driver.get('pitStops', []),
            sorted(strategy['pitStops'], key=lambda p: p['lap'])):
        logger.info("Strategy unchanged for %s — returning actual with zero bands",
                     target_code)
        return _wrap_actual(race_data, target_code, total_laps)

    # ---- full Monte Carlo ----
    gap_samples = np.zeros((n_samples, total_laps))
    pos_samples = np.zeros((n_samples, total_laps))
    time_samples = np.zeros((n_samples, total_laps))

    all_results = []
    rng = np.random.default_rng(2024)

    logger.info("Running %d Monte Carlo samples for %s...",
                n_samples, target_code)

    for i in range(n_samples):
        perturbed_model = tyre_model.perturbed_copy(rng)
        sim_rng = np.random.default_rng(rng.integers(0, 2**31))
        result = simulate(race_data, perturbed_model, strategy, rng=sim_rng)

        target = None
        for d in result['drivers']:
            if d['code'] == target_code:
                target = d
                break

        if target is None:
            continue

        lap_map = {l['lap']: l for l in target['laps']}
        for lap_num in range(1, total_laps + 1):
            entry = lap_map.get(lap_num)
            if entry:
                gap_samples[i, lap_num - 1] = entry.get('gapToLeader', 0)
                pos_samples[i, lap_num - 1] = entry.get('position', 0)
                time_samples[i, lap_num - 1] = entry.get('time_s', 0)

        all_results.append(result)

    if not all_results:
        return simulate(race_data, tyre_model, strategy)

    gap_pcts = {p: np.percentile(gap_samples, p, axis=0) for p in PERCENTILES}
    pos_pcts = {p: np.percentile(pos_samples, p, axis=0) for p in PERCENTILES}

    median_idx = _find_median_run(gap_samples, gap_pcts[50])
    median_result = all_results[min(median_idx, len(all_results) - 1)]

    for d in median_result['drivers']:
        if d['code'] == target_code:
            for lap_entry in d['laps']:
                idx = lap_entry['lap'] - 1
                if 0 <= idx < total_laps:
                    lap_entry['p5']  = round(float(gap_pcts[5][idx]), 1)
                    lap_entry['p25'] = round(float(gap_pcts[25][idx]), 1)
                    lap_entry['p50'] = round(float(gap_pcts[50][idx]), 1)
                    lap_entry['p75'] = round(float(gap_pcts[75][idx]), 1)
                    lap_entry['p95'] = round(float(gap_pcts[95][idx]), 1)
                    lap_entry['posP5']  = int(round(float(pos_pcts[5][idx])))
                    lap_entry['posP50'] = int(round(float(pos_pcts[50][idx])))
                    lap_entry['posP95'] = int(round(float(pos_pcts[95][idx])))
            break

    logger.info("Monte Carlo complete: %d valid samples", len(all_results))
    return median_result


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _wrap_actual(race_data, target_code, total_laps):
    """Return actual data annotated as 'simulated' with zero uncertainty."""
    result = copy.deepcopy(race_data)
    for d in result['drivers']:
        if d['code'] == target_code:
            for lap in d['laps']:
                gap = lap.get('gapToLeader', 0)
                pos = lap.get('position', 0)
                lap.update({
                    'isSimulated': True,
                    'p5': gap, 'p25': gap, 'p50': gap,
                    'p75': gap, 'p95': gap,
                    'posP5': pos, 'posP50': pos, 'posP95': pos,
                })
            break
    return result


def _find_median_run(samples, median_curve):
    """Find the sample run whose gap curve is closest to the median curve."""
    diffs = np.sum((samples - median_curve[np.newaxis, :]) ** 2, axis=1)
    return int(np.argmin(diffs))
