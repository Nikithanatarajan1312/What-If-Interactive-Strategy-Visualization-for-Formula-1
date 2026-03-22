"""
FastF1 data retrieval, preprocessing, and caching service.

Loads F1 race session data via the FastF1 library, extracts per-driver
lap-level telemetry (times, compounds, positions, pit stops, sector times),
session-level events (safety cars, VSC), and caches the preprocessed result
as JSON in data/cache/ for instant subsequent loads.

Public API:
    load_race_data(year, rnd) -> dict   structured race data
    get_available_races()     -> list    [{year, round, name}, ...]
    get_stint_data(year, rnd) -> list    raw stint records for model fitting
"""
import json
import os
import logging

import fastf1
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_FF1_CACHE = os.path.join(_BASE_DIR, 'ff1_cache')
_JSON_CACHE = os.path.join(_BASE_DIR, 'data', 'cache')

os.makedirs(_FF1_CACHE, exist_ok=True)
os.makedirs(_JSON_CACHE, exist_ok=True)
fastf1.Cache.enable_cache(_FF1_CACHE)

TEAM_COLORS = {
    'Red Bull Racing': '#3671C6',
    'Ferrari': '#E8002D',
    'Mercedes': '#27F4D2',
    'McLaren': '#FF8000',
    'Aston Martin': '#229971',
    'Alpine': '#FF87BC',
    'Williams': '#64C4FF',
    'Haas F1 Team': '#B6BABD',
    'RB': '#6692FF',
    'Kick Sauber': '#52E252',
}

COMPOUND_MAP = {
    'SOFT': 'SOFT', 'MEDIUM': 'MEDIUM', 'HARD': 'HARD',
    'INTERMEDIATE': 'INTERMEDIATE', 'WET': 'WET',
}

AVAILABLE_RACES = [
    {'year': 2024, 'round': 1},
    {'year': 2024, 'round': 4},
]

TOP_N_DRIVERS = 6

_memory_cache = {}


def _json_cache_path(year, rnd):
    return os.path.join(_JSON_CACHE, f'{year}-{rnd}.json')


def _team_color(team_name):
    for key, color in TEAM_COLORS.items():
        if key.lower() in team_name.lower() or team_name.lower() in key.lower():
            return color
    return '#888888'


def _safe_seconds(td):
    """Convert a Timedelta/NaT to float seconds, or None."""
    if td is None or pd.isna(td):
        return None
    if hasattr(td, 'total_seconds'):
        val = td.total_seconds()
        return val if np.isfinite(val) else None
    return None


def _is_pit_event(lap, field):
    val = lap.get(field)
    return val is not None and str(val) != 'NaT' and not pd.isna(val)


def _load_fastf1_session(year, rnd):
    logger.info("Loading FastF1 session %d round %d ...", year, rnd)
    session = fastf1.get_session(year, rnd, 'R')
    session.load()
    return session


def _compute_gap_to_leader(laps_df, driver_codes, total_laps):
    """Compute cumulative-time-based gap to leader per lap."""
    cum_times = {}
    for code in driver_codes:
        dlaps = laps_df[laps_df['Driver'] == code].sort_values('LapNumber')
        cum = 0.0
        entries = []
        for _, row in dlaps.iterrows():
            secs = _safe_seconds(row['LapTime'])
            cum += secs if secs is not None else 0
            entries.append({'lap': int(row['LapNumber']), 'cum': cum})
        cum_times[code] = {e['lap']: e['cum'] for e in entries}

    gap_data = {code: {} for code in driver_codes}
    for lap_num in range(1, total_laps + 1):
        leader_cum = min(
            (cum_times[c].get(lap_num, float('inf')) for c in driver_codes),
            default=float('inf'),
        )
        for code in driver_codes:
            ct = cum_times[code].get(lap_num)
            if ct is not None and leader_cum < float('inf'):
                gap_data[code][lap_num] = round(max(0.0, ct - leader_cum), 1)

    return gap_data, cum_times


