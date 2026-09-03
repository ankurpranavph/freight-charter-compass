"""
Tests for app/engine/voyage.py (Module 5 -- Simulate).

Three layers:
- haversine_nm against a hand-checked distance (1 degree of longitude at
  the equator is ~60nm, a standard sanity check for any haversine impl).
- calculate_voyage() arithmetic against a synthetic vessel/origin/port
  with round numbers, checked by hand.
- API tests against the real seeded vessel/origin/port data. The real
  distances were sanity-checked against typical trade-press figures for
  these actual routes before this module was written (Newcastle-India
  ~6200nm, Richards Bay-India ~4300nm, Indonesia-India ~2900nm -- all
  within the ranges commonly quoted for these routes) -- see
  DECISIONS.md for the full writeup. Not re-asserted here since a
  statsmodels-style "shape and contract" check is more robust than
  pinning exact nm figures that would need updating if a waypoint is
  ever refined.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.engine.voyage import (
    BAY_OF_BENGAL_ENTRY,
    ROUTE_WAYPOINTS,
    TIME_CHARTER_USD_PER_DAY,
    calculate_voyage,
    haversine_nm,
    route_distance_nm,
)
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_haversine_one_degree_longitude_at_equator():
    # 1 degree of longitude at the equator is ~60 nautical miles by
    # definition of the nautical mile (1 nm = 1 arcminute of a great circle).
    d = haversine_nm(0.0, 0.0, 0.0, 1.0)
    assert d == pytest.approx(60.0, abs=0.5)


def test_haversine_same_point_is_zero():
    assert haversine_nm(12.3, 45.6, 12.3, 45.6) == 0.0


def test_route_distance_uses_known_origin_and_sums_legs():
    origin = {"origin_id": "TABONEO_ID", "lat": -3.70, "lon": 114.44}
    port = {"port_id": "TESTPORT", "lat": BAY_OF_BENGAL_ENTRY[0], "lon": BAY_OF_BENGAL_ENTRY[1]}
    # port placed exactly at the route's last waypoint -> distance should
    # equal the sum of legs up to (not including) the final zero-length leg
    waypoints = ROUTE_WAYPOINTS["TABONEO_ID"]
    expected = sum(
        haversine_nm(*waypoints[i], *waypoints[i + 1]) for i in range(len(waypoints) - 1)
    )
    assert route_distance_nm(origin, port) == pytest.approx(expected, rel=1e-9)


def test_route_distance_unknown_origin_raises():
    origin = {"origin_id": "NOT_A_REAL_ORIGIN", "lat": 0, "lon": 0}
    port = {"port_id": "TESTPORT", "lat": 10, "lon": 80}
    with pytest.raises(KeyError):
        route_distance_nm(origin, port)


def test_calculate_voyage_arithmetic_with_round_numbers():
    # Rig a vessel/origin/port so the great-circle distance is a clean,
    # hand-checkable number: 1 degree of latitude ~= 60nm, so 10 degrees
    # of latitude along the same meridian ~= 600nm.
    vessel = {
        "vessel_type": "Panamax",  # must be a real key in TIME_CHARTER_USD_PER_DAY
        "dwt_tonnes": 76000,
        "speed_knots": 10.0,  # chosen so 600nm / 10kn / 24h = 2.5 exact days
        "fuel_cons_tpd": 20.0,
    }
    origin = {"origin_id": "SYNTHETIC", "lat": 0.0, "lon": 0.0}
    port = {"port_id": "SYNTHETIC_PORT", "lat": 10.0, "lon": 0.0}

    # Monkeypatch a trivial direct route for this synthetic origin.
    import app.engine.voyage as voyage_mod

    voyage_mod.ROUTE_WAYPOINTS["SYNTHETIC"] = [(0.0, 0.0)]
    try:
        result = calculate_voyage(vessel, origin, port)
    finally:
        del voyage_mod.ROUTE_WAYPOINTS["SYNTHETIC"]

    # 10 degrees of latitude is ~600nm, not exactly 600nm on a spherical
    # mean-radius haversine (~600.4nm) -- assert the arithmetic RELATIONSHIP
    # from the actual computed distance, not an idealized round number,
    # since a tight absolute tolerance here was itself a bug (an earlier
    # version of this test failed on that ~0.4nm rounding cascading into a
    # ~$34 difference in charter hire -- a test-precision issue, not an
    # engine bug).
    assert result.distance_nm == pytest.approx(600.0, abs=1.0)
    expected_days = result.distance_nm / (10.0 * 24)
    assert result.voyage_days == pytest.approx(expected_days, rel=1e-9)
    expected_fuel_tonnes = expected_days * 20.0
    assert result.fuel_tonnes == pytest.approx(expected_fuel_tonnes, rel=1e-9)
    expected_fuel_cost = expected_fuel_tonnes * voyage_mod.BUNKER_PRICE_USD_PER_TONNE
    assert result.fuel_cost_usd == pytest.approx(expected_fuel_cost, rel=1e-6)
    expected_hire = expected_days * TIME_CHARTER_USD_PER_DAY["Panamax"]
    assert result.charter_hire_usd == pytest.approx(expected_hire, rel=1e-6)
    assert result.total_cost_usd == pytest.approx(
        result.fuel_cost_usd + result.charter_hire_usd, rel=1e-9
    )
    assert result.cargo_tonnes == 76000  # defaults to full DWT
    assert result.cost_per_tonne_usd == pytest.approx(
        result.total_cost_usd / 76000, rel=1e-9
    )


def test_calculate_voyage_respects_explicit_cargo_tonnes():
    vessel = {
        "vessel_type": "Handysize",
        "dwt_tonnes": 35000,
        "speed_knots": 10.0,
        "fuel_cons_tpd": 20.0,
    }
    origin = {"origin_id": "SYNTHETIC2", "lat": 0.0, "lon": 0.0}
    port = {"port_id": "SYNTHETIC_PORT", "lat": 5.0, "lon": 0.0}
    import app.engine.voyage as voyage_mod

    voyage_mod.ROUTE_WAYPOINTS["SYNTHETIC2"] = [(0.0, 0.0)]
    try:
        result = calculate_voyage(vessel, origin, port, cargo_tonnes=10000)
    finally:
        del voyage_mod.ROUTE_WAYPOINTS["SYNTHETIC2"]

    assert result.cargo_tonnes == 10000
    assert result.assumptions["cargo_tonnes_basis"] == "user-specified"


def test_calculate_voyage_unknown_vessel_type_raises():
    vessel = {"vessel_type": "NotARealClass", "dwt_tonnes": 1, "speed_knots": 10, "fuel_cons_tpd": 1}
    origin = {"origin_id": "TABONEO_ID", "lat": -3.70, "lon": 114.44}
    port = {"port_id": "TESTPORT", "lat": 10, "lon": 80}
    with pytest.raises(KeyError):
        calculate_voyage(vessel, origin, port)


# ---------------------------------------------------------------------
# API tests, real seeded data
# ---------------------------------------------------------------------

def test_origin_ports_endpoint(client):
    r = client.get("/api/v1/origin-ports")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    ids = {o["origin_id"] for o in body}
    assert ids == {"NEWCASTLE_AU", "RICHARDS_BAY_ZA", "TABONEO_ID"}


def test_voyage_calculate_real_route(client):
    r = client.get(
        "/api/v1/voyage/calculate",
        params={"vessel_type": "Panamax", "origin_id": "NEWCASTLE_AU", "port_id": "VIZAG"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["distance_nm"] > 0
    assert body["voyage_days"] > 0
    assert body["total_cost_usd"] == pytest.approx(
        body["fuel_cost_usd"] + body["charter_hire_usd"], rel=1e-6
    )
    assert body["cargo_tonnes"] > 0
    assert "assumptions" in body
    assert "bunker_price_source" in body["assumptions"]


def test_voyage_calculate_larger_vessel_has_lower_cost_per_tonne(client):
    # Real economies-of-scale check on the actual seeded data: a Capesize
    # should cost less per tonne than a Handysize over the same route.
    handysize = client.get(
        "/api/v1/voyage/calculate",
        params={"vessel_type": "Handysize", "origin_id": "NEWCASTLE_AU", "port_id": "VIZAG"},
    ).json()
    capesize = client.get(
        "/api/v1/voyage/calculate",
        params={"vessel_type": "Capesize", "origin_id": "NEWCASTLE_AU", "port_id": "VIZAG"},
    ).json()
    assert capesize["cost_per_tonne_usd"] < handysize["cost_per_tonne_usd"]


def test_voyage_calculate_unknown_vessel_404(client):
    r = client.get(
        "/api/v1/voyage/calculate",
        params={"vessel_type": "NotReal", "origin_id": "NEWCASTLE_AU", "port_id": "VIZAG"},
    )
    assert r.status_code == 404


def test_voyage_calculate_unknown_origin_404(client):
    r = client.get(
        "/api/v1/voyage/calculate",
        params={"vessel_type": "Panamax", "origin_id": "NOT_REAL", "port_id": "VIZAG"},
    )
    assert r.status_code == 404


def test_voyage_calculate_unknown_port_404(client):
    r = client.get(
        "/api/v1/voyage/calculate",
        params={"vessel_type": "Panamax", "origin_id": "NEWCASTLE_AU", "port_id": "NOPE"},
    )
    assert r.status_code == 404
