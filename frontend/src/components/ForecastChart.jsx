import { useMemo, useRef, useState } from "react";

// Hand-rolled SVG line chart — no charting library. This is one chart on
// one page; a dependency (Recharts, etc.) would cost more in install size
// and default-look override than it saves here, consistent with the
// lean-tooling call in DECISIONS.md #18. Follows the dataviz method: form
// = trend-over-time (2-series, categorical color), marks = 2px lines /
// 10%-opacity area / hairline gridlines, crosshair + one tooltip, legend
// always present for 2 series, direct end-labels.

const WIDTH = 760;
const HEIGHT = 320;
const MARGIN = { top: 16, right: 16, bottom: 32, left: 60 };
const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;

// "Nice" tick step — 1/2/5 × 10^n — so axis labels are round numbers,
// not raw min+i*(range/4) fractions.
function niceStep(rawStep) {
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  let step;
  if (residual > 5) step = 10;
  else if (residual > 2) step = 5;
  else if (residual > 1) step = 2;
  else step = 1;
  return step * magnitude;
}

function niceTicks(min, max, count = 5) {
  const rawStep = (max - min) / (count - 1);
  const step = niceStep(rawStep || 1);
  const niceMin = Math.floor(min / step) * step;
  const niceMax = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = niceMin; v <= niceMax + step * 0.001; v += step) {
    ticks.push(Math.round(v * 1000) / 1000);
  }
  return ticks;
}

