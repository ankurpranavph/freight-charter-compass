"""
Freight Charter Compass — backend entrypoint.

Hour 0-2 scope: prove the skeleton is real. Two read endpoints backed by the
seeded SQLite database, plus a health check. Compatibility, voyage, forecast
and recommend endpoints are built in later modules (see TODO.md) — this file
grows by import, not by rewrite, as app/api/* fills in.
"""
import os
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.db.connection import db_session
from app.db.seed import run_seed
from app.engine.book_or_wait import DEFAULT_DECISION_HORIZON, evaluate_book_or_wait
from app.engine.compatibility import build_matrix, check_compatibility
from app.engine.currency import as_dict as exchange_rate_dict
from app.engine.data_sources import build_data_sources
from app.engine.forecast import DEFAULT_HORIZON, build_forecast
from app.engine.optimizer import CargoExceedsCapacityError, rank_options, rank_ports_for_vessel
from app.engine.voyage import ROUTE_WAYPOINTS, calculate_voyage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent: safe to run every time the server starts during development.
    run_seed()
    yield


app = FastAPI(
    title="Freight Charter Compass API",
    description="Decision support for overseas bulk-cargo vessel chartering — SIH26006.",
    version="0.1.0",
    lifespan=lifespan,
)

# The frontend (Vite dev server, default http://localhost:5173) is a
# different origin from this API (http://localhost:8000), so the browser
# blocks fetch() calls between them without explicit CORS headers. The
# local dev origins are always allowed; a deployed frontend's origin
# (e.g. a Vercel URL) is added via the ALLOWED_ORIGINS env var —
# comma-separated, set on the hosting platform, never hardcoded here —
# so this file doesn't need a code change per deployment. Still a fixed
# allowlist, not "allow *": this API serves only read-only public demo
# data (no auth, no cookies, no write endpoints), so the origin check
# is a sensible default rather than a strict security boundary — see
# DECISIONS.md #27.
_allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
] + [origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "freight-charter-compass-api"}


@app.get("/api/v1/vessels")
def list_vessels():
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM vessel_classes").fetchall()
        return [dict(r) for r in rows]


@app.get("/api/v1/ports")
def list_ports():
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM ports").fetchall()
        return [dict(r) for r in rows]


@app.get("/api/v1/ports/{port_id}")
def get_port(port_id: str):
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM ports WHERE port_id = ?", (port_id.upper(),)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown port_id '{port_id}'")
        return dict(row)


