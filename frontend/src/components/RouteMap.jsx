import { useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import InfoNote from "./InfoNote";

/*
 * Interactive route map for the Recommendation page (DECISIONS.md #30).
 *
 * Draws one fixed "anchor" point (the loading port in "by vessel" mode,
 * the destination port in "by port" mode) plus a set of candidate
 * "points" (destination ports, or origin ports, respectively), and a
 * route line from the anchor to whichever point is focused.
 *
 * The route line is NOT a straight line between two coordinates — it
 * follows the exact same hand-chosen open-ocean waypoints
 * app/engine/voyage.py's route_distance_nm uses for the real distance
 * and cost calculation (served by GET /api/v1/origin-ports as each
 * origin's `route_waypoints`), so the picture always matches the number
 * next to it rather than a shorter, land-crossing line a naive
 * origin-to-destination straight line would draw.
 *
 * Marker color follows the same status idea as the option cards below
 * the map: the focused/top option gets the app's accent color, other
 * compatible options a lighter tint, incompatible ones a muted gray —
 * never red, matching the existing ".incompat-row" treatment (being
 * excluded isn't an error).
 */

function FitBounds({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (!positions || positions.length === 0) return;
    if (positions.length === 1) {
      map.setView(positions[0], 4);
      return;
    }
    map.fitBounds(positions, { padding: [32, 32] });
  }, [map, positions]);
  return null;
}

function statusColor(status) {
  if (status === "top") return "#1f5f4f"; // --accent
  if (status === "compatible") return "#2a78d6"; // --series-actual
  return "#9b988f"; // muted, matches --text-muted-ish, never red
}

function statusRadius(status, isFocused) {
  if (isFocused) return 9;
  if (status === "incompatible") return 5;
  return 7;
}

export default function RouteMap({ anchor, anchorLabel, points, focusedId, onFocusChange, height = 320 }) {
  const focused = points.find((p) => p.id === focusedId) || null;

  // Whichever side actually owns the real ROUTE_WAYPOINTS (the origin —
  // fixed anchor in "by vessel" mode, or the varying point in "by port"
  // mode) supplies the open-ocean leg; the other side's own lat/lon
  // closes the path. Never falls back to a bare two-point straight line
  // when waypoints exist for either side.
  let routePath = null;
  if (focused) {
    if (anchor.routeWaypoints && anchor.routeWaypoints.length > 0) {
      routePath = [...anchor.routeWaypoints, [focused.lat, focused.lon]];
    } else if (focused.routeWaypoints && focused.routeWaypoints.length > 0) {
      routePath = [...focused.routeWaypoints, [anchor.lat, anchor.lon]];
    }
  }

  const allPositions = [
    [anchor.lat, anchor.lon],
    ...points.map((p) => [p.lat, p.lon]),
  ];

  return (
    <div className="route-map-wrap">
      <MapContainer
        center={[anchor.lat, anchor.lon]}
        zoom={3}
        style={{ height, width: "100%" }}
        scrollWheelZoom={false}
        className="route-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds positions={allPositions} />

        {routePath && (
          <Polyline
            positions={routePath}
            pathOptions={{ color: "#1f5f4f", weight: 3, opacity: 0.85 }}
          />
        )}

        <CircleMarker
          center={[anchor.lat, anchor.lon]}
          radius={9}
          pathOptions={{ color: "#22201c", fillColor: "#22201c", fillOpacity: 1, weight: 2 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <strong>{anchorLabel}:</strong> {anchor.name}
          </Tooltip>
        </CircleMarker>

        {points.map((p) => {
          const isFocused = p.id === focusedId;
          return (
            <CircleMarker
              key={p.id}
              center={[p.lat, p.lon]}
              radius={statusRadius(p.status, isFocused)}
              pathOptions={{
                color: statusColor(isFocused ? "top" : p.status),
                fillColor: statusColor(isFocused ? "top" : p.status),
                fillOpacity: p.status === "incompatible" ? 0.5 : 0.9,
                weight: isFocused ? 3 : 1.5,
              }}
              eventHandlers={
                p.status !== "incompatible" && onFocusChange
                  ? { click: () => onFocusChange(p.id) }
                  : undefined
              }
            >
              <Tooltip direction="top" offset={[0, -6]}>
                <strong>{p.name}</strong>
                <br />
                {p.status === "incompatible" ? "Not compatible" : p.tooltipDetail}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <InfoNote label="What this map is drawing" className="route-map-caption">
        <p>
          Port positions: REAL (harbour-level, for display — DECISIONS.md #11). Route line:
          the same hand-chosen open-ocean waypoints used to calculate cost and distance
          (DECISIONS.md #15), not a straight line. Click a marker to see its route.
        </p>
      </InfoNote>
    </div>
  );
}
