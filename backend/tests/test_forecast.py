"""
Tests for app/engine/forecast.py (Module 1 — Predict).

Two layers, deliberately kept separate:
- Pure-function tests (seasonal-naive, MAE/RMSE/MAPE) against hand-checked
  numbers — fast, no model fitting involved.
- build_forecast() end-to-end against a synthetic series long enough to
  exercise the real SARIMAX path, asserting shape/contract (status,
  fields present, forecast length, dates continue monthly) rather than
  exact numeric values — a statsmodels/scipy version bump can legitimately
  shift a fitted coefficient by a small amount without being a bug.

Real-data correctness (does the forecast look sane on the actual 1480-row
World Bank series) was checked manually against the user's real ingested
data before this module was written — see DECISIONS.md #13 for the actual
numbers (SARIMAX beat the seasonal-naive baseline on both commodities).
That real file isn't part of this repo (gitignored, device-only), so it
can't be a test fixture here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from app.engine.forecast import (
    MIN_POINTS_FOR_SARIMAX,
    _evaluate,
    _seasonal_naive_forecast,
    build_forecast,
    clear_cache,
)


@pytest.fixture(autouse=True)
def _no_cache_bleed():
    # build_forecast caches by (commodity, horizon, len(df)) — clear before
    # and after each test so tests can't see each other's cached results.
    clear_cache()
    yield
    clear_cache()


def test_seasonal_naive_full_season():
    train = np.array([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21], dtype=float)
    forecast = _seasonal_naive_forecast(train, steps=3, season_length=12)
    # steps 1-3 ahead should reuse the first 3 values of the last season
    assert list(forecast) == [10, 11, 12]


def test_seasonal_naive_wraps_for_long_horizon():
    train = np.array([10, 11, 12, 13], dtype=float)  # shorter than season_length
    forecast = _seasonal_naive_forecast(train, steps=3, season_length=12)
    # not a full season available -> flat last-value fallback
    assert list(forecast) == [13, 13, 13]


def test_evaluate_perfect_prediction_is_zero_error():
    actual = np.array([100.0, 110.0, 120.0])
    metrics = _evaluate(actual, actual.copy())
    assert metrics.mae == 0
    assert metrics.rmse == 0
    assert metrics.mape == 0


def test_evaluate_known_errors():
    actual = np.array([100.0, 200.0])
    predicted = np.array([110.0, 180.0])  # errors: -10, +20
    metrics = _evaluate(actual, predicted)
    assert metrics.mae == pytest.approx(15.0)
    assert metrics.rmse == pytest.approx(np.sqrt((100 + 400) / 2))
    # MAPE = mean(|error| / |actual|) * 100 = mean(0.10, 0.10) * 100
    assert metrics.mape == pytest.approx(10.0)


def _synthetic_series(n_months: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=n_months, freq="MS")
    trend = np.linspace(100, 130, n_months)
    seasonal = 5 * np.sin(2 * np.pi * np.arange(n_months) / 12)
    noise = rng.normal(0, 1, n_months)
    prices = trend + seasonal + noise
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "price_usd": prices})


def test_build_forecast_insufficient_data():
    df = _synthetic_series(MIN_POINTS_FOR_SARIMAX - 5)
    result = build_forecast("test_commodity", df, horizon=6, use_cache=False)
    assert result.status == "insufficient_data"
    assert result.forecast == []
    assert result.evaluation is None
    assert len(result.historical) == MIN_POINTS_FOR_SARIMAX - 5


def test_insufficient_data_note_is_honest_and_user_facing():
    # The insufficient_data note is shown as-is on both the Forecast page
    # and the Recommendation page's timing cards (DECISIONS.md #29) --
    # it must state the real month count plainly, without naming an
    # internal script path (that used to leak "Run
    # data_pipeline/ingest_rba_coking_coal.py" straight into the UI).
    df = _synthetic_series(1)
    result = build_forecast("coking_coal", df, horizon=6, use_cache=False)
    assert result.status == "insufficient_data"
    assert "1 real month" in result.note
    assert "coking coal" in result.note
    assert "ingest_" not in result.note
    assert ".py" not in result.note

    result2 = build_forecast("coal_australian", df, horizon=6, use_cache=False)
    assert "coal australian" in result2.note
    assert "ingest_" not in result2.note


def test_build_forecast_ok_path_shape_and_contract():
    df = _synthetic_series(60)  # 5 years, well above MIN_POINTS_FOR_SARIMAX
    result = build_forecast("test_commodity", df, horizon=6, use_cache=False)

    assert result.status == "ok"
    assert len(result.historical) == 60
    assert len(result.forecast) == 6

    # forecast dates continue monthly straight from the last historical date
    last_hist_date = pd.Timestamp(result.historical[-1]["date"])
    first_fc_date = pd.Timestamp(result.forecast[0]["date"])
    assert first_fc_date == last_hist_date + pd.DateOffset(months=1)
    for i in range(1, len(result.forecast)):
        prev = pd.Timestamp(result.forecast[i - 1]["date"])
        cur = pd.Timestamp(result.forecast[i]["date"])
        assert cur == prev + pd.DateOffset(months=1)

    for point in result.forecast:
        assert point["ci_lower"] <= point["forecast_price_usd"] <= point["ci_upper"]

    assert result.evaluation is not None
    assert "mae" in result.evaluation["baseline_seasonal_naive"]
    assert "mae" in result.evaluation["sarimax"]
    assert result.evaluation["holdout_months"] > 0

    assert result.model_info["model"] == "SARIMAX"
    assert result.model_info["order"]
    assert result.model_info["seasonal_order"]
    assert result.model_info["trained_on_months"] == 60


def test_build_forecast_uses_cache(monkeypatch):
    df = _synthetic_series(60)
    first = build_forecast("cache_test", df, horizon=6, use_cache=True)
    # Corrupt the module's private fit function so a second real fit would
    # raise — if the cache isn't hit, this call blows up.
    import app.engine.forecast as forecast_mod

    def _boom(*a, **k):
        raise AssertionError("should not re-fit — cache should have been used")

    monkeypatch.setattr(forecast_mod, "_select_best_order", _boom)
    second = build_forecast("cache_test", df, horizon=6, use_cache=True)
    assert second is first
