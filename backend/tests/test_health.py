"""
Hour 0-2 smoke tests: the skeleton boots, the seed data loads, the two list
endpoints return what we seeded. Run with: pytest (from backend/).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    # TestClient must be used as a context manager for FastAPI's lifespan
    # (startup/shutdown) to actually run — otherwise the DB never gets seeded.
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_vessels_seeded(client):
    r = client.get("/api/v1/vessels")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 4
    types = {v["vessel_type"] for v in body}
    assert types == {"Handysize", "Supramax", "Panamax", "Capesize"}


def test_ports_seeded(client):
    r = client.get("/api/v1/ports")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    ids = {p["port_id"] for p in body}
    assert ids == {"VIZAG", "PARADIP", "DHAMRA"}


def test_vizag_confirmed_draft(client):
    r = client.get("/api/v1/ports/VIZAG")
    assert r.status_code == 200
    port = r.json()
    assert port["verified"] == 1
    assert port["max_draft_m"] == 18.1


def test_paradip_now_verified(client):
    # Paradip was provisional at Hour 0-2; confirmed with real KICT terminal
    # data (draft 17.1m, Capesize-capable to 165,000 DWT) during the Hour 2-5
    # data-pipeline block. This test flips along with that fix.
    r = client.get("/api/v1/ports/PARADIP")
    port = r.json()
    assert port["verified"] == 1
    assert port["max_draft_m"] == 17.1


def test_unknown_port_404(client):
    r = client.get("/api/v1/ports/NOPE")
    assert r.status_code == 404


def test_commodity_prices_seeded(client):
    r = client.get("/api/v1/commodity-prices")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 6  # 3 months x 2 commodities, the real starter snapshot
    commodities = {row["commodity"] for row in body}
    assert commodities == {"coal_australian", "crude_oil_brent"}


def test_commodity_prices_filter(client):
    r = client.get("/api/v1/commodity-prices?commodity=coal_australian")
    body = r.json()
    assert len(body) == 3
    assert all(row["commodity"] == "coal_australian" for row in body)
