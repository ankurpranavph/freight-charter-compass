import { useEffect, useState } from "react";
import { api } from "../api/client";
import ForecastChart from "../components/ForecastChart";

const COMMODITIES = [
  { id: "coal_australian", label: "Coal (Australian)" },
  { id: "crude_oil_brent", label: "Crude oil (Brent)" },
];

const HORIZONS = [3, 6, 12, 24];

const DECISION_LABEL = {
  BOOK_NOW: "Book now",
  WAIT: "Wait",
  HOLD: "Hold",
};

function useForecastData(commodity, horizon) {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: null, data: null });

    async function load() {
      try {
        const [forecast, decision] = await Promise.all([
          api.forecast(commodity, horizon),
          api.bookOrWait(commodity, horizon),
        ]);
        if (cancelled) return;
        setState({ loading: false, error: null, data: { forecast, decision } });
      } catch (err) {
        if (cancelled) return;
        setState({ loading: false, error: err, data: null });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [commodity, horizon]);

  return state;
}

function DecisionCard({ decision }) {
  if (decision.status !== "ok") {
    return (
      <div className="decision-card decision-card-muted">
        <h3>Book now vs. wait</h3>
        <p>{decision.reasoning}</p>
      </div>
    );
  }

  return (
    <div className="decision-card">
      <h3>Book now vs. wait</h3>
      <div className="decision-verdict">
        <span className={`decision-badge decision-badge-${decision.decision}`}>
          {DECISION_LABEL[decision.decision] ?? decision.decision}
        </span>
        <span className="decision-confidence">
          {decision.confidence === "low" ? "Low confidence" : "High confidence"}
        </span>
      </div>
      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-value">${decision.latest_price_usd.toFixed(2)}</span>
          <span className="stat-label">Latest ({decision.latest_date})</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">${decision.forecast_price_usd.toFixed(2)}</span>
          <span className="stat-label">
            Forecast ({decision.horizon_months}mo, {decision.target_date})
          </span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {decision.pct_change_pct > 0 ? "+" : ""}
            {decision.pct_change_pct.toFixed(1)}%
          </span>
          <span className="stat-label">Expected change</span>
        </div>
      </div>
      <p className="decision-reasoning">{decision.reasoning}</p>
    </div>
  );
}

function MetricsPanel({ evaluation, modelInfo }) {
  if (!evaluation) return null;
  const { baseline_seasonal_naive: baseline, sarimax, holdout_months } = evaluation;
  return (
    <div className="section">
      <h2>Model accuracy</h2>
      <p className="section-note">
        CALCULATED — SARIMAX vs. a seasonal-naive baseline, evaluated on the
        last {holdout_months} real months held out of training (never seen
        during fitting). Lower is better on every metric.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>MAE</th>
              <th>RMSE</th>
              <th>MAPE</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Seasonal-naive baseline</td>
              <td>{baseline.mae}</td>
              <td>{baseline.rmse}</td>
              <td>{baseline.mape_pct}%</td>
            </tr>
            <tr>
              <td>SARIMAX</td>
              <td>{sarimax.mae}</td>
              <td>{sarimax.rmse}</td>
              <td>{sarimax.mape_pct}%</td>
            </tr>
          </tbody>
        </table>
      </div>
      {modelInfo && (
        <p className="section-note" style={{ marginTop: "0.6rem" }}>
          Order {JSON.stringify(modelInfo.order)} × seasonal{" "}
          {JSON.stringify(modelInfo.seasonal_order)}, AIC {modelInfo.aic}, trained
          on {modelInfo.trained_on_months} months (
          {modelInfo.data_range?.start} – {modelInfo.data_range?.end}).
        </p>
      )}
    </div>
  );
}

export default function Forecast() {
  const [commodity, setCommodity] = useState(COMMODITIES[0].id);
  const [horizon, setHorizon] = useState(6);
  const { loading, error, data } = useForecastData(commodity, horizon);

  return (
    <div className="page">
      <h1>Forecast</h1>
      <p className="page-intro">
        SARIMAX price forecast (Module 1) against a seasonal-naive baseline,
        and the resulting book-now-vs-wait read (Module 7) — reusing this
        same forecast, not a second model. See{" "}
        <code>docs/DECISIONS.md #13, #17</code>.
      </p>

      <div className="filter-row">
        <div className="filter-group">
          {COMMODITIES.map((c) => (
            <button
              key={c.id}
              className={c.id === commodity ? "filter-btn filter-btn-active" : "filter-btn"}
              onClick={() => setCommodity(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="filter-group">
          {HORIZONS.map((h) => (
            <button
              key={h}
              className={h === horizon ? "filter-btn filter-btn-active" : "filter-btn"}
              onClick={() => setHorizon(h)}
            >
              {h}mo
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="status-text">Loading forecast…</p>}

      {error && (
        <div className="error-box">
          <p>
            <strong>Couldn't load the forecast.</strong> {error.message}
          </p>
        </div>
      )}

      {!loading && !error && data && data.forecast.status === "insufficient_data" && (
        <div className="error-box error-box-info">
          <p>{data.forecast.note}</p>
        </div>
      )}

      {!loading && !error && data && data.forecast.status === "ok" && (
        <>
          <section className="section">
            <ForecastChart
              historical={data.forecast.historical}
              forecast={data.forecast.forecast}
            />
          </section>

          <section className="section">
            <DecisionCard decision={data.decision} />
          </section>

          <MetricsPanel
            evaluation={data.forecast.evaluation}
            modelInfo={data.forecast.model_info}
          />
        </>
      )}
    </div>
  );
}
