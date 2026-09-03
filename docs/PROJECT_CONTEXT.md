# Freight Charter Compass — Project Context

SIH26006 · Ministry of Steel · "Development of an Intelligent Freight
Forecasting Model for Optimized Vessel Chartering and Bulk Cargo Procurement
from overseas to East Coast of India." Category: Software. Theme:
Transportation & Logistics. Submission deadline: 30 September 2026.

This file is the single source of truth for a new session picking up this
project with no memory of prior conversations. Read this file first.

## Problem statement (paraphrased)

SAIL procures bulk cargo (coal) from overseas and ships it to India's East
Coast ports. Procurement decisions require: when to charter, which vessel
class, which port, whether the vessel can physically operate at that port,
total logistics cost, risk, and the best cost/risk tradeoff. Freight markets
are volatile; the decision is currently manual.

## Objective

A working prototype implementing the pipeline **Predict → Simulate →
Optimize → Recommend**: forecast freight-relevant market trends from real
public data, physically eliminate incompatible vessel/port combinations,
calculate voyage cost transparently, and recommend book-now vs. wait with a
risk-adjusted score and a plain-language explanation.

## Team & constraints

1–2 person team. ~36-hour effective build budget. Development happens on
the user's own machine at `C:\ps 6` (this repo), primarily via a terminal
they run directly — see "Environment / setup" below for why.

## Locked scope decisions

- **MVP dashboard: 5 pages**, not 7. Overview, Freight Forecast, Vessel &
  Port Recommendation (merged), Cost Optimization, Data Sources &
  Assumptions. Scenario Simulator and a dedicated Port Comparison page are
  Phase 2, built only if Phase 1 finishes with hours to spare.
- **Forecasting model: SARIMAX** (statsmodels) as the sole primary model,
  evaluated against a seasonal-naive baseline. XGBoost is an optional
  Phase 3 side-by-side comparison, never the primary model. Reasoning: with
  the amount of real, licensed historical data actually available (see Data
  sources below), a statistical model is more defensible, more explainable,
  and less prone to overfitting than a boosted-tree or neural model. Full
  reasoning in DECISIONS.md.
- **Ports staged: 3 first** (Visakhapatnam, Paradip, Dhamra), then Gangavaram
  / Krishnapatnam / Haldia added only after the MVP works end-to-end. The
  compatibility engine is data-driven, so adding a port later is a JSON row,
  not new code.
- **No microservices, no Docker/K8s, no Postgres, no auth, no mobile app.**
  Full "what NOT to build" list in the architecture proposal (artifact,
  linked from the chat this project started in) and in DECISIONS.md.

## Architecture

```
User Input → Data Ingestion → Cleaning & Features → Freight Forecast
  → Vessel + Port Constraint Engine → Voyage Cost Calculator
  → Risk-Adjusted Optimizer → Book-Now vs Wait → Scenario Simulator
  → Recommendation + Explanation → Dashboard
```

Single FastAPI monolith (no service boundaries) importing plain Python
modules for each engine step. SQLite file database. Pre-computed/offline
data ingestion and model training; the API only does inference and
arithmetic at request time (no live external calls during a demo).

## Technology stack

- Backend: Python 3.10+, FastAPI, plain `sqlite3` (stdlib) — no ORM at this
  stage, see DECISIONS.md.
- Frontend: React + Vite + TypeScript (not yet built — see TODO.md).
- Charts: Recharts. Map: React-Leaflet. (not yet built)
- Database: SQLite file (`backend/freight.db`, gitignored, rebuilt from seed
  JSON on every app startup).
- ML: statsmodels (SARIMAX) + numpy for hand-rolled MAE/RMSE/MAPE — no
  scikit-learn dependency, see DECISIONS.md #13. Fit-on-request with an
  in-memory cache (`app/engine/forecast.py`), not a separate offline
  training script.

## Database schema (current)

Two tables exist so far — `backend/app/db/schema.sql`:

- `vessel_classes` — vessel_type (PK), dwt_tonnes, draft_m, loa_m, beam_m,
  speed_knots, fuel_cons_tpd, opex_usd_day, is_assumption, source, source_url
- `ports` — port_id (PK), name, state, lat, lon, lat_lon_provenance,
  max_draft_m, max_loa_m, max_beam_m, coal_handling, berth_reference,
  annual_capacity_mtpa, verified, source, source_url, source_date

Plus (added Hour 2-5/9-13 as their owning modules were built):
`commodity_price_history`, `port_traffic_history` (schema in place, not
yet populated), `origin_ports` (the 3 fixed overseas coal-loading ports).
Remaining planned tables (routes_cache, voyage_estimates, scenario_log,
assumptions_registry) are added when the module that owns them is built —
not created speculatively upfront.

## API structure (current)

- `GET /health`
- `GET /api/v1/vessels` — all 4 vessel classes
- `GET /api/v1/ports` — all seeded ports
- `GET /api/v1/ports/{port_id}` — one port, 404 if unknown
- `GET /api/v1/commodity-prices` — real price history, optional `?commodity=` filter
- `GET /api/v1/forecast/{commodity}?horizon=1..24` — Module 1 (Predict):
  SARIMAX vs. seasonal-naive baseline, evaluated on a real holdout. 404 for
  an unknown/empty commodity; `status: "insufficient_data"` (not an error)
  if fewer than 30 months of history are loaded for that commodity.
