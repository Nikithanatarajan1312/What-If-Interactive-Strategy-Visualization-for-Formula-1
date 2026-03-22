"""
Simple F1 backend data pipeline for a student project.

What this script does:
1) Loads a FastF1 race session (default: 2023 Monza Race)
2) Extracts lap-level data into a pandas DataFrame
3) Calls OpenF1 API for race control / event-style enrichment
4) Saves raw outputs into data/raw/
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

import fastf1


OPENF1_BASE_URL = "https://api.openf1.org/v1"
RAW_OUTPUT_DIR = Path("data/raw")


def setup_fastf1_cache(cache_dir: str = "data/cache") -> None:
    """Enable local FastF1 cache so repeated runs are faster."""
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(cache_dir)


def load_race_session(year: int, grand_prix: str, session_name: str = "R"):
    """
    Load a race session using FastF1.

    Example:
    - year=2023
    - grand_prix='Monza'
    - session_name='R' (race)
    """
    session = fastf1.get_session(year, grand_prix, session_name)
    session.load()  # includes laps, weather, results, etc.
    return session


def safe_lap_time_seconds(lap_time: Any) -> Optional[float]:
    """Convert lap time timedelta to seconds; return None if missing."""
    if pd.isna(lap_time):
        return None
    try:
        return float(lap_time.total_seconds())
    except Exception:
        return None


def extract_lap_data(session) -> pd.DataFrame:
    """
    Extract simple lap-level columns:
    - driver
    - lap number
    - lap time (seconds)
    - stint
    - compound
    - position
    """
    laps = session.laps.copy()

    # Keep only columns we need and rename to clean output names.
    selected = laps[
        ["Driver", "LapNumber", "LapTime", "Stint", "Compound", "Position"]
    ].copy()

    selected["LapTimeSeconds"] = selected["LapTime"].apply(safe_lap_time_seconds)
    selected = selected.drop(columns=["LapTime"])
    selected = selected.rename(
        columns={
            "Driver": "driver",
            "LapNumber": "lap_number",
            "Stint": "stint",
            "Compound": "compound",
            "Position": "position",
            "LapTimeSeconds": "lap_time_seconds",
        }
    )

    # Basic missing value handling for easier downstream use.
    selected["compound"] = selected["compound"].fillna("UNKNOWN")
    selected["stint"] = selected["stint"].fillna(-1)
    selected["position"] = selected["position"].fillna(-1)

    # Convert numeric columns safely.
    selected["lap_number"] = pd.to_numeric(selected["lap_number"], errors="coerce")
    selected["stint"] = pd.to_numeric(selected["stint"], errors="coerce")
    selected["position"] = pd.to_numeric(selected["position"], errors="coerce")

    return selected


def call_openf1(endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Call OpenF1 endpoint and return JSON list (or empty list on failure)."""
    url = f"{OPENF1_BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []
    except requests.RequestException as exc:
        print(f"[WARN] OpenF1 request failed ({endpoint}): {exc}")
        return []


def fetch_openf1_session_key(year: int, country_name: str, session_name: str = "Race") -> Optional[int]:
    """
    Find OpenF1 session_key for a given year/country/session.

    Uses:
    - /v1/sessions?year=...&country_name=...&session_name=...
    """
    sessions = call_openf1(
        "sessions",
        {"year": year, "country_name": country_name, "session_name": session_name},
    )
    if not sessions:
        return None

    # Take the first match for a simple student-project workflow.
    return sessions[0].get("session_key")


def map_track_status(message_text: str) -> str:
    """
    Map race control message text to simplified track status.
    - SC: Safety Car
    - VSC: Virtual Safety Car
    - green: normal racing
    - other: anything else
    """
    text = (message_text or "").upper()
    if "VIRTUAL SAFETY CAR" in text or "VSC" in text:
        return "VSC"
    if "SAFETY CAR" in text or "SC DEPLOYED" in text:
        return "SC"
    if "GREEN FLAG" in text or "GREEN LIGHT" in text:
        return "green"
    return "other"


def fetch_openf1_track_and_events(session_key: int) -> pd.DataFrame:
    """
    Fetch race-control style events and derive simplified track status.

    Note:
    OpenF1 data availability can vary by session. We use race control
    messages as a practical source for SC/VSC/green signals and events.
    """
    # OpenF1 docs endpoint is "race_control".
    # Keep a fallback to legacy naming in case environments differ.
    messages = call_openf1("race_control", {"session_key": session_key})
    if not messages:
        messages = call_openf1("race_control_messages", {"session_key": session_key})
    if not messages:
        return pd.DataFrame(
            columns=["date", "category", "message", "flag", "track_status"]
        )

    df = pd.DataFrame(messages)

    # Keep fields if available; otherwise create empty columns.
    for col in ["date", "category", "message", "flag"]:
        if col not in df.columns:
            df[col] = None

    df["track_status"] = df["message"].apply(map_track_status)
    return df[["date", "category", "message", "flag", "track_status"]]


def save_outputs(laps_df: pd.DataFrame, openf1_df: pd.DataFrame, tag: str) -> None:
    """Save outputs to data/raw/ as CSV and JSON."""
    RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    laps_csv = RAW_OUTPUT_DIR / f"{tag}_laps.csv"
    laps_json = RAW_OUTPUT_DIR / f"{tag}_laps.json"
    openf1_csv = RAW_OUTPUT_DIR / f"{tag}_openf1_events.csv"
    openf1_json = RAW_OUTPUT_DIR / f"{tag}_openf1_events.json"

    laps_df.to_csv(laps_csv, index=False)
    laps_df.to_json(laps_json, orient="records", indent=2)
    openf1_df.to_csv(openf1_csv, index=False)
    openf1_df.to_json(openf1_json, orient="records", indent=2)

    print(f"Saved: {laps_csv}")
    print(f"Saved: {laps_json}")
    print(f"Saved: {openf1_csv}")
    print(f"Saved: {openf1_json}")


