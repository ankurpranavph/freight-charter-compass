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
