// Thin fetch wrapper around the FastAPI backend (see backend/app/main.py).
//
// Reads VITE_API_BASE at build time (set in Vercel's project settings for
// the deployed frontend — DECISIONS.md #27) and falls back to localhost:8000
// for local dev, where the backend always runs unconfigured. Vite only
// exposes env vars prefixed VITE_ to client code, and only substitutes them
// at build time — this is not a runtime-configurable value.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, params) {
  const url = new URL(API_BASE + path);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }

  let res;
  try {
    res = await fetch(url);
  } catch (err) {
    // Almost always means the backend isn't running — surface that
    // plainly rather than a cryptic "Failed to fetch".
    throw new ApiError(
      `Could not reach the API at ${API_BASE}. Is the backend running? (uvicorn app.main:app --reload)`,
      0,
      String(err),
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    throw new ApiError(detail, res.status, detail);
  }

  return res.json();
}

export const api = {
  health: () => request("/health"),
  vessels: () => request("/api/v1/vessels"),
  ports: () => request("/api/v1/ports"),
  port: (portId) => request(`/api/v1/ports/${portId}`),
  originPorts: () => request("/api/v1/origin-ports"),
  commodityPrices: (commodity) =>
    request("/api/v1/commodity-prices", { commodity }),
  forecast: (commodity, horizon) =>
    request(`/api/v1/forecast/${commodity}`, { horizon }),
  compatibilityCheck: (vesselType, portId) =>
    request("/api/v1/compatibility/check", {
      vessel_type: vesselType,
      port_id: portId,
    }),
  compatibilityMatrix: () => request("/api/v1/compatibility/matrix"),
  voyageCalculate: (vesselType, originId, portId, cargoTonnes) =>
    request("/api/v1/voyage/calculate", {
      vessel_type: vesselType,
      origin_id: originId,
      port_id: portId,
      cargo_tonnes: cargoTonnes,
    }),
  optimize: (portId, cargoTonnes) =>
    request(`/api/v1/optimize/${portId}`, { cargo_tonnes: cargoTonnes }),
  optimizeByVessel: (vesselType, originId, cargoTonnes) =>
    request("/api/v1/optimize/by-vessel", {
      vessel_type: vesselType,
      origin_id: originId,
      cargo_tonnes: cargoTonnes,
    }),
  bookOrWait: (commodity, horizon) =>
    request(`/api/v1/decision/book-vs-wait/${commodity}`, { horizon }),
  dataSources: () => request("/api/v1/data-sources"),
  exchangeRate: () => request("/api/v1/exchange-rate"),
  portTraffic: () => request("/api/v1/port-traffic"),
};

export { ApiError };
