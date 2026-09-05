# DECISIONS — Freight Charter Compass

Architectural decisions and why, in the order they were made. Read
PROJECT_CONTEXT.md for current state; this file explains *why* it looks
the way it does.

## 1. FastAPI monolith, not microservices

**Decision:** one FastAPI process importing plain Python modules for each
pipeline stage (forecast, compatibility, voyage, optimizer, ...).
**Alternatives considered:** separate services per module with internal
HTTP calls.
**Why rejected:** nothing in this problem needs independent horizontal
scaling for a prototype; a service boundary is one more thing to fail live
during a demo, and a judge asking "how do these talk to each other" gets a
function call, not a network hop.

## 2. SQLite, not PostgreSQL

**Decision:** a single SQLite file, gitignored, rebuilt from seed JSON on
every app startup.
**Why:** zero ops, trivial to reset before a demo, and the dataset size for
this prototype (a handful of vessels/ports, a few years of monthly
commodity data) will never approach where SQLite's single-writer model
matters. Swapping to Postgres later is a config change, not a rewrite,
because access goes through a small connection module either way.

## 3. Plain `sqlite3` (stdlib), not a SQLAlchemy ORM

**Decision:** `app/db/connection.py` + hand-written SQL, no ORM.
**Alternatives considered:** SQLAlchemy models (the original architecture
proposal sketched this).
**Why:** at this stage the schema is two tables. An ORM adds a dependency
and a mapping layer for no present benefit, and plain SQL keeps every query
visible/debuggable during a live demo. **Revisit trigger:** if Module 6's
optimizer needs joins complex enough that hand-written SQL becomes the
harder path, switch then — not preemptively.

## 4. SQLite `journal_mode=MEMORY` + `synchronous=OFF`

**Decision:** both pragmas set on every connection in
`app/db/connection.py`.
**Why:** discovered during Hour 0–2 testing — SQLite's default
rollback-journal file creation throws `disk I/O error` on the specific
mounted-folder bridge used to develop this project through chat (confirmed
with a minimal repro: even `rm` on the resulting file needed explicit
delete permission, pointing at non-standard file-locking behaviour on that
mount). `journal_mode=MEMORY` avoids creating the on-disk journal file
entirely. **Trade-off, stated plainly:** this sacrifices crash-durability —
a crash mid-write can corrupt the DB. Acceptable here because the DB is
fully rebuilt from `vessels.json`/`ports.json` on every startup and holds
no data that isn't reproducible. **Do not carry this pattern into a system
where losing the last transaction on a crash matters.**

## 5. 3 ports first, not all 6, for the MVP checkpoint

**Decision:** seed and build against Visakhapatnam, Paradip, Dhamra first;
Gangavaram, Krishnapatnam, Haldia are added after an Hour-27 checkpoint,
only if the team is ahead of schedule.
**Why:** the team is 1–2 people over ~36 hours (confirmed by the user
during planning). These three ports had the richest confirmed source
material during research (Visakhapatnam and Dhamra now have confirmed
draft figures in `ports.json`). The compatibility engine is data-driven —
adding a 4th–6th port later is a JSON row, not new code — so staging this
way costs nothing structurally and removes real risk from the critical
path.

## 6. SARIMAX as the sole primary forecasting model

**Decision:** statsmodels SARIMAX, evaluated against a seasonal-naive
baseline, chronological train/test split, MAE/RMSE/MAPE reported.
XGBoost/LSTM are explicitly not planned (XGBoost is an optional Phase-3
side-by-side comparison at most).
**Alternatives considered:** XGBoost/Random Forest, LSTM/Transformer.
**Why rejected:** no free, bulk-licensed, route-specific freight-rate series
exists (Baltic Exchange's route-level data is subscription-only — confirmed
by checking their public pages during research). What's available
legitimately is World Bank/FRED/RBA commodity-price history — realistically
on the order of 100–150 usable monthly data points once resampled. A
boosted-tree model is easy to overfit on data that size and harder to
justify live to a judge than a regression coefficient; an LSTM needs far
more data than is available and is a black box exactly where explainability
is a named judging criterion. SARIMAX's own coefficients on coal/oil price
as exogenous regressors *are* the explanation.
**Confirmed by the user** during the planning conversation before any code
was written.

## 7. 5-page MVP dashboard, not 7

**Decision:** Overview, Freight Forecast, Vessel & Port Recommendation
(merged), Cost Optimization, Data Sources & Assumptions. Scenario
Simulator and a dedicated Port Comparison page move to Phase 2.
**Why:** frontend breadth was identified as the single largest time risk
for a 1–2 person team in 36 hours during the architecture self-review. A
working 5-page/3-port demo beats a broken 7-page/6-port one.
**Confirmed by the user** during the planning conversation before any code
was written.

## 8. What we explicitly decided not to build

Microservices, Docker/Kubernetes, message queues, user auth, a mobile app,
blockchain, live web-scraping during the demo, and a general-purpose
port-to-port routing/geocoding system (routes are a fixed small set:
Australia/Indonesia/South Africa × the named East Coast ports). Reasoning
for each is in the architecture proposal from the planning conversation;
repeated here only if a future session is tempted to add one of these back
in without re-deriving why it was cut.

## 9. Dependency pins bumped for Python 3.14 (confirmed by the user)

**Decision:** `fastapi==0.141.1`, `uvicorn==0.52.4`, `pydantic==2.13.5`
(from the original `0.115.0` / `0.30.6` / `2.9.2`).
**Why:** the user's machine runs Python 3.14. The original `pydantic`
pin resolved to `pydantic-core 2.23.4`, which has no `cp314` wheel on
PyPI — `pip install` tried to build it from source and failed with no
Rust toolchain available. Verified on PyPI before changing anything:
`pydantic-core` first shipped a `cp314-win_amd64` wheel at version
`2.48.0`, which ships with `pydantic>=2.12`. Bumped `fastapi`/`uvicorn`
alongside it to current releases rather than leaving them stale.
**Verified before handing back to the user:** re-ran all 6 tests against
the new pins in a clean sandbox first. **Verified by the user:** clean
`pip install` + all 6 tests passing on their own machine, in their own
VS Code terminal, after deleting and recreating `.venv`.

## 10. Data ingestion scripts written but not execution-tested by Claude

**Decision:** `ingest_worldbank.py` is real, defensively-written code
(dynamic header-row detection instead of hardcoded row numbers, clear
error messages, unit-tested against a synthetic file matching the
documented Pink Sheet layout) — but it has not been run against the real
`thedocs.worldbank.org` file by Claude.
**Why:** confirmed by direct test — raw `curl` to `thedocs.worldbank.org`,
`fred.stlouisfed.org`, `rba.gov.au`, and several Indian port-authority
domains all fail to connect from both of Claude's execution environments
(the cloud sandbox and this project's device-bridge shell), consistent
with an organisation-level network egress policy that allows package
registries (PyPI, npm) but not arbitrary external sites. Claude's
`WebFetch` tool (a separate, Anthropic-hosted fetch path) can reach these
sites for HTML/PDF text — which is how the real Paradip port data and the
real 3-month commodity-price starter snapshot were obtained — but it
cannot hand back raw binary (XLSX) content for a script to parse.
**Consequence for how this project gets built:** any ingestion step that
needs the actual downloadable data file (not just text Claude can read
and transcribe) has to be run once by the user, in their own terminal,
which has normal unrestricted internet. This is a one-time step per data
refresh, not a demo-time dependency — the architecture already called for
ingest-once-cache-locally rather than live-fetching at request time, so
this constraint doesn't change the design, just who runs the ingestion
step during development.
**Alternative considered:** have Claude fabricate/estimate the full
historical series instead of leaving it to a real download. Rejected
outright — this project's entire credibility argument to SIH judges rests
on never presenting simulated numbers as real; a full synthetic 60-year
coal-price history dressed up as "World Bank data" would be exactly the
failure mode the Data Sources & Assumptions page exists to prevent.

## 11. Paradip's port data closed out with two independent real sources

**Decision:** Paradip flipped from `verified: false` (Hour 0-2 placeholder)
to `verified: true`, using the Kalinga International Coal Terminal (KICT)
— confirmed via a CareRatings credit-rating report (port-level draft
17.1m) and the terminal operator's own capability page (12 MMTPA, 165,000
DWT Capesize-capable, commenced January 2022) — rather than the official
Paradip Port Trust berth-table PDF, which returned a 404 when re-checked.
**Why this is still labelled honestly:** LOA/beam (290m/45m) are *inferred*
from the stated 165,000 DWT Capesize-class capability, not read off an
independent berth dimension table — `ports.json`'s `berth_reference` field
says so explicitly, so a future session (or a judge reading the Data
Sources page) doesn't mistake an inference for a direct citation.

## 12. World Bank Pink Sheet's real layout is transposed vs. documented format — parser rewritten, full history now ingested

