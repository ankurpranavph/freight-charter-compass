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


def test_paradip_flagged_unverified(client):
    r = client.get("/api/v1/ports/PARADIP")
    port = r.json()
    assert port["verified"] == 0, "Paradip figures are provisional and must stay flagged until Module 3"


def test_unknown_port_404(client):
    r = client.get("/api/v1/ports/NOPE")
    assert r.status_code == 404
