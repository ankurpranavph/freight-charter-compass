# TODO — Freight Charter Compass

Read PROJECT_CONTEXT.md first if you're a new session. This file is the
punch list; it should always reflect reality, not the original plan.

## Completed

- [x] Repo skeleton, `.gitignore`, folder structure (backend/frontend/data/docs)
- [x] `vessel_classes` + `ports` SQLite schema
- [x] Vessel seed data — 4 classes, assumption-labelled, sourced
- [x] Port seed data — Visakhapatnam, Dhamra, and Paradip all confirmed
      (`verified: true`); Paradip closed out via Kalinga International
      Coal Terminal sourcing, see DECISIONS.md #11
- [x] FastAPI skeleton: `/health`, `/api/v1/vessels`, `/api/v1/ports`,
      `/api/v1/ports/{id}`
- [x] 15 passing pytest tests (8 API smoke tests + 7 ingestion-parser tests)
- [x] Fixed a real bug: `TestClient(app)` without `with` never fires
      FastAPI's lifespan/startup, so the DB never got seeded — switched to
      the `with TestClient(app) as client:` fixture pattern
- [x] Fixed a real environment issue: SQLite `disk I/O error` on this
      bridge's mounted folder — fixed via `journal_mode=MEMORY` +
      `synchronous=OFF` in `app/db/connection.py`
- [x] Fixed a real dependency issue: original pins (pydantic 2.9.2 /
      fastapi 0.115.0 / uvicorn 0.30.6) predate Python 3.14, and
      `pydantic-core` had no cp314 wheel — install failed trying to build
      from source on the user's machine (no Rust toolchain). Bumped to
      fastapi 0.141.1 / uvicorn 0.52.4 / pydantic 2.13.5 (ships
      pydantic-core 2.48.0, confirmed cp314-win_amd64 wheel). **Confirmed
      by the user: clean install + all 6 tests passing on their own
      machine**, not just in a sandbox.

## Current task

None open. Hour 2–5 (Data pipeline) is fully done, including the real
data ingestion that was blocking — see "Remaining" below for what's next
(Hour 5–9, the forecast model).

## Remaining (in build order — see PROJECT_CONTEXT.md roadmap)

- [x] **Data pipeline (Hour 2–5), done:**
  - [x] `commodity_price_history` + `port_traffic_history` tables added to `schema.sql`
  - [x] Paradip's real berth data confirmed (Kalinga International Coal
        Terminal — 17.1m draft, Capesize-capable to 165,000 DWT, two
        independent sources) — `verified: false` → `true`
  - [x] `ingest_worldbank.py` written, then corrected against the real
        file's actual (transposed) layout after the first real run
        revealed the documented layout was wrong — see DECISIONS.md #12.
        7 passing tests against a synthetic file matching the confirmed
        real layout.
  - [x] **Full real history ingested and seeded**, confirmed by the user
        running it: 1480 rows — Crude oil Brent 1960–2026 (800 months),
        Coal Australian 1970–2026 (680 months) — now in
        `commodity_price_history`, replacing the 3-month starter snapshot.
  - [ ] FRED (PCOALAUUSDM) and RBA Index of Commodity Prices ingestion —
        deprioritized this block (World Bank alone covers both series we
        need); revisit only if the coking-coal-specific RBA sub-index
        becomes worth the effort later
  - [ ] Indian port traffic history (shipmin.gov.in monthly PDFs /
        data.gov.in) into `port_traffic_history` — not started
