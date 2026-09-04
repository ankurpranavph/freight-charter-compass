"""
Tests for app/engine/optimizer.py (Module 6 — Optimize).

Layers:
- Unit tests for the risk-margin math (_tightest_margin_ratio,
  _risk_multiplier) against hand-checked numbers.
- rank_options() against synthetic vessels/ports, covering: incompatible
  vessels excluded entirely, ascending sort by risk-adjusted cost, and
  cargo_tonnes exceeding a vessel's DWT excluding that vessel.
- API tests against the real seeded data. Verified by hand-running the
  engine before writing this module (see DECISIONS.md): at Vizag,
  Capesize's razor-thin 0.56% draft margin (18.1m limit vs 18.0m vessel)
  earns it the full risk penalty, yet it STILL ranks #1 overall (the
  short Indonesia route dominates) — a real, not cherry-picked, result.
  At Paradip, Capesize is entirely absent (fails Module 4's gate, not
  merely penalized) — exactly 3 vessels x 3 origins = 9 options.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.engine.optimizer import (
    MAX_RISK_PENALTY,
    SAFE_MARGIN_RATIO,
    CargoExceedsCapacityError,
    _risk_multiplier,
    _tightest_margin_ratio,
    rank_options,
    rank_ports_for_vessel,
)
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------
# Risk-margin math, unit tests
# ---------------------------------------------------------------------

def test_tightest_margin_ratio_picks_the_smallest():
    checks = [
        {"dimension": "draft", "status": "ok", "vessel_value": 18.0, "margin_m": 0.1},   # 0.56%
        {"dimension": "loa", "status": "ok", "vessel_value": 292.0, "margin_m": 8.0},     # 2.74%
        {"dimension": "beam", "status": "ok", "vessel_value": 45.0, "margin_m": 5.0},     # 11.1%
    ]
    ratio = _tightest_margin_ratio(checks)
    assert ratio == pytest.approx(0.1 / 18.0)


def test_tightest_margin_ratio_none_when_any_unknown():
    checks = [
        {"dimension": "draft", "status": "ok", "vessel_value": 18.0, "margin_m": 5.0},
        {"dimension": "loa", "status": "unknown", "vessel_value": 292.0, "margin_m": None},
    ]
    assert _tightest_margin_ratio(checks) is None


def test_risk_multiplier_no_penalty_above_safe_threshold():
    assert _risk_multiplier(SAFE_MARGIN_RATIO) == 1.0
    assert _risk_multiplier(SAFE_MARGIN_RATIO * 2) == 1.0


def test_risk_multiplier_max_penalty_at_zero_margin():
    assert _risk_multiplier(0.0) == pytest.approx(1.0 + MAX_RISK_PENALTY)


def test_risk_multiplier_unknown_treated_as_max_caution():
    assert _risk_multiplier(None) == pytest.approx(1.0 + MAX_RISK_PENALTY)


def test_risk_multiplier_scales_linearly_between():
    half_safe = SAFE_MARGIN_RATIO / 2
    mult = _risk_multiplier(half_safe)
    assert mult == pytest.approx(1.0 + 0.5 * MAX_RISK_PENALTY)


# ---------------------------------------------------------------------
# rank_options(), synthetic data
# ---------------------------------------------------------------------

GENEROUS_PORT = {
    "port_id": "TESTPORT", "lat": 10.0, "lon": 80.0,
    "max_draft_m": 20.0, "max_loa_m": 300.0, "max_beam_m": 50.0, "coal_handling": 1,
}
SMALL_VESSEL = {
    "vessel_type": "Handysize", "dwt_tonnes": 35000, "draft_m": 10.0, "loa_m": 180.0,
    "beam_m": 30.0, "speed_knots": 13.5, "fuel_cons_tpd": 20.0,
}
BIG_VESSEL = {
    "vessel_type": "Capesize", "dwt_tonnes": 180000, "draft_m": 18.0, "loa_m": 292.0,
    "beam_m": 45.0, "speed_knots": 14.0, "fuel_cons_tpd": 38.0,
}
TOO_DEEP_VESSEL = {
    "vessel_type": "Panamax", "dwt_tonnes": 76000, "draft_m": 25.0, "loa_m": 225.0,
    "beam_m": 32.3, "speed_knots": 14.0, "fuel_cons_tpd": 28.0,
}
ORIGIN = {"origin_id": "TABONEO_ID", "lat": -3.70, "lon": 114.44}


def test_rank_options_excludes_incompatible_vessels():
    ranked = rank_options(GENEROUS_PORT, [SMALL_VESSEL, TOO_DEEP_VESSEL], [ORIGIN])
    assert len(ranked) == 1
    assert ranked[0].vessel_type == "Handysize"


def test_rank_options_sorted_ascending_by_risk_adjusted_cost():
    ranked = rank_options(GENEROUS_PORT, [SMALL_VESSEL, BIG_VESSEL], [ORIGIN])
    costs = [o.risk_adjusted_cost_per_tonne_usd for o in ranked]
    assert costs == sorted(costs)


def test_rank_options_excludes_vessel_smaller_than_fixed_cargo():
    # SMALL_VESSEL's DWT is 35000 — a 50000t fixed cargo should exclude it
    ranked = rank_options(GENEROUS_PORT, [SMALL_VESSEL, BIG_VESSEL], [ORIGIN], cargo_tonnes=50000)
    types = {o.vessel_type for o in ranked}
    assert "Handysize" not in types
    assert "Capesize" in types


# ---------------------------------------------------------------------
# rank_ports_for_vessel(), synthetic data — the mirrored direction
# ---------------------------------------------------------------------

TIGHT_PORT = {
    "port_id": "TIGHTPORT", "lat": 12.0, "lon": 81.0,
    "max_draft_m": 12.0, "max_loa_m": 200.0, "max_beam_m": 32.0, "coal_handling": 1,
}


def test_rank_ports_for_vessel_returns_compatible_and_incompatible():
    compatible, incompatible = rank_ports_for_vessel(
        BIG_VESSEL, ORIGIN, [GENEROUS_PORT, TIGHT_PORT]
    )
    assert len(compatible) == 1
    assert compatible[0].port_id == "TESTPORT"
    assert len(incompatible) == 1
    assert incompatible[0]["port_id"] == "TIGHTPORT"
    assert incompatible[0]["compatible"] is False
    assert incompatible[0]["reasons"]  # never dropped silently — reasons are present


def test_rank_ports_for_vessel_sorted_ascending_by_risk_adjusted_cost():
    compatible, _incompatible = rank_ports_for_vessel(
        SMALL_VESSEL, ORIGIN, [GENEROUS_PORT, TIGHT_PORT]
    )
    costs = [o.risk_adjusted_cost_per_tonne_usd for o in compatible]
    assert costs == sorted(costs)


def test_rank_ports_for_vessel_raises_on_cargo_exceeding_dwt():
    # SMALL_VESSEL's DWT is 35000 — a 50000t fixed cargo exceeds it at
    # every port, so this is checked once up front, not per-port.
    with pytest.raises(CargoExceedsCapacityError):
        rank_ports_for_vessel(SMALL_VESSEL, ORIGIN, [GENEROUS_PORT], cargo_tonnes=50000)


def test_rank_ports_for_vessel_no_ports_compatible():
    # A vessel too big for every port on offer: compatible is empty,
    # incompatible carries all of them with real reasons — never a crash
    # or a silently-empty response with no explanation.
    compatible, incompatible = rank_ports_for_vessel(TOO_DEEP_VESSEL, ORIGIN, [TIGHT_PORT])
    assert compatible == []
    assert len(incompatible) == 1


# ---------------------------------------------------------------------
# API tests, real seeded data
# ---------------------------------------------------------------------

def test_optimize_vizag_includes_capesize_with_risk_penalty(client):
    r = client.get("/api/v1/optimize/VIZAG")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 12  # 4 vessels x 3 origins, all compatible at Vizag

    capesize_options = [o for o in body if o["vessel_type"] == "Capesize"]
    assert len(capesize_options) == 3
    for opt in capesize_options:
        assert opt["risk_multiplier"] > 1.0
        assert opt["tightest_margin_ratio_pct"] < 1.0  # the ~0.56% draft margin

    # ranks are 1-indexed and strictly ascending by risk-adjusted cost
    ranks = [o["rank"] for o in body]
    assert ranks == list(range(1, len(body) + 1))
    costs = [o["risk_adjusted_cost_per_tonne_usd"] for o in body]
    assert costs == sorted(costs)


def test_optimize_paradip_excludes_capesize_entirely(client):
    r = client.get("/api/v1/optimize/PARADIP")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 9  # 3 compatible vessels x 3 origins
    assert all(o["vessel_type"] != "Capesize" for o in body)


def test_optimize_unknown_port_404(client):
    r = client.get("/api/v1/optimize/NOPE")
    assert r.status_code == 404


def test_optimize_gangavaram_max_risk_penalty_at_exact_boundary(client):
    # Gangavaram's coal berths cap out at exactly 18.0m draft -- the same
    # figure as the Capesize class's own draft, an exact 0.0m margin (see
    # test_compatibility.py). All 4 vessel classes still clear every
    # dimension, so all 12 combinations are ranked, but Capesize's
    # razor-thin draft margin should earn it the optimizer's MAX risk
    # penalty (15%), same mechanics as Vizag's own near-zero-margin case.
    r = client.get("/api/v1/optimize/GANGAVARAM")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 12  # 4 vessels x 3 origins, all compatible

    capesize_options = [o for o in body if o["vessel_type"] == "Capesize"]
    assert len(capesize_options) == 3
    for opt in capesize_options:
        assert opt["tightest_margin_ratio_pct"] == 0.0
        assert opt["risk_multiplier"] == 1.15  # 1.0 + MAX_RISK_PENALTY at 0 margin


def test_optimize_krishnapatnam_all_compatible(client):
    # Krishnapatnam clears Capesize on every dimension (18.5m draft vs 18.0m
    # vessel, 300m LOA vs 292m, 48m beam vs 45m) -- real margins on all
    # three, tightest is LOA at ~2.7% (300-292=8m spare / 292m vessel), still
    # under the optimizer's 10% safe-margin threshold so it still carries a
    # real, non-maximum risk penalty, unlike Gangavaram's exact-boundary
    # (0.0m draft margin) case which hits the max.
    r = client.get("/api/v1/optimize/KRISHNAPATNAM")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 12  # 4 vessels x 3 origins, all compatible

    capesize_options = [o for o in body if o["vessel_type"] == "Capesize"]
    assert len(capesize_options) == 3
    for opt in capesize_options:
        assert 0.0 < opt["tightest_margin_ratio_pct"] < 10.0
        assert 1.0 < opt["risk_multiplier"] < 1.15


def test_optimize_haldia_returns_no_options(client):
    # Haldia's 9.1m tidal-channel draft excludes every one of the 4 modeled
    # vessel classes (see test_compatibility.py) -- the first real,
    # verified port in this dataset where the optimizer legitimately has
    # nothing to rank. A real finding, not a bug: 200 with an empty list,
    # never a 404 (the port itself is real and known) or a crash.
    r = client.get("/api/v1/optimize/HALDIA")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------
# /api/v1/optimize/by-vessel — mirrored direction, real seeded data.
# Verified by hand-running the endpoint before writing these assertions
# (see DECISIONS.md): a Capesize out of Newcastle clears exactly 3 of the
# 6 ports (Krishnapatnam, Vizag, Gangavaram — the same three that clear
# it in the port-first direction) and fails the other 3, each for a real,
# distinct reason; a Handysize out of Taboneo with a 20,000t fixed cargo
# clears 5 of 6, failing only at Haldia's 9.1m draft limit.
# ---------------------------------------------------------------------

def test_optimize_by_vessel_capesize_newcastle_splits_3_and_3(client):
    r = client.get("/api/v1/optimize/by-vessel?vessel_type=Capesize&origin_id=NEWCASTLE_AU")
    assert r.status_code == 200
    body = r.json()
    assert body["vessel_type"] == "Capesize"
    assert body["origin_id"] == "NEWCASTLE_AU"

    compat_ids = [p["port_id"] for p in body["compatible_ports"]]
    assert compat_ids == ["KRISHNAPATNAM", "VIZAG", "GANGAVARAM"]  # rank order, cheapest first
    ranks = [p["rank"] for p in body["compatible_ports"]]
    assert ranks == [1, 2, 3]

    incompat_ids = {p["port_id"] for p in body["incompatible_ports"]}
    assert incompat_ids == {"PARADIP", "DHAMRA", "HALDIA"}
    for entry in body["incompatible_ports"]:
        assert entry["compatible"] is False
        assert entry["reasons"]  # every exclusion is explained, never silent


def test_optimize_by_vessel_handysize_taboneo_custom_cargo(client):
    r = client.get(
        "/api/v1/optimize/by-vessel?vessel_type=Handysize&origin_id=TABONEO_ID&cargo_tonnes=20000"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cargo_tonnes"] == 20000.0

    compat_ids = [p["port_id"] for p in body["compatible_ports"]]
    assert len(compat_ids) == 5
    incompat_ids = [p["port_id"] for p in body["incompatible_ports"]]
    assert incompat_ids == ["HALDIA"]  # only port Handysize's 10.0m draft can't clear

    # every voyage in the response actually used the user's 20,000t figure,
    # not the vessel's full DWT
    for opt in body["compatible_ports"]:
        assert opt["voyage"]["cargo_tonnes"] == 20000.0
        assert opt["voyage"]["assumptions"]["cargo_tonnes_basis"] == "user-specified"


def test_optimize_by_vessel_unknown_vessel_404(client):
    r = client.get("/api/v1/optimize/by-vessel?vessel_type=Nope&origin_id=NEWCASTLE_AU")
    assert r.status_code == 404


def test_optimize_by_vessel_unknown_origin_404(client):
    r = client.get("/api/v1/optimize/by-vessel?vessel_type=Capesize&origin_id=NOPE")
    assert r.status_code == 404


def test_optimize_by_vessel_cargo_exceeds_dwt_422(client):
    r = client.get(
        "/api/v1/optimize/by-vessel?vessel_type=Handysize&origin_id=NEWCASTLE_AU&cargo_tonnes=999999"
    )
    assert r.status_code == 422
    assert "35,000t DWT" in r.json()["detail"]


def test_optimize_by_vessel_route_registered_ahead_of_port_id(client):
    # /api/v1/optimize/{port_id} is registered right after this route —
    # confirms "by-vessel" is never swallowed as a port_id and 404'd.
    r = client.get("/api/v1/optimize/by-vessel?vessel_type=Capesize&origin_id=NEWCASTLE_AU")
    assert r.status_code == 200
    assert "compatible_ports" in r.json()
