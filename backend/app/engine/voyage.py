"""
Module 5: voyage cost calculator.

For a given vessel class, overseas loading port, and East Coast India
destination port: how far is it, how long does the laden voyage take, and
what does it cost (fuel + time-charter hire)? This is the "Simulate" half
of Predict -> Simulate -> Optimize -> Recommend - Module 6's optimizer
scores the outputs of this module, it doesn't recompute them.

SCOPE, DELIBERATELY: a single laden (loaded, one-way) voyage cost under a
time-charter cost model (charter hire + fuel), not a full round-trip
owner's P&L. No port charges, no ballast/repositioning leg, no canal
tolls. This mirrors how the freight-rate/chartering decision is actually
framed in the trade the app is modelling - "what does it cost to move
this cargo on this vessel" - and keeps Module 5 sized for a hackathon.
Extending to round-trip/port-charges is a documented future step, not an
oversight (see docs/TODO.md).

DISTANCE, CALCULATED not real-time: real point-to-point AIS routing is a
paid product (weather routing services, commercial voyage-estimation
tools). This computes great-circle (haversine) distance through a small,
hand-chosen set of open-ocean waypoints per origin region - enough to
keep the path from cutting across a landmass, not a certified routing
engine. Waypoints were chosen by reasoning about real shipping-lane
geography (which strait or cape a route from that region would actually
clear) and are documented per-route below. This is consistent with
DECISIONS.md #8: a fixed small set of routes, not a general-purpose
routing system.

MARKET REFERENCE FIGURES, ASSUMPTION not live: bunker fuel price and
time-charter day rates are real, cited, single point-in-time figures -
not live feeds. A production version would refresh these on a schedule;
here they're constants with a source and date, exactly like every other
ASSUMPTION-labelled figure in this project. See the constants below for
sources.
"""
import math
from dataclasses import dataclass

EARTH_RADIUS_NM = 3440.065  # mean Earth radius in nautical miles

# Common entry point into the Bay of Bengal (south of Sri Lanka) that every
# route below converges on before the final, open-water leg to whichever
# East Coast India port is requested - Visakhapatnam/Paradip/Dhamra are
# close enough together that this shared final leg doesn't cut across land
# for any of them.
BAY_OF_BENGAL_ENTRY = (6.0, 82.0)

# Each route: [origin, ...open-ocean waypoints..., Bay of Bengal entry].
# The destination port's own lat/lon (from the `ports` table) is appended
# at query time as the final leg.
ROUTE_WAYPOINTS: dict[str, list[tuple[float, float]]] = {
    # Newcastle sits on Australia's EAST coast, so reaching the Indian
    # Ocean means going around the continent. Routed south (via Bass
    # Strait / south of Tasmania, then well clear of Cape Leeuwin) rather
    # than north via Torres Strait - the southern route is deep water,
    # suited to Capesize-size vessels, and is the route real Australia to
    # South Asia coal voyages typically take for large bulk carriers.
    "NEWCASTLE_AU": [
        (-32.93, 151.78),   # Newcastle
        (-43.5, 147.3),     # south of Tasmania, clear of Bass Strait / the mainland
        (-38.0, 110.0),     # well offshore past Cape Leeuwin, into the open Indian Ocean
        (-8.0, 95.0),       # mid-Indian Ocean, south of Sumatra
        BAY_OF_BENGAL_ENTRY,
    ],
    # Richards Bay is already on South Africa's Indian Ocean (east) coast
    # - no Cape of Good Hope routing needed, just a direct-ish path north
    # of Madagascar across the open Indian Ocean.
    "RICHARDS_BAY_ZA": [
        (-28.80, 32.03),    # Richards Bay
        (-20.0, 55.0),      # open Indian Ocean, north of Madagascar
        BAY_OF_BENGAL_ENTRY,
    ],
    # Taboneo sits in the Java Sea side of the Indonesian archipelago;
    # routed out via the Sunda Strait (between Java and Sumatra) into the
    # open Indian Ocean rather than through the shallower, more congested
    # Malacca Strait.
    "TABONEO_ID": [
        (-3.70, 114.44),    # Taboneo anchorage
        (-6.5, 105.0),      # near the Sunda Strait exit into the open Indian Ocean
        BAY_OF_BENGAL_ENTRY,
    ],
}

# Ship & Bunker, Singapore VLSFO, 2026-09-02: https://shipandbunker.com/prices/apac/sea/sg-sin-singapore
# A single cited snapshot, not a live feed - see module docstring.
BUNKER_PRICE_USD_PER_TONNE = 856.00
BUNKER_PRICE_SOURCE = "Ship & Bunker, Singapore VLSFO, 2026-09-02"
BUNKER_PRICE_SOURCE_URL = "https://shipandbunker.com/prices/apac/sea/sg-sin-singapore"

