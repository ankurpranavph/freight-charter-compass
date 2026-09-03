"""
Load app/data/vessels.json and app/data/ports.json into SQLite.

Idempotent: uses INSERT OR REPLACE keyed on the primary key, so re-running
this after editing a seed JSON file (e.g. once Paradip's real berth draft is
extracted in Module 3) simply refreshes the row.
"""
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


def run_seed() -> None:
    init_db()
    with db_session() as conn:
        n_vessels = seed_vessels(conn)
        n_ports = seed_ports(conn)
    print(f"Seeded {n_vessels} vessel classes and {n_ports} ports.")


if __name__ == "__main__":
    run_seed()
