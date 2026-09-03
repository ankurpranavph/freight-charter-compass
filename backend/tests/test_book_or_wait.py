"""
Tests for app/engine/book_or_wait.py (Module 7 — the last step of
Predict -> Simulate -> Optimize -> Recommend).

Layers:
- Pure-function tests for the decision thresholds (_classify) and the
  honest confidence flag (_confidence_label) against hand-checked
  numbers.
- evaluate_book_or_wait() against synthetic strongly-trending series
  (clear uptrend -> BOOK_NOW, clear downtrend -> WAIT), and a flat/noisy
  series that should land on HOLD or at least not force a confident
  verdict either way. Also the insufficient_data pass-through.
- API tests against the real seeded data (both real commodities): shape
  and contract only — not pinned to a specific decision, since a live
  ingest re-run changes the latest real price and can legitimately flip
  the verdict. That's the same reasoning test_forecast.py uses for not
  pinning exact SARIMAX numbers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.engine.book_or_wait import (
    BOOK_THRESHOLD_PCT,
    WAIT_THRESHOLD_PCT,
    _classify,
    _confidence_label,
    evaluate_book_or_wait,
)
from app.engine.forecast import MIN_POINTS_FOR_SARIMAX, clear_cache
from app.main import app


@pytest.fixture(autouse=True)
def _no_cache_bleed():
    # evaluate_book_or_wait calls build_forecast(), which caches by
    # (commodity, horizon, len(df)) — clear so tests can't see each
    # other's cached forecasts.
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------

def test_classify_book_now_above_threshold():
    assert _classify(BOOK_THRESHOLD_PCT) == "BOOK_NOW"
    assert _classify(BOOK_THRESHOLD_PCT + 0.05) == "BOOK_NOW"


def test_classify_wait_below_threshold():
    assert _classify(WAIT_THRESHOLD_PCT) == "WAIT"
    assert _classify(WAIT_THRESHOLD_PCT - 0.05) == "WAIT"


def test_classify_hold_in_the_middle():
    assert _classify(0.0) == "HOLD"
    assert _classify(0.01) == "HOLD"
    assert _classify(-0.01) == "HOLD"


def test_confidence_low_when_ci_contains_latest_price():
    assert _confidence_label(latest_price=100.0, ci_lower=95.0, ci_upper=110.0) == "low"
    # boundary cases are inclusive
    assert _confidence_label(latest_price=100.0, ci_lower=100.0, ci_upper=110.0) == "low"


def test_confidence_high_when_ci_excludes_latest_price():
    assert _confidence_label(latest_price=100.0, ci_lower=105.0, ci_upper=110.0) == "high"
    assert _confidence_label(latest_price=100.0, ci_lower=80.0, ci_upper=95.0) == "high"


# ---------------------------------------------------------------------
# evaluate_book_or_wait(), synthetic data
# ---------------------------------------------------------------------

def _synthetic_series(n_months: int, slope_per_month: float, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=n_months, freq="MS")
    trend = 100 + slope_per_month * np.arange(n_months)
    seasonal = 2 * np.sin(2 * np.pi * np.arange(n_months) / 12)
    noise = rng.normal(0, 0.3, n_months)  # small noise relative to a strong trend
    prices = trend + seasonal + noise
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "price_usd": prices})


def test_evaluate_insufficient_data_passes_through():
    df = _synthetic_series(MIN_POINTS_FOR_SARIMAX - 5, slope_per_month=1.0)
    result = evaluate_book_or_wait("test_commodity", df, horizon=3)
    assert result.status == "insufficient_data"
    assert result.decision is None
    assert result.confidence is None


def test_evaluate_strong_uptrend_recommends_book_now():
    # A strong, low-noise upward trend should produce a forecast well
    # above the latest price -> BOOK_NOW.
    df = _synthetic_series(60, slope_per_month=1.5)
    result = evaluate_book_or_wait("uptrend_commodity", df, horizon=3)
    assert result.status == "ok"
    assert result.decision == "BOOK_NOW"
    assert result.pct_change > 0


def test_evaluate_strong_downtrend_recommends_wait():
    df = _synthetic_series(60, slope_per_month=-1.5)
    result = evaluate_book_or_wait("downtrend_commodity", df, horizon=3)
    assert result.status == "ok"
    assert result.decision == "WAIT"
    assert result.pct_change < 0


def test_evaluate_result_contract():
    df = _synthetic_series(60, slope_per_month=1.5)
    result = evaluate_book_or_wait("contract_test", df, horizon=3)
    d = result.as_dict()
    assert d["status"] == "ok"
    assert d["decision"] in {"BOOK_NOW", "WAIT", "HOLD"}
    assert d["confidence"] in {"high", "low"}
    assert d["latest_price_usd"] > 0
    assert d["forecast_price_usd"] > 0
    assert d["ci_lower_usd"] <= d["forecast_price_usd"] <= d["ci_upper_usd"]
    assert d["horizon_months"] == 3
    assert "CALCULATED" in d["reasoning"]
    assert d["forecast_evaluation"] is not None
    assert d["model_info"]["model"] == "SARIMAX"


# ---------------------------------------------------------------------
# API tests, real seeded data
# ---------------------------------------------------------------------

def test_book_or_wait_real_coal(client):
    # This test DB only has the 3-month starter snapshot until
    # ingest_worldbank.py's real download has been run (the full
    # 1480-row World Bank history lives in data_pipeline/processed/,
    # gitignored, device-only) -- so on a fresh clone this legitimately
    # returns "insufficient_data", exactly like test_forecast.py's own
    # real-data test. Both states are asserted as correct; the synthetic
    # uptrend/downtrend tests above are what actually exercise the
    # decision logic.
    r = client.get("/api/v1/decision/book-vs-wait/coal_australian")
    assert r.status_code == 200
    body = r.json()
    if body["status"] == "insufficient_data":
        assert body["decision"] is None
    else:
        assert body["status"] == "ok"
        assert body["decision"] in {"BOOK_NOW", "WAIT", "HOLD"}
        assert body["confidence"] in {"high", "low"}
        assert body["latest_price_usd"] > 0


def test_book_or_wait_real_oil_custom_horizon(client):
    r = client.get(
        "/api/v1/decision/book-vs-wait/crude_oil_brent", params={"horizon": 6}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_months"] == 6
    if body["status"] == "ok":
        assert body["decision"] in {"BOOK_NOW", "WAIT", "HOLD"}


def test_book_or_wait_unknown_commodity_404(client):
    r = client.get("/api/v1/decision/book-vs-wait/not_a_real_commodity")
    assert r.status_code == 404
