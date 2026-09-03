"""
Module 7: book-now-vs-wait decision.

Answers a narrower, different question than Module 6: not "which vessel
and route" but "should procurement lock in the commodity price now, or
is it worth waiting?" This is the last piece of Predict -> Simulate ->
Optimize -> Recommend — it's built directly on top of Module 1's own
forecast, not a new model.

SIGNAL, DELIBERATELY SCOPED: this compares the latest REAL commodity
price to Module 1's own SARIMAX point forecast at a near-term horizon
(default 3 months — long enough to be an actionable procurement window,
short enough that the forecast hasn't degraded into the wide, low-value
uncertainty of a 12+ month projection). If the forecast expects the
price to rise meaningfully, booking now avoids paying the higher future
price; if it expects the price to fall, waiting is worth considering.
Nothing here is invented: the forecast, its 95% CI, and its own
evaluated accuracy (vs. the seasonal-naive baseline) all come straight
from build_forecast() in forecast.py, reused as-is.

WHY NOT FOLD THIS INTO MODULE 6: Module 6's "risk" is about physical
berth clearance, a property of a specific vessel/port pair. This
module's signal is about WHEN to buy the commodity, a property of the
market alone, independent of which vessel eventually carries it. Mixing
the two into one blended score would hide which factor is actually
driving a recommendation — see DECISIONS.md #16 for the same reasoning
applied to Module 6.

HONESTY ON CONFIDENCE: a point forecast alone can look more decisive
than it is. If the forecast's own 95% CI at the target horizon still
contains today's real price, the model itself isn't confident the price
will move in the predicted direction at all — that's reported as
`confidence: "low"` rather than buried, so a BOOK_NOW/WAIT verdict next
to "confidence: low" reads as the honest hedge it is, not a strong
signal. This is a CALCULATED decision aid from a forecast model, never
presented as certain or as real-time market intelligence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.engine.forecast import build_forecast

DEFAULT_DECISION_HORIZON = 3  # months — see module docstring for why

# Expected price move (relative to the latest real price) required to
# call a direction at all. Below this magnitude either way, the forecast
# is treated as "no strong signal" rather than forced into a verdict.
BOOK_THRESHOLD_PCT = 0.03
WAIT_THRESHOLD_PCT = -0.03


def _classify(pct_change: float) -> str:
    if pct_change >= BOOK_THRESHOLD_PCT:
        return "BOOK_NOW"
    if pct_change <= WAIT_THRESHOLD_PCT:
        return "WAIT"
    return "HOLD"


def _confidence_label(latest_price: float, ci_lower: float, ci_upper: float) -> str:
    """'low' if the forecast's own 95% CI at the target horizon still
    contains today's real price — meaning the model can't rule out "no
    real change" even though its point estimate leans one way."""
    return "low" if ci_lower <= latest_price <= ci_upper else "high"


@dataclass
class BookOrWaitResult:
    commodity: str
    status: str  # "ok" | "insufficient_data"
    decision: Optional[str]  # "BOOK_NOW" | "WAIT" | "HOLD" | None
    confidence: Optional[str]  # "high" | "low" | None
    latest_price_usd: Optional[float]
    latest_date: Optional[str]
    horizon_months: int
    target_date: Optional[str]
    forecast_price_usd: Optional[float]
    ci_lower_usd: Optional[float]
    ci_upper_usd: Optional[float]
    pct_change: Optional[float]
    reasoning: str
    forecast_evaluation: Optional[dict]
    model_info: Optional[dict]

    def as_dict(self) -> dict:
        return {
            "commodity": self.commodity,
            "status": self.status,
            "decision": self.decision,
            "confidence": self.confidence,
            "latest_price_usd": self.latest_price_usd,
            "latest_date": self.latest_date,
            "horizon_months": self.horizon_months,
            "target_date": self.target_date,
            "forecast_price_usd": self.forecast_price_usd,
            "ci_lower_usd": self.ci_lower_usd,
            "ci_upper_usd": self.ci_upper_usd,
            "pct_change_pct": round(self.pct_change * 100, 2)
            if self.pct_change is not None
            else None,
            "reasoning": self.reasoning,
            "forecast_evaluation": self.forecast_evaluation,
            "model_info": self.model_info,
        }


def evaluate_book_or_wait(
    commodity: str, df: pd.DataFrame, horizon: int = DEFAULT_DECISION_HORIZON
) -> BookOrWaitResult:
    """df: same shape build_forecast expects (['date', 'price_usd'])."""
    forecast_result = build_forecast(commodity, df, horizon=horizon)

    if forecast_result.status != "ok":
        return BookOrWaitResult(
            commodity=commodity,
            status=forecast_result.status,
            decision=None,
            confidence=None,
            latest_price_usd=None,
            latest_date=None,
            horizon_months=horizon,
            target_date=None,
            forecast_price_usd=None,
            ci_lower_usd=None,
            ci_upper_usd=None,
            pct_change=None,
            reasoning=forecast_result.note,
            forecast_evaluation=None,
            model_info=None,
        )

    latest = forecast_result.historical[-1]
    target = forecast_result.forecast[-1]  # last point at exactly `horizon` months out

    latest_price = latest["price_usd"]
    target_price = target["forecast_price_usd"]
    pct_change = (target_price - latest_price) / latest_price

    decision = _classify(pct_change)
    confidence = _confidence_label(latest_price, target["ci_lower"], target["ci_upper"])

    direction = "rise" if pct_change > 0 else ("fall" if pct_change < 0 else "stay flat")
    reasoning = (
        f"Latest real price ({latest['date']}): ${latest_price:.2f}/t. "
        f"{horizon}-month SARIMAX forecast ({target['date']}): "
        f"${target_price:.2f}/t ({pct_change:+.1%}), 95% CI "
        f"[${target['ci_lower']:.2f}, ${target['ci_upper']:.2f}]/t. "
        f"The model expects price to {direction} over this window."
    )
    if confidence == "low":
        reasoning += (
            " Confidence is LOW: the forecast's own 95% CI still contains "
            "today's real price, so the model can't rule out little or no "
            "real change — treat this verdict as a lean, not a certainty."
        )
    reasoning += " CALCULATED from Module 1's forecast model, not a live market signal."

    return BookOrWaitResult(
        commodity=commodity,
        status="ok",
        decision=decision,
        confidence=confidence,
        latest_price_usd=round(latest_price, 3),
        latest_date=latest["date"],
        horizon_months=horizon,
        target_date=target["date"],
        forecast_price_usd=target_price,
        ci_lower_usd=target["ci_lower"],
        ci_upper_usd=target["ci_upper"],
        pct_change=pct_change,
        reasoning=reasoning,
        forecast_evaluation=forecast_result.evaluation,
        model_info=forecast_result.model_info,
    )
