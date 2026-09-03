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

Hour 0–2 (setup) complete: schema, seed data (4 vessel classes, 3 ports),
FastAPI skeleton with 3 working endpoints, 6 passing tests. Everything from
the compatibility engine onward is not yet built — see TODO.md.

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

## Frontend

Not yet built (`frontend/` is currently empty) — see `docs/TODO.md` for
when it starts.