def _extract_driver(laps_df, results_row, gap_data, total_laps):
    """Build the JSON structure for one driver."""
    code = results_row['Abbreviation']
    dlaps = laps_df[laps_df['Driver'] == code].sort_values('LapNumber')

    clean_times = []
    for _, lap in dlaps.iterrows():
        s = _safe_seconds(lap['LapTime'])
        if (s and not _is_pit_event(lap, 'PitInTime')
                and not _is_pit_event(lap, 'PitOutTime')
                and 60 < s < 200):
            clean_times.append(s)
    median_clean = float(np.median(clean_times)) if clean_times else 95.0

    laps_list = []
    pit_stops = []
    sector_times = []

    for _, lap in dlaps.iterrows():
        lap_num = int(lap['LapNumber'])
        time_s = _safe_seconds(lap['LapTime'])
        if time_s is not None:
            time_s = round(time_s, 3)

        compound = COMPOUND_MAP.get(str(lap.get('Compound', '')), 'MEDIUM')
        tyre_life = int(lap.get('TyreLife', 1)) if pd.notna(lap.get('TyreLife', np.nan)) else 1
        position = int(lap.get('Position', 0)) if pd.notna(lap.get('Position', np.nan)) else 0
        gap = gap_data[code].get(lap_num, 0.0)
        is_pit = _is_pit_event(lap, 'PitInTime')

        s1 = _safe_seconds(lap.get('Sector1Time'))
        s2 = _safe_seconds(lap.get('Sector2Time'))
        s3 = _safe_seconds(lap.get('Sector3Time'))
        if s1 is not None and s2 is not None and s3 is not None:
            sector_times.append({
                'lap': lap_num,
                's1': round(s1, 3), 's2': round(s2, 3), 's3': round(s3, 3),
            })

        entry = {
            'lap': lap_num,
            'time_s': time_s,
            'compound': compound,
            'tyreAge': tyre_life,
            'position': position,
            'gapToLeader': gap,
        }

        if is_pit:
            entry['isPitLap'] = True
            pit_lap_t = _safe_seconds(lap['LapTime'])
            pit_loss = round((pit_lap_t or median_clean + 22) - median_clean, 1)

            next_laps = dlaps[dlaps['LapNumber'] > lap_num]
            next_compound = compound
            if len(next_laps) > 0:
                next_compound = COMPOUND_MAP.get(
                    str(next_laps.iloc[0].get('Compound', '')), compound)

            pit_stops.append({
                'lap': lap_num,
                'duration_s': max(pit_loss, 2.0),
                'fromCompound': compound,
                'toCompound': next_compound,
            })

        if time_s is not None:
            laps_list.append(entry)

    return {
        'code': code,
        'name': results_row['FullName'],
        'team': results_row['TeamName'],
        'color': _team_color(results_row['TeamName']),
        'laps': laps_list,
        'pitStops': pit_stops,
        'sectorTimes': sector_times,
        'medianCleanLap': round(median_clean, 3),
    }


def _extract_events(session):
    """Extract safety car and VSC periods from session messages."""
    events = []
    try:
        msgs = session.race_control_messages
        if msgs is not None and len(msgs) > 0:
            sc_start = None
            vsc_start = None
            for _, msg in msgs.iterrows():
                cat = str(msg.get('Category', ''))
                flag = str(msg.get('Flag', ''))
                lap = int(msg.get('Lap', 0)) if pd.notna(msg.get('Lap')) else 0

                if 'SafetyCar' in cat and 'DEPLOYED' in flag:
                    sc_start = lap
                elif 'SafetyCar' in cat and ('ENDING' in flag or 'IN THIS LAP' in flag):
                    if sc_start is not None:
                        events.append({'type': 'SafetyCar', 'startLap': sc_start, 'endLap': lap})
                        sc_start = None

                if 'VSC' in cat and 'DEPLOYED' in flag:
                    vsc_start = lap
                elif 'VSC' in cat and 'ENDING' in flag:
                    if vsc_start is not None:
                        events.append({'type': 'VSC', 'startLap': vsc_start, 'endLap': lap})
                        vsc_start = None
    except Exception:
        logger.debug("Could not extract race control messages", exc_info=True)
    return events


