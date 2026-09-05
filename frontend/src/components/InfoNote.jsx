/*
 * A small, consistent disclosure for explanatory/methodology text —
 * page intros, sourcing notes, model-detail dumps — the kind of copy
 * that matters for verifying the app's numbers but doesn't need to be
 * read on every glance. Nothing is removed, only collapsed by default,
 * following the same <details>/<summary> pattern already used for each
 * option card's "Why this port/vessel works" breakdown (DECISIONS.md
 * #31 — the text-reduction / "more professional" pass).
 */
export default function InfoNote({ label = "Details", children, className = "" }) {
  return (
    <details className={`info-note ${className}`.trim()}>
      <summary>{label}</summary>
      <div className="info-note-body">{children}</div>
    </details>
  );
}
