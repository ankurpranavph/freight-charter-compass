import { useEffect, useState } from "react";
import { api } from "../api/client";

const HORIZONS = [3, 6, 12, 24];

const DECISION_LABEL = {
  BOOK_NOW: "Book now",
  WAIT: "Wait",
  HOLD: "Hold",
};

// The two commodities this app tracks, shown side by side as a timing
// signal in "by vessel" mode — coking_coal is what SAIL actually
// procures (DECISIONS.md #23) but only has 1 real seeded point until the
// user runs ingest_rba_coking_coal.py, so it's expected to often show an
// honest insufficient_data note rather than a real decision.
const TIMING_COMMODITIES = [
  { id: "coking_coal", label: "Coking coal timing" },
  { id: "coal_australian", label: "Thermal coal timing" },
];

function marginLabel(pct) {
  if (pct === null || pct === undefined) return "unconfirmed clearance";
  return `${pct.toFixed(1)}% spare margin (tightest dimension)`;
}

/* -----------------------------------------------------------------------
   Mode A: fixed destination port -> rank vessel x origin-port combos.
   ------------------------------------------------------------------- */

function useByPortData(portId, cargoTonnes) {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    if (!portId) return undefined;
    let cancelled = false;
    setState({ loading: true, error: null, data: null });

    api
      .optimize(portId, cargoTonnes || undefined)
      .then((ranked) => {
        if (cancelled) return;
        setState({ loading: false, error: null, data: ranked });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ loading: false, error: err, data: null });
      });

    return () => {
      cancelled = true;
    };
  }, [portId, cargoTonnes]);

  return state;
}

function VesselOriginOptionCard({ option, originName }) {
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

function ByPortPanel({ ports, originPorts }) {
  const [portId, setPortId] = useState(ports.length ? ports[0].port_id : null);
  const [cargoInput, setCargoInput] = useState("");
  const cargoTonnes = cargoInput && Number(cargoInput) > 0 ? Number(cargoInput) : null;
  const { loading, error, data } = useByPortData(portId, cargoTonnes);

  function originName(originId) {
    const match = originPorts.find((o) => o.origin_id === originId);
    return match ? match.name : originId;
  }

  return (
    <>
      <p className="page-intro">
        Every physically-compatible vessel × loading-port combination for the
        chosen destination, ranked by risk-adjusted cost per tonne (Module 6)
        — composing Module 4's compatibility gate and Module 5's voyage cost,
        not a separate score. See <code>docs/DECISIONS.md #14, #16</code>.
      </p>

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

      {loading && <p className="status-text">Ranking options…</p>}

      {error && (
        <div className="error-box">
          <p>
            <strong>Couldn't load recommendations.</strong> {error.message}
          </p>
        </div>
      )}

      {!loading && !error && data && data.length === 0 && (
        <div className="error-box error-box-info">
          <p>
            No vessel class physically clears this port
            {cargoTonnes ? ` at ${cargoTonnes.toLocaleString()}t` : ""} — see the Overview
            page's port table for its draft/LOA/beam limits, or try a smaller cargo size.
          </p>
        </div>
      )}

      {!loading && !error && data && data.length > 0 && (
        <div className="option-list">
          {data.map((opt) => (
            <VesselOriginOptionCard
              key={`${opt.vessel_type}-${opt.origin_id}`}
              option={opt}
              originName={originName(opt.origin_id)}
            />
          ))}
        </div>
      )}
    </>
  );
}

/* -----------------------------------------------------------------------
   Mode B: fixed vessel + loading port -> rank the 6 destination ports.
   Added after re-checking the app against the SIH26006 problem statement
   — a real charterer usually starts here ("I have this ship, where
   should it go?"), not with a destination already picked. See
   DECISIONS.md #24.
   ------------------------------------------------------------------- */

function useByVesselData(vesselType, originId, cargoTonnes) {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    if (!vesselType || !originId) return undefined;
    let cancelled = false;
    setState({ loading: true, error: null, data: null });

    api
      .optimizeByVessel(vesselType, originId, cargoTonnes || undefined)
      .then((data) => {
        if (cancelled) return;
        setState({ loading: false, error: null, data });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ loading: false, error: err, data: null });
      });

    return () => {
      cancelled = true;
    };
  }, [vesselType, originId, cargoTonnes]);

  return state;
}

