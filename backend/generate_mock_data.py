"""
Generates realistic mock data from real F1 races using FastF1.
Outputs backend/mock-data.json with multiple races in the frontend-expected format.
"""
import json
import os
import fastf1
import numpy as np

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'ff1_cache')
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

RACES = [
    {'year': 2024, 'round': 1},   # Bahrain GP
    {'year': 2024, 'round': 4},   # Japan GP (Suzuka)
]

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
    'SOFT': 'SOFT',
    'MEDIUM': 'MEDIUM',
    'HARD': 'HARD',
    'INTERMEDIATE': 'INTERMEDIATE',
    'WET': 'WET',
}

TOP_N_DRIVERS = 6


def load_session(year, rnd):
    session = fastf1.get_session(year, rnd, 'R')
    session.load()
    return session


def get_team_color(team_name):
    for key, color in TEAM_COLORS.items():
        if key.lower() in team_name.lower() or team_name.lower() in key.lower():
            return color
    return '#888888'


def compute_gap_to_leader(laps_df, driver_codes, total_laps):
    cum_times = {}
    for code in driver_codes:
        driver_laps = laps_df[laps_df['Driver'] == code].sort_values('LapNumber')
        times = []
        cum = 0.0
        for _, row in driver_laps.iterrows():
            lt = row['LapTime']
            if lt is not None and hasattr(lt, 'total_seconds'):
                secs = lt.total_seconds()
            else:
                secs = np.nan
            cum += secs if not np.isnan(secs) else 0
            times.append({'lap': int(row['LapNumber']), 'cum': cum, 'lap_s': secs})
        cum_times[code] = times

    gap_data = {}
    for code in driver_codes:
        gap_data[code] = []

    for lap_num in range(1, total_laps + 1):
        leader_cum = float('inf')
        for code in driver_codes:
            entry = next((e for e in cum_times[code] if e['lap'] == lap_num), None)
            if entry and not np.isnan(entry['cum']) and entry['cum'] > 0:
                leader_cum = min(leader_cum, entry['cum'])

        for code in driver_codes:
            entry = next((e for e in cum_times[code] if e['lap'] == lap_num), None)
            if entry and not np.isnan(entry['cum']) and leader_cum < float('inf'):
                gap = max(0.0, entry['cum'] - leader_cum)
                gap_data[code].append(round(gap, 1))
            else:
                gap_data[code].append(None)

    return gap_data


def build_race_data(session, year, rnd):
    laps = session.laps
    total_laps = int(laps['LapNumber'].max())

    results = session.results
    top_drivers = results.head(TOP_N_DRIVERS)
    driver_codes = list(top_drivers['Abbreviation'])

    gap_data = compute_gap_to_leader(laps, driver_codes, total_laps)

    drivers_json = []
    for _, row in top_drivers.iterrows():
        code = row['Abbreviation']
        full_name = row['FullName']
        team = row['TeamName']
        color = get_team_color(team)

        driver_laps = laps[laps['Driver'] == code].sort_values('LapNumber')

        clean_times = []
        for _, lap in driver_laps.iterrows():
            lt = lap['LapTime']
            is_pit = bool(lap.get('PitInTime') is not None and str(lap.get('PitInTime')) != 'NaT')
            is_out = bool(lap.get('PitOutTime') is not None and str(lap.get('PitOutTime')) != 'NaT')
            if not is_pit and not is_out and lt is not None and hasattr(lt, 'total_seconds'):
                t = lt.total_seconds()
                if 80 < t < 120:
                    clean_times.append(t)
        median_clean = float(np.median(clean_times)) if clean_times else 95.0

        laps_list = []
        pit_stops = []

        for i, (_, lap) in enumerate(driver_laps.iterrows()):
            lap_num = int(lap['LapNumber'])
            lt = lap['LapTime']
            if lt is not None and hasattr(lt, 'total_seconds'):
                val = lt.total_seconds()
                time_s = round(val, 3) if not np.isnan(val) else None
            else:
                time_s = None

            compound = COMPOUND_MAP.get(str(lap.get('Compound', '')), 'MEDIUM')
            tyre_life = int(lap.get('TyreLife', 1)) if not np.isnan(lap.get('TyreLife', 1)) else 1
            position = int(lap.get('Position', 0)) if not np.isnan(lap.get('Position', 0)) else 0

            gap = gap_data[code][lap_num - 1] if lap_num <= len(gap_data[code]) else None

            is_pit = bool(lap.get('PitInTime') is not None and str(lap.get('PitInTime')) != 'NaT')

            lap_entry = {
                'lap': lap_num,
                'time_s': time_s,
                'compound': compound,
                'tyreAge': tyre_life,
                'position': position,
                'gapToLeader': gap if gap is not None else 0.0,
            }

            if is_pit:
                lap_entry['isPitLap'] = True
                pit_lap_time = lt.total_seconds() if lt is not None and hasattr(lt, 'total_seconds') else median_clean + 22
                pit_loss = round(pit_lap_time - median_clean, 1)

                next_laps = driver_laps[driver_laps['LapNumber'] > lap_num]
                if len(next_laps) > 0:
                    next_compound = COMPOUND_MAP.get(str(next_laps.iloc[0].get('Compound', '')), compound)
                else:
                    next_compound = compound

                pit_stops.append({
                    'lap': lap_num,
                    'duration_s': max(pit_loss, 2.0),
                    'fromCompound': compound,
                    'toCompound': next_compound,
                })

            if time_s is not None:
                laps_list.append(lap_entry)

        drivers_json.append({
            'code': code,
            'name': full_name,
            'team': team,
            'color': color,
            'laps': laps_list,
            'pitStops': pit_stops,
        })

    event_name = session.event['EventName']

    return {
        'race': {
            'name': event_name,
            'year': year,
            'round': rnd,
            'totalLaps': total_laps,
        },
        'drivers': drivers_json,
        'events': [],
    }, event_name


def main():
    all_races = []
    all_race_data = {}

    for race_cfg in RACES:
        year = race_cfg['year']
        rnd = race_cfg['round']
        key = f"{year}-{rnd}"

        print(f"\nLoading {year} Round {rnd} race session...")
        session = load_session(year, rnd)
        print("Building JSON...")

        race_data, event_name = build_race_data(session, year, rnd)

        all_races.append({'year': year, 'round': rnd, 'name': event_name})
        all_race_data[key] = race_data

        driver_count = len(race_data['drivers'])
        lap_count = race_data['race']['totalLaps']
        print(f"  Race: {event_name}")
        print(f"  Drivers: {driver_count}, Laps: {lap_count}")
        for d in race_data['drivers']:
            print(f"    {d['code']} ({d['team']}): {len(d['laps'])} laps, {len(d['pitStops'])} pits")

    output = {
        'races': all_races,
        'raceData': all_race_data,
    }

    out_path = os.path.join(os.path.dirname(__file__), 'mock-data.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, allow_nan=False)

    print(f"\nWrote {out_path} with {len(all_races)} races.")


if __name__ == '__main__':
    main()
