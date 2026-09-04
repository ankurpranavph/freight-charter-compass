export default function Forecast() {
  return (
    <div className="page">
      <h1>Forecast</h1>
      <p className="page-intro">
        This page will chart the SARIMAX vs. seasonal-naive forecast for
        each commodity (backed by <code>GET /api/v1/forecast/{"{commodity}"}</code>,
        Module 1) and surface the book-now-vs-wait verdict (Module 7).
        Coming in the next build step.
      </p>
    </div>
  );
}
