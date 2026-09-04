export default function Recommendation() {
  return (
    <div className="page">
      <h1>Recommendation</h1>
      <p className="page-intro">
        This page will let you pick a destination port and cargo size and
        see the ranked vessel/route options from{" "}
        <code>GET /api/v1/optimize/{"{port_id}"}</code> (Module 6), with
        each option's physical-compatibility and risk-margin reasoning
        (Module 4) visible alongside it. Coming in the next build step.
      </p>
    </div>
  );
}
