"""
FastAPI backend: race loading (fetch/cache/preprocess) + pit what-if simulation.

Full UI flow:
  1) GET /api/options/years -> /countries -> /races
  2) GET or POST /api/race -> full payload + cache_tag
  3) POST /api/simulate with cache_tag (or year+grand_prix) + driver + new_pit_lap

Run from repo root:
  uvicorn backend.api:app --reload --port 8000
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import cache + simulator separately: missing simulator must not fall back to broken
# flat `race_cache_service` when running as `uvicorn backend.api:app`.
try:
    from .race_cache_service import (
        cache_tag_for_request,
        get_available_years,
        get_race_data,
        list_countries_for_year,
        list_race_names_for_country,
    )
except ImportError:
    from race_cache_service import (
        cache_tag_for_request,
        get_available_years,
        get_race_data,
        list_countries_for_year,
        list_race_names_for_country,
    )

try:
    from .simulator import simulate_pit_strategy
except ImportError:
    from simulator import simulate_pit_strategy

try:
    from .json_sanitize import sanitize_for_json
except ImportError:
    from json_sanitize import sanitize_for_json

# Project root = parent of backend/
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_JSON_DIR = REPO_ROOT / "data" / "cache"

SAFE_CACHE_TAG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

app = FastAPI(title="F1 Strategy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RaceLoadRequest(BaseModel):
    """Load one race: FastF1 + OpenF1 -> cache JSON -> same structure as CLI cache."""

    year: int
    grand_prix: str = Field(..., min_length=1, description="e.g. Spanish Grand Prix")
    country: Optional[str] = Field(
        default=None,
        description="Host country for OpenF1 session lookup; defaults from FastF1 event",
    )


class SimulateRequest(BaseModel):
    """Race source: either cache_tag OR (year + grand_prix)."""

    cache_tag: Optional[str] = Field(
        default=None,
        description="Filename stem under data/cache/, e.g. spanish_grand_prix_2024",
    )
    year: Optional[int] = Field(default=None, description="Used with grand_prix if no cache_tag")
    grand_prix: Optional[str] = Field(
        default=None,
        description="FastF1 event name, e.g. Spanish Grand Prix",
    )
    country: Optional[str] = Field(
        default=None,
        description="Country for OpenF1 when fetching via get_race_data",
    )

    driver: str = Field(..., min_length=1, description="Driver code, e.g. VER")
    new_pit_lap: int = Field(..., ge=1, description="Lap number where the pit stop happens")
    new_compound: Optional[str] = Field(
        default=None,
        description="Tyre after stop: SOFT, MEDIUM, HARD, ... (optional)",
    )
    pit_loss_sec: Optional[float] = Field(
        default=None,
        gt=0,
        description="Extra seconds on pit lap (optional, default ~22)",
    )


def load_payload_from_cache_tag(cache_tag: str) -> Dict[str, Any]:
    if not SAFE_CACHE_TAG.match(cache_tag.strip()):
        raise HTTPException(
            status_code=400,
            detail="Invalid cache_tag: use letters, numbers, underscore, hyphen only.",
        )
    path = CACHE_JSON_DIR / f"{cache_tag.strip()}.json"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Cache file not found: {path.relative_to(REPO_ROOT)}",
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_race_payload(body: SimulateRequest) -> Dict[str, Any]:
    if body.cache_tag:
        return load_payload_from_cache_tag(body.cache_tag)
    if body.year is not None and body.grand_prix:
        return get_race_data(body.year, body.grand_prix.strip(), body.country)
    raise HTTPException(
        status_code=400,
        detail="Provide either cache_tag, or both year and grand_prix.",
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Step 1: dropdown data (same logic as terminal menus) ---


@app.get("/api/options/years", response_model=List[int])
def api_options_years():
    return get_available_years()


@app.get("/api/options/countries", response_model=List[str])
def api_options_countries(year: int = Query(..., description="Season year")):
    try:
        return list_countries_for_year(year)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not load schedule for {year}: {exc}"
        ) from exc


@app.get("/api/options/races", response_model=List[str])
def api_options_races(
    year: int = Query(...),
    country: str = Query(..., description="Country name, e.g. Spain"),
):
    try:
        return list_race_names_for_country(year, country)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not list races for {year} / {country}: {exc}",
        ) from exc


@app.get("/api/races")
def api_races_flat(year: int = Query(..., description="Season to list all Grands Prix for")):
    """
    Flat list for a single-season race dropdown (year + grand_prix + country).
    """
    try:
        countries = list_countries_for_year(year)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not load schedule for {year}: {exc}"
        ) from exc

    out: List[Dict[str, Any]] = []
    for country in countries:
        for gp in list_race_names_for_country(year, country):
            gp_strip = str(gp).strip()
            out.append(
                {
                    "year": year,
                    "grand_prix": gp_strip,
                    "country": country,
                    # Shown in UI; year is chosen separately — do not use as grand_prix.
                    "label": f"{gp_strip} ({country})",
                    "cache_tag": cache_tag_for_request(gp_strip, year),
                }
            )
    return out


# --- Step 2: load full preprocessed race (cache hit or fetch+save) ---


def _normalize_country(country: Optional[str]) -> Optional[str]:
    if country is None:
        return None
    s = str(country).strip()
    return s if s else None


def _load_race_payload(year: int, grand_prix: str, country: Optional[str]) -> Dict[str, Any]:
    try:
        payload = get_race_data(year, grand_prix.strip(), _normalize_country(country))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to load race data: {exc}",
        ) from exc
    laps = payload.get("laps_clean") or []
    if not laps:
        raise HTTPException(
            status_code=502,
            detail="No race data available (empty laps). The session may be incomplete or not yet held.",
        )
    return payload


@app.get("/api/race")
def api_race_get(
    year: int = Query(...),
    grand_prix: str = Query(..., min_length=1),
    country: Optional[str] = Query(None),
):
    """
    Fetch/cache/preprocess one race. Returns ``cache_tag`` for later ``/api/simulate`` calls.

    Prefer **POST /api/race** from the frontend (JSON body) so ``grand_prix`` is never
    mangled by query strings.
    """
    payload = _load_race_payload(year, grand_prix, _normalize_country(country))
    tag = cache_tag_for_request(grand_prix.strip(), year)
    return {
        "cache_tag": tag,
        "year": year,
        "grand_prix": grand_prix.strip(),
        "country": _normalize_country(country) or payload.get("meta", {}).get("country_name"),
        "race": sanitize_for_json(payload),
    }


@app.post("/api/race")
def api_race_post(body: RaceLoadRequest):
    """Preferred load path: JSON ``{ year, grand_prix, country? }`` — exact FastF1 event names."""
    country = _normalize_country(body.country)
    payload = _load_race_payload(body.year, body.grand_prix, country)
    tag = cache_tag_for_request(body.grand_prix.strip(), body.year)
    return {
        "cache_tag": tag,
        "year": body.year,
        "grand_prix": body.grand_prix.strip(),
        "country": country or payload.get("meta", {}).get("country_name"),
        "race": sanitize_for_json(payload),
    }


# --- Step 3: what-if simulation (slider lap + driver) ---


@app.post("/api/simulate")
def api_simulate(body: SimulateRequest):
    """
    Run rule-based pit what-if on cached / loaded race data.

    Returns the same structure as simulate_pit_strategy (JSON-safe floats).
    """
    payload = resolve_race_payload(body)

    try:
        result = simulate_pit_strategy(
            payload,
            driver=body.driver,
            new_pit_lap=body.new_pit_lap,
            new_compound=body.new_compound,
            pit_loss_sec=body.pit_loss_sec,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return sanitize_for_json(result)