**Decision:** rewrote `ingest_worldbank.py`'s parsing logic entirely, based
on the actual downloaded file rather than documentation.
**What happened:** the first execution attempt (run by the user, since
Claude cannot reach `thedocs.worldbank.org` — see Decision #10) downloaded
successfully but matched zero commodity rows. A diagnostic dump of the raw
grid (requested from the user, since Claude cannot open the file either)
showed the real "Monthly Prices" sheet has months running **down** column A
(`"1960M01"`, `"1960M02"`, ...) with commodities **across** the columns as
headers (col 1 "Crude oil, average", col 2 "Crude oil, Brent", col 5 "Coal,
Australian", etc.), one units row below the header, then data. This is the
opposite orientation from what the original script assumed (commodities
down column A, months across) — that assumption came from older
documentation of the Pink Sheet format; the real file's layout has
apparently changed since.
**Fix:** `find_header_row`/`parse` replaced with three dynamic detection
steps — `find_date_column` (scans all columns for the one with the most
`"\d{4}M\d{2}"` matches), `find_first_data_row` (first row where that
column matches), `find_header_row` (nearest row above the first data row
with mostly commodity-name text, skipping a units row if present). Also
handles the real file's missing-value marker, the literal string `'…'`
(ellipsis) rather than a blank cell. Tests rewritten against a synthetic
file matching the *confirmed real* layout (7 tests, all passing).
**Result, confirmed by the user running it for real:** 1480 rows —
Crude oil Brent 1960-01 to 2026-08 (800 monthly points), Coal Australian
1970-01 to 2026-08 (680 monthly points) — loaded into
`commodity_price_history` via `python -m app.db.seed`, replacing the
3-month starter snapshot. This is now a genuinely strong real dataset for
the Hour 5–9 SARIMAX forecast — 55-plus years for oil, 56 years for coal,
both continuous through the present month.
**Lesson for future data-ingestion steps in this project:** don't assume a
documented file layout is current: get a raw grid dump of the actual file
(via the user, since Claude can't open XLSX binaries itself) before writing
the parser, not after it fails.

## 13. Forecast model: fit-on-request with in-memory caching, no training script or pickled artifact

**Decision:** `app/engine/forecast.py` fits SARIMAX when `GET
/api/v1/forecast/{commodity}` is first called for a given
(commodity, horizon), then caches the result in a module-level dict for
the life of the running process. There is no `backend/ml/` training
script and no pickled model file.
**Alternatives considered:** a separate offline training script that
writes pickled `statsmodels` result objects to disk, loaded at API
startup (this was the original architecture-proposal sketch).
**Why rejected:** pickled `statsmodels`/`scipy` objects are version-
fragile — a `pip install -U` on either library can make an old pickle
unloadable or silently wrong, which is a bad failure mode to discover
during a demo. Fitting SARIMAX on real data takes 4-6 seconds per
commodity (measured against the full 1480-row real series, see below) —
too slow for a page needing to feel instant, but entirely fine to pay
once per commodity per server run, which the in-memory cache guarantees.
This also keeps the "ingest once, compute at request time, no live
external calls during a demo" architecture (PROJECT_CONTEXT.md) intact
without adding artifact-management complexity a 1-2 person team doesn't
need. **Revisit trigger:** if the forecast page needs to support many
different horizons interactively such that re-fitting on every distinct
horizon becomes a real wait, switch to fitting once on the full series
and slicing `get_forecast(steps=max_horizon)` down to whatever horizon
is requested, rather than one fit per horizon value.

**Order selection:** a small curated grid of 5 (order, seasonal_order)
pairs, picked by AIC on the training split — not exhaustive auto-ARIMA
(`pmdarima` isn't a dependency). The SAME selected order is refit on the
full series for the deployed forecast; the evaluation-time model and the
deployed model are never allowed to silently differ.

**Real result, on the actual ingested data (not a synthetic sanity
check):** both commodities independently selected order `(1,1,1)` /
seasonal `(0,1,1,12)`. SARIMAX beat the seasonal-naive baseline on the
last-12-months holdout for both:
- Coal Australian (680 months, 1970-2026): MAE 20.44 vs. baseline 26.23;
  MAPE 15.72% vs. baseline 21.49%.
- Crude oil Brent (800 months, 1960-2026): MAE 16.50 vs. baseline 19.32;
  MAPE 16.67% vs. baseline 21.29%.

This is a genuine, holdout-measured improvement over the baseline a judge
would expect us to compare against — not a claim, a number anyone can
reproduce by calling the endpoint.

**Metrics library:** hand-rolled MAE/RMSE/MAPE with `numpy`, not
`scikit-learn` (the original architecture proposal listed scikit-learn
for this). Three summary statistics don't justify an extra dependency
and its own Python 3.14 wheel-compatibility risk — `statsmodels` and
`scipy` already needed checking (see requirements.txt; both confirmed
`cp314-win_amd64` wheels on PyPI before pinning `statsmodels==0.15.0`).

## 14. Compatibility engine: a hard gate with an honest "unknown" state, not a score

**Decision:** `app/engine/compatibility.py` returns a boolean `compatible`
plus exact per-dimension reasons — never a fuzzy compatibility score. A
port missing a dimension figure is reported as `"unknown"` for that
dimension and the whole result is `compatible: false`, not `true` by
default.
**Alternatives considered:** a soft "compatibility score" (e.g. 0-100)
that Module 6's optimizer could weigh directly, and treating a missing
port dimension as a pass (benefit of the doubt).
**Why rejected:** physical fit isn't a matter of degree — a vessel with
a draft deeper than the berth either can call there or it can't. Turning
that into a fuzzy score would hide the real reason from both the
optimizer and a judge asking "why was this combination excluded". Treating
missing data as a pass would mean a Phase-2 port added with incomplete
figures could get recommended for a vessel it might not actually fit —
exactly the kind of overclaim this project's data-honesty rules exist to
prevent. Cost/risk *is* a matter of degree and gets scored in Module 6 —
but only among the vessel/port pairs that already cleared this gate.
**Verified against real data, not just synthetic tests:** Capesize (draft
18.0m, LOA 292m) is the only one of the 4 vessel classes that doesn't fit
all 3 currently seeded ports — it fails at Paradip on both draft (17.1m
limit) and LOA (290m limit), and at Dhamra on LOA alone (Dhamra's draft
limit is exactly 18.0m, an exact-boundary pass, not a failure). Handysize,
Supramax, and Panamax fit all 3 ports.

## 15. Voyage cost calculator: fixed waypoint routing + cited real market snapshots, not live feeds

**Decision:** `app/engine/voyage.py` computes a one-way laden voyage cost
(distance -> days -> fuel cost + time-charter hire) for 3 fixed overseas
origin ports x the 3 seeded East Coast India ports. Distance is
great-circle (haversine) through a small, hand-chosen set of open-ocean
waypoints per origin region — not a licensed routing product. Bunker
price and time-charter day rates are real, cited, single point-in-time
figures, not live feeds.

**Origin ports, real and sourced:** Newcastle, Australia (world's largest
coal export port); Richards Bay, South Africa (Richards Bay Coal
Terminal, Africa's largest coal export facility); Taboneo anchorage,
Indonesia (South Kalimantan coal-loading anchorage). Coordinates
cross-checked across independent sources — the Indonesian anchorage's
coordinates disagreed by about 1 degree of latitude between two fields on
the same source page; resolved by checking a second independent source,
which agreed with one of the two figures.

**Waypoints, reasoned not sourced:** there's no free routing API for this
(commercial weather-routing services are paid products), so waypoints
were chosen by reasoning about real shipping-lane geography — e.g.
Newcastle routes south around Australia via Bass Strait and well clear of
Cape Leeuwin (the deep-water route Capesize vessels actually take,
avoiding the shallower/more congested Torres Strait), Richards Bay
doesn't need Cape of Good Hope routing at all since it's already on
South Africa's Indian Ocean coast, and the Indonesian anchorage exits via
the Sunda Strait rather than Malacca. **Sanity-checked against real
trade-press distance figures before being trusted:** Newcastle-India
~6,200-6,400nm, Richards Bay-India ~4,300-4,500nm, Indonesia-India
~2,900-3,100nm — all within the ranges commonly quoted for these actual
routes, not just internally self-consistent numbers.

**Market reference figures, with sources:** VLSFO bunker fuel, Singapore,
$856.00/tonne (Ship & Bunker, 2026-09-02). Time-charter day rates by
vessel class (HandyBulk, 1-year TC, 2026-09-03, matched to our DWT
classes almost exactly): Handysize $14,500/day, Supramax $18,000/day,
Panamax $20,000/day, Capesize $38,500/day. Both are single cited
snapshots — the response's `assumptions` block always states this
explicitly, and a judge asking "is this live" gets an honest "no, and
here's the exact source and date" rather than an implied real-time claim.

**Scope, deliberately narrow:** one-way laden voyage cost (charter hire +
fuel) only — no port charges, no ballast/repositioning leg, no canal
tolls. This mirrors how the freight/chartering decision is actually
framed ("what does it cost to move this cargo on this vessel") and keeps
the module sized for the time budget. Documented as a known simplification
in TODO.md, not silently dropped.

**Verified real result:** cost per tonne correctly decreases with vessel
size on the actual seeded data (Newcastle -> Vizag: Handysize $17.3/t,
Panamax $10.7/t, Capesize $7.3/t) — the expected economies-of-scale
pattern, and it connects directly to Module 4's finding: Capesize is the
cheapest per tonne but is exactly the vessel class that can't call at
Paradip or Dhamra (DECISIONS.md #14). Module 6's optimizer will need to
weigh this real tension, not a synthetic one.

## 16. Cost optimizer: risk signal scoped to physical clearance margin, not price-trend uncertainty

**Decision:** Module 6 ranks every physically-compatible vessel x
origin-port combination for a destination by a *risk-adjusted* cost per
tonne, where "risk" means one specific, calculated thing: how tight the
vessel's physical clearance is at that port (draft/LOA/beam margin as a
fraction of the vessel's own dimension), not a general-purpose "risk
score."

**Why this scope and not a broader one:** the temptation with an
"optimizer" module is to fold in everything that could matter — price
trend, market volatility, congestion, weather. We deliberately didn't.
The physical-margin signal is defensible because it's a real number
already sitting in Module 4's own check data (no invented weights, no
synthetic distribution), and it answers a genuine operational question:
a vessel that clears a port's draft limit by 10cm carries real tide-
window and grounding risk that one clearing by 8 metres doesn't, even
though the hard pass/fail gate treats both as simply "compatible."
Price-trend/forecast uncertainty (Module 1's job) is intentionally left
out of this score and reserved for Module 7 (book now vs. wait) — that
module answers "when," this one answers "which vessel and route,"
and keeping them separate keeps each one's reasoning legible on its own
rather than producing one opaque blended score.

**Mechanics:** `SAFE_MARGIN_RATIO = 0.10` — at or above 10% spare
clearance on the tightest of the three dimensions, no penalty is
applied. Below that, cost is scaled upward linearly, up to
`MAX_RISK_PENALTY = 0.15` (a 15% cost markup) at an exact-boundary fit
(zero margin). An "unknown" dimension (a port missing a limit, per
DECISIONS.md #14) is treated as maximum caution (full penalty) rather
than assumed safe. An option that fails Module 4's hard gate outright is
excluded from the ranking entirely, never scored — see the matrix
endpoint for the full pass/fail picture. If a fixed `cargo_tonnes` is
requested and exceeds a vessel's DWT, that vessel is excluded for that
port too (this prices a single voyage, not a multi-voyage plan — see
TODO.md).

**Verified real result, not cherry-picked:** at VIZAG, Capesize's real
margin is razor-thin — its 18.0m draft against Vizag's 18.1m limit is
just 0.56% spare clearance, so it earns the full ~14.2% risk penalty
(risk_multiplier ≈ 1.142). Even so, it still ranks #1 overall out of all
12 compatible options (4 vessel classes x 3 origins), because the short
Taboneo (Indonesia) route's raw cost advantage outweighs the penalty —
a genuine tension the model surfaces rather than hides. At PARADIP,
Capesize doesn't get a risk penalty at all — it's absent from the
ranking entirely (9 = 3 vessels x 3 origins), because it fails Module
4's physical gate there (DECISIONS.md #14), which is a stronger and
more honest statement than a merely-penalized option would be.

## 17. Book-now-vs-wait: reuses Module 1's forecast as-is, no second model

**Decision:** Module 7 (the last piece of Predict -> Simulate -> Optimize
-> Recommend) answers "should procurement lock in this commodity's price
now, or wait?" by directly reusing Module 1's own SARIMAX forecast — it
does not train, fit, or invent a second model. It compares the latest
real price to the forecast's point estimate at a near-term horizon
(default 3 months) and classifies the expected move: >= +3% -> BOOK_NOW,
<= -3% -> WAIT, otherwise HOLD (no strong signal either way).

**Why reuse instead of building a second model:** every number this
module needs — the forecast, its 95% CI, and its own evaluated accuracy
against the seasonal-naive baseline — already exists from Module 1. A
second, separate "decision model" would either quietly duplicate that
work or diverge from it, and either way would be harder to defend to a
judge asking "is this the same forecast as the one on the Predict page."
Reuse keeps the two pages provably consistent.

**Why 3 months and not the full horizon:** a near-term window is the
actionable one for a procurement decision — long enough to matter, short
enough that the forecast hasn't degraded into the wide, low-value
uncertainty a 12+ month SARIMAX projection carries. `horizon` is exposed
as a query parameter (1-24, same bounds as the forecast endpoint) for
anyone who wants a longer view.

**Why this is scoped away from Module 6:** Module 6's "risk" is a
property of a specific vessel/port pair (physical berth clearance).
This module's signal is a property of the market alone, independent of
which vessel eventually carries the cargo. Blending the two into one
score would hide which factor is actually driving a recommendation — see
DECISIONS.md #16 for the same reasoning applied in the other direction.

**Honesty on confidence, not just a verdict:** a point forecast can look
more decisive than it is. If the forecast's own 95% CI at the target
horizon still contains today's real price, the model itself can't rule
out little or no real movement — that's surfaced as `confidence: "low"`
rather than hidden, so a BOOK_NOW/WAIT verdict paired with "confidence:
low" reads as the honest lean it is. This mirrors DECISIONS.md #14's
"unknown" state and #16's uncertainty-as-max-caution treatment: every
module in this app has one place where it admits what it doesn't know,
rather than forcing a confident-looking number out of thin data.

**Tested against direction, not against real-data verdicts:** unit tests
assert BOOK_NOW on a strong synthetic uptrend and WAIT on a strong
synthetic downtrend (unambiguous by construction). The real-data API
tests assert shape/contract only, not a specific decision — a fresh
`git clone` only has the 3-month starter snapshot (`insufficient_data`
until `ingest_worldbank.py` is re-run), and even on this machine, the
actual verdict depends on the latest real World Bank price at whatever
moment the test runs, which will legitimately change over time. Pinning
an exact verdict in a test would be pinning today's market, not the
code's correctness.

## 18. Frontend: plain JavaScript React (not TypeScript), a thin fetch client, and CORS scoped to localhost

**Decision:** the frontend is React + Vite in plain JavaScript (`.jsx`),
not TypeScript as originally planned in PROJECT_CONTEXT.md's technology
stack list, with `react-router-dom` for a 3-page shell (Overview,
Forecast, Recommendation) and a single hand-written fetch wrapper
(`src/api/client.js`) instead of a generated API client.

**Why JavaScript, not TypeScript, deviating from the original plan:**
this is a 3-page dashboard consuming a small, already-documented REST
API (every endpoint's shape is defined and tested on the backend, see
`app/main.py`'s docstrings). TypeScript's payoff is catching a mismatch
between what the frontend expects and what the API actually returns —
here that contract is already enforced by 72 passing backend tests and
FastAPI's own response validation, and a runtime `ApiError` in
`client.js` surfaces a mismatch immediately during manual testing
anyway. Adding TypeScript would mean a `tsconfig`, type definitions for
every API response shape, and more build friction, for a hackathon-scale
app with one frontend developer and a hard deadline — not a good
trade here. This mirrors the same reasoning as #7 (5-page MVP, not 7)
and #13 (no separate training script): match the tooling to the actual
size of the problem, not the size a "proper" production app would
eventually need.

**CORS scoped to two localhost origins, not `allow_origins=["*"]`:**
the Vite dev server runs on `http://localhost:5173` by default, a
different origin from the API's `http://localhost:8000`, so the browser
blocks the frontend's `fetch()` calls without explicit CORS headers.
The allowlist in `app/main.py` is exactly `localhost:5173` and
`127.0.0.1:5173` — GET only. This app has no public deployment planned
(it's a local demo, per the 5-page MVP scope), so there's no reason to
open the API to arbitrary origins; a fixed small allowlist is the
correct scope, not a shortcut that would need tightening later.

**Verified before pushing to the user's machine:** built the full scaffold
in a sandbox first (same pattern as every backend module), started both
the FastAPI backend and the Vite dev server, and used a headless browser
to load the Overview page end-to-end — confirmed it fetches and renders
real data from all 5 endpoints it calls (health, vessels, ports,
origin-ports, commodity-prices for both commodities) with zero console
errors, confirmed client-side routing works between all three pages, and
confirmed the error state (backend not running) renders a clear,
actionable message rather than a blank page or a raw fetch exception.
`npm run build` was also verified clean in the sandbox before this went
to the user's machine.

**Scope of this pass:** Overview page is fully wired to live data
(fleet, ports, origin ports, latest commodity prices, and a data-honesty
panel restating the REAL/CALCULATED/SIMULATED/ASSUMPTION breakdown for
what's shown). Forecast and Recommendation pages are routed but
currently placeholder text — they're the next build step, once charting
(Forecast, Module 1 + 7) and the interactive port/cargo picker
(Recommendation, Module 4 + 6) are built out.

## 19. Forecast page: hand-rolled SVG chart, following the dataviz method deliberately, not by eye

**Decision:** the Forecast page's price chart (`frontend/src/components/ForecastChart.jsx`)
is a hand-rolled SVG line chart, not a charting library — same lean-tooling
reasoning as #18 (one chart, one page; a library's install size and
default-look override cost more here than they save). Rather than eyeball
the result, it was built by explicitly following the project's dataviz
skill: form first (trend-over-time, two-series categorical), then color
(the skill's own validated default palette, slots 1/2 — blue/orange,
already proven to clear every CVD and contrast gate, used unmodified —
see the palette-sourcing note in the component), then marks (2px lines,
10%-opacity area for the confidence band, hairline gridlines, >=8px end
markers), then interaction (crosshair + one tooltip, per-point on hover),
then a mandatory legend for the two series plus a third swatch for the
CI band.

**What real testing caught before this reached the user's machine:** the
first sandbox render had two genuine layout bugs, not just polish
issues. (1) Y-axis "nice" tick values were computed from the raw
data range independently of the padded plotting domain, so a tick
could land outside `[MARGIN.top, HEIGHT-MARGIN.bottom]` — with
`overflow: visible` (needed so labels aren't clipped), that tick's text
rendered above the chart, overlapping the legend. Fixed by computing
nice ticks FIRST and then widening the plotted y-domain to match them,
never the reverse — a standard chart-library behavior that a hand-rolled
chart has to implement deliberately. (2) X-axis date labels were picked
by a fixed index-modulo step, which put the actual/forecast boundary
label and the final forecast-endpoint label within a few pixels of each
other whenever the forecast horizon was short relative to the full
history (their text collided). Fixed by selecting labels by actual
rendered pixel spacing (greedy nearest-fit with a minimum gap) instead
of index arithmetic, and by dropping the boundary's own text label
entirely — the vertical dashed guide plus the "Forecast →" annotation
already marks the split, so a third label there was redundant clutter
as well as a collision risk. Both were caught by rendering real output
(a headless browser against a running backend with a realistic ~70-month
series) and looking at the screenshot, not by reading the code — exactly
the "render it and look at it" step the dataviz method itself calls for
as the final check.

**Sandbox-only synthetic data for this verification, never shipped:** the
cloud sandbox only has the 6-row starter snapshot (same situation as
every other module's testing — see DECISIONS.md #17), which is far too
short to exercise SARIMAX or produce a meaningful chart. A ~70-month
synthetic trending series was generated purely to drive the chart
through its real code path during testing (multi-year x-axis, a visible
seasonal pattern, a widening confidence band at longer horizons) and was
deleted from the sandbox afterward — it never touched the user's machine
or this repository. On the user's real machine, with the real 1480-row
World Bank history already loaded, the chart renders the actual
coal/oil series.

**The book-now-vs-wait decision badge deliberately does NOT use the
dataviz skill's status palette** (good/warning/serious/critical).
BOOK_NOW/WAIT/HOLD are recommended actions, not health or error states —
using status-red for "wait" would read as "something is wrong," which
isn't the claim being made. The badges instead reuse the app's own accent
teal (BOOK_NOW) and a neutral amber/gray pair (WAIT/HOLD) that carry no
implied severity, consistent with the status palette's own collision
rule: "when a series means good/bad it wears status tokens; when it's
just an action, it doesn't."

**Environment note, not a code issue:** getting `npm install` working
cleanly on the user's machine (via the device bridge) required a real
detour this round — an earlier interrupted install had left one
platform-mismatched optional dependency (`@rolldown/binding-win32-x64-msvc`,
Vite's Windows-specific native binding) in a Linux-side `node_modules`,
and one specific `.node` binary inside it refused to delete
(`Input/output error`, most likely a Windows-side file lock — antivirus
scanning a freshly-written binary is the common cause). Worked around by
leaving that one orphaned file in place (it's not on any resolvable
package path, so npm ignores it) and reinstalling everything else
cleanly around it. `npm run build` now succeeds on the user's machine
with the correct Linux binding present. This is a one-time repair, not a
recurring risk — the reinstall wrote a clean, consistent `node_modules`.

## 20. Recommendation page composes Module 6 directly; INR display deliberately deferred; a correction on the `node_modules` note above

**Recommendation page** is the last of the 3 MVP frontend pages. It's
deliberately thin: a port picker (3 seeded ports) and an optional
cargo-tonnes number input drive `GET /api/v1/optimize/{port_id}` as-is —
no new backend logic, no second ranking. Every returned option is
already physically compatible (Module 4's hard gate ran inside the
optimizer), so the page never shows a fail state for an individual
option; the only empty state is *zero* compatible options for the
current port + cargo combination, which does happen (e.g. an
unrealistically large fixed cargo tonnage against every vessel's DWT)
and is shown as an explanatory message, not a blank list. Each ranked
card shows the risk-adjusted cost headline plus the plain base cost and
the risk premium in one line, with the exact draft/LOA/beam margins
behind that risk score available in a `<details>` expander — the same
"never claim a number without the reasoning behind it one click away"
pattern as the Forecast page's decision card. Verified with a headless
browser across all 3 ports and a few cargo sizes: switching ports
re-ranks correctly, a small fixed cargo (5,000t) correctly re-ranks
toward smaller vessels (fixed charter-hire cost spread over far fewer
tonnes makes large vessels' cost-per-tonne spike), and the compatibility
expander renders the right numbers — zero console errors throughout.

**Both the Forecast page and this Recommendation page are still awaiting
the user's own on-machine confirmation** before their commits
(`09-forecast-page`, `10-recommendation-page`) land — same
test-confirm-commit discipline as every backend module this whole
project. Sandbox/headless-browser verification is necessary but not
sufficient; only the user's own browser, against their own running
backend, is what gates a commit.

**INR currency display, deliberately deferred, not forgotten:** the user
asked whether USD or INR is the right choice for an SIH (Ministry of
Steel) submission. Decision: keep USD as the sole primary/source-of-truth
currency everywhere in the engine and API — World Bank Pink Sheet
prices, Ship & Bunker VLSFO bunker price, and HandyBulk time-charter
rates are all genuinely USD-denominated in the real world (that's how
international dry-bulk shipping and commodity trade are actually priced),
so USD-primary is what keeps the REAL/CALCULATED labelling honest. When
built, INR will be added as a secondary, clearly-labelled CALCULATED
conversion using one cited, dated exchange rate (e.g. an RBI reference
rate for a specific date) shown alongside the USD figure — never a
silent wholesale switch of the underlying numbers to INR, which would
inject an unsourced, undated exchange-rate assumption into figures that
are currently clean REAL data. The user explicitly asked for this to be
built at the end, after the 3-page MVP is confirmed working, not now.

**Correction to the environment note under #19:** that note called the
`node_modules` platform-mismatch a "one-time repair, not a recurring
risk." It recurred on the very next build check. Root cause understood
now: this device bridge's Linux VM and the user's actual Windows
terminal share the same on-disk `node_modules` folder (it's the same
real files on the user's machine), but each writes platform-specific
native binaries into it (`@rolldown/binding-linux-x64-gnu` from an
`npm install` run through this bridge vs. `@rolldown/binding-win32-x64-msvc`
from an `npm install` run directly in the user's own terminal, which is
exactly what the user was told to do to run the app for real). Whichever
one installs *last* wins, so this bridge's own `npm run build` /
`npm run lint` sanity checks will keep flipping between working and
"Cannot find module" depending on which side last touched
`node_modules` — that's expected, not a regression, and it doesn't
affect the user: their own `npm install` / `npm run dev` on their actual
Windows machine always gets the correct Windows bindings for their own
use. This bridge's build check is a convenience for catching real code
bugs before pushing, not the source of truth for whether the app runs;
the user's own browser against their own `npm run dev` is that source of
truth, same as it's been since DECISIONS.md #18.

## 21. Data Sources & Assumptions page reads the database live — never a separate hand-maintained catalog

The 5th and final page of the locked 5-page MVP (DECISIONS.md #7). New
backend endpoint `GET /api/v1/data-sources`, built by
`app/engine/data_sources.py`, and a matching frontend page at
`/data-sources`.

**Deliberately not a hand-written list.** ports.json, vessels.json, and
origin_ports.json already carry `source` / `source_url` / `source_date`
on every row (from Module 2/3), and the World Bank ingestion already
writes `source` / `source_url` onto every `commodity_price_history` row
(Module 2, see DECISIONS.md #12). `build_data_sources()` reads those same
rows straight out of the live database, plus the same cited constants
Module 5 already uses for bunker price and time-charter rates
(`BUNKER_PRICE_SOURCE`, `TIME_CHARTER_SOURCE` in `app/engine/voyage.py`).
There is exactly one place each of these figures is typed in anywhere in
the codebase — this page cannot silently drift out of sync with what the
API is actually using, because it isn't a second copy of the citations,
it's the same rows and constants read back out.

**Six categories, and the classification is never asserted, it's
derived:** commodity prices (REAL, with row counts and date ranges
pulled live from the database, not hardcoded); East Coast India ports
(REAL when `verified: true`, ASSUMPTION otherwise — the classification
literally reads the same `verified` column the Overview page's badge
already uses, so the two can never disagree); overseas loading ports
(REAL, coordinates); vessel class specifications (ASSUMPTION, one entry
per class from `vessel_classes`); voyage cost inputs (ASSUMPTION —
bunker price and time-charter rates, cited and dated, not live feeds);
and calculated methodology (five CALCULATED entries — voyage distance,
the SARIMAX forecast, the compatibility engine, the risk-adjusted
optimizer, and book-now-vs-wait — each a short note on what's computed
from what, deliberately carrying no `source_url`, since attaching a URL
to arithmetic would misleadingly imply an external citation that doesn't
exist).

**Caught by the test suite, not by inspection:** while building this,
running it against my own sandbox database surfaced 4 commodity-price
entries instead of 2 — turned out to be leftover rows from an earlier
ad hoc synthetic dataset I'd loaded into that sandbox DB during Forecast
chart testing (deleted from the repo, per DECISIONS.md #19, but the
already-seeded rows sat in that one sandbox's `freight.db`, which
`INSERT OR REPLACE`-based seeding never clears). Confirmed this was a
sandbox-only artifact (the real device's `freight.db` was never touched
by that script) by wiping the sandbox DB and re-seeding clean, which
produced exactly the 2 expected entries. Documented here rather than
silently fixed, since it's a genuine reminder that `INSERT OR REPLACE`
seeding is additive, not a migration — a row whose primary key is no
longer in the seed source stays in the database forever unless something
explicitly deletes it. Not a problem for this hackathon's scope (nobody
is removing seed rows), but worth knowing if the seed data ever shrinks.

**Also fixed:** a copy-paste transcription bug caught by hashing every
file after pushing it to the device this round (`"ASSUMPTISN"` instead
of `"ASSUMPTION"` on one line of `data_sources.py`) — every file pushed
in this session's block was verified with `sha256sum` against the
sandbox original after writing, and this one didn't match on the first
try. Fixed in place and reverified. A reminder that byte-for-byte
verification after a manual device-bridge file push is worth doing, not
just eyeballing the diff.

Test coverage: 8 new tests in `backend/tests/test_data_sources.py`
(shape of the response, every entry has a valid classification, ports'
classification never disagrees with their own `verified` flag, vessel
classes and voyage inputs are correctly ASSUMPTION, methodology entries
are correctly CALCULATED with no `source_url`) plus 1 new API smoke test
in `test_health.py`. 81 passing tests total (up from 72 before this
session's frontend work started).

## 22. Ports 4-6 (Gangavaram, Krishnapatnam, Haldia) — real, sourced, and a genuine zero-compatibility finding at Haldia

At the Hour 27-29 checkpoint (DECISIONS.md #5's original build order), on
schedule, so per the plan this was the point to add the remaining 3 East
Coast ports rather than jump straight to polish. Confirmed with the user
before starting (AskUserQuestion, offered alongside the deferred INR
display and Indian port traffic history) — chose ports 4-6.

**Why this was cheap:** the compatibility engine (`app/engine/compatibility.py`),
optimizer (`app/engine/optimizer.py`), and Data Sources catalog
(`app/engine/data_sources.py`) are all fully data-driven off the `ports`
table — none of them hardcode a port list or count. Adding 3 rows to
`app/data/ports.json` was the entire code change; the frontend (Overview's
port table, the Recommendation page's port picker, the Data Sources page)
needed zero changes, confirmed by grepping for hardcoded port IDs/counts
across `frontend/src` before starting (none found) and by a headless-browser
pass afterward (all 6 ports render correctly everywhere, zero console
errors).

**Research, done before writing any code** (per this project's research-first
discipline): each port's draft/LOA/beam and coal-handling capability was
looked up from named, dated sources rather than assumed.

- **Gangavaram Port** (17.6215°N, 83.2298°E): 18.0m draft, 292m LOA at
  coal-priority Berth 5 / 300m at Berth 6, sourced from Adani Gangavaram's
  own 2022-23 Berthing Policy & Tariff Structure document — an official
  tariff filing, the single strongest source of any port in this dataset
  (stronger than Vizag/Paradip/Dhamra's mix of authority PDFs and press).
  Beam (48m) is not published there — an engineering inference for the
  port's own stated "fully laden Capesize up to 200,000 DWT" capability,
  flagged as such, same inference style already used for Paradip/Dhamra's
  LOA/beam. Two mechanized coal berths, 20 MTPA combined coal capacity,
  64 MTPA total (Wikipedia, FY2021-22).
- **Krishnapatnam Port** (14.2508°N, 80.1313°E): 18.5m current operational
  draft (Global Energy Monitor, 2023 figures), corroborated by an
  independent 2012 Dredging Today record of the port reaching 18.0m —
  two sources agreeing within 0.5m over an 11-year gap is a reasonable
  confirmation. One of only 3 Indian ports (with Mundra and Gangavaram)
  equipped for Capesize; 41 million tonnes of coal handled in 2018-19 is
  real audited throughput, not a capacity claim. LOA/beam (300m/48m) are
  the same engineering inference as Gangavaram's, flagged as such.
- **Haldia Dock Complex** (22.0667°N, 88.0698°E): the genuinely interesting
  result of this module. A real, verified, coal-handling port (confirmed:
  a floating terminal with a coal-specific hopper/conveyor) — but its
  approach channel is shallow and tidal-dependent: 9.1m is the *maximum*
  tidal-supported draft (Wikipedia, citing Kolkata Port Trust figures);
  the average channel draft is only 8.2-8.6m. LOA 240m / beam 32.26m come
  from a shipping agent's Haldia general-info reference, specifically for
  Berths 2, 3 & 4A (4A is Haldia's dedicated coal berth) — the most
  precise LOA/beam sourcing of any port in this dataset, better than the
  inferred figures used at Gangavaram/Krishnapatnam or even Paradip/Dhamra.

**The Haldia result, run for real through the actual engine (not
hand-waved):** every one of the 4 modeled vessel classes fails Haldia's
draft. Handysize (10.0m draft) fails by 0.9m — the narrowest margin of any
failure in this dataset. Supramax and Panamax fail on draft *and* beam:
their 32.3m beam exceeds Haldia's 32.26m max by exactly 0.04m, a real
near-miss between two independently-sourced numbers, not a rounding
artifact — left as-is rather than fudged to make it pass. Capesize fails on
all three dimensions, unsurprising given the size gap. `GET
/api/v1/optimize/HALDIA` therefore returns `[]` — confirmed this doesn't
404 or crash (the port itself is real; the endpoint's contract is "no
compatible options" is a valid 200 response, per the existing
`main.py`/`optimizer.py` design), and confirmed in the browser that the
Recommendation page's existing empty-state message ("No vessel class
physically clears this port…") renders correctly with zero frontend code
changes — that message was already written generically when the
Recommendation page shipped (DECISIONS.md #20), before Haldia's result was
even known.

This is a real, documented limitation, not a bug: Haldia's actual real-world
traffic is "mainly fully loaded Handysize carriers of 28,000-40,000 DWT" at
real-world drafts below our assumed representative 10.0m figure, plus
Panamax vessels accepted at only 40-50% of capacity (partial loading).
This app's compatibility engine only models full-DWT vessels — partial
loading / part-cargo voyages are explicitly out of scope (see
`docs/TODO.md`'s known-limitations list) — so a port whose real practice
depends on partial loading will legitimately show as fully incompatible
here. Worth revisiting if partial-loading ever gets modeled, but not before
then; not fudging Haldia's numbers to force a false "compatible" result
just to avoid an empty page.

**Gangavaram's own notable finding:** its draft limit (18.0m) exactly
equals Capesize's own draft (18.0m) — an exact 0.0m boundary, same shape as
Dhamra's existing exact-boundary case (DECISIONS.md #16), but here Capesize
clears every other dimension too, so it's ranked, not excluded. The
optimizer's risk engine correctly assigns it the maximum 15% risk penalty
(`tightest_margin_ratio_pct == 0.0`) — same mechanics already proven and
tested at Vizag, now confirmed at a second port from real data rather than
synthetic test fixtures.

Test coverage: 3 new per-port `verified`/draft checks in `test_health.py`
(`test_gangavaram_verified`, `test_krishnapatnam_verified`,
`test_haldia_verified_but_shallow` — the last explicitly asserts
`coal_handling` stays `true` even though Haldia excludes every vessel
class, since the flag describes the port's real activity, not our
engine's compatibility verdict); the compatibility matrix test extended
from 12 to 24 combinations with the full Haldia failure-reason set
asserted per vessel class; 3 new optimizer tests
(`test_optimize_gangavaram_max_risk_penalty_at_exact_boundary`,
`test_optimize_krishnapatnam_all_compatible`,
`test_optimize_haldia_returns_no_options`); the Data Sources destination-port
count updated from 3 to 6. **87 passing tests total** (up from 81).

Pushed to the device via `SendUserFile` + `device_commit_files` this round
instead of the manual base64-heredoc reconstruction used earlier in the
session — all 5 changed files matched byte-for-byte on the first
`sha256sum` check, no transcription errors this time. Worth preferring
this path going forward: it removes the manual-reconstruction step
entirely rather than just verifying after the fact.

## 23. Coking coal proxy fix — SAIL procures metallurgical coal, not the thermal coal the World Bank Pink Sheet tracks

Raised by the user asking whether the app actually satisfies the SIH26006
problem statement. Answer at the time: mostly yes on the Predict->Simulate->
Optimize->Recommend pipeline, but with two named gaps -- this decision
closes the more substantive of the two (the other, cross-port
recommendation, is a separate follow-up module, not yet started).

**The gap:** `coal_australian` (the only coal series in this app until now)
is the World Bank Pink Sheet's "Coal, Australia" line -- confirmed by
fetching the real Pink Sheet's column headers directly: it lists only
thermal coal varieties (Australia/Colombia/South Africa), no coking coal at
all. SAIL is a steel maker; it procures coking (metallurgical) coal for
blast furnaces, not thermal coal for power generation. The two commodities
move somewhat together but are priced on different markets and have
diverged meaningfully at times (thermal coal was ~$132-139/t across
May-July 2026 in this app's own seeded data; coking coal's real FOB
Australia price ranged roughly $215-241/t across the same window per the
sources below) -- treating one as a stand-in for the other would have been
a real, if easy-to-miss, proxy error against a Ministry-of-Steel problem
statement.

**Why RBA over the alternatives, researched before writing any code:**
- World Bank Pink Sheet: confirmed (again, directly) to have no coking
  coal line at all -- ruled out.
- FRED series IQ11010 ("Export Price Index (End Use): Metallurgical Grade
  Coal", US BLS): genuinely metallurgical-grade, but starts January 2025 --
  only ~18 months of history as of this build, below this app's own
  30-month SARIMAX floor (`MIN_POINTS_FOR_SARIMAX`), and it's a US export
  price INDEX (base 100), not an Australian-origin $/tonne benchmark
  matching this app's own NEWCASTLE_AU origin port. Ruled out.
- RBA's Index of Commodity Prices: confirmed via RBA's own July 2026
  release commentary that "coking coal" and "thermal coal" are tracked as
  distinct named components. Australian-origin (matches NEWCASTLE_AU), and
  the RBA's ICP has run for decades, so real historical depth is expected
  once ingested -- chosen as the target series.

**The real network constraint, same as DECISIONS.md #10:** confirmed by a
direct connection test that Claude's execution environments (cloud sandbox
and the device-bridge shell) cannot reach rba.gov.au -- same
organisation-level egress policy already documented for thedocs.worldbank.org
and fred.stlouisfed.org. `data_pipeline/ingest_rba_coking_coal.py` is real,
defensively-written code, but -- like `ingest_worldbank.py` before it --
has not been run against the real `i02hist.xlsx` file by Claude. The user
needs to run it once, in their own terminal with normal internet, exactly
the same one-time step already established for the World Bank ingestion.

**UNLIKE `ingest_worldbank.py`, this parser's layout is unverified, not
just untested.** The World Bank parser's dynamic-detection logic was
written and confirmed against a real downloaded copy of the file (see
DECISIONS.md #12's transposed-layout correction). This RBA parser's
assumed layout -- a metadata block with one label per row in column A
(Description/Frequency/Type/Unit/Source/Publication date/Series ID), then
dated data rows below -- is built from RBA's well-documented standard
statistical-table convention, not a confirmed dump of the real file. Every
lookup is done by SEARCHING for a label or a date-shaped column/row rather
than a hardcoded position, specifically so a real-layout surprise (same
shape as #12) still has a real chance of being found automatically -- but
this is flagged plainly in the module's own docstring and its test file's
docstring: a first real run may reveal the layout differs and need a
follow-up parser fix. That would not be a failure, just the same honest
process #12 already went through once.

**What's real and live right now, without the user running anything:** one
real, dated, cited coking-coal price point -- $214.90/tonne, FOB Australia,
7 August 2026, from IndexBox citing a Fastmarkets-style high-quality coking
coal assessment (a single spot-day snapshot, explicitly labelled as such,
not averaged into a fake "month" the way the real monthly WB data is).
Seeded via `commodity_prices_seed.csv` alongside the existing 3-month
coal/oil starter rows. This is NOT a substitute for the real monthly
series -- with 1 row, `GET /api/v1/forecast/coking_coal` correctly returns
`status: "insufficient_data"`, now pointing the user at
`ingest_rba_coking_coal.py` specifically (a real small bug caught while
building this: the insufficient_data message was hardcoded to always
recommend `ingest_worldbank.py`, which would have been actively wrong
advice for any future non-WB-sourced commodity -- fixed via a
per-commodity `INGEST_SCRIPT_BY_COMMODITY` lookup in `forecast.py` rather
than a second hardcode).

**Also fixed while building this:** the Data Sources catalog's
`_commodity_price_entries()` used to unconditionally describe every
commodity row-group as "monthly price history" -- correct for
coal_australian/crude_oil_brent (3+ real months each) but actively
misleading for coking_coal's single spot-day point. Now branches on
`n == 1` to say "single dated snapshot" instead, with a detail pointing at
the real ingestion script -- caught by writing the Data Sources page
change in the first place, not by a bug report.

**Kept, not replaced:** `coal_australian` (thermal) stays in the app,
relabelled everywhere from "Coal (Australian)" to "Coal (Australian,
thermal)" so the thermal/coking distinction is explicit rather than
implied. It remains the Forecast page's default selection (680 real
months, a working forecast on first load) -- coking_coal is listed FIRST
in the commodity picker (it's the one that matters to SAIL) but is not the
default, specifically so the page's first paint shows a working forecast
rather than an (honest, but less demo-friendly) insufficient-data message.
Overview's "Latest commodity prices" section gained a third stat tile,
coking coal shown first.

**Schema:** no migration needed -- `commodity` was already a free-text
column. Comment updated to list the third value and to note `date` may now
be an exact single-snapshot date, not only first-of-month, and `unit` may
be whatever `ingest_rba_coking_coal.py`'s real run actually reports (the
parser reads the file's own Unit row rather than assuming `usd_per_tonne`
-- if RBA's ICP turns out to publish coking coal as an index-points figure
rather than a raw price, this parser will report that honestly rather than
mislabel it).

**seed.py redesigned to layer multiple processed CSVs**, not just prefer
one: starter snapshot (always) -> `commodity_prices_worldbank.csv` (if
ingested) -> `commodity_prices_rba_coking.csv` (if ingested), each via
`INSERT OR REPLACE` keyed on (date, commodity) same as before -- so running
just the RBA script, without re-running the World Bank one, works
correctly, and vice versa.

Test coverage: 9 new tests in `test_ingest_rba_coking_coal.py` (mirroring
`test_ingest_worldbank.py`'s style -- label search, date-column search,
target-column search, unit extraction, and the full parse, plus clear-error
cases for a missing label row or missing coking-coal column) against a
synthetic file matching the ASSUMED (not confirmed) layout; 1 new
`test_forecast.py` test asserting the insufficient_data note names the
right script per commodity; 1 new `test_health.py` API test asserting
`GET /api/v1/forecast/coking_coal` deterministically returns
insufficient_data with that same script name (deterministic, unlike the
existing coal_australian test, since coking_coal always has exactly 1
seeded row regardless of local processed-CSV state); the existing
commodity-set assertion in `test_commodity_prices_seeded` extended to
include `coking_coal`. **98 passing tests total** (up from 87). Verified
end-to-end in a sandbox headless browser: Overview's third stat tile,
Forecast's honest insufficient-data message (correct script name), and
Data Sources' "single dated snapshot" wording all render correctly, zero
console errors, `npm run build` clean.

## 24. Cross-port recommendation, and making the Recommendation page genuinely interactive

The second of the two gaps named when the user asked whether the app
satisfies the SIH26006 problem statement (the first, the coking-coal
proxy fix, closed in #23). Then the user asked directly for the app to
be more interactive — "a way for the people who use these port services
to add their thing and check" — which turned out to be the same gap
wearing a different name: the missing direction was never a chart
feature, it was letting a real user start from what they actually have
(a ship, a loading port) instead of a destination they'd have to already
know to pick.

**The gap:** `/api/v1/optimize/{port_id}` — and the Recommendation page
built on it — only ever answers "given this destination port, which
vessel/route is cheapest?" A real charterer usually starts the other way
round: "I have this vessel class loading from this port, which of the 6
East Coast destinations should the cargo actually go to?" There was no
way to ask that question without already knowing the answer.

**What changed, backend:** `app/engine/optimizer.py` gained
`rank_ports_for_vessel(vessel, origin, ports, cargo_tonnes=None)` — the
mirror of the existing `rank_options`, fixing the vessel and origin
instead of the port. Both directions now share one `_score_option`
helper so the risk-margin methodology (Module 6, DECISIONS.md #16) can
never drift apart between them. New endpoint:
`GET /api/v1/optimize/by-vessel?vessel_type=&origin_id=&cargo_tonnes=`,
registered ahead of `/api/v1/optimize/{port_id}` so the literal segment
`by-vessel` is never swallowed as a port_id.

One deliberate difference from `rank_options`: **incompatible ports are
never silently dropped.** `rank_options` iterating over vessels for a
fixed port can afford to drop a failing vessel — there are others to
rank. Here there are only 6 named, enumerable destinations, and a real
user picking among them benefits from seeing all 6 with the exact reason
a given one doesn't work, not a shorter list they can't account for. The
response splits `compatible_ports` (ranked, same shape as before) from
`incompatible_ports` (each with its Module 4 checks and reasons).

`cargo_tonnes` exceeding the fixed vessel's own DWT is a fact independent
of which port is picked, so it's validated once up front
(`CargoExceedsCapacityError` → HTTP 422 with a plain-language message)
rather than silently producing 6 empty compatibility checks.

**What changed, frontend:** the Recommendation page gained a mode toggle
— "By vessel & loading port" (new, and now the default) vs. "By
destination port" (the original behaviour, unchanged, still reachable).
The new mode lets the user pick a vessel class, an overseas loading port,
an optional custom cargo tonnage, and a forecast horizon (3/6/12/24
months); it shows the ranked compatible destinations as cards (reusing
the same option-card pattern as the original mode) and the incompatible
ones as a plainly-labelled list with their real reasons underneath, never
just missing. This is the genuinely interactive piece the user asked
for: not a static demo of the algorithm, but a form a real user plugs
their own scenario into and gets a live, computed answer back.

**Timing, composed not duplicated:** the same panel shows two timing
cards side by side — "should I book now or wait?" for both thermal coal
and coking coal at the chosen horizon — by calling the existing
`GET /api/v1/decision/book-vs-wait/{commodity}` (Module 7, unchanged) for
both commodities at once. No new timing logic was written; this is
composition of an existing endpoint, same discipline as the optimizer
itself composing Modules 4 and 5. Coking coal's card correctly shows the
honest `insufficient_data` message (1 real seeded point, DECISIONS.md
#23) rather than a fabricated verdict.

**Verified against real, not cherry-picked, data before writing tests:**
a Capesize out of Newcastle clears exactly 3 of the 6 ports
(Krishnapatnam #1 at $7.83/t risk-adjusted, Vizag #2, Gangavaram #3) and
fails the other 3 (Paradip: draft + LOA; Dhamra: LOA only; Haldia: all
three dimensions) — the same three that clear it in the existing
port-first direction, confirming the two directions agree. A Handysize
out of Taboneo with a fixed 20,000t cargo clears 5 of 6, failing only at
Haldia's 9.1m draft limit. Both scenarios are hand-run against the live
API before being written into assertions, then screenshotted end-to-end
in a sandbox headless browser (both modes, the cargo-exceeds-DWT error
path, and the timing cards) with zero console errors and a clean
`npm run build`.

Test coverage: 4 new unit tests for `rank_ports_for_vessel` against
synthetic fixtures (compatible/incompatible split, ascending sort, the
`CargoExceedsCapacityError` path, and the all-incompatible case) plus 6
new API tests against the real seeded data (the Capesize/Newcastle
3-and-3 split with reasons, the Handysize/Taboneo custom-cargo case,
unknown vessel/origin 404s, the cargo-exceeds-DWT 422, and a route-
registration-order check). **108 passing tests total** (up from 98).

## 25. INR secondary currency display, built as deferred (DECISIONS.md #20)

Picked by the user as the next item after both named SIH26006
problem-statement gaps closed (#23, #24). Deferred back at #20 until the
3-page MVP was confirmed working — that condition is long since met.

**Kept the #20 decision exactly as made:** USD stays the sole
primary/source-of-truth currency throughout the engine and API. Every
REAL price this app uses is genuinely USD-denominated in the real world
(World Bank Pink Sheet commodity prices, Ship & Bunker VLSFO bunker
price, HandyBulk time-charter day rates, IndexBox's coking-coal
snapshot) — that's how international dry-bulk freight and commodity
trade are actually priced, so USD-primary is what keeps the
REAL/CALCULATED labelling honest. INR is added ONLY as a secondary,
clearly-labelled CALCULATED conversion, shown alongside the USD figure
it was derived from, never in place of it, and never used as the basis
for any ranking, sort order, or decision logic anywhere in the app.

**The rate:** new `backend/app/engine/currency.py`, one cited constant,
`USD_TO_INR_RATE = 94.43`. Cross-checked across two independent sources
before being set, not taken from a single unverified number: Trading
Economics' USD/INR spot quote (94.4290-94.4380 intraday) on 2026-09-04
agrees with State Bank of India's same-day forex card rate (TT Buy
94.13 / TT Sell 94.98) to within ~0.5%. Same treatment as voyage.py's
bunker price and time-charter rates: a constant with a source and a
date, refreshed on a schedule in a production system, not here.

**Backend:** new `GET /api/v1/exchange-rate` endpoint serving the rate
plus its source/URL/date — a single place the frontend fetches it from,
rather than the number being hand-copied into every component that
needs it. Also wired into `app/engine/data_sources.py` as a new
"Currency conversion" category (CALCULATED, 1 entry) so the Data Sources
& Assumptions page's claim to cover "every figure this app uses" stays
true — `test_data_sources_endpoint`'s category count moved from 6 to 7
correctly, not silently.

**Frontend:** a shared `frontend/src/hooks/useExchangeRate.js` (fetches
the rate once per page, fails silently — an INR line is a nice-to-have
on top of an already-shown USD figure, never worth its own error box)
and `frontend/src/utils/currency.js`'s `formatInr(usdValue, exchangeRate)`
(Indian digit grouping via `toLocaleString("en-IN", {style: "currency",
currency: "INR"})` — ₹1,23,456 rather than ₹123,456). Wired into every
headline USD figure a user actually reads a decision off: Overview's
three commodity-price stat cards, Forecast's decision card (latest price
and forecast price — deliberately NOT the chart itself, since a second
currency axis would be a dual-axis chart, the dataviz skill's #1
anti-pattern; the stat cards carry the CALCULATED INR figure instead),
and both Recommendation modes' ranked option cards (risk-adjusted cost
per tonne). Voyage's own fuel/charter/total cost breakdown inside each
card's `<details>` expander was deliberately left USD-only — a
documented scope choice to keep this addition sized to what a user
reads a decision off, not a hunt for every dollar figure in the app.

**Verified before writing this down:** every wired location was checked
in a running sandbox — including forcing `coal_australian`'s forecast to
`status: "ok"` with a temporary 36-row synthetic history (verification-
only, deleted immediately after, never touched anything pushed to the
user's machine) to confirm the Forecast decision card's INR line
actually renders in its "ok" branch, not just its already-checked
insufficient_data branch. 5 new tests (`test_currency.py`: the
conversion arithmetic, the `as_dict()` shape, the live endpoint) plus 2
updated (`test_data_sources_endpoint`'s category count, a new dedicated
currency-category test) — **113 passing tests total** (up from 108).
Zero console errors across all 4 pages, clean `npm run build`.

## 26. Indian port traffic history — a genuine data-availability wall, resolved by asking rather than fabricating

The last open TODO item after coking coal (#23), cross-port
recommendation (#24), and INR (#25): populate `port_traffic_history`
with real monthly coal-traffic figures for the 6 East Coast ports.

**The wall, confirmed two ways before it was treated as real:**
direct network tests (`curl`/`python`, both from the cloud sandbox and
from this device bridge) to `shipmin.gov.in`, `data.gov.in`, and
`ipa.nic.in` all failed the same way as `thedocs.worldbank.org` and
`rba.gov.au` did back at DECISIONS.md #10 — `connect_rejected
(organization policy)` / a 403 on the CONNECT tunnel. That rules out
programmatic ingestion, same as before. But this time targeted
`WebSearch`/`WebFetch` research (a separate fetch path that isn't
subject to the same block) also turned up no freely-accessible,
structured, coal-specific MONTHLY series for any of the 6 ports,
through any source — not shipmin, not data.gov.in, not a port
authority's own site, not a industry-tracker mirror. Unlike the coking-
coal case (#23), there was no substitute monthly series to fall back
on either.

**Rather than fabricate a plausible-looking series or quietly drop the
feature, this was surfaced to the user directly** with three real
options: seed the few genuinely real one-off facts that targeted
research *could* find, clearly labelled as such; skip the feature
entirely and document the gap as a limitation (the same treatment
DECISIONS.md #10 gives the Baltic Exchange route-level rates); or spend
more time searching. The user chose the first. This is the same
anti-fabrication discipline as every other REAL/CALCULATED/SIMULATED/
ASSUMPTION line in this app — the honest answer here was "no monthly
series exists," and the app says exactly that rather than implying
otherwise.

**What targeted research actually found:** one individually-reported,
citable coal-handling record per port — never a monthly aggregate. A
24-hour discharge record, a single shipment, or a berth record,
depending on what each port's own reporting happened to cover:

- Visakhapatnam (VGCB terminal): 1,06,190t steam coal, a 24-hour slice
  of a 53.5-hour, 1,64,960t total discharge from MV Gina Oldendorff,
  14–16 Apr 2025 (VisCan / India Shipping News).
- Paradip: 62,730t coking coal, a 24-hour discharge record from MV
  Pacific Energy, Jan 2017 (MarineLink) — the oldest and most dated of
  the six.
- Dhamra: 55,450t thermal coal, Berth BB-3, Apr 2025 — the source
  doesn't state whether this is a single-day or full-month figure, so
  the measurement window is flagged as unconfirmed, not asserted as a
  monthly total (Adani Ports & SEZ FY2026 digital operational report).
- Krishnapatnam: 58,594t coal, a 24-hour discharge record, Oct 2025,
  exact date not stated (same Adani FY2026 report).
- Gangavaram: 1,56,339t non-coking coal, a 24-hour discharge record
  from MV Cape Asia, Apr 2016 (AL Circle / Construction & Architecture)
  — an "all-India record" claim at the time, and the oldest along with
  Paradip.
- Haldia: 27,100t thermal coal, a single coastal shipment to Andhra
  Pradesh Power Development Company Ltd marking Haldia's resumption of
  thermal coal handling after a 9-month gap, Jul 2026 (ITLN).

These 6 rows span **2016–2026**, use different measurement windows
(single-shipment / 24-hour-slice-of-a-longer-discharge / unconfirmed
berth window), and are explicitly **not comparable to each other or to
a "typical month" for that port** — reading them as a trend would be
worse than not having them at all, so the schema and UI both work to
prevent that reading.

**Schema:** `port_traffic_history` gained a `note TEXT` column (new —
the commodity-price tables didn't need this, since row count alone
told you "snapshot" vs. "series" there; here every row needs its own
explanation of what it actually measures, since the six rows are
individually heterogeneous rather than uniformly one or the other).
`month` holds the event's own date (or first-of-month if the source
only gave a month), never a full-month total unless the note says so.
New seed file `backend/app/data/port_traffic_seed.csv`, loaded by a new
`seed_port_traffic()` in `seed.py` — kept as a row-by-row loop (not a
single INSERT) so a second, independently-researched batch can layer
on top later the same way the commodity-price seeds do.

**Backend:** new `GET /api/v1/port-traffic?port_id=` — optional filter,
returns `[]` for an unknown port rather than 404 (same honest "real
port, nothing to show" shape as `/api/v1/optimize/HALDIA` before Haldia
had compatible options). Also wired into `data_sources.py` as an 8th
Data Sources category, "Port cargo-handling records (individually
reported events, not a monthly series — see each entry's detail)" — 6
entries, all REAL, each carrying its own `note` as the entry's detail
rather than a bare citation.

**Frontend:** a new "Notable port coal-handling records" section on the
Overview page, between the East Coast ports table and the overseas
loading ports table — one card per record (port, tonnage, commodity,
date, the full note, and a working source link), with the section's own
copy stating plainly that these span multiple years, aren't comparable
to each other, and exist because no freely-accessible monthly series
does.

**Test coverage:** new `test_port_traffic.py` (6 tests: exactly one row
per port and no more, every row has a note/source/positive volume, the
years genuinely span more than one — a real assertion that this is NOT
a series clustered in one convenient month, the endpoint returns all 6,
the `?port_id=` filter, and the unknown-port-returns-`[]`-not-404
shape) plus 2 updated category-count assertions (7→8) and a new
dedicated "REAL and individually captioned" category test in
`test_data_sources.py`. **120 passing tests total** (up from 113).
Verified in a sandbox headless browser: the Overview section renders
all 6 ports with their notes and working citation links, the "not
comparable... span N different years" copy renders correctly, the Data
Sources page shows the new category, zero console errors, clean
`npm run build`.

This closes the last item from the original SIH26006 gap-check (#22 →
#23 → #24 → #25 → #26). What's left open: the real RBA coking-coal
ingestion script (#23) still hasn't been run against the live file by
anyone, and Phase 2 polish / demo readiness are next per the user's own
sequencing.

## 27. Making the app deployable, so a few people can access it and give feedback

Everything up to this point ran on localhost only — a deliberate scope
choice (see the CORS comment removed by this change) since there was no
audience beyond the user's own machine yet. The user now wants a
handful of people to be able to open the app and give feedback, without
requiring their own laptop to stay on and connected the whole time —
so this is a real deployment (Render for the backend, Vercel for the
frontend), not a temporary tunnel.

**Two hardcoded localhost assumptions had to become configurable
first**, both minimal, backward-compatible changes — local dev behavior
is unchanged if neither env var is set:

- `frontend/src/api/client.js`'s `API_BASE` now reads Vite's
  `import.meta.env.VITE_API_BASE`, falling back to
  `http://localhost:8000` exactly as before. Verified both branches by
  building the frontend twice — once with no env var (embeds
  `localhost:8000`, confirmed via `grep` on the built JS) and once with
  `VITE_API_BASE=https://example-backend.onrender.com` (embeds that
  URL instead). Vite only substitutes `VITE_`-prefixed vars at *build*
  time, so this is set once in Vercel's project settings, not something
  the running app reads at request time.
- `backend/app/main.py`'s CORS `allow_origins` now always includes the
  two local dev origins, plus whatever's in the `ALLOWED_ORIGINS` env
  var (comma-separated, unset by default — verified with a synthetic
  env var producing the right combined list). This stays a fixed
  allowlist, not `allow_origins=["*"]`: the API is read-only public
  demo data with no auth or cookies, so an open CORS policy would carry
  no real risk, but a small explicit allowlist costs nothing and is the
  more defensible default to show reviewers.

**New deployment config, both platform-native so no custom scripting is
needed:**

- `render.yaml` at the repo root — a Render Blueprint. `rootDir:
  backend`, `pip install -r requirements.txt`, `uvicorn app.main:app
  --host 0.0.0.0 --port $PORT`, health check on the existing `/health`
  endpoint. Pinned `PYTHON_VERSION: 3.11.15` to match the exact
  interpreter this project's pinned dependencies (fastapi 0.141.1,
  pydantic 2.13.5, statsmodels 0.15.0) are confirmed installing cleanly
  under in this sandbox — not a guess. `freight.db` is fully rebuilt
  from the seed files on every startup (`run_seed()`, already the case
  since Hour 0), so Render's ephemeral free-tier filesystem being wiped
  on every redeploy is a non-issue — there was never anything stateful
  to lose.
- `frontend/vercel.json` — a SPA rewrite (`/(.*) -> /index.html`) so
  `react-router-dom`'s client-side routes (`/forecast`,
  `/recommendation`, etc.) don't 404 on a direct load or refresh, which
  a static host serves literally without this.

**Deliberately left for the user to do by hand, not automated here:**
pushing to GitHub (the user already has a GitHub account; this session
has no GitHub credentials of its own and no `gh` CLI on the device),
and the actual Render/Vercel account creation and "connect this repo"
clicks (OAuth sign-in flows aren't something this session can complete
on the user's behalf). Once both are live, the two URLs get cross-wired
by hand once: the Render backend URL into Vercel's `VITE_API_BASE`, and
the Vercel frontend URL into Render's `ALLOWED_ORIGINS` — a one-time
manual step, not something worth automating for a two-service demo
deploy.

**Verified before writing this down:** 120/120 backend tests still
pass unchanged (the CORS change touches middleware config, not
behavior any test exercises), and both frontend build variants
(default and `VITE_API_BASE` override) were built and grepped to
confirm the right URL lands in the bundled JS either way.

## 28. Checking the real World Bank price history into git, for the deployed backend's sake

Discovered right after the first live Render+Vercel deploy: the
Forecast page on the deployed site showed "insufficient_data" even
though the exact same app on localhost has shown full SARIMAX
forecasts for months. Not a bug — a real gap in what Render's git
checkout actually contained.

`app/db/seed.py`'s `seed_commodity_prices` has always looked for
`data_pipeline/processed/commodity_prices_worldbank.csv` and layered
it on top of the small starter snapshot when present (see its own
docstring). That file is real — the full 1,480-row coal_australian/
crude_oil_brent history (1970-2026), ingested once by the user running
`ingest_worldbank.py` on their own machine back at the Hour 2-5
checkpoint, and used ever since for every local SARIMAX result in this
project (DECISIONS.md #13's actual MAE/RMSE numbers came from it).

But `.gitignore` filed the whole `data_pipeline/processed/` directory
under "generated/local data" — a sensible default when the only
"deployment" was the user's own machine, since the file is themselves
reproducible by re-running the ingestion script. Once Render started
building from a fresh `git clone`, that default became a problem: the
file was never in the repo, so Render's checkout had only the 3-month
starter snapshot — one month short of `build_forecast`'s own 30-month
minimum — and the honest "insufficient_data" message did exactly what
it's supposed to do, just somewhere the user didn't expect to see it.

**Fix:** a narrow `.gitignore` exception for this one file only (the
blanket `processed/*` ignore stays for everything else), and the file
itself checked in — 1,480 rows, ~330KB, real and already cited/sourced
in every row. No code change needed anywhere: `seed_commodity_prices`
already knew to look for exactly this path: it simply never found it
on Render before now.

**Deliberately not done the same way yet:** `commodity_prices_rba_coking.csv`
doesn't exist locally at all — the RBA coking-coal ingestion script
(DECISIONS.md #23) has never actually been run against the real file
by anyone, so there's nothing to check in. `coking_coal` stays on its
single starter snapshot on both localhost and the deployed site until
that changes — an honest, consistent gap rather than a deployment-only
one.

A smaller lesson worth naming for future modules: `.gitignore` choices
made when "the app" meant "one person's machine" don't automatically
survive the app growing a second, from-scratch deployment target. Any
future gitignored "local" file that a fresh clone actually needs to
run correctly is worth checking for at that point, not assumed fine
because it always worked locally.

## 29. Cleaning up the insufficient_data message for real testers

Found right after sharing the deployed link for the first round of
feedback: the "insufficient_data" message shown for coking coal (on
both the Forecast page and the Recommendation page's "Coking coal
timing" card) read `Run data_pipeline/ingest_rba_coking_coal.py to load
the full history.` — an internal script path, straight in front of
people who have no reason to know this app has a `data_pipeline/`
folder. It read like a broken error, not a deliberate design choice.

**Considered and rejected: removing coking coal from view entirely.**
Coking coal is the commodity SAIL actually procures — the whole reason
DECISIONS.md #23 exists — and it's deliberately the default selection
on the Forecast page and shown on Overview's stat cards. Hiding it
would have meant losing a real, documented differentiator (this app
caught and fixed a thermal-vs-coking-coal proxy gap most builds would
miss) while only partially fixing the problem: the same script-path
leak would still show the moment anyone selected coking coal on the
Forecast page, since removing just the Recommendation card doesn't
touch that.

**Fix:** reworded the one place this message is actually generated —
`build_forecast`'s `note` field in `app/engine/forecast.py` (both the
Forecast page and `book_or_wait.py`'s `reasoning` field for the timing
cards read this exact string, so one change fixes both surfaces).
Dropped the `INGEST_SCRIPT_BY_COMMODITY` lookup and the script-path
sentence entirely; the note now reads plainly — "Only 1 real month(s)
of price history are loaded for coking coal — a seasonal forecast
needs at least 30. See the Data Sources page for exactly what's loaded
and why." — pointing a curious tester at the page built for exactly
this question instead of a file path only the developer can act on.
Still fully honest: it states the real month count and the real
threshold, same as before, just without assuming the reader can run
Python scripts.

Updated the two tests that had pinned the old wording
(`test_insufficient_data_note_points_at_the_right_ingest_script` in
`test_forecast.py`, `test_coking_coal_forecast_insufficient_data` in
`test_health.py`) to assert the new, honest, script-free message
instead. 120/120 tests still pass — no behavior changed, only the
wording of one string.


## 30. Interactive route map on the Recommendation page

**What:** added a small interactive map to both modes of the
Recommendation page (by-vessel and by-port) showing the loading port,
the East Coast destination ports, and a line for the actual route
between whichever pair is currently focused. Clicking a compatible
marker refocuses the map on that option; incompatible ports are still
shown (never dropped, consistent with DECISIONS.md #24) but drawn
muted and are not clickable.

**Why:** a tester asked whether a "live map" would help. Two very
different things go by that name — a real-time AIS vessel-tracking
feed, and a static, interactive route visualization. AIS tracking
would mean a live third-party data dependency, ongoing cost, and a
feature this app has no real ship positions to back — inconsistent
with the project's data-honesty framing, and too much new surface
area to build and verify before the SIH demo. A route map that draws
the app's own already-real port coordinates and its own already-real
route calculation is low-risk by comparison: no new data source, no
external dependency beyond map tiles, and it makes the existing
distance/cost numbers easier to sanity-check at a glance.

**Key decision — reuse the real route, don't invent a new one.**
`app/engine/voyage.py` already has a hand-chosen `ROUTE_WAYPOINTS`
dict per origin port, used by `route_distance_nm()` for the actual
distance/cost numbers shown everywhere else in the app. A naive
straight line between origin and destination coordinates would be
shorter than the real distance and would visibly cut across land
masses (e.g. Australia to India) — wrong, and inconsistent with the
number displayed right next to it. Instead, `GET /api/v1/origin-ports`
now also returns each origin's `route_waypoints` (the exact list
`route_distance_nm` uses), and the frontend draws that same path,
closed off with whichever port is focused. The picture always matches
the number.

**What was built:**
- Backend: `route_waypoints` field added to `GET /api/v1/origin-ports`
  (`app/main.py`), sourced directly from `ROUTE_WAYPOINTS` — no new
  data, just exposing what the engine already had. New test
  (`test_origin_ports_carry_the_same_route_waypoints_voyage_calc_uses`
  in `test_voyage.py`) asserts the API's waypoints match the engine's
  own dict exactly, so the two can never silently drift apart. 121/121
  backend tests passing (up from 120).
- Frontend: new `RouteMap.jsx` component built on `react-leaflet`
  (`leaflet` + `react-leaflet` added as dependencies). Uses
  `CircleMarker`s (not image-based markers) to sidestep the classic
  Leaflet-plus-bundler broken-marker-icon problem. Marker color
  follows the same status convention already used elsewhere in the
  app (accent green = top/focused, blue = other compatible, muted
  gray = incompatible — never red, since being excluded isn't an
  error here, matching the existing `.incompat-row` treatment).
  Map tiles are OpenStreetMap; port positions are the same REAL
  harbour-level coordinates already used and labeled elsewhere
  (DECISIONS.md #11).
- Wired into both Recommendation panels: in "by vessel" mode the
  anchor is the fixed loading port (which owns the real waypoints)
  and the points are the 6 destination ports; in "by port" mode the
  anchor is the fixed destination and the points are the 3 loading
  ports (each carrying its own waypoints). The component picks up
  whichever side actually has `route_waypoints` rather than assuming
  a fixed direction.

**Honest caveat, not fixed, not hidden:** in "by vessel" mode the map
is zoomed out enough to show the full ocean crossing, which means the
6 Indian destination ports — genuinely close together compared to the
distance from Australia/South Africa/Indonesia — can appear as a
tight cluster at the default zoom. The map's own zoom controls let a
user zoom into that cluster to click individual ports; this wasn't
"fixed" with a split-view or auto-zoom because that adds real
complexity for a cosmetic issue, and the tight clustering is itself an
accurate reflection of the real geography, not a rendering bug.

**Verification:** `npm run build` clean; both Recommendation modes
screenshotted via a headless browser with zero console errors (network
errors for map tiles are a cloud-sandbox egress restriction only —
`tile.openstreetmap.org` isn't reachable from the verification
sandbox, unrelated to the app code, and not expected to occur on the
user's own machine or on the deployed site).


## 31. Text-reduction / "more professional" pass across all 4 pages

**What:** every page's intro paragraph, and every "sourcing"/"methodology"
explanation that sits under a section heading (REAL/CALCULATED provenance
notes, the SARIMAX model-parameter dump, the map's "what this is drawing"
caption, the Data Sources classification legend, Overview's REAL/
CALCULATED/SIMULATED/ASSUMPTION definitions), is now collapsed by default
behind a small "ⓘ Label" disclosure, instead of always-visible paragraph
text. Nothing was cut or reworded — every sentence that was on the page
before is still there, one click away.

**Why:** a tester asked for a more professional look with less text on
screen. The app's own data-honesty framing means a lot of real
explanatory copy (what's REAL vs. CALCULATED, where a number came from,
why a set of records isn't comparable) — genuinely useful for someone
checking the app's credibility, but not something every visitor needs to
read on every glance. Two options were on the table: shorten the copy
(risking cutting a real caveat) or hide it behind an expand/collapse
(risking nothing, since the full text survives, just not open by
default). Chose the second — consistent with a pattern the app already
had (each option card's "Why this port/vessel works" breakdown is a
`<details>` collapsed by default) rather than a new idea.

**What was built:** a single reusable `InfoNote` component
(`frontend/src/components/InfoNote.jsx`) — a `<details>`/`<summary>`
disclosure styled as a small muted "ⓘ Label" line, expanding to the full
text below it. Applied it to: each page's top intro paragraph (Overview,
Forecast, Data Sources, and both Recommendation-page views); every
section's REAL/CALCULATED/ASSUMPTION sourcing note on Overview; the
SARIMAX methodology note and the raw model-parameter dump on Forecast;
the Data Sources page's top intro and its classification legend
(the actual source catalog below it — the reason the page exists — is
left fully visible, not collapsed, since hiding the sources themselves
would work against the page's purpose); and the route map's caption.

**What was deliberately left alone:** the book-now-vs-wait `reasoning`
text (DecisionCard / TimingCard) and the `insufficient_data` notes stay
fully visible — these are the actual answer the page exists to give, not
background methodology, so collapsing them by default would hide the
one thing a visitor came to read. The "Why this port/vessel works"
breakdown on each option card and the "Not compatible" reasons list were
already collapsed/itemized appropriately and needed no change. Every
individual Data Sources / port-traffic entry (label, detail, citation)
stays fully visible per entry — collapsing a source catalog's own
sources would undercut the one page whose whole job is to be checked.

**Verification:** `npm run build` clean, backend still 121/121 passing
(no backend files touched this pass). All 4 pages (Overview, Forecast,
both Recommendation views, Data Sources) screenshotted twice each via a
headless browser — once in the default collapsed state, once with every
`<details>` on the page forced open — confirming nothing was lost and
every InfoNote expands cleanly. Zero console errors on any page (the
same map-tile-blocked warnings from the sandbox's network egress as in
DECISIONS.md #30, unrelated to this change).
