# Backend flow (interface → cache → simulate)

This ties together **FastF1**, **OpenF1**, **preprocessing**, **JSON cache**, and the **what-if simulator** for the frontend.

## Sequence

```
┌─────────────┐     GET /api/options/*      ┌─────────────┐
│  Frontend   │ ──────────────────────────► │   FastAPI   │
│  (D3)       │ ◄────────────────────────── │   backend   │
└─────────────┘     years / countries /     └──────┬──────┘
                     races lists                   │
                                                   │ FastF1 schedule
                                                   ▼
┌─────────────┐     GET or POST /api/race   ┌─────────────┐
│  Frontend   │ ──────────────────────────► │ get_race_   │
│             │ ◄────────────────────────── │ data()      │
└─────────────┘     cache_tag + race JSON     └──────┬──────┘
                                                   │
                     ┌─────────────────────────────┼─────────────────────────────┐
                     │                             │                             │
                     ▼                             ▼                             ▼
              load_from_cache              load_race_session              save_to_cache
              (JSON hit)                   (FastF1 + OpenF1)              (JSON miss)
                     │                             │                             │
                     └─────────────────────────────┴─────────────────────────────┘
                                                   │
                                                   ▼
                              meta, laps_clean, stints_clean, race_trace, events

┌─────────────┐     POST /api/simulate       ┌─────────────┐
│  Frontend   │ ──────────────────────────► │ simulate_   │
│  (slider +  │     cache_tag, driver,      │ pit_strategy│
│   driver)   │ ◄────────────────────────── │             │
└─────────────┘     traces + simulated_laps └─────────────┘
```

## 1. Build dropdowns (year → country → race)

| Call | Purpose |
|------|---------|
| `GET /api/options/years` | List of seasons (e.g. 2018 … current year) |
| `GET /api/options/countries?year=2024` | Countries with a race that year |
| `GET /api/options/races?year=2024&country=Spain` | Grand Prix names (e.g. `Spanish Grand Prix`) |

Same data as the terminal menus in `race_cache_service.py`.

## 2. Load race (fetch + preprocess + cache)

| Call | Purpose |
|------|---------|
| `POST /api/race` with JSON `{ "year", "grand_prix", "country?" }` | **Preferred** — exact event name, no query-string mangling |
| `GET /api/race?year=...&grand_prix=...&country=...` | Still supported; easy to break if `grand_prix` is not URL-encoded |

The race list (`GET /api/races?year=...`) returns separate `year`, `grand_prix`, `country`, and `cache_tag`. **Do not** send the display `label` as `grand_prix`.

**Response shape:**

```json
{
  "cache_tag": "spanish_grand_prix_2024",
  "year": 2024,
  "grand_prix": "Spanish Grand Prix",
  "country": "Spain",
  "race": { "meta": {}, "laps_clean": [], "stints_clean": [], "race_trace": [], "events": [] }
}
```

- **First request** for that race: `get_race_data` runs FastF1 + OpenF1, preprocesses, writes `data/cache/<cache_tag>.json`.
- **Later requests**: cache hit, no refetch.

**Frontend:** keep `cache_tag` in memory (or state) for step 3.

**Driver list:** `const drivers = [...new Set(race.laps_clean.map(r => r.driver))]`.

## 3. What-if (pit lap slider + driver)

`POST /api/simulate` with body:

```json
{
  "cache_tag": "spanish_grand_prix_2024",
  "driver": "VER",
  "new_pit_lap": 28,
  "new_compound": "HARD",
  "pit_loss_sec": 21.5
}
```

You can omit `new_compound` / `pit_loss_sec` (defaults apply).  
Alternatively pass `year` + `grand_prix` (+ `country`) instead of `cache_tag` (reloads via `get_race_data`).

**Response:** `actual_trace`, `simulated_trace`, `simulated_laps`, etc. (see `simulator.py`).

## Run the server

From **repository root**:

```bash
uvicorn backend.api:app --reload --port 8000
```

CORS is open (`*`) so a static D3 page on another port can call the API.

### Race list (Vue app dropdown)

`GET /api/races?year=2024` returns `{ year, grand_prix, country, label }[]` for that season.

## Frontend (Vite + Vue)

1. Start API on port **8000** (above).
2. In another terminal:

```bash
cd frontend && npm install && npm run dev
```

Vite proxies `/api` → `http://127.0.0.1:8000` (see `frontend/vite.config.js`).

The app uses `src/api/index.js` → `src/utils/raceAdapter.js` → `src/stores/raceStore.js` to match backend payloads to chart components.

## Files

| File | Role |
|------|------|
| `backend/f1_data_pipeline.py` | FastF1 session + OpenF1 HTTP helpers |
| `backend/race_cache_service.py` | Preprocess, `get_race_data`, schedule helpers, JSON cache |
| `backend/simulator.py` | Rule-based pit what-if |
| `backend/api.py` | FastAPI routes |
| `data/cache/*.json` | One processed race per file (not CSV) |
