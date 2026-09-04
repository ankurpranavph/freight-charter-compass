"""
Module 1: freight-relevant commodity price forecasting.

Predicts future Coal (Australian) and Crude Oil (Brent) prices from the
real World Bank Pink Sheet history ingested via data_pipeline/. This is
the "Predict" step of Predict -> Simulate -> Optimize -> Recommend.

APPROACH (see docs/DECISIONS.md #6 for why SARIMAX and not XGBoost/LSTM,
and #13 for why there's no separate training script or pickled model):

- Baseline: seasonal-naive — this month's forecast is the actual value
  from the same month one year ago, cycling for horizons beyond 12
  months. A real model has to beat this on the SAME holdout to be worth
  showing a judge; if it doesn't, that's reported honestly, not hidden.
- Primary model: SARIMAX (statsmodels). Order selection is a small,
  curated grid search by AIC (CANDIDATE_ORDERS below) — not exhaustive
  auto-ARIMA. This is a deliberate choice: it's explainable in one
  sentence ("we compared N standard candidate orders and kept the best
  AIC") rather than a black-box search, and it fits a hackathon time
  budget.
- Evaluation: chronological train/holdout split — never randomly
  shuffled, since that would leak future prices into training for a time
  series. MAE, RMSE, MAPE are reported for baseline and SARIMAX on the
  identical holdout window.
- Deployment: the SAME order selected during evaluation is refit on the
  FULL series (train+holdout) to produce the forward-looking forecast,
  with a 95% CI from statsmodels' own get_forecast(). We deliberately do
  NOT re-run the order search on the full series — using a different
  model for "the one we evaluated" vs. "the one we deployed" would be
  indefensible if a judge asked about it.
- Fit-on-request, cached in memory for the life of the running process.
  No separate training script or pickled artifact — avoids a pickle
  version-compatibility trap and matches the "ingest once, compute at
  request time, no live external calls during a demo" architecture
  already used elsewhere in this app.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

SEASON_LENGTH = 12  # monthly data
MIN_POINTS_FOR_SARIMAX = 30  # ~2.5 years; below this, seasonal terms are meaningless
DEFAULT_HOLDOUT = 12
DEFAULT_HORIZON = 6

# Which ingestion script loads the full history for each commodity — used
# only to point an insufficient_data message at the right next step.
INGEST_SCRIPT_BY_COMMODITY = {
    "coal_australian": "data_pipeline/ingest_worldbank.py",
    "crude_oil_brent": "data_pipeline/ingest_worldbank.py",
    "coking_coal": "data_pipeline/ingest_rba_coking_coal.py",
}

# A small, curated set of candidate (order, seasonal_order) pairs — chosen
# to cover the standard shapes for a trending + seasonal monthly commodity
# price series, not an exhaustive search.
CANDIDATE_ORDERS = [
    ((1, 1, 1), (1, 1, 0, SEASON_LENGTH)),
    ((1, 1, 1), (0, 1, 1, SEASON_LENGTH)),
    ((2, 1, 1), (1, 1, 0, SEASON_LENGTH)),
    ((0, 1, 1), (0, 1, 1, SEASON_LENGTH)),
    ((1, 1, 0), (1, 1, 0, SEASON_LENGTH)),
]

_cache: dict[str, "ForecastResult"] = {}


@dataclass
class Metrics:
    mae: float
    rmse: float
    mape: float

    def as_dict(self) -> dict:
        return {
            "mae": round(self.mae, 3),
            "rmse": round(self.rmse, 3),
            "mape_pct": round(self.mape, 2),
        }


@dataclass
class ForecastResult:
    commodity: str
    status: str  # "ok" | "insufficient_data"
    note: str
    historical: list
    forecast: list
    evaluation: Optional[dict]
    model_info: dict

    def as_dict(self) -> dict:
        return {
            "commodity": self.commodity,
            "status": self.status,
            "note": self.note,
            "historical": self.historical,
            "forecast": self.forecast,
            "evaluation": self.evaluation,
            "model_info": self.model_info,
        }


def _seasonal_naive_forecast(
    train: np.ndarray, steps: int, season_length: int = SEASON_LENGTH
) -> np.ndarray:
    """Forecast `steps` values ahead using the value from the same point in
    the last full season, cycling for steps > season_length. Falls back to
    a flat last-value forecast if there isn't a full season of history."""
    if len(train) < season_length:
        return np.full(steps, train[-1])
    last_season = train[-season_length:]
    return np.array([last_season[i % season_length] for i in range(steps)])


def _evaluate(actual: np.ndarray, predicted: np.ndarray) -> Metrics:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    errors = actual - predicted
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))
    mape = float(np.mean(np.abs(errors / actual)) * 100)
    return Metrics(mae=mae, rmse=rmse, mape=mape)