function formatMonth(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export default function ForecastChart({ historical, forecast }) {
  const [hoverIdx, setHoverIdx] = useState(null);
  const svgRef = useRef(null);

  const points = useMemo(() => {
    const hist = historical.map((h) => ({
      date: h.date,
      actual: h.price_usd,
      forecast: null,
      ciLower: null,
      ciUpper: null,
    }));
    const fc = forecast.map((f) => ({
      date: f.date,
      actual: null,
      forecast: f.forecast_price_usd,
      ciLower: f.ci_lower,
      ciUpper: f.ci_upper,
    }));
    // Bridge point: the last actual value doubles as the forecast line's
    // start, so the dashed forecast segment connects to the solid line
    // instead of floating with a gap.
    if (hist.length && fc.length) {
      const bridge = { ...hist[hist.length - 1] };
      bridge.forecast = bridge.actual;
      bridge.ciLower = bridge.actual;
      bridge.ciUpper = bridge.actual;
      return [...hist.slice(0, -1), bridge, ...fc];
    }
    return [...hist, ...fc];
  }, [historical, forecast]);

  const boundaryIdx = historical.length - 1;

  const { xScale, yScale, yTicks } = useMemo(() => {
    const n = points.length;
    const values = points.flatMap((p) =>
      [p.actual, p.ciLower, p.ciUpper, p.forecast].filter(
        (v) => v !== null && v !== undefined,
      ),
    );
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const pad = (rawMax - rawMin) * 0.08 || rawMax * 0.05 || 1;

    // "Nice" round ticks, THEN widen the plotted y-domain to match them —
    // never the other way around. Ticks generated from a domain narrower
    // than the nice bounds land outside [MARGIN.top, HEIGHT-MARGIN.bottom]
    // and (with overflow: visible for labels) collide with the legend
    // above and the x-axis below.
    const ticks = niceTicks(rawMin - pad, rawMax + pad, 5);
    const yMin = Math.min(ticks[0], rawMin - pad);
    const yMax = Math.max(ticks[ticks.length - 1], rawMax + pad);

    const xS = (i) => MARGIN.left + (n <= 1 ? 0 : (i / (n - 1)) * PLOT_W);
    const yS = (v) =>
      MARGIN.top + PLOT_H - ((v - yMin) / (yMax - yMin)) * PLOT_H;

    return { xScale: xS, yScale: yS, yTicks: ticks };
  }, [points]);

  const actualPath = useMemo(() => {
    const segs = points
      .map((p, i) => (p.actual !== null ? `${xScale(i)},${yScale(p.actual)}` : null))
      .filter(Boolean);
    return segs.length ? `M ${segs.join(" L ")}` : "";
  }, [points, xScale, yScale]);

  const forecastPath = useMemo(() => {
    const segs = points
      .map((p, i) => (p.forecast !== null ? `${xScale(i)},${yScale(p.forecast)}` : null))
      .filter(Boolean);
    return segs.length ? `M ${segs.join(" L ")}` : "";
  }, [points, xScale, yScale]);

  const ciAreaPath = useMemo(() => {
    const withCi = points
      .map((p, i) => (p.ciUpper !== null ? { i, ...p } : null))
      .filter(Boolean);
    if (withCi.length < 2) return "";
    const top = withCi.map((p) => `${xScale(p.i)},${yScale(p.ciUpper)}`).join(" L ");
    const bottom = [...withCi]
      .reverse()
      .map((p) => `${xScale(p.i)},${yScale(p.ciLower)}`)
      .join(" L ");
    return `M ${top} L ${bottom} Z`;
  }, [points, xScale, yScale]);

  // Pick x-axis label indices by actual pixel spacing, not index modulo —
  // a fixed index step can still collide near the end when the forecast
  // segment is short relative to the full series (the boundary label and
  // the final label land within a few points of each other). The
  // forecast/actual split already has its own marker (the dashed guide +
  // "Forecast →" label above), so it doesn't need a duplicate date label
  // fighting the regular ticks for space.
  const xLabelIdxs = useMemo(() => {
    const n = points.length;
    if (n === 0) return new Set();
    const minGapPx = 64;
    const kept = [0];
    for (let i = 1; i < n; i++) {
      if (xScale(i) - xScale(kept[kept.length - 1]) >= minGapPx) {
        kept.push(i);
      }
    }
    const last = n - 1;
    if (kept[kept.length - 1] !== last) {
      if (xScale(last) - xScale(kept[kept.length - 1]) < minGapPx) {
        kept.pop();
      }
      kept.push(last);
    }
    return new Set(kept);
  }, [points, xScale]);

  function handlePointerMove(evt) {
    const rect = svgRef.current.getBoundingClientRect();
    const scaleFactor = WIDTH / rect.width;
    const svgX = (evt.clientX - rect.left) * scaleFactor;
    const relX = svgX - MARGIN.left;
    const n = points.length;
    const idx = Math.round((relX / PLOT_W) * (n - 1));
    setHoverIdx(Math.max(0, Math.min(n - 1, idx)));
  }

  const hovered = hoverIdx !== null ? points[hoverIdx] : null;
  const tooltipIsForecast = hovered && hovered.forecast !== null && hoverIdx > boundaryIdx;
  // At the boundary point both actual and forecast are populated (the
  // bridge point) — prefer showing it as the actual reading there.
  const tooltipValue = hovered
    ? hoverIdx <= boundaryIdx
      ? hovered.actual
      : hovered.forecast
    : null;

  return (
    <div className="chart-root">
      <div className="chart-legend">
        <span className="legend-item">
          <span className="legend-swatch legend-line" style={{ background: "var(--series-actual)" }} />
          Actual price
        </span>
        <span className="legend-item">
          <span
            className="legend-swatch legend-line legend-dashed"
            style={{ borderColor: "var(--series-forecast)" }}
          />
          SARIMAX forecast
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--series-forecast-band)" }} />
          95% confidence interval
        </span>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart-svg"
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHoverIdx(null)}
      >
        {/* gridlines */}
        {yTicks.map((t) => (
          <g key={t}>
            <line
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={yScale(t)}
              y2={yScale(t)}
              className="chart-gridline"
            />
            <text x={MARGIN.left - 8} y={yScale(t)} className="chart-tick chart-tick-y">
              ${t.toLocaleString()}
            </text>
          </g>
        ))}

        {/* x-axis labels */}
        {points.map((p, i) =>
          xLabelIdxs.has(i) ? (
            <text
              key={p.date}
              x={xScale(i)}
              y={HEIGHT - MARGIN.bottom + 18}
              className="chart-tick chart-tick-x"
              textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
            >
              {formatMonth(p.date)}
            </text>
          ) : null,
        )}

        {/* forecast boundary divider */}
        <line
          x1={xScale(boundaryIdx)}
          x2={xScale(boundaryIdx)}
          y1={MARGIN.top}
          y2={HEIGHT - MARGIN.bottom}
          className="chart-boundary"
        />
        <text
          x={xScale(boundaryIdx) + 6}
          y={MARGIN.top + 10}
          className="chart-boundary-label"
        >
          Forecast →
        </text>

        {/* CI band */}
        {ciAreaPath && <path d={ciAreaPath} className="chart-ci-band" />}

        {/* lines */}
        {actualPath && <path d={actualPath} className="chart-line-actual" />}
        {forecastPath && <path d={forecastPath} className="chart-line-forecast" />}

        {/* end markers */}
        {historical.length > 0 && (
          <circle
            cx={xScale(boundaryIdx)}
            cy={yScale(historical[historical.length - 1].price_usd)}
            r="5"
            className="chart-marker chart-marker-actual"
          />
        )}
        {forecast.length > 0 && (
          <circle
            cx={xScale(points.length - 1)}
            cy={yScale(forecast[forecast.length - 1].forecast_price_usd)}
            r="5"
            className="chart-marker chart-marker-forecast"
          />
        )}

        {/* crosshair */}
        {hovered && (
          <line
            x1={xScale(hoverIdx)}
            x2={xScale(hoverIdx)}
            y1={MARGIN.top}
            y2={HEIGHT - MARGIN.bottom}
            className="chart-crosshair"
          />
        )}
      </svg>

      {hovered && (
        <div
          className="chart-tooltip"
          style={{
            left: `${(xScale(hoverIdx) / WIDTH) * 100}%`,
            top: `${(yScale(tooltipValue) / HEIGHT) * 100}%`,
          }}
        >
          <div className="chart-tooltip-date">{hovered.date}</div>
          <div className="chart-tooltip-row">
            <span
              className="chart-tooltip-key"
              style={{
                background: tooltipIsForecast ? "var(--series-forecast)" : "var(--series-actual)",
              }}
            />
            <span className="chart-tooltip-value">${tooltipValue.toFixed(2)}</span>
            <span className="chart-tooltip-label">
              {tooltipIsForecast ? "forecast" : "actual"}
            </span>
          </div>
          {tooltipIsForecast && hovered.ciLower !== hovered.actual && (
            <div className="chart-tooltip-ci">
              95% CI: ${hovered.ciLower.toFixed(2)} – ${hovered.ciUpper.toFixed(2)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
