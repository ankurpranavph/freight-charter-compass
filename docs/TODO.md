# TODO — Freight Charter Compass

Read PROJECT_CONTEXT.md first if you're a new session. This file is the
punch list; it should always reflect reality, not the original plan.

## Completed

- [x] Repo skeleton, `.gitignore`, folder structure (backend/frontend/data/docs)
- [x] `vessel_classes` + `ports` SQLite schema
- [x] Vessel seed data — 4 classes, assumption-labelled, sourced
- [x] Port seed data — Visakhapatnam (confirmed), Dhamra (confirmed),
      Paradip (provisional, flagged unverified)
- [x] FastAPI skeleton: `/health`, `/api/v1/vessels`, `/api/v1/ports`,
      `/api/v1/ports/{id}`
- [x] 6 passing pytest smoke tests
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

None in progress — Hour 0–2 (Setup) block is complete. Next session/step
starts Hour 2–5 (Data pipeline) below.

## Remaining (in build order — see PROJECT_CONTEXT.md roadmap)

- [ ] **Data pipeline (Hour 2–5):** ingestion scripts for World Bank Pink
      Sheet, FRED (PCOALAUUSDM), RBA Index of Commodity Prices; extract the
      real berth-wise draft/LOA/beam table for Paradip from the official
      PDF/page and flip `verified: false` → `true` once confirmed; add
      `commodity_price_history` and `port_traffic_history` tables to
      `schema.sql`.
- [ ] **Forecast model (Hour 5–9):** baseline (seasonal-naive) + SARIMAX,
      time-series-aware split, MAE/RMSE/MAPE reported, artifacts saved to
      `backend/ml/artifacts/`.
- [ ] **Backend core (Hour 9–13):** `app/engine/compatibility.py` (Module
      4 — draft/LOA/beam check with explicit rejection reasons),
      `app/engine/voyage.py` (Module 5 — distance via waypoints, fuel,
      cost), corresponding `/api/v1/compatibility/check` and
      `/api/v1/voyage/calculate` endpoints.
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

## Priority / blockers

- Paradip's port figures are a placeholder — needs the official
  berth-wise draft table extracted before it can be trusted in a demo.
  Not currently blocking (the app runs fine with it flagged unverified),
  but should not ship to the final demo unresolved.
- **Dev-environment note, not a blocker:** running `pytest`/`uvicorn`
  through this chat's device bridge occasionally hits background-process
  networking quirks unrelated to the app (see DECISIONS.md). Running the
  same commands in a normal terminal on the user's machine is unaffected
  and is the recommended way to do day-to-day development.
