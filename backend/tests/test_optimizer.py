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
    _risk_multiplier,
    _tightest_margin_ratio,
    rank_options,
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
