// USD stays the source-of-truth currency everywhere in this app's engine
// and API (see backend/app/engine/currency.py, docs/DECISIONS.md #25) —
// this is a display-only helper that turns an already-real USD figure
// into a secondary, clearly-labelled INR figure using the one cited
// exchange rate the backend serves at GET /api/v1/exchange-rate. Never
// call this without also showing the USD figure it was derived from.

// `exchangeRate` is the object returned by api.exchangeRate() —
// { usd_to_inr_rate, source, source_url, source_date } — or null while
// it's still loading, in which case this returns null and callers should
// simply omit the INR line rather than show a stale/zero value.
export function formatInr(usdValue, exchangeRate) {
  if (usdValue === null || usdValue === undefined || !exchangeRate) return null;
  const inr = usdValue * exchangeRate.usd_to_inr_rate;
  return inr.toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: Math.abs(inr) >= 1000 ? 0 : 2,
  });
}
