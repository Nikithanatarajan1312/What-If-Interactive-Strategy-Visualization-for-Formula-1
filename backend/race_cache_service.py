"""
Simple race-level JSON caching for the F1 backend.

Flow:
1) Check cache JSON in data/cache/
2) Return cached data if present
3) Otherwise fetch + preprocess + save one JSON file per race

Example cache file:
- data/cache/monza_2023.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import fastf1
import pandas as pd

from backend.f1_data_pipeline import (
    extract_lap_data,
    fetch_openf1_session_key,
    fetch_openf1_track_and_events,
    load_race_session,
    setup_fastf1_cache,
    slugify,
)
from backend.json_sanitize import sanitize_for_json


CACHE_DIR = Path("data/cache")


def cache_file_path(grand_prix: str, year: int) -> Path:
    """Build one cache filename per race."""
    return CACHE_DIR / f"{slugify(grand_prix)}_{year}.json"


def select_from_menu(prompt: str, options: List[str], default_index: int = 0) -> str:
    """Show a simple numbered menu and return selected value."""
    if not options:
        raise ValueError("No options available for selection.")

    print(f"\n{prompt}")
    for idx, option in enumerate(options, start=1):
        default_mark = " (default)" if idx - 1 == default_index else ""
        print(f"  {idx}. {option}{default_mark}")

    raw = input("Select number: ").strip()
    if not raw:
        return options[default_index]

    try:
        choice = int(raw)
    except ValueError:
        print("[WARN] Invalid selection. Using default.")
        return options[default_index]

    if 1 <= choice <= len(options):
        return options[choice - 1]

    print("[WARN] Selection out of range. Using default.")
    return options[default_index]


def get_available_years(start_year: int = 2018) -> List[int]:
    """Return year list for dropdown selection."""
    current_year = int(pd.Timestamp.now().year)
    return list(range(start_year, current_year + 1))


def get_user_race_selection() -> Dict[str, Any]:
    """
    Ordered interactive flow:
    1) year
    2) country
    3) race
    """
    years = get_available_years()
    year_labels = [str(y) for y in years]
    default_year = 2023 if 2023 in years else years[-1]
    year = int(
        select_from_menu(
            "Select year:", year_labels, default_index=years.index(default_year)
        )
    )

    schedule = fastf1.get_event_schedule(year)
    races_only = schedule[schedule["Session5"] == "Race"].copy()

    countries = sorted({str(c) for c in races_only["Country"].dropna().tolist()})
    default_country = "Italy" if "Italy" in countries else countries[0]
    country = select_from_menu(
        "Select country:", countries, default_index=countries.index(default_country)
    )

    races_in_country = races_only[races_only["Country"] == country]
    race_options = [str(name) for name in races_in_country["EventName"].tolist()]
    if not race_options:
        race_options = [str(name) for name in races_only["EventName"].tolist()]

    default_race = "Italian Grand Prix" if "Italian Grand Prix" in race_options else race_options[0]
    gp = select_from_menu(
        "Select race:", race_options, default_index=race_options.index(default_race)
    )

    return {"year": year, "gp": gp, "country": country}


def list_countries_for_year(year: int) -> List[str]:
    """Countries that host a race in ``year`` (for API dropdowns)."""
    schedule = fastf1.get_event_schedule(year)
    races_only = schedule[schedule["Session5"] == "Race"].copy()
    return sorted({str(c) for c in races_only["Country"].dropna().tolist()})


def list_race_names_for_country(year: int, country: str) -> List[str]:
    """Grand Prix event names in ``country`` for ``year`` (for API dropdowns)."""
    schedule = fastf1.get_event_schedule(year)
    races_only = schedule[schedule["Session5"] == "Race"].copy()
    filtered = races_only[races_only["Country"] == country]
    names = [str(n) for n in filtered["EventName"].tolist()]
    if not names:
        names = [str(n) for n in races_only["EventName"].tolist()]
    return names


def cache_tag_for_request(grand_prix: str, year: int) -> str:
    """Stem of the JSON cache file for this request (e.g. spanish_grand_prix_2024)."""
    return cache_file_path(grand_prix, year).stem


def load_from_cache(grand_prix: str, year: int) -> Optional[Dict[str, Any]]:
    """
    Load race JSON from cache if it exists.
    Returns None when missing.
    """
    path = cache_file_path(grand_prix, year)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_to_cache(grand_prix: str, year: int, payload: Dict[str, Any]) -> Path:
    """Save race payload to one JSON cache file (NaN/Inf → null, strict JSON)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_file_path(grand_prix, year)
    clean = sanitize_for_json(payload)
    with path.open("w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
    return path


def build_laps_clean(laps_df: pd.DataFrame) -> pd.DataFrame:
    """Create laps_clean table with tyre_age."""
    df = laps_df.copy()

    # Rename to visualization schema.
    df = df.rename(
        columns={
            "lap_number": "lap",
            "lap_time_seconds": "lap_time_sec",
        }
    )

    # Keep only expected columns and normalize types.
    keep = ["driver", "lap", "lap_time_sec", "stint", "compound", "position"]
    df = df[keep].copy()
    for col in ["lap", "lap_time_sec", "stint", "position"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["compound"] = df["compound"].fillna("UNKNOWN")

    # Tyre age is lap index within each (driver, stint).
    df = df.sort_values(["driver", "stint", "lap"]).reset_index(drop=True)
    df["tyre_age"] = df.groupby(["driver", "stint"]).cumcount() + 1
    return df


def build_stints_clean(laps_clean: pd.DataFrame) -> pd.DataFrame:
    """Build stints summary table."""
    stints = (
        laps_clean.groupby(["driver", "stint"], dropna=False)
        .agg(
            start_lap=("lap", "min"),
            end_lap=("lap", "max"),
            compound=("compound", lambda s: s.mode().iloc[0] if not s.mode().empty else "UNKNOWN"),
        )
        .reset_index()
    )
    return stints


def build_race_trace(laps_clean: pd.DataFrame) -> pd.DataFrame:
    """
    Compute gap_to_leader by lap from cumulative lap times.

    Note:
    This is a simplified proxy for race gaps and may differ from official
    live timing in edge cases (pit cycles, lapped traffic, missing laps).
    """
    df = laps_clean.sort_values(["driver", "lap"]).copy()
    df["cum_time_sec"] = df.groupby("driver")["lap_time_sec"].cumsum()

    leader = (
        df.groupby("lap", dropna=True)["cum_time_sec"]
        .min()
        .rename("leader_cum_time_sec")
        .reset_index()
    )
    trace = df.merge(leader, on="lap", how="left")
    trace["gap_to_leader"] = trace["cum_time_sec"] - trace["leader_cum_time_sec"]
    return trace[["driver", "lap", "gap_to_leader"]]


def build_events(laps_clean: pd.DataFrame, openf1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build events table:
    - pit_stop from stint changes
    - SC/VSC from OpenF1 race control messages
    """
    # Pit stops from stint transitions.
    work = laps_clean.sort_values(["driver", "lap"]).copy()
    work["prev_stint"] = work.groupby("driver")["stint"].shift(1)
    pit = work[(work["prev_stint"].notna()) & (work["stint"] != work["prev_stint"])][
        ["lap", "driver"]
    ].copy()
    pit["type"] = "pit_stop"

    # OpenF1 track status events (lap mapping is approximate).
    # We spread SC/VSC messages across race laps by event order only.
    control_rows = []
    if not openf1_df.empty and "track_status" in openf1_df.columns:
        max_lap = int(pd.to_numeric(laps_clean["lap"], errors="coerce").max())
        # Approximate event lap by row position across SC/VSC messages.
        control = openf1_df.copy()
        control = control[control["track_status"].isin(["SC", "VSC"])].reset_index(drop=True)
        n = len(control)
        if n > 0 and max_lap > 0:
            for i, row in control.iterrows():
                lap = max(1, min(max_lap, int(round((i + 1) / n * max_lap))))
                control_rows.append({"lap": lap, "type": row["track_status"], "driver": None})

    control_df = pd.DataFrame(control_rows, columns=["lap", "type", "driver"])

    # Avoid pandas concat warning when one side is empty/all-NA.
    frames = []
    pit_df = pit[["lap", "type", "driver"]]
    if not pit_df.empty:
        frames.append(pit_df)
    if not control_df.empty:
        frames.append(control_df)

    if not frames:
        return pd.DataFrame(columns=["lap", "type", "driver"])

    events = pd.concat(frames, ignore_index=True)
    if events.empty:
        return pd.DataFrame(columns=["lap", "type", "driver"])
    return events.sort_values(["lap", "type", "driver"], na_position="last").reset_index(drop=True)


def process_race(year: int, grand_prix: str, country_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Main processing function:
    - fetch FastF1 + OpenF1
    - preprocess to clean tables
    - return JSON-serializable dict
    """
    setup_fastf1_cache()

    session = load_race_session(year, grand_prix, "R")
    resolved_event = str(session.event["EventName"])
    resolved_country = country_name or str(session.event["Country"])

    # Raw tables from sources.
    laps_raw = extract_lap_data(session)
    session_key = fetch_openf1_session_key(year, resolved_country, "Race")
    openf1_raw = (
        fetch_openf1_track_and_events(session_key)
        if session_key is not None
        else pd.DataFrame(columns=["date", "category", "message", "flag", "track_status"])
    )

    # Clean tables for visualization.
    laps_clean = build_laps_clean(laps_raw)
    stints_clean = build_stints_clean(laps_clean)
    race_trace = build_race_trace(laps_clean)
    events = build_events(laps_clean, openf1_raw)

    return {
        "meta": {
            "year": year,
            "requested_grand_prix": grand_prix,
            "resolved_event_name": resolved_event,
            "country_name": resolved_country,
            "openf1_session_key": session_key,
        },
        "laps_clean": laps_clean.to_dict(orient="records"),
        "stints_clean": stints_clean.to_dict(orient="records"),
        "race_trace": race_trace.to_dict(orient="records"),
        "events": events.to_dict(orient="records"),
    }


def get_race_data(year: int, grand_prix: str, country_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Public helper:
    1) load_from_cache
    2) process_race if missing
    3) save_to_cache
    4) return payload
    """
    cached = load_from_cache(grand_prix, year)
    if cached is not None:
        print(f"[CACHE HIT] {cache_file_path(grand_prix, year)}")
        return sanitize_for_json(cached)

    print("[CACHE MISS] Processing race data...")
    payload = process_race(year, grand_prix, country_name)

    # Save using request key style, e.g. monza_2023.json.
    cache_path = save_to_cache(grand_prix, year, payload)
    print(f"[CACHE SAVE] {cache_path}")
    return sanitize_for_json(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and cache one F1 race as JSON.")
    parser.add_argument("--year", type=int, required=False, help="Race year, e.g. 2023")
    parser.add_argument("--gp", type=str, required=False, help="Grand Prix, e.g. Monza")
    parser.add_argument("--country", type=str, default=None, help="Country name for OpenF1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # If year/gp are not passed, use interactive ordered flow.
    if args.year is None or not args.gp:
        print("Select race (ordered flow: year -> country -> race).")
        selected = get_user_race_selection()
        year = selected["year"]
        gp = selected["gp"]
        country = args.country if args.country else selected["country"]
    else:
        year = args.year
        gp = args.gp
        country = args.country

    payload = get_race_data(year, gp, country)
    print(
        f"Done. Laps: {len(payload['laps_clean'])}, "
        f"Stints: {len(payload['stints_clean'])}, "
        f"Trace rows: {len(payload['race_trace'])}, "
        f"Events: {len(payload['events'])}"
    )


if __name__ == "__main__":
    main()
