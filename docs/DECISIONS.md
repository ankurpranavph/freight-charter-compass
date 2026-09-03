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
