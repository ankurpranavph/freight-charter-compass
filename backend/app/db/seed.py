"""
Load app/data/vessels.json, app/data/ports.json, and
app/data/commodity_prices_seed.csv into SQLite.

Idempotent: uses INSERT OR REPLACE keyed on the primary key, so re-running
this after editing a seed file (e.g. once Paradip's real berth draft is
extracted in Module 3, or once ingest_worldbank.py produces the full
historical CSV) simply refreshes the affected rows.
"""
import csv
import json
from pathlib import Path
from app.db.connection import db_session
from app.db.init_db import init_db

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def seed_vessels(conn) -> int:
    rows = json.loads((DATA_DIR / "vessels.json").read_text())
    for r in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO vessel_classes
                (vessel_type, dwt_tonnes, draft_m, loa_m, beam_m, speed_knots,
                 fuel_cons_tpd, opex_usd_day, is_assumption, source, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["vessel_type"], r["dwt_tonnes"], r["draft_m"], r["loa_m"],
                r["beam_m"], r["speed_knots"], r["fuel_cons_tpd"],
                r.get("opex_usd_day"), int(r["is_assumption"]), r.get("source"),
                r.get("source_url"),
            ),
        )
    return len(rows)


def seed_ports(conn) -> int:
    rows = json.loads((DATA_DIR / "ports.json").read_text())
    for r in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO ports
                (port_id, name, state, lat, lon, lat_lon_provenance,
                 max_draft_m, max_loa_m, max_beam_m, coal_handling,
                 berth_reference, annual_capacity_mtpa, verified,
                 source, source_url, source_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["port_id"], r["name"], r.get("state"), r.get("lat"), r.get("lon"),
                r.get("lat_lon_provenance"), r.get("max_draft_m"), r.get("max_loa_m"),
                r.get("max_beam_m"), int(r["coal_handling"]), r.get("berth_reference"),
                r.get("annual_capacity_mtpa"), int(r["verified"]), r.get("source"),
                r.get("source_url"), r.get("source_date"),
            ),
        )
    return len(rows)


def seed_origin_ports(conn) -> int:
    rows = json.loads((DATA_DIR / "origin_ports.json").read_text())
    for r in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO origin_ports
                (origin_id, name, country, lat, lon, source, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["origin_id"], r["name"], r["country"], r["lat"], r["lon"],
                r.get("source"), r.get("source_url"),
            ),
        )
    return len(rows)


def seed_commodity_prices(conn) -> int:
    """
    Loads whichever commodity-price CSV is available, preferring the full
    history from ingest_worldbank.py if the user has run it, falling back
    to the small real starter snapshot checked into the repo.
    """
    full_history = (
        Path(__file__).resolve().parents[2]
        / "data_pipeline" / "processed" / "commodity_prices_worldbank.csv"
    )
    starter = DATA_DIR / "commodity_prices_seed.csv"
    path = full_history if full_history.exists() else starter

    n = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                """
                INSERT OR REPLACE INTO commodity_price_history
                    (date, commodity, price_usd, unit, source, source_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["date"], row["commodity"], float(row["price_usd"]),
                    row["unit"], row.get("source"), row.get("source_url"),
                ),
            )
            n += 1
    return n, path


def run_seed() -> None:
    init_db()
    with db_session() as conn:
        n_vessels = seed_vessels(conn)
        n_ports = seed_ports(conn)
        n_origin_ports = seed_origin_ports(conn)
        n_prices, price_source = seed_commodity_prices(conn)
    print(
        f"Seeded {n_vessels} vessel classes, {n_ports} ports, "
        f"{n_origin_ports} origin ports, {n_prices} commodity-price rows "
        f"(from {price_source.name})."
    )


if __name__ == "__main__":
    run_seed()
