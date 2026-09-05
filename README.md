# Freight Charter Compass

**SIH26006 · Ministry of Steel · Transportation & Logistics**

A decision-support prototype for SAIL's overseas bulk-cargo (coal) vessel
chartering: given a cargo requirement, it forecasts freight-relevant market
trends from real public data, checks which vessel/port combinations are
physically possible, prices every feasible option transparently, and
recommends whether to book now or wait — with a plain-language explanation,
never a black-box score.

Full project context, architecture, data sources, and current status:
**[`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md)** — read that first.
Punch list: [`docs/TODO.md`](docs/TODO.md). Why things are built the way
they are: [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Status

Backend is functionally complete for the MVP's decision-engine: real
ingested commodity price history for three commodities — coal
(thermal AND coking, priced and forecast separately since SAIL procures
coking coal, not thermal — see DECISIONS.md #23) and crude oil — a
SARIMAX forecast model, a physical vessel/port compatibility gate, a
voyage cost calculator, a risk-adjusted optimizer that ranks in both
directions (destination-first, and now vessel-first across all 6 ports
— DECISIONS.md #24), a book-now-vs-wait recommendation, a secondary INR
currency display alongside every USD figure a user reads a decision off
(DECISIONS.md #25), 6 real individually-sourced port coal-handling
records (DECISIONS.md #26), and a Data Sources & Assumptions catalog,
covering 6 East Coast ports (Visakhapatnam, Paradip, Dhamra,
Gangavaram, Krishnapatnam, Haldia) — 121 passing tests, all wired into
the running API. The frontend (React + Vite) has all 5 locked MVP pages
built — Overview, Forecast (SARIMAX chart + decision card),
Recommendation (now genuinely interactive: pick your own vessel,
loading port, cargo size and horizon and get a live ranked answer
across all 6 destinations, or the original destination-first view),
and Data Sources & Assumptions (every REAL/CALCULATED/SIMULATED/
ASSUMPTION figure the app uses, in one place) — all live against the
real API and verified in a sandbox headless browser, fully data-driven
so ports 4-6 needed zero frontend changes (confirmed by the user,
committed as `11-ports-4-6`). The Recommendation page also now has an
interactive route map in both modes, drawing the real port coordinates
and the same route waypoints the voyage-cost calculation itself uses
(DECISIONS.md #30). Every page's intro text and sourcing/methodology
notes are collapsed by default behind a small "ⓘ" disclosure for a
cleaner, less text-heavy look — nothing removed, just tucked away one
click deep (DECISIONS.md #31). The coking-coal proxy fix
(`12-coking-coal-proxy`), the cross-port recommendation module
(`13-cross-port-recommendation`), and the INR currency display
(`14-inr-currency-display`) are all confirmed and committed. The
Indian port traffic history module (6 real, individually-sourced,
individually-captioned one-off records — no freely-accessible monthly
series exists for these ports, see DECISIONS.md #26) is confirmed and
committed. The app is also now deployed for outside testers (GitHub ->
Render -> Vercel — DECISIONS.md #27-29). The real RBA coking-coal
ingestion script hasn't been run by anyone against the real file yet
(so the app honestly shows "insufficient data" for coking coal rather
than faking a series). See TODO.md for the exact punch list.

## Quick start (backend)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
python -m pytest tests/ -v
python -m uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/docs` for interactive API docs, or try:

```
http://127.0.0.1:8000/health
http://127.0.0.1:8000/api/v1/vessels
http://127.0.0.1:8000/api/v1/ports
http://127.0.0.1:8000/api/v1/ports/VIZAG
```

## Data honesty

Every number in this project is labelled **Real**, **Calculated**,
**Simulated**, or **Assumption** — see `docs/PROJECT_CONTEXT.md` for the
full breakdown and source URLs. Nothing here is claimed to be SAIL's actual
procurement data; the goal is a defensible decision-support *method* built
on real public data where it exists.

## Quick start (frontend)

Needs the backend running first (see above) — the frontend fetches live
data from `http://localhost:8000` and shows a clear error if it can't
reach it.

```bash
cd frontend
npm install
npm run dev
```

Then open the URL Vite prints (default `http://localhost:5173`). The
Overview page is fully live; Forecast and Recommendation are placeholders
for now — see `docs/TODO.md`.
