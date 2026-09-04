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

Frontend shell (Hour 17-23): scaffold, routing, API client, and all
three pages (Overview, Forecast, Recommendation) are built and verified
in a sandbox headless browser. The Forecast page and the Recommendation
page are both still awaiting the user's own on-machine confirmation
before their commits land (same test-confirm-commit discipline as every
other module) -- see DECISIONS.md #20. INR currency display was
discussed and deliberately deferred to later, after the MVP pages are
confirmed working -- see DECISIONS.md #20.

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
- [x] **Cost optimizer (Module 6), done:**
      `app/engine/optimizer.py` — ranks every physically-compatible
      vessel x origin-port combination for a destination by risk-adjusted
      cost per tonne, composing Module 4 (compatibility) and Module 5
      (voyage cost) rather than recomputing them. "Risk" is deliberately
      scoped to physical clearance margin at berth (a real number already
      in Module 4's own data), not price-trend uncertainty — that's
      reserved for Module 7. See DECISIONS.md #16 for the full mechanics
      and the real verified result: at Vizag, Capesize's razor-thin 0.56%
      draft margin earns it the full ~14.2% risk penalty yet it STILL
      ranks #1 of 12 options (the short Taboneo route wins anyway); at
      Paradip it's simply absent (9 = 3 vessels x 3 origins), excluded by
      Module 4's hard gate rather than merely penalized. New endpoint
      `GET /api/v1/optimize/{port_id}?cargo_tonnes=`. 12 new tests (9
      unit, 3 against real seeded data). 60 total now.
- [x] **Book-now-vs-wait decision (Module 7), done — last "Decision
      engine" module:** `app/engine/book_or_wait.py` — reuses Module 1's
      own SARIMAX forecast as-is (no second model) to compare the latest
      real price against the forecast at a near-term horizon (default 3
      months). Classifies BOOK_NOW / WAIT / HOLD by expected % move, plus
      an honest `confidence: "low"` flag whenever the forecast's own 95%
      CI still contains today's real price (the model can't rule out no
      real change). Deliberately kept separate from Module 6's risk score
      — see DECISIONS.md #17. New endpoint `GET
      /api/v1/decision/book-vs-wait/{commodity}?horizon=1..24`. 12 new
      tests (9 unit incl. synthetic uptrend/downtrend direction checks,
      3 against real seeded data — asserting shape/contract, not a pinned
      verdict, since the actual decision legitimately depends on the
      latest real price whenever the test runs). 72 total now.
- [x] **Frontend shell (Hour 17-23), done (pending user confirmation on the last two pages):** React+Vite scaffold
      (plain JavaScript, not TypeScript — see DECISIONS.md #18),
      `react-router-dom` 3-page shell with a shared Layout/nav
      (`frontend/src/components/Layout.jsx`) and a hand-written fetch
      client (`frontend/src/api/client.js`).
      - [x] Overview page: fleet, ports, origin ports, latest commodity
            prices, and a data-honesty panel, all fetched live from the
            API. Verified end-to-end in a sandbox (headless browser
            against a running backend + Vite dev server) before pushing:
            real data renders, routing works, zero console errors, and
            the "backend not running" error state is a clear message,
            not a blank page.
      - [x] Backend: added a CORS policy scoped to the Vite dev server's
            two localhost origins (`localhost:5173` / `127.0.0.1:5173`,
            GET only) — see DECISIONS.md #18.
      - [x] Forecast page, done: hand-rolled SVG line chart
            (`frontend/src/components/ForecastChart.jsx`) — actual price
            vs. SARIMAX forecast with a shaded 95% CI band, crosshair +
            tooltip, commodity and horizon pickers, a book-now-vs-wait
            decision card (Module 7), and a model-accuracy table (SARIMAX
            vs. seasonal-naive baseline). Built by following the dataviz
            skill's method (form -> color -> marks -> interaction ->
            legend), not by eye — caught and fixed two real layout bugs
            (y-axis ticks escaping the plot bounds, x-axis label
            collision near the forecast boundary) via a headless-browser
            render before this ever reached the user's machine. See
            DECISIONS.md #19.
      - [x] Recommendation page, done: a port picker (3 seeded ports)
            and an optional cargo-tonnes input drive
            `GET /api/v1/optimize/{port_id}`, rendered as ranked option
            cards (vessel x loading-port) showing risk-adjusted cost per
            tonne, the base cost, and a plain-language risk-premium
            readout. Each card's "Why this vessel clears the port"
            expander shows the exact Module 4 draft/LOA/beam margins
            behind the risk score, not just the pass/fail. Verified with
            a headless browser: port switching, cargo-tonnes filtering
            (confirmed it correctly re-ranks -- fixed charter-hire cost
            spread over fewer tonnes changes the winner at low cargo
            sizes), and the compatibility-detail expander, all with zero
            console errors.
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
