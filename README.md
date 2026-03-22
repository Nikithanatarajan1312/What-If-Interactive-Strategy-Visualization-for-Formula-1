# What-If-Interactive-Strategy-Visualization-for-Formula-1

## Backend API (simulate pit strategy)

Install deps:

```bash
pip install -r requirements.txt
```

Run server **from the repo root** (so `data/cache/` resolves correctly):

```bash
uvicorn backend.api:app --reload --port 8000
```

Swagger UI: <http://127.0.0.1:8000/docs>

**Simulate** (uses a pre-built cache JSON under `data/cache/`):

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

Or load via **year + grand_prix** (uses `get_race_data` / cache):

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

Optional fields: `new_compound`, `pit_loss_sec`.

---

## End-to-end backend flow (for D3 UI)

1. **Dropdowns:** `GET /api/options/years` → `GET /api/options/countries?year=...` → `GET /api/options/races?year=...&country=...`
2. **Load race:** `GET /api/race?year=...&grand_prix=...&country=...` (or `POST /api/race` with JSON). Save `cache_tag` from the response.
3. **What-if:** `POST /api/simulate` with `{ "cache_tag", "driver", "new_pit_lap", ... }` when the user moves the pit lap slider / picks a driver.

Details: [docs/BACKEND_FLOW.md](docs/BACKEND_FLOW.md).

---

## Frontend (integrated with this API)

Two terminals:

```bash
# Terminal 1 — repo root
pip install -r requirements.txt
uvicorn backend.api:app --reload --port 8000
```

```bash
# Terminal 2
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:5173** — the dev server proxies `/api` to the FastAPI backend on port **8000**.

Flow: pick **Year** → **Race** → charts load via `GET /api/race`; drag a pit stop → **Run Simulation** → `POST /api/simulate`.