# HandyBulk, 1-year time charter rates, dated 2026-09-03 (matched to our
# vessel classes by DWT: Handysize 38K, Supramax 58K, Panamax 75K,
# Capesize 180K - close enough to our 35k/58k/76k/180k seeded specs to use
# directly). https://www.handybulk.com/ship-charter-rates/
TIME_CHARTER_USD_PER_DAY = {
    "Handysize": 14_500,
    "Supramax": 18_000,
    "Panamax": 20_000,
    "Capesize": 38_500,
}
TIME_CHARTER_SOURCE = "HandyBulk, 1-year time charter rates, 2026-09-03"
TIME_CHARTER_SOURCE_URL = "https://www.handybulk.com/ship-charter-rates/"


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_NM * c


def route_distance_nm(origin: dict, port: dict) -> float:
    """origin: a row from origin_ports (needs origin_id). port: a row from
    ports (needs lat/lon). Raises KeyError if origin_id has no defined
    route - deliberately, rather than silently falling back to a direct
    great-circle line that might cross land."""
    waypoints = ROUTE_WAYPOINTS[origin["origin_id"]]
    points = list(waypoints) + [(port["lat"], port["lon"])]
    return sum(
        haversine_nm(*points[i], *points[i + 1]) for i in range(len(points) - 1)
    )


@dataclass
class VoyageResult:
    vessel_type: str
    origin_id: str
    port_id: str
    distance_nm: float
    voyage_days: float
    fuel_tonnes: float
    fuel_cost_usd: float
    charter_hire_usd: float
    total_cost_usd: float
    cargo_tonnes: float
    cost_per_tonne_usd: float
    assumptions: dict

    def as_dict(self) -> dict:
        return {
            "vessel_type": self.vessel_type,
            "origin_id": self.origin_id,
            "port_id": self.port_id,
            "distance_nm": round(self.distance_nm, 1),
            "voyage_days": round(self.voyage_days, 2),
            "fuel_tonnes": round(self.fuel_tonnes, 1),
            "fuel_cost_usd": round(self.fuel_cost_usd, 2),
            "charter_hire_usd": round(self.charter_hire_usd, 2),
            "total_cost_usd": round(self.total_cost_usd, 2),
            "cargo_tonnes": self.cargo_tonnes,
            "cost_per_tonne_usd": round(self.cost_per_tonne_usd, 3),
            "assumptions": self.assumptions,
        }


def calculate_voyage(
    vessel: dict, origin: dict, port: dict, cargo_tonnes: float | None = None
) -> VoyageResult:
    """
    vessel: a row from vessel_classes (vessel_type, speed_knots, fuel_cons_tpd, dwt_tonnes).
    origin: a row from origin_ports (origin_id, lat, lon).
    port: a row from ports (port_id, lat, lon).
    cargo_tonnes: defaults to the vessel's full DWT (an ASSUMPTION -
      real utilization is always somewhat below full deadweight once fuel,
      water, and stores are accounted for; flagged in the result).
    """
    if vessel["vessel_type"] not in TIME_CHARTER_USD_PER_DAY:
        raise KeyError(f"No time-charter rate on file for vessel_type '{vessel['vessel_type']}'")

    distance_nm = route_distance_nm(origin, port)
    voyage_days = distance_nm / (vessel["speed_knots"] * 24)
    fuel_tonnes = voyage_days * vessel["fuel_cons_tpd"]
    fuel_cost_usd = fuel_tonnes * BUNKER_PRICE_USD_PER_TONNE

    tc_rate = TIME_CHARTER_USD_PER_DAY[vessel["vessel_type"]]
    charter_hire_usd = voyage_days * tc_rate

    total_cost_usd = fuel_cost_usd + charter_hire_usd
    cargo = cargo_tonnes if cargo_tonnes is not None else vessel["dwt_tonnes"]
    cost_per_tonne_usd = total_cost_usd / cargo if cargo else float("inf")

    return VoyageResult(
        vessel_type=vessel["vessel_type"],
        origin_id=origin["origin_id"],
        port_id=port["port_id"],
        distance_nm=distance_nm,
        voyage_days=voyage_days,
        fuel_tonnes=fuel_tonnes,
        fuel_cost_usd=fuel_cost_usd,
        charter_hire_usd=charter_hire_usd,
        total_cost_usd=total_cost_usd,
        cargo_tonnes=cargo,
        cost_per_tonne_usd=cost_per_tonne_usd,
        assumptions={
            "scope": "one-way laden voyage under time charter (charter hire + fuel); "
            "no port charges, no ballast leg, no canal tolls - see module docstring",
            "distance": "CALCULATED: great-circle via hand-chosen open-ocean waypoints, "
            "not a licensed routing product",
            "cargo_tonnes_basis": "full vessel DWT"
            if cargo_tonnes is None
            else "user-specified",
            "bunker_price_usd_per_tonne": BUNKER_PRICE_USD_PER_TONNE,
            "bunker_price_source": f"{BUNKER_PRICE_SOURCE} ({BUNKER_PRICE_SOURCE_URL})",
            "time_charter_usd_per_day": tc_rate,
            "time_charter_source": f"{TIME_CHARTER_SOURCE} ({TIME_CHARTER_SOURCE_URL})",
        },
    )
