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
    assert len(body) == 6
    ids = {p["port_id"] for p in body}
    assert ids == {"VIZAG", "PARADIP", "DHAMRA", "GANGAVARAM", "KRISHNAPATNAM", "HALDIA"}


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


def test_gangavaram_verified(client):
    # Added at the Hour 27-29 checkpoint (ports 4-6). Draft sourced from
    # Adani Gangavaram's own Berthing Policy & Tariff Structure document.
    r = client.get("/api/v1/ports/GANGAVARAM")
    port = r.json()
    assert port["verified"] == 1
    assert port["max_draft_m"] == 18.0


def test_krishnapatnam_verified(client):
    r = client.get("/api/v1/ports/KRISHNAPATNAM")
    port = r.json()
    assert port["verified"] == 1
    assert port["max_draft_m"] == 18.5


def test_haldia_verified_but_shallow(client):
    # Haldia is a real, verified, coal-handling port -- but its tidal channel
    # tops out at 9.1m draft, below even the smallest modeled vessel class
    # (Handysize, 10.0m). coal_handling stays true (it genuinely does handle
    # coal); the draft limit is what excludes every class here, not a
    # mislabeled flag. See test_compatibility.py for the resulting matrix.
    r = client.get("/api/v1/ports/HALDIA")
    port = r.json()
    assert port["verified"] == 1
    assert port["coal_handling"] == 1
    assert port["max_draft_m"] == 9.1


def test_unknown_port_404(client):
    r = client.get("/api/v1/ports/NOPE")
    assert r.status_code == 404


def test_commodity_prices_seeded(client):
    # Whether this seeds just the starter snapshot or the full ~1480-row
    # World Bank history (and, once run for real, the RBA coking-coal
    # history too) depends on which data_pipeline/processed/*.csv files
    # exist locally (both gitignored — present once their ingest_*.py
    # script has been run for real, absent on a fresh clone) -- seed.py
    # layers whichever are present on top of the starter snapshot, per its
    # docstring. All of these are correct outcomes; assert the invariant
    # that holds either way rather than a fixed row count.
    r = client.get("/api/v1/commodity-prices")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 7  # at least the starter snapshot (3+3+1)
    commodities = {row["commodity"] for row in body}
    assert commodities == {"coal_australian", "crude_oil_brent", "coking_coal"}


def test_commodity_prices_filter(client):
    r = client.get("/api/v1/commodity-prices?commodity=coal_australian")
    body = r.json()
    assert len(body) >= 3  # at least the 3-month starter snapshot
    assert all(row["commodity"] == "coal_australian" for row in body)


def test_forecast_unknown_commodity_404(client):
    r = client.get("/api/v1/forecast/not_a_real_commodity")
    assert r.status_code == 404


def test_forecast_insufficient_data_with_starter_snapshot(client):
    # This test DB only has the 3-month starter snapshot before you run
    # ingest_worldbank.py's real download (the full 1480-row World Bank
    # history lives in data_pipeline/processed/, gitignored) -- so this
    # exercises the "not enough history yet" contract, not a real SARIMAX
    # fit. See test_forecast.py for the full model-fitting path against a
    # synthetic long series, and try GET /api/v1/forecast/coal_australian
    # yourself once the real history is loaded -- it'll return status: "ok".
    r = client.get("/api/v1/forecast/coal_australian")
    assert r.status_code == 200
    body = r.json()
    if body["status"] == "insufficient_data":
        assert body["forecast"] == []
    else:
        # if you've already run the real ingestion, the full history is
        # loaded and this legitimately returns a real forecast instead.
        assert body["status"] == "ok"
        assert len(body["forecast"]) > 0


def test_coking_coal_forecast_insufficient_data(client):
    # Unlike coal_australian/crude_oil_brent, coking_coal has exactly 1
    # real seeded row (a single dated snapshot, DECISIONS.md #23) until the
    # user runs ingest_rba_coking_coal.py for the real full RBA history --
    # this is deterministic, not conditional on local processed-CSV state.
    r = client.get("/api/v1/forecast/coking_coal")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "insufficient_data"
    assert body["forecast"] == []
    assert "ingest_rba_coking_coal.py" in body["note"]


def test_data_sources_endpoint(client):
    r = client.get("/api/v1/data-sources")
    assert r.status_code == 200
    body = r.json()
    assert len(body["categories"]) == 7
    all_labels = [e["label"] for cat in body["categories"] for e in cat["entries"]]
    assert any("Vizag" in l or "Visakhapatnam" in l for l in all_labels)