def _build_from_session(session, year, rnd):
    """Build the full race data dict from a loaded FastF1 session."""
    laps = session.laps
    total_laps = int(laps['LapNumber'].max())
    results = session.results
    top_drivers = results.head(TOP_N_DRIVERS)
    driver_codes = list(top_drivers['Abbreviation'])

    gap_data, _ = _compute_gap_to_leader(laps, driver_codes, total_laps)

    drivers = []
    for _, row in top_drivers.iterrows():
        drivers.append(_extract_driver(laps, row, gap_data, total_laps))

    events = _extract_events(session)

    return {
        'race': {
            'name': session.event['EventName'],
            'year': year,
            'round': rnd,
            'totalLaps': total_laps,
        },
        'drivers': drivers,
        'events': events,
    }


def load_race_data(year, rnd):
    """
    Load race data for a given year/round.

    Checks JSON cache first, then falls back to FastF1 (slow, network).
    """
    key = f"{year}-{rnd}"
    if key in _memory_cache:
        return _memory_cache[key]

    cache_path = _json_cache_path(year, rnd)
    if os.path.exists(cache_path):
        logger.info("Loading cached JSON for %s", key)
        with open(cache_path, 'r') as f:
            data = json.load(f)
        _memory_cache[key] = data
        return data

    session = _load_fastf1_session(year, rnd)
    data = _build_from_session(session, year, rnd)

    with open(cache_path, 'w') as f:
        json.dump(data, f, indent=2, allow_nan=False)
    logger.info("Cached race data to %s", cache_path)

    _memory_cache[key] = data
    return data


def get_available_races():
    """Return metadata list of races we can serve."""
    races = []
    for cfg in AVAILABLE_RACES:
        year, rnd = cfg['year'], cfg['round']
        try:
            data = load_race_data(year, rnd)
            name = data['race']['name']
        except Exception:
            name = f"{year} Round {rnd}"
        races.append({'year': year, 'round': rnd, 'name': name})
    return races


def get_stint_data(year, rnd):
    """
    Extract raw stint records for tyre model fitting.

    Returns list of dicts:
      {driver, compound, tyre_age, lap_time, lap_number, fuel_corrected_lap}
    """
    data = load_race_data(year, rnd)
    total_laps = data['race']['totalLaps']
    records = []

    for driver in data['drivers']:
        code = driver['code']
        pit_laps = {p['lap'] for p in driver['pitStops']}

        for lap in driver['laps']:
            t = lap.get('time_s')
            if t is None or lap['lap'] in pit_laps:
                continue
            if t < 60 or t > 200:
                continue

            fuel_fraction = 1.0 - (lap['lap'] / total_laps)
            records.append({
                'driver': code,
                'compound': lap['compound'],
                'tyre_age': lap['tyreAge'],
                'lap_time': t,
                'lap_number': lap['lap'],
                'fuel_load': fuel_fraction,
            })

    return records


def seed_cache_from_mock_data():
    """
    Populate the JSON cache from the legacy mock-data.json file
    so the server can start instantly without FastF1 network calls.
    """
    mock_path = os.path.join(_BASE_DIR, 'mock-data.json')
    if not os.path.exists(mock_path):
        return

    with open(mock_path, 'r') as f:
        blob = json.load(f)

    for key, race_data in blob.get('raceData', {}).items():
        cache_path = _json_cache_path(*key.split('-'))
        if not os.path.exists(cache_path):
            with open(cache_path, 'w') as f:
                json.dump(race_data, f, indent=2, allow_nan=False)
            logger.info("Seeded cache from mock-data.json: %s", key)
