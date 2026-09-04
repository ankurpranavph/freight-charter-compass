"""
Module: Data Sources & Assumptions catalog.

Answers, for the whole app in one place: where did every number actually
come from? This is the last page of the locked 5-page MVP scope
(DECISIONS.md #7). It is deliberately NOT a hand-maintained duplicate of
the sourcing already recorded elsewhere — ports.json, vessels.json, and
origin_ports.json already carry source/source_url/source_date per row,
and the World Bank ingestion already writes source/source_url onto every
commodity_price_history row. This module reads those same rows back out
of the live database, plus the same cited constants Module 5 already
uses (BUNKER_PRICE_SOURCE, TIME_CHARTER_SOURCE), so this page can never
silently drift out of sync with what the rest of the app is actually
using — there is exactly one place each of those figures is typed in.

The CALCULATED entries (voyage distance, forecast, compatibility,
optimizer, book-or-wait) have no external citation by definition — they
are arithmetic or a statistical model over the REAL/ASSUMPTION data
above, not a fact pulled from anywhere — so those five are static
methodology notes, not database-derived.
"""
from app.engine.currency import (
    USD_TO_INR_RATE,
    USD_TO_INR_SOURCE,
    USD_TO_INR_SOURCE_URL,
)
from app.engine.voyage import (
    BUNKER_PRICE_SOURCE,
    BUNKER_PRICE_SOURCE_URL,
    BUNKER_PRICE_USD_PER_TONNE,
    TIME_CHARTER_SOURCE,
    TIME_CHARTER_SOURCE_URL,
    TIME_CHARTER_USD_PER_DAY,
)

VALID_CLASSIFICATIONS = {"REAL", "CALCULATED", "SIMULATED", "ASSUMPTION"}

COMMODITY_LABELS = {
    "coal_australian": "Coal (Australian, thermal)",
    "crude_oil_brent": "Crude oil (Brent)",
    "coking_coal": "Coking coal (Australian, metallurgical — what SAIL actually procures)",
}


def _entry(label, classification, detail=None, source=None, source_url=None, source_date=None, verified=None):
    if classification not in VALID_CLASSIFICATIONS:
        raise ValueError(f"Unknown classification '{classification}' for '{label}'")
    return {
        "label": label,
        "classification": classification,
        "detail": detail,
        "source": source,
        "source_url": source_url,
        "source_date": source_date,
        "verified": verified,
    }


def _commodity_price_entries(conn) -> list:
    rows = conn.execute(
        """
        SELECT commodity, source, source_url,
               COUNT(*) AS n, MIN(date) AS d0, MAX(date) AS d1
        FROM commodity_price_history
        GROUP BY commodity, source, source_url
        ORDER BY commodity
        """
    ).fetchall()
    entries = []
    for r in rows:
        row = dict(r)
        label = COMMODITY_LABELS.get(row["commodity"], row["commodity"])
        if row["n"] == 1:
            # A single dated snapshot (e.g. the one real coking-coal price
            # point seeded before its full-history ingestion script has
            # been run) is not "monthly price history" -- say so plainly
            # rather than implying a series that doesn't exist yet.
            title = f"{label} — single dated snapshot"
            detail = (
                f"1 real cited data point ({row['d0']}) — not yet a monthly "
                "series; run data_pipeline/ingest_rba_coking_coal.py for "
                "the full history (see DECISIONS.md #23)."
            )
        else:
            title = f"{label} — monthly price history"
            detail = f"{row['n']} months, {row['d0']} to {row['d1']}"
        entries.append(
            _entry(
                title,
                "REAL",
                detail=detail,
                source=row["source"],
                source_url=row["source_url"],
            )
        )
    if not entries:
        entries.append(
            _entry(
                "Commodity price history",
                "REAL",
                detail=(
                    "No rows loaded yet in this database — see "
                    "docs/DECISIONS.md #12 for the ingestion pipeline."
                ),
            )
        )
    return entries


def _port_entries(conn) -> list:
    rows = conn.execute("SELECT * FROM ports ORDER BY port_id").fetchall()
    entries = []
    for r in rows:
        row = dict(r)
        entries.append(
            _entry(
                f"{row['name']} — draft / LOA / beam limits",
                "REAL" if row["verified"] else "ASSUMPTION",
                detail=row.get("berth_reference"),
                source=row.get("source"),
                source_url=row.get("source_url"),
                source_date=row.get("source_date"),
                verified=bool(row["verified"]),
            )
        )
    return entries


def _origin_port_entries(conn) -> list:
    rows = conn.execute("SELECT * FROM origin_ports ORDER BY origin_id").fetchall()
    entries = []
    for r in rows:
        row = dict(r)
        entries.append(
            _entry(
                f"{row['name']} — coordinates",
                "REAL",
                source=row.get("source"),
                source_url=row.get("source_url"),
            )
        )
    return entries


