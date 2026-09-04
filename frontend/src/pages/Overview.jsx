import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useExchangeRate } from "../hooks/useExchangeRate";
import { formatInr } from "../utils/currency";

function useOverviewData() {
  const [state, setState] = useState({
    loading: true,
    error: null,
    data: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [health, vessels, ports, originPorts, coal, oil, cokingCoal] =
          await Promise.all([
            api.health(),
            api.vessels(),
            api.ports(),
            api.originPorts(),
            api.commodityPrices("coal_australian"),
            api.commodityPrices("crude_oil_brent"),
            api.commodityPrices("coking_coal"),
          ]);
        if (cancelled) return;
        setState({
          loading: false,
          error: null,
          data: { health, vessels, ports, originPorts, coal, oil, cokingCoal },
        });
      } catch (err) {
        if (cancelled) return;
        setState({ loading: false, error: err, data: null });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

function latestPrice(rows) {
  if (!rows || rows.length === 0) return null;
  // rows are ordered by date ascending (see /api/v1/commodity-prices)
  return rows[rows.length - 1];
}

export default function Overview() {
  const { loading, error, data } = useOverviewData();
  const fx = useExchangeRate();

  if (loading) {
    return <p className="status-text">Loading live data from the API…</p>;
  }

  if (error) {
    return (
      <div className="error-box">
        <p>
          <strong>Couldn't load data.</strong> {error.message}
        </p>
      </div>
    );
  }

  const { vessels, ports, originPorts, coal, oil, cokingCoal } = data;
  const latestCoal = latestPrice(coal);
  const latestOil = latestPrice(oil);
  const latestCokingCoal = latestPrice(cokingCoal);
  const verifiedPorts = ports.filter((p) => p.verified).length;

  return (
    <div className="page">
      <h1>Overview</h1>
      <p className="page-intro">
        Live snapshot of the fleet, ports, and commodity data this app's
        forecasts and recommendations are built on — pulled straight from
        the running API, not hardcoded here.
      </p>

      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-value">{vessels.length}</span>
          <span className="stat-label">Vessel classes</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {verifiedPorts}/{ports.length}
          </span>
          <span className="stat-label">East Coast ports verified</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{originPorts.length}</span>
          <span className="stat-label">Overseas loading ports</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {coal.length + oil.length + cokingCoal.length}
          </span>
          <span className="stat-label">Commodity price rows loaded</span>
        </div>
      </div>

      {(latestCoal || latestOil || latestCokingCoal) && (
        <section className="section">
          <h2>Latest commodity prices</h2>
          <p className="section-note">
            REAL — coal/oil from the World Bank Pink Sheet (monthly), coking
            coal from a single cited spot snapshot pending its own full RBA
            ingestion run. USD is the source-of-truth figure throughout this
            app; INR below is a secondary CALCULATED conversion at one cited
            rate, shown alongside it, never in place of it. See{" "}
            <code>docs/DECISIONS.md #12, #23, #25</code>.
          </p>
          <div className="stat-row">
            {latestCokingCoal && (
              <div className="stat-card">
                <span className="stat-value">
                  ${latestCokingCoal.price_usd.toFixed(2)}
                </span>
                {formatInr(latestCokingCoal.price_usd, fx) && (
                  <span className="stat-sub">≈ {formatInr(latestCokingCoal.price_usd, fx)}</span>
                )}
                <span className="stat-label">
                  Coking coal (Australian), {latestCokingCoal.date}
                </span>
              </div>
            )}
            {latestCoal && (
              <div className="stat-card">
                <span className="stat-value">
                  ${latestCoal.price_usd.toFixed(2)}
                </span>
                {formatInr(latestCoal.price_usd, fx) && (
                  <span className="stat-sub">≈ {formatInr(latestCoal.price_usd, fx)}</span>
                )}
                <span className="stat-label">
                  Coal (Australian, thermal), {latestCoal.date}
                </span>
              </div>
            )}
            {latestOil && (
              <div className="stat-card">
                <span className="stat-value">
                  ${latestOil.price_usd.toFixed(2)}
                </span>
                {formatInr(latestOil.price_usd, fx) && (
                  <span className="stat-sub">≈ {formatInr(latestOil.price_usd, fx)}</span>
                )}
                <span className="stat-label">
                  Crude oil (Brent), {latestOil.date}
                </span>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="section">
        <h2>Vessel classes</h2>
        <p className="section-note">
          ASSUMPTION — typical-class figures compiled from public maritime
          references, not one specific registered hull.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Class</th>
                <th>DWT (t)</th>
                <th>Draft (m)</th>
                <th>LOA (m)</th>
                <th>Beam (m)</th>
                <th>Speed (kn)</th>
              </tr>
            </thead>
            <tbody>
              {vessels.map((v) => (
                <tr key={v.vessel_type}>
                  <td>{v.vessel_type}</td>
                  <td>{v.dwt_tonnes.toLocaleString()}</td>
                  <td>{v.draft_m}</td>
                  <td>{v.loa_m}</td>
                  <td>{v.beam_m}</td>
                  <td>{v.speed_knots}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>East Coast India ports</h2>
        <p className="section-note">
          REAL where marked verified — sourced from port authority and
          terminal operator data. See{" "}
          <code>docs/DECISIONS.md #11, #14</code>.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Port</th>
                <th>Max draft (m)</th>
                <th>Max LOA (m)</th>
                <th>Max beam (m)</th>
                <th>Coal handling</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {ports.map((p) => (
                <tr key={p.port_id}>
                  <td>{p.name}</td>
                  <td>{p.max_draft_m ?? "unknown"}</td>
                  <td>{p.max_loa_m ?? "unknown"}</td>
                  <td>{p.max_beam_m ?? "unknown"}</td>
                  <td>{p.coal_handling ? "Yes" : "No"}</td>
                  <td>
                    <span
                      className={
                        p.verified ? "badge badge-verified" : "badge"
                      }
                    >
                      {p.verified ? "Verified" : "Unverified"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Overseas loading ports</h2>
        <p className="section-note">
          REAL — cross-checked coordinates. See{" "}
          <code>docs/DECISIONS.md #15</code> for sourcing and route
          reasoning.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Port</th>
                <th>Country</th>
                <th>Lat</th>
                <th>Lon</th>
              </tr>
            </thead>
            <tbody>
              {originPorts.map((o) => (
                <tr key={o.origin_id}>
                  <td>{o.name}</td>
                  <td>{o.country}</td>
                  <td>{o.lat}</td>
                  <td>{o.lon}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section data-honesty">
        <h2>Data honesty</h2>
        <p className="section-note">
          Every number in this app falls into one of four buckets — this
          page never blurs the line between them.
        </p>
        <dl className="honesty-list">
          <dt>REAL</dt>
          <dd>
            World Bank commodity prices, port draft/LOA/beam limits,
            overseas port coordinates, bunker fuel price and time-charter
            rates — all cited, dated, and sourced (see each table above and
            the Forecast/Recommendation pages).
          </dd>
          <dt>CALCULATED</dt>
          <dd>
            Voyage distance (great-circle via hand-chosen waypoints),
            sailing time, fuel and charter cost, forecast prices,
            risk-adjusted rankings — all derived from the REAL inputs
            above, never invented.
          </dd>
          <dt>SIMULATED</dt>
          <dd>
            Not used on this page. Where it appears elsewhere in the app
            (e.g. a future port-congestion multiplier), it is explicitly
            labelled as such.
          </dd>
          <dt>ASSUMPTION</dt>
          <dd>
            Vessel class specs (typical-class figures, not one registered
            hull) and full-DWT cargo utilization by default.
          </dd>
        </dl>
      </section>
    </div>
  );
}
