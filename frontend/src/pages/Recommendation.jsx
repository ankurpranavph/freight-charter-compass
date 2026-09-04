import { useEffect, useState } from "react";
import { api } from "../api/client";

function useRecommendationData(portId, cargoTonnes) {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    if (!portId) return undefined;
    let cancelled = false;
    setState({ loading: true, error: null, data: null });

    async function load() {
      try {
        const [ranked, originPorts] = await Promise.all([
          api.optimize(portId, cargoTonnes || undefined),
          api.originPorts(),
        ]);
        if (cancelled) return;
        setState({ loading: false, error: null, data: { ranked, originPorts } });
      } catch (err) {
        if (cancelled) return;
        setState({ loading: false, error: err, data: null });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [portId, cargoTonnes]);

  return state;
}

function marginLabel(pct) {
  if (pct === null || pct === undefined) return "unconfirmed clearance";
  return `${pct.toFixed(1)}% spare margin (tightest dimension)`;
}

function OptionCard({ option, originName }) {
  const { voyage, compatibility } = option;
  const marginPct = option.tightest_margin_ratio_pct;
  const hasPenalty = option.risk_multiplier > 1;

  return (
    <div className="option-card">
      <div className="option-rank">#{option.rank}</div>
      <div className="option-body">
        <div className="option-head">
          <h3>
            {option.vessel_type}
            <span className="option-from"> from {originName}</span>
          </h3>
          <span className="option-cost">
            ${option.risk_adjusted_cost_per_tonne_usd.toFixed(2)}/t
          </span>
        </div>

        <div className="option-meta">
          <span>
            {voyage.distance_nm.toLocaleString()} nm · {voyage.voyage_days} days
          </span>
          <span>Base cost ${option.cost_per_tonne_usd.toFixed(2)}/t</span>
          {hasPenalty ? (
            <span className="option-risk-flag">
              +{((option.risk_multiplier - 1) * 100).toFixed(1)}% risk premium —{" "}
              {marginLabel(marginPct)}
            </span>
          ) : (
            <span className="option-risk-ok">No risk premium — {marginLabel(marginPct)}</span>
          )}
        </div>

        <details className="option-details">
          <summary>Why this vessel clears the port</summary>
          <ul className="option-checks">
            {compatibility.checks.map((c) => (
              <li key={c.dimension}>
                <strong>{c.dimension}</strong>: vessel {c.vessel_value}m vs. port max{" "}
                {c.port_max ?? "unknown"}m
                {c.margin_m !== null
                  ? ` (${c.margin_m >= 0 ? "+" : ""}${c.margin_m}m margin)`
                  : ""}
              </li>
            ))}
          </ul>
          <p className="section-note">
            CALCULATED (Module 5) — fuel ${voyage.fuel_cost_usd.toLocaleString()} + charter
            hire ${voyage.charter_hire_usd.toLocaleString()} = $
            {voyage.total_cost_usd.toLocaleString()} total for{" "}
            {voyage.cargo_tonnes.toLocaleString()}t of cargo. Risk premium is CALCULATED from
            the same physical margin shown above, not a price-trend forecast — see{" "}
            <code>docs/DECISIONS.md #16</code>.
          </p>
        </details>
      </div>
    </div>
  );
}

export default function Recommendation() {
  const [ports, setPorts] = useState(null);
  const [portsError, setPortsError] = useState(null);
  const [portId, setPortId] = useState(null);
  const [cargoInput, setCargoInput] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .ports()
      .then((rows) => {
        if (cancelled) return;
        setPorts(rows);
        if (rows.length) setPortId(rows[0].port_id);
      })
      .catch((err) => {
        if (cancelled) return;
        setPortsError(err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cargoTonnes = cargoInput && Number(cargoInput) > 0 ? Number(cargoInput) : null;
  const { loading, error, data } = useRecommendationData(portId, cargoTonnes);

  function originName(originId) {
    const match = data?.originPorts.find((o) => o.origin_id === originId);
    return match ? match.name : originId;
  }

  return (
    <div className="page">
      <h1>Recommendation</h1>
      <p className="page-intro">
        Every physically-compatible vessel × loading-port combination for the
        chosen destination, ranked by risk-adjusted cost per tonne (Module 6)
        — composing Module 4's compatibility gate and Module 5's voyage cost,
        not a separate score. See <code>docs/DECISIONS.md #14, #16</code>.
      </p>

      {portsError && (
        <div className="error-box">
          <p>
            <strong>Couldn't load ports.</strong> {portsError.message}
          </p>
        </div>
      )}

      {ports && (
        <div className="filter-row">
          <div className="filter-group">
            {ports.map((p) => (
              <button
                key={p.port_id}
                className={p.port_id === portId ? "filter-btn filter-btn-active" : "filter-btn"}
                onClick={() => setPortId(p.port_id)}
              >
                {p.name}
              </button>
            ))}
          </div>
          <label className="cargo-input-label">
            Cargo tonnes
            <input
              type="number"
              min="1"
              placeholder="Full DWT"
              value={cargoInput}
              onChange={(e) => setCargoInput(e.target.value)}
              className="cargo-input"
            />
          </label>
        </div>
      )}

      {loading && <p className="status-text">Ranking options…</p>}

      {error && (
        <div className="error-box">
          <p>
            <strong>Couldn't load recommendations.</strong> {error.message}
          </p>
        </div>
      )}

      {!loading && !error && data && data.ranked.length === 0 && (
        <div className="error-box error-box-info">
          <p>
            No vessel class physically clears this port
            {cargoTonnes ? ` at ${cargoTonnes.toLocaleString()}t` : ""} — see the Overview
            page's port table for its draft/LOA/beam limits, or try a smaller cargo size.
          </p>
        </div>
      )}

      {!loading && !error && data && data.ranked.length > 0 && (
        <div className="option-list">
          {data.ranked.map((opt) => (
            <OptionCard
              key={`${opt.vessel_type}-${opt.origin_id}`}
              option={opt}
              originName={originName(opt.origin_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