@app.get("/api/v1/commodity-prices")
def list_commodity_prices(commodity: str | None = None):
    """Real commodity price history (World Bank Pink Sheet for
    coal_australian/crude_oil_brent, RBA Index of Commodity Prices for
    coking_coal — see docs/PROJECT_CONTEXT.md for the real/calculated/
    simulated breakdown). Optional
    ?commodity=coal_australian|crude_oil_brent|coking_coal filter."""
    with db_session() as conn:
        if commodity:
            rows = conn.execute(
                "SELECT * FROM commodity_price_history WHERE commodity = ? ORDER BY date",
                (commodity,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM commodity_price_history ORDER BY commodity, date"
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/v1/forecast/{commodity}")
def get_forecast(commodity: str, horizon: int = Query(DEFAULT_HORIZON, ge=1, le=24)):
    """Module 1 (Predict): freight-relevant commodity price forecast.
    SARIMAX vs. a seasonal-naive baseline, evaluated on a holdout slice of
    real World Bank Pink Sheet history. See app/engine/forecast.py for
    methodology and docs/PROJECT_CONTEXT.md for the real/calculated/
    simulated data-honesty breakdown. `horizon` = months ahead (1-24)."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT date, price_usd FROM commodity_price_history WHERE commodity = ? ORDER BY date",
            (commodity,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Unknown or empty commodity '{commodity}'")
    df = pd.DataFrame([dict(r) for r in rows])
    try:
        result = build_forecast(commodity, df, horizon=horizon)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.as_dict()


@app.get("/api/v1/compatibility/check")
def compatibility_check(vessel_type: str, port_id: str):
    """Module 4 (physical gate): can this vessel class call at this port?
    Checks draft/LOA/beam against the port's stated limits plus coal
    handling. See app/engine/compatibility.py for the exact rules."""
    with db_session() as conn:
        vessel_row = conn.execute(
            "SELECT * FROM vessel_classes WHERE vessel_type = ?", (vessel_type,)
        ).fetchone()
        port_row = conn.execute(
            "SELECT * FROM ports WHERE port_id = ?", (port_id.upper(),)
        ).fetchone()
    if vessel_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown vessel_type '{vessel_type}'")
    if port_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown port_id '{port_id}'")
    return check_compatibility(dict(vessel_row), dict(port_row)).as_dict()


@app.get("/api/v1/compatibility/matrix")
def compatibility_matrix():
    """Every vessel class x every seeded port, each with a pass/fail and
    the exact reason for any failure. Powers the Vessel & Port
    Recommendation dashboard page."""
    with db_session() as conn:
        vessels = [dict(r) for r in conn.execute("SELECT * FROM vessel_classes").fetchall()]
        ports = [dict(r) for r in conn.execute("SELECT * FROM ports").fetchall()]
    return build_matrix(vessels, ports)


@app.get("/api/v1/origin-ports")
def list_origin_ports():
    """The fixed small set of overseas coal-loading ports this app costs
    voyages from — see docs/DECISIONS.md #8 for why this isn't a general
    port database. Each row also carries `route_waypoints`: the exact
    open-ocean waypoints app/engine/voyage.py's route_distance_nm uses for
    this origin's real distance/cost calculation (DECISIONS.md #30) — the
    frontend's route map draws this same path, not an invented straight
    line, so the picture matches the number."""
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM origin_ports").fetchall()
        result = []
        for r in rows:
            row = dict(r)
            waypoints = ROUTE_WAYPOINTS.get(row["origin_id"], [])
            row["route_waypoints"] = [list(point) for point in waypoints]
            result.append(row)
        return result


@app.get("/api/v1/voyage/calculate")
def voyage_calculate(
    vessel_type: str,
    origin_id: str,
    port_id: str,
    cargo_tonnes: float | None = Query(None, gt=0),
):
    """Module 5 (Simulate): one-way laden voyage cost for a vessel class
    from an overseas loading port to an East Coast India port. Distance is
    CALCULATED (great-circle via hand-chosen waypoints); bunker price and
    time-charter rate are real, cited, point-in-time ASSUMPTIONs, not live
    feeds — see app/engine/voyage.py and the response's `assumptions`
    block. `cargo_tonnes` defaults to the vessel's full DWT."""
    with db_session() as conn:
        vessel_row = conn.execute(
            "SELECT * FROM vessel_classes WHERE vessel_type = ?", (vessel_type,)
        ).fetchone()
        origin_row = conn.execute(
            "SELECT * FROM origin_ports WHERE origin_id = ?", (origin_id.upper(),)
        ).fetchone()
        port_row = conn.execute(
            "SELECT * FROM ports WHERE port_id = ?", (port_id.upper(),)
        ).fetchone()
    if vessel_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown vessel_type '{vessel_type}'")
    if origin_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown origin_id '{origin_id}'")
    if port_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown port_id '{port_id}'")
    try:
        result = calculate_voyage(
            dict(vessel_row), dict(origin_row), dict(port_row), cargo_tonnes=cargo_tonnes
        )
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.as_dict()


@app.get("/api/v1/optimize/by-vessel")
def optimize_by_vessel(
    vessel_type: str,
    origin_id: str,
    cargo_tonnes: float | None = Query(None, gt=0),
):
    """Module 6, mirrored direction: fixed vessel class + overseas
    loading port — which of the 6 East Coast destinations should this
    cargo actually go to? /api/v1/optimize/{port_id} answers the other
    question (fixed destination, rank vessel x origin); this fixes
    vessel x origin and ranks destinations instead — added after
    re-checking the app against the SIH26006 problem statement, since a
    real charterer usually starts here, not with a port already picked.
    Registered ahead of /api/v1/optimize/{port_id} so "by-vessel" is
    never swallowed as a port_id. Every port is returned: compatible
    ones ranked by risk-adjusted cost/tonne, incompatible ones with the
    exact reason (never silently dropped — see
    app/engine/optimizer.py's rank_ports_for_vessel). 404 for an
    unknown vessel_type/origin_id; 422 if cargo_tonnes exceeds this
    vessel's own DWT (true at every port, so checked once)."""
    with db_session() as conn:
        vessel_row = conn.execute(
            "SELECT * FROM vessel_classes WHERE vessel_type = ?", (vessel_type,)
        ).fetchone()
        origin_row = conn.execute(
            "SELECT * FROM origin_ports WHERE origin_id = ?", (origin_id.upper(),)
        ).fetchone()
        if vessel_row is None:
            raise HTTPException(status_code=404, detail=f"Unknown vessel_type '{vessel_type}'")
        if origin_row is None:
            raise HTTPException(status_code=404, detail=f"Unknown origin_id '{origin_id}'")
        ports = [dict(r) for r in conn.execute("SELECT * FROM ports").fetchall()]
    try:
        compatible, incompatible = rank_ports_for_vessel(
            dict(vessel_row), dict(origin_row), ports, cargo_tonnes=cargo_tonnes
        )
    except CargoExceedsCapacityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "vessel_type": vessel_type,
        "origin_id": origin_id.upper(),
        "cargo_tonnes": cargo_tonnes,
        "compatible_ports": [
            {**opt.as_dict(), "rank": i + 1} for i, opt in enumerate(compatible)
        ],
        "incompatible_ports": incompatible,
    }


@app.get("/api/v1/optimize/{port_id}")
def optimize(port_id: str, cargo_tonnes: float | None = Query(None, gt=0)):
    """Module 6 (Optimize): rank every physically-compatible vessel x
    origin-port combination for this destination by risk-adjusted cost
    per tonne. Composes Module 4 (compatibility) and Module 5 (voyage
    cost) — see app/engine/optimizer.py for the risk-margin methodology.
    An incompatible vessel, or one too small for a given cargo_tonnes, is
    simply absent from the ranking (see /api/v1/compatibility/matrix for
    the full pass/fail picture). 404 if port_id is unknown."""
    with db_session() as conn:
        port_row = conn.execute(
            "SELECT * FROM ports WHERE port_id = ?", (port_id.upper(),)
        ).fetchone()
        if port_row is None:
            raise HTTPException(status_code=404, detail=f"Unknown port_id '{port_id}'")
        vessels = [dict(r) for r in conn.execute("SELECT * FROM vessel_classes").fetchall()]
        origins = [dict(r) for r in conn.execute("SELECT * FROM origin_ports").fetchall()]
    ranked = rank_options(dict(port_row), vessels, origins, cargo_tonnes=cargo_tonnes)
    return [{**opt.as_dict(), "rank": i + 1} for i, opt in enumerate(ranked)]


@app.get("/api/v1/decision/book-vs-wait/{commodity}")
def book_or_wait(
    commodity: str, horizon: int = Query(DEFAULT_DECISION_HORIZON, ge=1, le=24)
):
    """Module 7 (last step of Predict -> Simulate -> Optimize -> Recommend):
    should procurement lock in this commodity's price now, or wait? Built
    directly on Module 1's own SARIMAX forecast — compares the latest real
    price to the forecast at `horizon` months out. See
    app/engine/book_or_wait.py for the decision thresholds and the honest
    low/high confidence flag. 404 for an unknown/empty commodity;
    `status: "insufficient_data"` (not an error) if there isn't enough
    history loaded yet for that commodity."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT date, price_usd FROM commodity_price_history WHERE commodity = ? ORDER BY date",
            (commodity,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Unknown or empty commodity '{commodity}'")
    df = pd.DataFrame([dict(r) for r in rows])
    try:
        result = evaluate_book_or_wait(commodity, df, horizon=horizon)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result.as_dict()


@app.get("/api/v1/port-traffic")
def list_port_traffic(port_id: str | None = None):
    """One individually-reported coal-handling record per port (a 24-hour
    discharge record, a single shipment, a berth record) -- never a
    monthly series. Every row's `note` states plainly what the figure
    actually measures; rows span 2016-2026 and are NOT comparable to
    each other or to a "typical month" for that port. Context only --
    not used by any ranking or decision logic in this app. See
    app/db/schema.sql's table comment and DECISIONS.md #26 for why no
    real monthly series exists through any freely-accessible source for
    these 6 ports. Optional `?port_id=` filter."""
    with db_session() as conn:
        if port_id:
            rows = conn.execute(
                "SELECT * FROM port_traffic_history WHERE port_id = ? ORDER BY month",
                (port_id.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM port_traffic_history ORDER BY port_id, month"
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/v1/exchange-rate")
def exchange_rate():
    """Module 8: the single cited USD->INR rate used to show every USD
    figure in the app with a secondary INR figure alongside it. USD stays
    the source-of-truth currency everywhere in the engine and API — this
    endpoint exists so the frontend can compute a display-only INR figure
    from it in one place rather than the rate being hand-copied into
    multiple components. See app/engine/currency.py and DECISIONS.md
    #25."""
    return exchange_rate_dict()


@app.get("/api/v1/data-sources")
def data_sources():
    """Data Sources & Assumptions page backing: every REAL/CALCULATED/
    SIMULATED/ASSUMPTION figure in the app, in one catalog, read live from
    the same seeded rows and cited constants the rest of the API already
    uses (never a separately hand-maintained duplicate) — see
    app/engine/data_sources.py."""
    with db_session() as conn:
        return build_data_sources(conn)
