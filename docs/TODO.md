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

The locked 5-page MVP (DECISIONS.md #7) is fully built, confirmed by the
user on their own machine, and committed (10-data-sources-page).

Ports 4-6 (Gangavaram, Krishnapatnam, Haldia) are also confirmed and
committed (11-ports-4-6, the Hour 27-29 checkpoint) -- 6 East Coast ports
total, 87 passing tests. See DECISIONS.md #22 for the full sourcing and
the genuine Haldia zero-compatibility finding (a real, verified,
coal-handling port whose 9.1m tidal draft excludes every modeled vessel
class -- confirmed correct, not a bug, on the user's own machine).

The user then asked whether the app actually satisfies the SIH26006
problem statement -- answer: mostly yes on Predict->Simulate->Optimize->
Recommend, with two named gaps (coking-vs-thermal-coal proxy, and no
cross-port recommendation). User chose to fix both, one at a time,
starting with the coking coal proxy.

**Coking coal proxy fix, done, confirmed, committed (`12-coking-coal-proxy`):**
`coal_australian` was thermal coal (confirmed by fetching the real World
Bank Pink Sheet's own columns -- no coking coal line at all), but SAIL
procures coking (metallurgical) coal. Added `coking_coal`, sourced from
RBA's Index of Commodity Prices (real, Australian-origin, chosen over
FRED's too-short 18-month series) via a new
`data_pipeline/ingest_rba_coking_coal.py` -- real code, same one-time
"user runs it, Claude's environments can't reach rba.gov.au" pattern as
`ingest_worldbank.py`, except this parser's layout is UNVERIFIED against
the real file (unlike the World Bank one) -- see DECISIONS.md #23. One
real cited coking-coal snapshot ($214.90/t, 7 Aug 2026) seeded now so the
app degrades honestly (insufficient_data, correct script name) rather
than showing nothing. 98 passing tests at the time.

**Cross-port recommendation + interactive Recommendation page, done,
confirmed, committed (`13-cross-port-recommendation`):** the second
named gap -- closed after the user also asked, separately, for the app
to be more interactive. New `rank_ports_for_vessel` in
`app/engine/optimizer.py` (mirrors `rank_options`: fixed vessel +
loading port, ranks the 6 destinations) and `GET
/api/v1/optimize/by-vessel`. The Recommendation page gained a mode
toggle -- "by vessel & loading port" (new default): pick a vessel class,
loading port, optional custom cargo tonnage, and a forecast horizon, and
get back live ranked destinations (incompatible ones shown too, with
reasons, never dropped) plus book-now-vs-wait timing cards for both
commodities. "By destination port" (the original page) is still there,
unchanged. 108 passing tests at the time.

**INR secondary currency display, done, confirmed, committed
(`14-inr-currency-display`):** the deliberately-deferred item from
DECISIONS.md #20, picked by the user as the next thing to build once
both named gaps closed. New `app/engine/currency.py` (one cited,
cross-checked USD->INR rate, 94.43 as of 2026-09-04) and `GET
/api/v1/exchange-rate`. USD stays the source-of-truth currency
everywhere; INR shows only as a secondary CALCULATED figure alongside
it -- Overview's commodity stat cards, Forecast's decision card, and
both Recommendation modes' cost figures. Also added to the Data Sources
catalog as its own category. 113 passing tests at the time. See
DECISIONS.md #25.

**Indian port traffic history, confirmed and committed
(`15-port-traffic-history`).** shipmin.gov.in/data.gov.in/IPA are
network-blocked the same way as thedocs.worldbank.org/rba.gov.au
(DECISIONS.md #10), and extensive research found no freely-accessible
monthly coal-traffic series for any of the 6 ports through any source
-- surfaced to the user directly (three options) rather than
fabricated or silently skipped; the user chose to seed the real
one-off facts targeted research could find, clearly labelled. New
`note` column on `port_traffic_history`, 6 real individually-sourced
records (a 24-hour discharge record, a single shipment, or a berth
record per port, spanning 2016-2026, explicitly not comparable to each
other). New `GET /api/v1/port-traffic?port_id=`, an 8th Data Sources
category, and a new Overview page section. 120 passing tests (up from
113). See DECISIONS.md #26.

**Real deployment shipped (`16-deployment-config`, `17-real-price-
history-checked-in`, `18-honest-insufficient-data-message`).** The app
is live for outside testers: GitHub -> Render (backend) -> Vercel
(frontend), auto-deploying on push. Along the way, fixed a real gap
where the real World Bank price history CSV was gitignored and never
reached a fresh deploy (now checked in with a narrow `.gitignore`
exception, DECISIONS.md #28), and reworded the coking-coal
`insufficient_data` message so it no longer leaks an internal script
path to real testers while staying just as honest about the real month
count (DECISIONS.md #29).

**Interactive route map and the text-reduction / "more professional"
pass, both done in sandbox, awaiting on-machine confirmation -- the
current task.** Both Recommendation modes show a small interactive map
(loading port, destination ports, and the route line between whichever
pair is focused) drawn from the exact same real `ROUTE_WAYPOINTS` the
voyage-cost calculation already uses, not an invented straight line --
see DECISIONS.md #30. On top of that, every page intro and every
sourcing/methodology note across all 4 pages is now collapsed by
default behind a small reusable disclosure (`InfoNote`), matching the
pattern the option cards already used for "Why this port/vessel
works." Nothing cut -- everything is still there, one click away. The
actual answers (book-now-vs-wait reasoning, insufficient_data notes,
every Data Sources entry) were deliberately left always-visible -- see
DECISIONS.md #31. 121 passing tests (up from 120; the text-reduction
pass touched frontend copy/layout only, no new tests). Verified in a
sandbox headless browser (build clean, all 4 pages screenshotted
collapsed and fully expanded, zero real console errors); neither is
yet confirmed on the user's own machine or committed.

Still open after that: the real RBA coking-coal ingestion, which no one
has run for real yet -- then Phase 2 polish / demo readiness.

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
  - [x] Indian port traffic history: no freely-accessible monthly
        series exists for any of the 6 ports (confirmed via both a
        network block and extensive research) -- 6 real, individually-
        sourced, individually-captioned one-off records seeded instead
        (a 24-hour discharge record / single shipment / berth record
        per port, 2016-2026, explicitly not a series). See
        DECISIONS.md #26.
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
- [x] **Frontend, rest of MVP (Hour 23–27), done:** Cost Optimization is
      fulfilled by the Recommendation page (DECISIONS.md #20); Data
      Sources & Assumptions page shipped in 10-data-sources-page
      (DECISIONS.md #21).
- [x] **Checkpoint (Hour 27–29), done:** on schedule; ports 4-6
      (Gangavaram, Krishnapatnam, Haldia) added as real, sourced rows --
      see DECISIONS.md #22. Now 6 East Coast ports total.
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
