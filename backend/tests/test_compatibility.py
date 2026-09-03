"""
Tests for app/engine/compatibility.py (Module 4 -- the physical gate).

Two layers:
- Unit tests against synthetic vessel/port dicts, covering full pass, a
  single-dimension failure, a missing-data ("unknown") dimension, and a
  non-coal-handling port.
- API tests against the REAL seeded vessel/port data (cheap -- this is
  pure arithmetic, no model fitting, so there's no reason to fake it).
  The real numbers produce a genuine, demo-worthy finding: Capesize
  (draft 18.0m, LOA 292m) is the only vessel class that doesn't fit
  everywhere. It clears Visakhapatnam (18.1m draft, 300m LOA) with room
  to spare, but fails at Paradip on BOTH draft (17.1m max, 0.9m short)
  and LOA (290m max, 2m over), and fails at Dhamra on LOA alone -- Dhamra's
  max draft is exactly 18.0m, an exact-limit boundary case that correctly
  counts as fitting (margin 0), not failing. These numbers were verified
  against ports.json/vessels.json by running the test, not by hand-math --
  an initial hand-calculated assertion here was itself wrong (missed that
  Paradip's draft also fails), which is exactly the kind of mistake this
  test suite exists to catch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.engine.compatibility import build_matrix, check_compatibility
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------
# Unit tests, synthetic data
# ---------------------------------------------------------------------

FITS_EVERYTHING_VESSEL = {"vessel_type": "TinyBoat", "draft_m": 5.0, "loa_m": 100.0, "beam_m": 15.0}
GENEROUS_PORT = {
    "port_id": "TESTPORT",
    "max_draft_m": 20.0,
    "max_loa_m": 300.0,
    "max_beam_m": 50.0,
    "coal_handling": 1,
}


def test_fully_compatible():
    result = check_compatibility(FITS_EVERYTHING_VESSEL, GENEROUS_PORT)
    assert result.compatible is True
    assert result.reasons == []
    assert all(c["status"] == "ok" for c in result.checks)


def test_draft_failure_reported_with_margin():
    vessel = {**FITS_EVERYTHING_VESSEL, "draft_m": 25.0}  # exceeds port's 20.0
    result = check_compatibility(vessel, GENEROUS_PORT)
    assert result.compatible is False
    draft_check = next(c for c in result.checks if c["dimension"] == "draft")
    assert draft_check["status"] == "fail"
    assert draft_check["margin_m"] == -5.0
    assert any("draft" in r for r in result.reasons)


def test_exact_limit_is_compatible_not_a_failure():
    # margin == 0 should count as fitting, not failing (boundary case)
    vessel = {**FITS_EVERYTHING_VESSEL, "loa_m": 300.0}  # exactly the port's max
    result = check_compatibility(vessel, GENEROUS_PORT)
    loa_check = next(c for c in result.checks if c["dimension"] == "loa")
    assert loa_check["status"] == "ok"
    assert loa_check["margin_m"] == 0.0


def test_missing_port_dimension_is_unknown_not_compatible():
    port = {**GENEROUS_PORT, "max_beam_m": None}
    result = check_compatibility(FITS_EVERYTHING_VESSEL, port)
    assert result.compatible is False
    beam_check = next(c for c in result.checks if c["dimension"] == "beam")
    assert beam_check["status"] == "unknown"
    assert any("no recorded beam limit" in r for r in result.reasons)


def test_non_coal_handling_port_is_incompatible():
    port = {**GENEROUS_PORT, "coal_handling": 0}
    result = check_compatibility(FITS_EVERYTHING_VESSEL, port)
    assert result.compatible is False
    assert any("not flagged as a coal-handling port" in r for r in result.reasons)


def test_build_matrix_covers_every_combination():
    vessels = [FITS_EVERYTHING_VESSEL, {**FITS_EVERYTHING_VESSEL, "vessel_type": "BigBoat", "draft_m": 25.0}]
    ports = [GENEROUS_PORT, {**GENEROUS_PORT, "port_id": "OTHERPORT"}]
    matrix = build_matrix(vessels, ports)
    assert len(matrix) == 4  # 2 vessels x 2 ports
    pairs = {(m["vessel_type"], m["port_id"]) for m in matrix}
    assert pairs == {
        ("TinyBoat", "TESTPORT"), ("TinyBoat", "OTHERPORT"),
        ("BigBoat", "TESTPORT"), ("BigBoat", "OTHERPORT"),
    }


# ---------------------------------------------------------------------
# API tests, real seeded vessel/port data
# ---------------------------------------------------------------------

def test_matrix_endpoint_real_data(client):
    r = client.get("/api/v1/compatibility/matrix")
    assert r.status_code == 200
    matrix = r.json()
    assert len(matrix) == 12  # 4 vessel classes x 3 ports

    failures = {(m["vessel_type"], m["port_id"]): m for m in matrix if not m["compatible"]}
    assert set(failures) == {("Capesize", "PARADIP"), ("Capesize", "DHAMRA")}

    # Paradip: Capesize fails on BOTH draft (17.1m max vs 18.0m vessel) and
    # LOA (290m max vs 292m vessel).
    paradip_reasons = " ".join(failures[("Capesize", "PARADIP")]["reasons"]).lower()
    assert "draft" in paradip_reasons
    assert "loa" in paradip_reasons
    assert len(failures[("Capesize", "PARADIP")]["reasons"]) == 2

    # Dhamra: max draft is exactly 18.0m (Capesize's draft) -- an exact
    # boundary that counts as fitting, so only LOA fails here.
    dhamra_reasons = failures[("Capesize", "DHAMRA")]["reasons"]
    assert len(dhamra_reasons) == 1
    assert "loa" in dhamra_reasons[0].lower()


def test_check_endpoint_real_compatible_pair(client):
    r = client.get("/api/v1/compatibility/check?vessel_type=Handysize&port_id=VIZAG")
    assert r.status_code == 200
    body = r.json()
    assert body["compatible"] is True
    assert body["reasons"] == []


def test_check_endpoint_real_incompatible_pair(client):
    r = client.get("/api/v1/compatibility/check?vessel_type=Capesize&port_id=PARADIP")
    assert r.status_code == 200
    body = r.json()
    assert body["compatible"] is False
    # fails on both draft and LOA at Paradip -- see module docstring above
    assert len(body["reasons"]) == 2
    reasons_lower = " ".join(body["reasons"]).lower()
    assert "draft" in reasons_lower
    assert "loa" in reasons_lower


def test_check_endpoint_unknown_vessel_404(client):
    r = client.get("/api/v1/compatibility/check?vessel_type=NotARealVessel&port_id=VIZAG")
    assert r.status_code == 404


def test_check_endpoint_unknown_port_404(client):
    r = client.get("/api/v1/compatibility/check?vessel_type=Handysize&port_id=NOPE")
    assert r.status_code == 404
