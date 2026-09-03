"""
Freight Charter Compass — backend entrypoint.

Hour 0-2 scope: prove the skeleton is real. Two read endpoints backed by the
seeded SQLite database, plus a health check. Compatibility, voyage, forecast
and recommend endpoints are built in later modules (see TODO.md) — this file
grows by import, not by rewrite, as app/api/* fills in.
"""
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from app.db.connection import db_session
from app.db.seed import run_seed
from app.engine.compatibility import build_matrix, check_compatibility
from app.engine.forecast import DEFAULT_HORIZON, build_forecast
from app.engine.voyage import calculate_voyage


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
    """Real commodity price history (World Bank Pink Sheet — see
    docs/PROJECT_CONTEXT.md for the real/calculated/simulated breakdown).
    Optional ?commodity=coal_australian|crude_oil_brent filter."""
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
    voyages from - see docs/DECISIONS.md #8 for why this isn't a general
    port database."""
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM origin_ports").fetchall()
        return [dict(r) for r in rows]


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
    feeds - see app/engine/voyage.py and the response's `assumptions`
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
