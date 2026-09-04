// Thin fetch wrapper around the FastAPI backend (see backend/app/main.py).
//
// No env-based config yet: the backend always runs on localhost:8000 in
// this dev/demo setup (see PROJECT_CONTEXT.md's 5-page MVP scope — there's
// no deployed backend to point at). If that changes, this is the one
// place to add a configurable base URL.
const API_BASE = "http://localhost:8000";

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