def slugify(text: str) -> str:
    """Create a simple lowercase filename-friendly tag."""
    return (
        (text or "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def validate_grand_prix_input(grand_prix: str) -> None:
    """
    Reject very short non-numeric race inputs.

    FastF1 can resolve short strings, but that can be too ambiguous
    (e.g., "a"). We require at least 3 letters unless the user is
    passing a numeric round (e.g., "1", "14").
    """
    value = (grand_prix or "").strip()
    if value.isdigit():
        return
    if len(value) < 3:
        raise ValueError(
            "Grand Prix input is too short. Use at least 3 letters "
            "(example: 'Monza', 'China') or a round number like '1'."
        )


def select_from_menu(prompt: str, options: List[str], default_index: int = 0) -> str:
    """
    Simple terminal dropdown using numbered options.

    User enters the option number, or presses Enter for default.
    """
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
    """Return a practical year range for modern F1 datasets."""
    current_year = pd.Timestamp.now().year
    return list(range(start_year, current_year + 1))


def get_user_inputs() -> Dict[str, Any]:
    """
    Ask user for race inputs with dropdown-style menus:
    - year
    - country
    - race (event)

    Press Enter at each step to use default.
    """
    # Year dropdown
    years = get_available_years()
    year_labels = [str(y) for y in years]
    default_year = 2023 if 2023 in years else years[-1]
    default_year_index = years.index(default_year)
    year_selected = select_from_menu(
        "Select year:", year_labels, default_index=default_year_index
    )
    year = int(year_selected)

    # Build country + race options from official FastF1 event schedule.
    schedule = fastf1.get_event_schedule(year)
    races_only = schedule[schedule["Session5"] == "Race"].copy()

    countries = sorted({str(c) for c in races_only["Country"].dropna().tolist()})
    default_country = "Italy" if "Italy" in countries else countries[0]
    default_country_index = countries.index(default_country)
    country_name = select_from_menu(
        "Select country:", countries, default_index=default_country_index
    )

    races_in_country = races_only[races_only["Country"] == country_name]
    race_options = [str(name) for name in races_in_country["EventName"].tolist()]

    # If no events found for country (unlikely), fall back to all races.
    if not race_options:
        race_options = [str(name) for name in races_only["EventName"].tolist()]

    default_race = "Italian Grand Prix" if "Italian Grand Prix" in race_options else race_options[0]
    default_race_index = race_options.index(default_race)
    grand_prix = select_from_menu(
        "Select race:", race_options, default_index=default_race_index
    )

    return {
        "year": year,
        "grand_prix": grand_prix,
        "country_name": country_name,
    }


def parse_args() -> argparse.Namespace:
    """Optional CLI flags for non-interactive runs."""
    parser = argparse.ArgumentParser(
        description="Fetch FastF1 lap data + OpenF1 events for a race session."
    )
    parser.add_argument("--year", type=int, help="Race year (e.g., 2023)")
    parser.add_argument("--gp", type=str, help="Grand Prix for FastF1 (e.g., Monza)")
    parser.add_argument(
        "--country",
        type=str,
        help="Country name for OpenF1 session lookup (e.g., Italy)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use defaults/CLI args only and skip input prompts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.non_interactive:
        year = args.year if args.year is not None else 2023
        grand_prix = args.gp if args.gp else "Monza"
        country_name = args.country if args.country else "Italy"
    else:
        print("Select race (press Enter to use defaults).")
        user_inputs = get_user_inputs()
        year = args.year if args.year is not None else user_inputs["year"]
        grand_prix = args.gp if args.gp else user_inputs["grand_prix"]
        country_name = args.country if args.country else user_inputs["country_name"]

    validate_grand_prix_input(grand_prix)

    print("Setting up FastF1 cache...")
    setup_fastf1_cache()

    print(f"Loading FastF1 session: {year} {grand_prix} Race")
    session = load_race_session(year, grand_prix, "R")
    resolved_event_name = str(session.event["EventName"])
    file_tag = f"{year}_{slugify(resolved_event_name)}_race"
    print(f"Resolved event: {resolved_event_name}")

    print("Extracting lap-level data...")
    laps_df = extract_lap_data(session)
    print("\nLap data sample:")
    print(laps_df.head(10))

    print("\nFetching OpenF1 session metadata...")
    session_key = fetch_openf1_session_key(year, country_name, "Race")
    if session_key is None:
        print("[WARN] Could not find OpenF1 session_key. OpenF1 dataframe will be empty.")
        openf1_df = pd.DataFrame(
            columns=["date", "category", "message", "flag", "track_status"]
        )
    else:
        print(f"Found OpenF1 session_key: {session_key}")
        print("Fetching OpenF1 race control / event data...")
        openf1_df = fetch_openf1_track_and_events(session_key)

    print("\nOpenF1 data sample:")
    print(openf1_df.head(10))

    print("\nSaving raw outputs...")
    save_outputs(laps_df, openf1_df, file_tag)
    print("\nDone.")


if __name__ == "__main__":
    main()
