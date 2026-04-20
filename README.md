# What If? — Interactive F1 Strategy Visualization

Explore Grand Prix strategy with real session data (FastF1 / OpenF1), cached as JSON. Load a race, inspect how the field evolved, stress-test a different pit lap, and compare actual and modelled outcomes side by side—including optional Monte Carlo uncertainty on the simulated gap trace.

---

## What this project does

- Browse seasons and races; load a full preprocessed payload (`laps_clean`, `stints_clean`, `race_trace`, …).
- Visualize pace, position, tyres, and modelled pit-window tradeoffs in a single dashboard.
- Simulate strategy changes via `POST /api/simulate` and overlay results on the charts. Multiple drivers can keep saved what-if runs in one session.
- The backend can use hybrid ML plus heuristics when artifacts exist under `backend/strategy/artifacts/`, with fallback when not.

---

## Visualization

The UI is a **linked dashboard**: one race selection drives every view. Charts are built with **D3** inside Vue; shared state (selected race, drivers, hovered lap, brush range, simulated overlays) keeps the panels visually aligned. Typical flow: scan the trace and positions, read tyre stints, then use the heatmap and delta panels to interpret *why* a stop window matters and *what changes* when you move a pit.

### Shared interactions

- **Brush on the time-based charts** (race trace, bump chart) to zoom a lap range; reset returns to the full race.
- **Hover** shows a lap-synchronized crosshair and tooltip where implemented (gap, position, tyre context).
- **Driver chips / selection** in the controls reduce clutter when you only care about a subset of the field.
- **Simulated overlay** uses distinct styling (dashed lines, italic labels) so it never reads as observed telemetry.

### Race trace (gap to leader)

Each driver is a **line in their team color**: vertical axis is **seconds behind the race leader** (gap), horizontal axis is **lap number**. Lower on the chart means closer to the leader. **Pit stops** appear as markers on the lap before the stop, coloured by the **compound fitted after the stop** (soft / medium / hard / inter / wet).

When you run a simulation with **more than one Monte Carlo sample**, the backend returns per-lap percentiles for the simulated gap. The chart draws a **shaded band** (5th–95th and 25th–75th) only when that spread is meaningful—never a decorative ribbon on real data.

### Bump chart (positions)

**Classification position** (P1 at the top of the scale) is plotted against lap. Line crossings are easy to read as position changes; **overtakes** are called out with small circles (green when the driver gained a place, red when they lost). The chart stops at retirement if positions become invalid. A **saved simulation** adds a dashed position trace for that driver when enabled.

### Stint bar

A **horizontal strip per driver** shows **compound** segments in canonical tyre colours, with length proportional to stint duration in laps. It answers “who was on what rubber, and for how long?” at a glance, and complements the gap chart when you explain pace and stops.

### Pit window heatmap

A **2D grid**: one axis is **candidate pit lap**, the other is **driver** (or the model’s pit-window dimension as implemented). Cell colour encodes the **modelled gain or loss** (e.g. final gap vs baseline) if that driver stopped on that lap—warmer/cooler or signed colour scales depending on theme. The view is fed by `POST /api/strategy-viz` so it stays consistent with the same strategy model as the rest of the app.

### Delta breakdown

This panel is split on purpose so **scales are not mixed**:

1. **Baseline breakdown** — For each selected driver, **stacked horizontal bars** show **modelled components** (pit timing, tyre/pace, traffic/rejoin) that sum to a **full “model total”** explanation of outcome. This is *descriptive*: why the model thinks they ended up where they did relative to the narrative encoded in the breakdown.

2. **What-if delta** — Only drivers with a **saved simulation** appear. Bars show **changes vs the actual baseline** (same component colours). **Positive** values mean improvement (e.g. closer to the leader in gap terms, per the model); **negative** mean worse. A line labelled **net vs actual** ties to the overall simulated delta.

Colours are **consistent** between the two blocks (pit / pace / traffic), so you can map stripes in one section to stripes in the other without relearning the legend.

### Controls strip

Pick **year** and **race**, then load. Choose **drivers** to include, **edit** the pit strategy for one driver (move a stop, change compound), and **run simulation**. Toggles control whether simulated layers appear on the charts once you have saved runs.

---

## Tech stack

| Layer | Technologies |
|--------|----------------|
| Frontend | Vue 3, Vite, Pinia, D3 |
| Backend | FastAPI, Uvicorn, Pydantic |
| Data | FastF1, OpenF1, pandas |
| Models (optional) | scikit-learn, joblib under `backend/strategy/` |

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
└── requirements.txt
```

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
