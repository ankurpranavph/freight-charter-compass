import { useEffect, useState } from "react";
import { api } from "../api/client";

// Fetched once per page and shared by every price display on it — a
// single GET /api/v1/exchange-rate call, not one per stat card. Returns
// null until loaded (or if the fetch fails); callers should treat null
// as "don't show an INR line yet" rather than block the page on it —
// the USD figures this app is built on never depend on this succeeding.
export function useExchangeRate() {
  const [rate, setRate] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .exchangeRate()
      .then((data) => {
        if (cancelled) return;
        setRate(data);
      })
      .catch(() => {
        // Deliberately silent: an INR line is a nice-to-have on top of
        // the USD figure that's already shown, not something worth an
        // error box of its own.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return rate;
}