def _vessel_entries(conn) -> list:
    rows = conn.execute("SELECT * FROM vessel_classes ORDER BY vessel_type").fetchall()
    entries = []
    for r in rows:
        row = dict(r)
        entries.append(
            _entry(
                f"{row['vessel_type']} — dimensions, speed, fuel consumption",
                "ASSUMPTION",
                detail="Typical-class figures, not one specific registered hull.",
                source=row.get("source"),
                source_url=row.get("source_url"),
            )
        )
    return entries


def _voyage_cost_entries() -> list:
    rate_lines = ", ".join(f"{k} ${v:,}/day" for k, v in TIME_CHARTER_USD_PER_DAY.items())
    return [
        _entry(
            "Bunker fuel price (VLSFO, Singapore)",
            "ASSUMPTION",
            detail=(
                f"${BUNKER_PRICE_USD_PER_TONNE:,.2f}/tonne — a single cited "
                "snapshot, not a live feed."
            ),
            source=BUNKER_PRICE_SOURCE,
            source_url=BUNKER_PRICE_SOURCE_URL,
        ),
        _entry(
            "Time-charter day rates, by vessel class",
            "ASSUMPTION",
            detail=rate_lines,
            source=TIME_CHARTER_SOURCE,
            source_url=TIME_CHARTER_SOURCE_URL,
        ),
    ]


def _currency_entries() -> list:
    return [
        _entry(
            "USD -> INR display rate",
            "CALCULATED",
            detail=(
                f"1 USD = ₹{USD_TO_INR_RATE:.2f} — a single cited spot rate, "
                "not a live feed. USD stays the source-of-truth currency "
                "everywhere in this app; INR is shown only as a secondary "
                "figure alongside it, never in place of it. See "
                "DECISIONS.md #25."
            ),
            source=USD_TO_INR_SOURCE,
            source_url=USD_TO_INR_SOURCE_URL,
        ),
    ]


def _methodology_entries() -> list:
    return [
        _entry(
            "Voyage distance & sailing time",
            "CALCULATED",
            detail=(
                "Great-circle (haversine) distance through a small, "
                "hand-chosen set of open-ocean waypoints per origin region "
                "— not a certified routing engine or live AIS data. See "
                "app/engine/voyage.py."
            ),
        ),
        _entry(
            "Freight price forecast",
            "CALCULATED",
            detail=(
                "SARIMAX, fit on the real World Bank price history above, "
                "evaluated against a seasonal-naive baseline on a real "
                "holdout slice. See app/engine/forecast.py and "
                "DECISIONS.md #6, #13."
            ),
        ),
        _entry(
            "Vessel <-> port physical compatibility",
            "CALCULATED",
            detail=(
                "Direct arithmetic comparison of the REAL/ASSUMPTION vessel "
                "and port dimensions above — a hard gate, not a score. "
                "Reports 'unknown' rather than a false pass when a port "
                "dimension isn't on file. See app/engine/compatibility.py "
                "and DECISIONS.md #14."
            ),
        ),
        _entry(
            "Risk-adjusted cost ranking",
            "CALCULATED",
            detail=(
                "Composes the compatibility and voyage-cost figures above "
                "— the risk premium is the vessel's own physical clearance "
                "margin at the port, not a price-trend signal. See "
                "app/engine/optimizer.py and DECISIONS.md #16."
            ),
        ),
        _entry(
            "Book-now-vs-wait recommendation",
            "CALCULATED",
            detail=(
                "Reuses the freight price forecast above as-is (no second "
                "model) — compares the latest real price to the forecast "
                "at the chosen horizon. See app/engine/book_or_wait.py and "
                "DECISIONS.md #17."
            ),
        ),
    ]


def build_data_sources(conn) -> dict:
    """conn: a live db_session() connection (row_factory returning rows
    that support dict()). Reads current seeded data, so this always
    reflects what's actually in the database right now, not a fixed
    hand-written list."""
    return {
        "categories": [
            {
                "category": "Commodity prices",
                "entries": _commodity_price_entries(conn),
            },
            {
                "category": "East Coast India ports (destination)",
                "entries": _port_entries(conn),
            },
            {
                "category": "Overseas loading ports (origin)",
                "entries": _origin_port_entries(conn),
            },
            {
                "category": "Vessel class specifications",
                "entries": _vessel_entries(conn),
            },
            {
                "category": "Voyage cost inputs",
                "entries": _voyage_cost_entries(),
            },
            {
                "category": "Currency conversion",
                "entries": _currency_entries(),
            },
            {
                "category": (
                    "Calculated methodology (derived from the REAL/"
                    "ASSUMPTION data above — no separate external citation)"
                ),
                "entries": _methodology_entries(),
            },
        ]
    }
