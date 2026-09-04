"""
Tests for port_traffic_history seeding and GET /api/v1/port-traffic.

Every row here is one individually-reported real coal-handling event
(a 24-hour discharge record, a single shipment, a berth record) -- never
a monthly aggregate. See schema.sql's table comment and DECISIONS.md #26
for why no real monthly series exists for these 6 ports through any
freely-accessible source. These tests check the shape and honesty of
what's seeded, not that it forms any kind of trend -- it deliberately
doesn't.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.connection import db_session
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_one_record_per_port_seeded(client):
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM port_traffic_history").fetchall()
    ports = {r["port_id"] for r in rows}
    assert ports == {"VIZAG", "PARADIP", "DHAMRA", "GANGAVARAM", "KRISHNAPATNAM", "HALDIA"}
    assert len(rows) == 6


def test_every_row_has_a_note_a_source_and_a_positive_volume(client):
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM port_traffic_history").fetchall()
    for r in rows:
        row = dict(r)
        assert row["note"], f"{row['port_id']} row is missing its 'what this measures' note"
        assert row["source"] and row["source_url"]
        assert row["volume_tonnes"] > 0


def test_rows_span_multiple_years_not_a_single_recent_month(client):
    # A real finding, not a bug: these are one-off records found via
    # research, not a series -- they should NOT all cluster in one
    # "current" month, which would misleadingly look like a real time
    # series if someone weren't reading the notes.
    with db_session() as conn:
        rows = conn.execute("SELECT month FROM port_traffic_history").fetchall()
    years = {r["month"][:4] for r in rows}
    assert len(years) > 1


def test_port_traffic_endpoint_returns_all_rows(client):
    r = client.get("/api/v1/port-traffic")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 6
    for row in body:
        assert "note" in row
        assert "source_url" in row


def test_port_traffic_endpoint_filters_by_port(client):
    r = client.get("/api/v1/port-traffic?port_id=vizag")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["port_id"] == "VIZAG"


def test_port_traffic_endpoint_unknown_port_returns_empty_not_404(client):
    # port_id here isn't validated against the ports table the way
    # vessel_type/origin_id are elsewhere -- an unknown or misspelled
    # port simply has no records, same honest "real port, nothing to
    # show" shape as GET /api/v1/optimize/HALDIA before Haldia had any
    # compatible options.
    r = client.get("/api/v1/port-traffic?port_id=NOPE")
    assert r.status_code == 200
    assert r.json() == []
