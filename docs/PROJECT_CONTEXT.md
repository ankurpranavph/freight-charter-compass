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
- ML: statsmodels (SARIMAX), pandas, numpy, scikit-learn for metrics.
  (not yet built)

## Database schema (current)

Two tables exist so far — `backend/app/db/schema.sql`:

- `vessel_classes` — vessel_type (PK), dwt_tonnes, draft_m, loa_m, beam_m,
  speed_knots, fuel_cons_tpd, opex_usd_day, is_assumption, source, source_url
- `ports` — port_id (PK), name, state, lat, lon, lat_lon_provenance,
  max_draft_m, max_loa_m, max_beam_m, coal_handling, berth_reference,
  annual_capacity_mtpa, verified, source, source_url, source_date

More tables (commodity_price_history, freight_index_history,
port_traffic_history, routes_cache, voyage_estimates, scenario_log,
assumptions_registry) are added when the module that owns them is built —
not created speculatively upfront.

## API structure (current)

- `GET /health`
- `GET /api/v1/vessels` — all 4 vessel classes
- `GET /api/v1/ports` — all seeded ports
- `GET /api/v1/ports/{port_id}` — one port, 404 if unknown

Planned next (Module 4 onward): `/api/v1/compatibility/check`,
`/api/v1/forecast/freight`, `/api/v1/voyage/calculate`, `/api/v1/recommend`,
`/api/v1/decision/book-vs-wait`, `/api/v1/scenario/simulate`,
`/api/v1/data-sources`.

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

**Not yet built:** FRED/RBA ingestion (deprioritized — World Bank alone
covers the two series we need), Indian port traffic history, and
everything from Module 4 (compatibility engine) onward — see TODO.md for
the exact next step.

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
