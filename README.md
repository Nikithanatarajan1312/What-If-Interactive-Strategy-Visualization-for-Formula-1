# What If? — Interactive F1 Strategy Visualization

Explore **Grand Prix strategy** with real session data (**FastF1** / **OpenF1**), cached as JSON. Load a race, inspect **gap traces**, **positions**, **tyre stints**, and a **pit-window heatmap**. Edit a pit stop, **run a what-if simulation**, and compare **actual vs simulated** outcomes—including optional **Monte Carlo** uncertainty on the simulated gap trace.

---

## What this project does

- **Browse** seasons and races; **load** a full preprocessed payload (`laps_clean`, `stints_clean`, `race_trace`, …).
- **Visualize** how the race unfolded and how alternative pit timing might change the result.
- **Simulate** strategy changes via `POST /api/simulate`; overlay simulated traces on charts. Multiple drivers can keep **saved** what-if runs in one session.
- The backend can use **hybrid ML + heuristics** when artifacts exist under `backend/strategy/artifacts/`, with **fallback** when not.

---

## Dashboard (panels)

| Panel | What you see |
|--------|----------------|
| **Race trace** | Gap to leader vs lap; actual lines + pit markers; simulated dashed line and **p5–p95** band when Monte Carlo spread is meaningful. |
| **Bump chart** | Position vs lap; overtakes highlighted; optional sim overlay. |
| **Stint bar** | Tyre-compound timeline per driver. |
| **Pit heatmap** | Model **pit-window** tradeoffs by candidate stop lap (`POST /api/strategy-viz`). |
| **Delta breakdown** | Two **separate** blocks: **Baseline breakdown** (full modeled component totals per driver—*why they finished where they did*) and **What-if delta** (saved simulation only—*how the edited strategy changed the outcome*, deltas vs actual). Same pit / pace / traffic **colors** in both. |
| **Controls** | Year, race, drivers, pit editor, run simulation, toggles. |

**Stack:** Vue 3, Vite, Pinia, **D3** · FastAPI, Uvicorn · FastF1, OpenF1, pandas · optional scikit-learn / joblib for strategy models.

---

## Quick start (local)

**1. Backend** — from the **repository root**:

```bash
pip install -r requirements.txt
uvicorn backend.api:app --reload --port 8000
```

API docs: <http://127.0.0.1:8000/docs>

**2. Frontend** — second terminal:

```bash
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:5173**. Vite **proxies `/api`** to port **8000** (`frontend/vite.config.js`).

**Flow:** Year → Race → explore charts → adjust pit → **Run simulation** → toggle simulated overlay.

---

## API flow (high level)

```
┌─────────────┐  GET /api/options/years     ┌─────────────┐
│  Frontend   │  GET /api/races?year=…  ──► │   FastAPI   │
│  (Vue+D3)   │ ◄────────────────────────── │   backend   │
└─────────────┘                             └──────┬──────┘
                                                   ▼
┌─────────────┐  POST /api/race (preferred) ┌─────────────┐
│  Frontend   │  or GET /api/race           │ get_race_   │
│             │ ◄────────────────────────── │ data()      │
└─────────────┘  cache_tag + race JSON       └──────┬──────┘
                     cache hit OR FastF1 + OpenF1 + save JSON
                                                   ▼
                        laps_clean, stints_clean, race_trace, …

┌─────────────┐  POST /api/strategy-viz     ┌─────────────┐
│  Frontend   │ ──────────────────────────► │ strategy_   │
│             │ ◄────────────────────────── │ model viz   │
└─────────────┘                             └─────────────┘

┌─────────────┐  POST /api/simulate         ┌─────────────┐
│  Frontend   │ ──────────────────────────► │ simulate_   │
│             │ ◄────────────────────────── │ pit_strategy│
└─────────────┘  traces + simulated_laps    │ (strategy/) │
                                            └─────────────┘
```

### Dropdowns and race list

The Vue app uses **`GET /api/options/years`** and the **flat** list **`GET /api/races?year=…`** (returns `year`, `grand_prix`, `country`, `label`, **`cache_tag`**).

For country-scoped UIs you can also use **`GET /api/options/countries`** and **`GET /api/options/races?year=…&country=…`** (names only).

**Do not** use the display `label` as `grand_prix` when calling **`POST /api/race`**; use the exact `grand_prix` and `country` from the list row.

### Load race

Prefer **`POST /api/race`** with JSON `{ "year", "grand_prix", "country" }` so `grand_prix` is never mangled. **`GET /api/race`** with query params still works.

First load may fetch via FastF1/OpenF1 and write **`data/cache/<cache_tag>.json`**; later loads hit the cache.

### Simulate

**`POST /api/simulate`** accepts `cache_tag` **or** `year` + `grand_prix` (+ `country`). Optional: `new_compound`, `pit_loss_sec`, `monte_carlo_samples` (1 = deterministic; 2+ = gap percentiles), `random_seed`, `use_ml`.

Response includes `actual_trace`, `simulated_trace` (median gap + `p5`…`p95`), `simulated_laps` (with mirrored `simulated_gap_p05`…`p95` per lap), `delta_breakdown`, `monte_carlo_samples`, `has_simulated_gap_uncertainty`.

### Frontend data path

`frontend/src/api/index.js` → **`raceAdapter.js`** → **`stores/raceStore.js`** → components.

---

## Try `curl`

```bash
curl -s -X POST http://127.0.0.1:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "cache_tag": "spanish_grand_prix_2024",
    "driver": "VER",
    "new_pit_lap": 28,
    "new_compound": "HARD",
    "pit_loss_sec": 21.5
  }' | head -c 2000
```

Or inline race resolution:

```bash
curl -s -X POST http://127.0.0.1:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2024,
    "grand_prix": "Spanish Grand Prix",
    "country": "Spain",
    "driver": "VER",
    "new_pit_lap": 28
  }'
```

---

## Repository layout

```
├── frontend/                 # Vue 3 + Vite SPA
│   ├── src/api/index.js
│   ├── src/stores/raceStore.js
│   ├── src/utils/raceAdapter.js
│   └── src/components/       # RaceTrace, BumpChart, StintBar, PitHeatmap, DeltaBreakdown, ControlsPanel
├── backend/
│   ├── api.py                # FastAPI routes
│   ├── race_cache_service.py # get_race_data, JSON cache
│   ├── f1_data_pipeline.py  # FastF1 + OpenF1
│   ├── strategy_model.py     # Strategy viz / pit-window helpers
│   ├── simulator.py          # Shim → strategy.simulator
│   └── strategy/
│       ├── simulator.py      # Gap-trace simulation, Monte Carlo
│       └── artifacts/        # Optional joblib models
├── data/cache/               # Cached race JSON (per cache_tag)
├── docs/                     # See note below
└── requirements.txt
```

Legacy link: **`docs/BACKEND_FLOW.md`** redirects here so the README stays the single overview.

---

## Deployment

- Run Uvicorn **from the repo root** so `data/cache/` and `backend/strategy/artifacts/` resolve.
- **Build:** `cd frontend && npm ci && npm run build` → `frontend/dist/`.
- The UI calls **`/api/...`** relative paths. Prefer **one origin** in production (reverse-proxy `/api` to Uvicorn and serve static files), or set a build-time API base URL for split hosting.
- CORS defaults to permissive; tighten if needed.

```bash
uvicorn backend.api:app --host 0.0.0.0 --port 8000
```

Health / docs: **`/docs`**.
