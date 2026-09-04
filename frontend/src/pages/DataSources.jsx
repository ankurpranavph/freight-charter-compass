import { useEffect, useState } from "react";
import { api } from "../api/client";

const CLASSIFICATION_NOTE = {
  REAL: "An actual figure from a cited, dated source.",
  CALCULATED: "Derived by arithmetic or a model from the REAL/ASSUMPTION data on this page — never invented.",
  ASSUMPTION: "A real, cited, point-in-time figure standing in for a live feed, or a typical-class value rather than one specific hull.",
  SIMULATED: "Not used anywhere in this app right now — reserved for a figure with no real substitute available.",
};

function useDataSources() {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    let cancelled = false;
    api
      .dataSources()
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
  }, []);

  return state;
}

function EntryRow({ entry }) {
  return (
    <div className="source-entry">
      <div className="source-entry-head">
        <span className={`classification-badge classification-badge-${entry.classification}`}>
          {entry.classification}
        </span>
        <span className="source-entry-label">{entry.label}</span>
        {entry.verified === false && <span className="badge">Unverified</span>}
      </div>
      {entry.detail && <p className="source-entry-detail">{entry.detail}</p>}
      {(entry.source || entry.source_url) && (
        <p className="source-entry-citation">
          {entry.source_url ? (
            <a href={entry.source_url} target="_blank" rel="noreferrer">
              {entry.source || entry.source_url}
            </a>
          ) : (
            entry.source
          )}
          {entry.source_date ? ` — ${entry.source_date}` : ""}
        </p>
      )}
    </div>
  );
}

export default function DataSources() {
  const { loading, error, data } = useDataSources();

  return (
    <div className="page">
      <h1>Data Sources &amp; Assumptions</h1>
      <p className="page-intro">
        Every REAL, CALCULATED, SIMULATED, or ASSUMPTION figure this app uses,
        in one place — read live from the same seeded rows and cited constants
        every other page already uses, not a separately hand-maintained list
        that could drift out of sync. See <code>docs/DECISIONS.md #21</code>.
      </p>

      <section className="data-honesty" style={{ marginBottom: "1.75rem" }}>
        <dl className="honesty-list">
          {Object.entries(CLASSIFICATION_NOTE).map(([label, note]) => (
            <div key={label} style={{ display: "contents" }}>
              <dt>
                <span className={`classification-badge classification-badge-${label}`}>
                  {label}
                </span>
              </dt>
              <dd>{note}</dd>
            </div>
          ))}
        </dl>
      </section>

      {loading && <p className="status-text">Loading data sources…</p>}

      {error && (
        <div className="error-box">
          <p>
            <strong>Couldn't load data sources.</strong> {error.message}
          </p>
        </div>
      )}

      {!loading &&
        !error &&
        data &&
        data.categories.map((cat) => (
          <section className="section" key={cat.category}>
            <h2>{cat.category}</h2>
            <div className="source-list">
              {cat.entries.map((entry, i) => (
                <EntryRow entry={entry} key={`${cat.category}-${i}`} />
              ))}
            </div>
          </section>
        ))}
    </div>
  );
}