- [x] **Forecast model (Hour 5–9), done:**
      `app/engine/forecast.py` — seasonal-naive baseline + SARIMAX (small
      curated AIC grid search, not exhaustive auto-ARIMA), chronological
      train/holdout split, MAE/RMSE/MAPE for both. Fit-on-request with an
      in-memory cache, not a separate training script/pickled artifact —
      see DECISIONS.md #13. New endpoint `GET
      /api/v1/forecast/{commodity}?horizon=1..24`. On your real ingested
      data: SARIMAX beats the seasonal-naive baseline on both commodities
      (coal MAE 20.4 vs 26.2; oil MAE 16.5 vs 19.3 — see DECISIONS.md #13
      for full numbers). 24 total tests now (10 API smoke tests including
      2 new forecast-endpoint tests, 7 ingestion-parser tests, 7
      forecast-engine tests) — `pytest tests/ -v` to confirm.
- [x] **Compatibility engine (Module 4), done:**
      `app/engine/compatibility.py` — draft/LOA/beam vs. port limits plus
      coal-handling, exact rejection reason(s) per failing dimension,
      missing port data reported "unknown" (never assumed to fit). `GET
      /api/v1/compatibility/check` + `/matrix`. Real finding: Capesize
      fails at Paradip (draft + LOA) and Dhamra (LOA only) — the other 3
      vessel classes fit all 3 ports. 11 new tests (6 unit against
      synthetic data, 5 against the real seeded vessel/port data) — 35
      total now.
- [x] **Voyage cost calculator (Module 5), done:**
      `app/engine/voyage.py` — great-circle distance via hand-chosen,
      sourced-geography waypoints (not a licensed routing product, see
      DECISIONS.md #15), fuel cost, time-charter hire. Real research
      done before coding: 3 origin ports (Newcastle AU, Richards Bay ZA,
      Taboneo ID) with cross-checked coordinates, real bunker price
      ($856/t VLSFO Singapore, 2026-09-02) and time-charter day rates by
      vessel class (HandyBulk, 2026-09-03) — both cited ASSUMPTIONs, not
      live. `GET /api/v1/origin-ports` + `/api/v1/voyage/calculate`.
      Known, documented scope limit: one-way laden voyage only (charter
      hire + fuel) — no port charges, ballast leg, or canal tolls yet.
      13 new tests (8 unit incl. hand-checked arithmetic, 5 against real
      seeded data). 48 total now.
- [ ] **Decision engine (Hour 13–17):** `app/engine/optimizer.py` (Module
      6 — risk-adjusted scoring), `app/engine/book_or_wait.py` (Module 7),
      `/api/v1/recommend` and `/api/v1/decision/book-vs-wait` wired
      end-to-end.
- [ ] **Frontend shell (Hour 17–23):** React+Vite scaffold, Overview /
      Forecast / Recommendation pages wired to the live API.
- [ ] **Frontend, rest of MVP (Hour 23–27):** Cost Optimization page, Data
      Sources & Assumptions page generated from `/api/v1/data-sources`.
- [ ] **Checkpoint (Hour 27–29):** if on schedule, add ports 4–6
      (Gangavaram, Krishnapatnam, Haldia) and start Phase 2. If behind,
      skip straight to polish.
- [ ] **Phase 2 / Polish (Hour 29–33)**
- [ ] **Demo readiness (Hour 33–36):** rehearse the demo script twice,
      freeze the build.

## Bugs

None currently open.

**Fixed this block:** `test_commodity_prices_seeded`/`test_commodity_prices_filter`
hardcoded the 3-month starter's exact row counts (6, 3). Once the real
World Bank history was ingested on this machine, `data_pipeline/processed/
commodity_prices_worldbank.csv` persisted locally (it's gitignored, not a
one-time thing that goes away) and `seed.py` correctly started preferring
it over the starter every time — so the DB now always seeds ~1480 rows
here, and those two tests failed on an assumption that stopped being true,
not on a real app bug. Fixed to assert the invariant that holds either
way (>= 6 / >= 3, both commodities present) instead of an exact count,
since a fresh clone (no processed CSV yet) and this machine (processed CSV
present) are both correct states for the same code — confirmed passing on
this machine (24/24) after the fix.

## Priority / blockers

None currently open — all three ports are verified, and the commodity
price history is a full real series rather than a placeholder.

- **Minor, not blocking:** `pytest` prints a `StarletteDeprecationWarning`
  about `httpx` with `starlette.testclient` being deprecated in favour of
  `httpx2`. Cosmetic for now; revisit only if a future `httpx`/`starlette`
  bump actually breaks something.
- **Dev-environment note, not a blocker:** running `pytest`/`uvicorn`
  through this chat's device bridge occasionally hits background-process
  networking quirks unrelated to the app (see DECISIONS.md). Running the
  same commands in a normal terminal on the user's machine is unaffected
  and is the recommended way to do day-to-day development.