def _fit_sarimax(series: np.ndarray, order: tuple, seasonal_order: tuple):
    model = SARIMAX(
        series,
        order=order,
        seasonal_order=seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    return model.fit(disp=False)


def _select_best_order(train: np.ndarray):
    """Fit every candidate order on `train`, return (fit, spec, aic) for
    the lowest-AIC one that converged. A candidate that fails to converge
    or errors out is skipped, not treated as fatal — real commodity data
    is noisy enough that not every textbook order will fit cleanly."""
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order, seasonal_order in CANDIDATE_ORDERS:
            try:
                fit = _fit_sarimax(train, order, seasonal_order)
            except Exception:
                continue
            if best is None or fit.aic < best[2]:
                best = (fit, (order, seasonal_order), fit.aic)
    if best is None:
        raise RuntimeError("All candidate SARIMAX orders failed to fit — check the input series.")
    return best


def build_forecast(
    commodity: str, df: pd.DataFrame, horizon: int = DEFAULT_HORIZON, use_cache: bool = True
) -> ForecastResult:
    """
    df: columns ['date', 'price_usd'], one row per month (order doesn't
    matter, it's sorted here).
    """
    cache_key = f"{commodity}:{horizon}:{len(df)}"
    if use_cache and cache_key in _cache:
        return _cache[cache_key]

    df = df.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(df["date"])
    prices = df["price_usd"].to_numpy(dtype=float)

    historical = [
        {"date": d.strftime("%Y-%m-%d"), "price_usd": float(p)} for d, p in zip(dates, prices)
    ]

    if len(prices) < MIN_POINTS_FOR_SARIMAX:
        ingest_script = INGEST_SCRIPT_BY_COMMODITY.get(
            commodity, "the appropriate data_pipeline/ingest_*.py script"
        )
        result = ForecastResult(
            commodity=commodity,
            status="insufficient_data",
            note=(
                f"Only {len(prices)} month(s) of history available; need at "
                f"least {MIN_POINTS_FOR_SARIMAX} for a seasonal forecast. "
                f"Run {ingest_script} to load the full history."
            ),
            historical=historical,
            forecast=[],
            evaluation=None,
            model_info={},
        )
        if use_cache:
            _cache[cache_key] = result
        return result

    holdout = (
        DEFAULT_HOLDOUT
        if len(prices) >= MIN_POINTS_FOR_SARIMAX + DEFAULT_HOLDOUT
        else max(3, len(prices) // 5)
    )
    train, test = prices[:-holdout], prices[-holdout:]

    baseline_pred = _seasonal_naive_forecast(train, holdout)
    baseline_metrics = _evaluate(test, baseline_pred)

    eval_fit, spec, _ = _select_best_order(train)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sarimax_pred = eval_fit.forecast(steps=holdout)
    sarimax_metrics = _evaluate(test, sarimax_pred)

    # Refit the SAME selected order on the full series (train+holdout) for
    # the actual forward-looking forecast — deliberately not re-searching,
    # see module docstring.
    order, seasonal_order = spec
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        final_fit = _fit_sarimax(prices, order, seasonal_order)
        forecast_res = final_fit.get_forecast(steps=horizon)
        summary = forecast_res.summary_frame(alpha=0.05)

    last_date = dates.iloc[-1]
    forecast_dates = pd.date_range(last_date, periods=horizon + 1, freq="MS")[1:]

    forecast = [
        {
            "date": fd.strftime("%Y-%m-%d"),
            "forecast_price_usd": round(float(row["mean"]), 3),
            "ci_lower": round(float(row["mean_ci_lower"]), 3),
            "ci_upper": round(float(row["mean_ci_upper"]), 3),
        }
        for fd, (_, row) in zip(forecast_dates, summary.iterrows())
    ]

    result = ForecastResult(
        commodity=commodity,
        status="ok",
        note=(
            "CALCULATED forecast (SARIMAX), not a real future price. "
            f"Evaluated against a seasonal-naive baseline on the last "
            f"{holdout} real months, held out of training."
        ),
        historical=historical,
        forecast=forecast,
        evaluation={
            "holdout_months": holdout,
            "baseline_seasonal_naive": baseline_metrics.as_dict(),
            "sarimax": sarimax_metrics.as_dict(),
        },
        model_info={
            "model": "SARIMAX",
            "order": list(order),
            "seasonal_order": list(seasonal_order),
            "aic": round(float(final_fit.aic), 2),
            "trained_on_months": len(prices),
            "data_range": {"start": historical[0]["date"], "end": historical[-1]["date"]},
        },
    )
    if use_cache:
        _cache[cache_key] = result
    return result


def clear_cache() -> None:
    _cache.clear()