function useTimingData(horizon) {
  const [state, setState] = useState({ loading: true, results: {} });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, results: {} });

    Promise.all(
      TIMING_COMMODITIES.map((c) =>
        api
          .bookOrWait(c.id, horizon)
          .then((result) => [c.id, result])
          .catch((err) => [c.id, { status: "error", error: err }]),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setState({ loading: false, results: Object.fromEntries(pairs) });
    });

    return () => {
      cancelled = true;
    };
  }, [horizon]);

  return state;
}

function TimingCard({ label, result, loading }) {
  if (loading) {
    return (
      <div className="decision-card decision-card-muted">
        <h3>{label}</h3>
        <p className="status-text">Loading…</p>
      </div>
    );
  }
  if (!result || result.status === "error") {
    return (
      <div className="decision-card decision-card-muted">
        <h3>{label}</h3>
        <p>Couldn't load a timing signal for this commodity.</p>
      </div>
    );
  }
  if (result.status !== "ok") {
    return (
      <div className="decision-card decision-card-muted">
        <h3>{label}</h3>
        <p>{result.reasoning}</p>
      </div>
    );
  }
  return (
    <div className="decision-card">
      <h3>{label}</h3>
      <div className="decision-verdict">
        <span className={`decision-badge decision-badge-${result.decision}`}>
          {DECISION_LABEL[result.decision] ?? result.decision}
        </span>
        <span className="decision-confidence">
          {result.confidence === "low" ? "Low confidence" : "High confidence"}
        </span>
      </div>
      <p className="decision-reasoning">{result.reasoning}</p>
    </div>
  );
}

function PortOptionCard({ option, rank, portName }) {
  const { voyage, compatibility } = option;
  const marginPct = option.tightest_margin_ratio_pct;
  const hasPenalty = option.risk_multiplier > 1;

  return (
    <div className="option-card">
      <div className="option-rank">#{rank}</div>
      <div className="option-body">
        <div className="option-head">
          <h3>{portName}</h3>
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
          <summary>Why this port works</summary>
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
            {voyage.cargo_tonnes.toLocaleString()}t of cargo.
          </p>
        </details>
      </div>
    </div>
  );
}