- `GET /api/v1/compatibility/check?vessel_type=X&port_id=Y` — Module 4
  (physical gate): draft/LOA/beam + coal-handling check, with the exact
  rejection reason(s). 404 for an unknown vessel_type or port_id.
- `GET /api/v1/compatibility/matrix` — every vessel class x every seeded
  port (currently 12 combinations), same format.
- `GET /api/v1/origin-ports` — the 3 fixed overseas coal-loading ports
  (Australia/South Africa/Indonesia).
- `GET /api/v1/voyage/calculate?vessel_type=&origin_id=&port_id=&cargo_tonnes=`
  — Module 5 (Simulate): one-way laden voyage distance/time/cost. 404 for
  an unknown vessel/origin/port. `cargo_tonnes` optional, defaults to the
  vessel's full DWT.
- `GET /api/v1/optimize/{port_id}?cargo_tonnes=` — Module 6 (Optimize):
  every physically-compatible vessel x origin-port combination for this
  destination, ranked by risk-adjusted cost per tonne (risk = physical
  clearance margin at berth, see DECISIONS.md #16). 404 for an unknown
  port_id. An incompatible or too-small-for-cargo_tonnes option is simply
  absent from the ranking, not flagged.

Planned next (Module 7 onward): `/api/v1/decision/book-vs-wait`,
`/api/v1/scenario/simulate`, `/api/v1/data-sources`.

## Data sources — real vs. calculated vs. simulated

Full breakdown with source URLs, licence notes, and per-port confirmation
status lives in the architecture proposal artifact from the planning
conversation. Summary:

**Real, confirmed reachable without login:** World Bank Pink Sheet
(thedocs.worldbank.org, monthly coal/oil prices since 1960, free XLSX), FRED
PCOALAUUSDM (free API), RBA Index of Commodity Prices (free, includes a
coking-coal sub-index), shipmin.gov.in monthly port cargo PDFs, data.gov.in
port traffic dataset, six East Coast port authority sites (Visakhapatnam, Dhamra, and Paradip
numbers confirmed; Gangavaram, Krishnapatnam, Haldia sources confirmed
reachable, exact figures pending extraction — deferred until the Hour-27
checkpoint per the port-staging decision, DECISIONS.md #5).

**Confirmed NOT freely available:** Baltic Exchange's route-level rates
(BCI/BPI/BSI, the actual Panamax Australia→India voyage rate) — subscription
only. We use the openly viewable Baltic Dry Index level as a
periodically-updated qualitative indicator, not a bulk-licensed model input.

**Calculated:** voyage distance (multi-waypoint great-circle, routed around
landmasses), sailing time, fuel cost, an estimated freight $/tonne
(calibrated against trade-press reference points, not a direct market
quote), total logistics cost, all risk/optimizer scores.

**Simulated, always labelled:** live port congestion (real monthly traffic
used as a slow proxy + a user-controlled multiplier), vessel availability,
SAIL's actual cargo/contract volumes (illustrative scenarios only).

## Current implementation status

**Done (commit `01-initial-architecture` + Hour 2-5 data-pipeline commits):**
- Repo skeleton, `.gitignore`, folder structure.
- `vessel_classes`, `ports`, `commodity_price_history`, `port_traffic_history`
  schema, seeded with 4 vessel classes (industry-typical, flagged as
  assumptions) and 3 ports — all three **verified: true**:
  Visakhapatnam (18.1m coal-berth draft), Dhamra (18m draft, 207,000 DWT
  vessel record), Paradip (17.1m draft via the Kalinga International Coal
  Terminal, confirmed Capesize-capable to 165,000 DWT — two independent
  sources).
- **Full real commodity-price history ingested and seeded**:
  `data_pipeline/ingest_worldbank.py` downloads and parses the World Bank
  Pink Sheet, run for real by the user (Claude's sandboxes can't reach
  `thedocs.worldbank.org` — see DECISIONS.md #10). The first real run
  revealed the file's actual layout is transposed from what was assumed
  (months down rows, commodities across columns — see DECISIONS.md #12);
  the parser was rewritten against the confirmed real layout and re-run
  successfully: **1480 rows** — Crude oil Brent 1960-01 to 2026-08 (800
  months), Coal Australian 1970-01 to 2026-08 (680 months) — now loaded
  into `commodity_price_history` via `python -m app.db.seed`, replacing
  the earlier 3-month starter snapshot.
- FastAPI app with `/health`, `/api/v1/vessels`, `/api/v1/ports`,
  `/api/v1/ports/{id}`, `/api/v1/commodity-prices`, seeded on startup via a
  lifespan handler.
- 15 passing pytest tests (8 API smoke tests + 7 ingestion-parser tests),
  confirmed by the user on their own machine.

- **Module 1 (Predict) built:** `app/engine/forecast.py` — seasonal-naive
  baseline + SARIMAX (small curated AIC grid search over 5 candidate
  orders), chronological train/holdout split, MAE/RMSE/MAPE for both.
  `GET /api/v1/forecast/{commodity}`. On the real ingested data, SARIMAX
  beats the baseline on both commodities — Coal Australian MAE 20.4 vs.
  26.2 (MAPE 15.7% vs. 21.5%), Crude oil Brent MAE 16.5 vs. 19.3 (MAPE
  16.7% vs. 21.3%) — see DECISIONS.md #13 for the full numbers and
  methodology.
- 24 passing pytest tests (10 API smoke tests + 7 ingestion-parser tests +
  7 forecast-engine tests).
- **Module 4 (physical gate) built:** `app/engine/compatibility.py` —
  draft/LOA/beam vs. port limits, plus coal-handling, with the exact
  rejection reason(s) per failing dimension. A port missing a dimension
  is reported "unknown" and treated as NOT compatible (never silently
  assumed to fit). Real finding on the actual seeded data: Capesize is
  the only vessel class that doesn't fit everywhere — it fails at Paradip
  on both draft and LOA, and at Dhamra on LOA alone (Dhamra's draft limit
  is exactly Capesize's draft, an exact-boundary pass). `GET
  /api/v1/compatibility/check` and `/matrix`.
- 35 passing pytest tests (10 API smoke + 7 ingestion-parser + 7
  forecast-engine + 11 compatibility-engine).
- **Module 5 (Simulate) built:** `app/engine/voyage.py` — one-way laden
  voyage cost (great-circle distance via hand-chosen, sourced-geography
  waypoints; fuel cost; time-charter hire) for the 3 origin ports x 3
  destination ports. Bunker price and time-charter rates are real, cited,
  dated snapshots (2026-09-02/03), not live — see DECISIONS.md #15 for
  full sourcing and the real sanity-check against trade-press distance
  figures. `GET /api/v1/origin-ports` + `/api/v1/voyage/calculate`. Real
  result: cost/tonne correctly falls with vessel size (economies of
  scale), and directly connects to Module 4's finding — the cheapest
  vessel per tonne (Capesize) is also the one that can't call at 2 of the
  3 ports.
- 48 passing pytest tests (10 API smoke + 7 ingestion-parser + 7
  forecast-engine + 11 compatibility-engine + 13 voyage-engine).
- **Module 6 (Optimize) built:** `app/engine/optimizer.py` — ranks every
  physically-compatible vessel x origin-port combination for a
  destination by risk-adjusted cost per tonne, composing Module 4
  (compatibility) and Module 5 (voyage cost). "Risk" is deliberately
  scoped to physical clearance margin at berth (a real number already in
  Module 4's own data, not price-trend uncertainty — that's Module 7's
  job) — see DECISIONS.md #16 for the full mechanics. Real result: at
  Vizag, Capesize's razor-thin 0.56% draft margin earns it the full
  ~14.2% risk penalty yet it still ranks #1 of 12 options (the short
  Taboneo route wins on raw cost anyway); at Paradip it's simply absent
  (9 = 3 vessels x 3 origins), excluded by Module 4's hard gate rather
  than merely penalized. `GET /api/v1/optimize/{port_id}`.
- 60 passing pytest tests (10 API smoke + 7 ingestion-parser + 7
  forecast-engine + 11 compatibility-engine + 13 voyage-engine + 12
  optimizer-engine).

**Not yet built:** FRED/RBA ingestion (deprioritized — World Bank alone
covers the two series we need), Indian port traffic history, and
everything from Module 7 (book-now-vs-wait) onward — see TODO.md for the
exact next step.

## Important assumptions

- Vessel class specs are typical-class figures compiled from public
  maritime references, not one specific registered hull — every row in
  `vessels.json` carries `is_assumption: true` and a source.
- Paradip's LOA/beam figures in `ports.json` are *inferred* from its
  confirmed Capesize-class (165,000 DWT) capability, not read off an
  independent berth-dimension table like the draft figure was — see
  DECISIONS.md #11. The port as a whole is `verified: true`; this is a
  narrower caveat about two specific fields.
- Port lat/lon are harbour-level approximations for map display, not
  surveyed berth positions.

## Environment / setup

- Project lives at `C:\ps 6` on the user's Windows machine, developed
  through a connected-folder bridge (Cowork) that mounts it into a Linux
  dev shell.
- **Known limitation:** SQLite on this specific bridge mount throws
  `disk I/O error` unless `PRAGMA journal_mode=MEMORY` and
  `PRAGMA synchronous=OFF` are set — already baked into
  `app/db/connection.py`, with the reasoning documented there and in
  DECISIONS.md. This trades strict crash-durability for portability, which
  is fine for a demo DB rebuilt from seed JSON on every startup.
- Backend setup (from `backend/`):
  ```
  python -m venv .venv
  .venv\Scripts\activate        (Windows)  /  source .venv/bin/activate (mac/Linux)
  pip install -r requirements.txt
  python -m pytest tests/ -v
  python -m uvicorn app.main:app --reload
  ```
  Then visit `http://127.0.0.1:8000/docs` for interactive API docs, or
  `http://127.0.0.1:8000/api/v1/ports`.