function IncompatiblePortRow({ entry, portName }) {
  return (
    <div className="incompat-row">
      <span className="badge">Not compatible</span>
      <div className="incompat-body">
        <strong>{portName}</strong>
        <ul className="option-checks">
          {entry.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ByVesselPanel({ vessels, originPorts, ports }) {
  const [vesselType, setVesselType] = useState(vessels.length ? vessels[0].vessel_type : null);
  const [originId, setOriginId] = useState(originPorts.length ? originPorts[0].origin_id : null);
  const [cargoInput, setCargoInput] = useState("");
  const [horizon, setHorizon] = useState(6);
  const cargoTonnes = cargoInput && Number(cargoInput) > 0 ? Number(cargoInput) : null;

  const { loading, error, data } = useByVesselData(vesselType, originId, cargoTonnes);
  const timing = useTimingData(horizon);

  function portName(portId) {
    const match = ports.find((p) => p.port_id === portId);
    return match ? match.name : portId;
  }

  return (
    <>
      <p className="page-intro">
        Pick a vessel class and an overseas loading port you already have —
        see which of the 6 East Coast destinations it can actually call at,
        ranked by risk-adjusted cost per tonne, and whether current pricing
        favors booking now or waiting. The mirror of the port-first view:
        that one fixes where you're shipping to and ranks vessels; this
        fixes the vessel and ranks destinations. See{" "}
        <code>docs/DECISIONS.md #24</code>.
      </p>

      <div className="filter-row">
        <div className="filter-group">
          {vessels.map((v) => (
            <button
              key={v.vessel_type}
              className={
                v.vessel_type === vesselType ? "filter-btn filter-btn-active" : "filter-btn"
              }
              onClick={() => setVesselType(v.vessel_type)}
            >
              {v.vessel_type}
            </button>
          ))}
        </div>
        <div className="filter-group">
          {originPorts.map((o) => (
            <button
              key={o.origin_id}
              className={
                o.origin_id === originId ? "filter-btn filter-btn-active" : "filter-btn"
              }
              onClick={() => setOriginId(o.origin_id)}
            >
              {o.name}
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

      <div className="filter-row">
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
        <span className="cargo-input-label">Timing horizon — should you book now or wait?</span>
      </div>

      <div className="section">
        <div className="timing-row">
          {TIMING_COMMODITIES.map((c) => (
            <TimingCard
              key={c.id}
              label={c.label}
              result={timing.results[c.id]}
              loading={timing.loading}
            />
          ))}
        </div>
      </div>

      {loading && <p className="status-text">Checking every East Coast port…</p>}

      {error && (
        <div className="error-box">
          <p>
            <strong>Couldn't check destinations.</strong> {error.message}
          </p>
        </div>
      )}

      {!loading && !error && data && (
        <div className="section">
          <h2>Destinations for this {vesselType}</h2>
          <p className="section-note">
            {data.compatible_ports.length} of {data.compatible_ports.length + data.incompatible_ports.length}{" "}
            East Coast ports can take this vessel
            {data.cargo_tonnes ? ` at ${data.cargo_tonnes.toLocaleString()}t` : ""} — every
            port is shown, compatible or not, with the exact reason either way.
          </p>

          {data.compatible_ports.length === 0 && (
            <div className="error-box error-box-info">
              <p>
                No East Coast port on file currently clears this {vesselType}
                {data.cargo_tonnes ? ` at ${data.cargo_tonnes.toLocaleString()}t` : ""} — see
                the reasons below, or try a smaller cargo size or a different vessel class.
              </p>
            </div>
          )}

          {data.compatible_ports.length > 0 && (
            <div className="option-list">
              {data.compatible_ports.map((opt) => (
                <PortOptionCard
                  key={opt.port_id}
                  option={opt}
                  rank={opt.rank}
                  portName={portName(opt.port_id)}
                />
              ))}
            </div>
          )}

          {data.incompatible_ports.length > 0 && (
            <div className="section">
              <h2>Not compatible ({data.incompatible_ports.length})</h2>
              <div className="incompat-list">
                {data.incompatible_ports.map((entry) => (
                  <IncompatiblePortRow
                    key={entry.port_id}
                    entry={entry}
                    portName={portName(entry.port_id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}

/* -----------------------------------------------------------------------
   Page shell — shared reference data + mode toggle.
   ------------------------------------------------------------------- */

export default function Recommendation() {
  const [mode, setMode] = useState("by-vessel");
  const [ref, setRef] = useState({ ports: null, originPorts: null, vessels: null, error: null });

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.ports(), api.originPorts(), api.vessels()])
      .then(([ports, originPorts, vessels]) => {
        if (cancelled) return;
        setRef({ ports, originPorts, vessels, error: null });
      })
      .catch((err) => {
        if (cancelled) return;
        setRef((s) => ({ ...s, error: err }));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page">
      <h1>Recommendation</h1>

      <div className="filter-row">
        <div className="filter-group">
          <button
            className={mode === "by-vessel" ? "filter-btn filter-btn-active" : "filter-btn"}
            onClick={() => setMode("by-vessel")}
          >
            By vessel &amp; loading port
          </button>
          <button
            className={mode === "by-port" ? "filter-btn filter-btn-active" : "filter-btn"}
            onClick={() => setMode("by-port")}
          >
            By destination port
          </button>
        </div>
      </div>

      {ref.error && (
        <div className="error-box">
          <p>
            <strong>Couldn't load reference data.</strong> {ref.error.message}
          </p>
        </div>
      )}

      {!ref.error && (!ref.ports || !ref.originPorts || !ref.vessels) && (
        <p className="status-text">Loading…</p>
      )}

      {ref.ports && ref.originPorts && ref.vessels && mode === "by-vessel" && (
        <ByVesselPanel vessels={ref.vessels} originPorts={ref.originPorts} ports={ref.ports} />
      )}

      {ref.ports && ref.originPorts && ref.vessels && mode === "by-port" && (
        <ByPortPanel ports={ref.ports} originPorts={ref.originPorts} />
      )}
    </div>
  );
}
