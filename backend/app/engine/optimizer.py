"""
Module 6: risk-adjusted cost optimizer.

Ranks vessel-class x origin-port combinations for a given destination
port by risk-adjusted cost per tonne. Composes, rather than recomputes,
Module 4 (physical compatibility) and Module 5 (voyage cost) — an
option that fails Module 4's gate is excluded outright, never scored.

RISK SIGNAL, DELIBERATELY SCOPED: "risk" here means physical operating
margin at berth — how much spare draft/LOA/beam clearance a vessel has
at the destination port, derived directly from Module 4's own numbers.
A vessel that clears a port's draft limit by 10cm carries real
operational risk (tide-window dependency, grounding risk, less room for
survey error) that a vessel clearing by 8 metres doesn't, even though
both are "compatible" by the hard pass/fail gate. This is a genuine,
calculated signal from data already in the database — not a synthetic
"risk score" invented for the demo.

We deliberately do NOT fold price-trend/forecast uncertainty (Module 1)
into this score — that belongs to Module 7 (book now vs. wait), which
is about WHEN to act, not WHICH vessel/route to use. Keeping the two
separate keeps each optimizer's reasoning legible on its own.

CARGO CAPACITY: if a fixed `cargo_tonnes` is given and exceeds a vessel's
DWT, that vessel is excluded for this port rather than silently computing
a cost-per-tonne that implies one voyage carries more cargo than the
vessel can actually hold — a single voyage per option is what Module 5
prices, not a multi-voyage plan (not modeled, see docs/TODO.md).

TWO DIRECTIONS, ONE SCORING FUNCTION: `rank_options` fixes the
destination port and ranks every vessel x origin combination for it —
"I know where I'm shipping to, what should I book?" `rank_ports_for_vessel`
fixes the vessel and origin instead, and ranks the 6 destination ports —
"I already have a ship and a loading port, where should it go?" Added at
the Hour 30+ checkpoint after re-checking the app against the SIH26006
problem statement: a real charterer usually starts from the second
question, not the first, and a fixed `port_id` in the URL meant that
question had no answer before this. Both directions call `_score_option`
so the risk-margin methodology never diverges between them.
"""
from dataclasses import dataclass

from app.engine.compatibility import check_compatibility
from app.engine.voyage import calculate_voyage

# Below this margin ratio (spare clearance / vessel dimension), an option
# is considered to carry meaningful physical risk and its cost is
# adjusted upward. At or above it, no penalty is applied.
SAFE_MARGIN_RATIO = 0.10

# The maximum risk adjustment applied at zero clearance (an exact-boundary
# fit). Scaled linearly between 0 (at SAFE_MARGIN_RATIO) and this value
# (at 0 margin).
MAX_RISK_PENALTY = 0.15


def _tightest_margin_ratio(checks: list) -> float | None:
    """The smallest (margin / vessel_value) across all 'ok' dimension
    checks — the single tightest physical clearance. None if any
    dimension is 'unknown' (can't assess risk on unconfirmed port data)
    or if there are no 'ok' checks to measure."""
    ratios = []
    for c in checks:
        if c["status"] == "unknown":
            return None
        if c["status"] == "ok":
            if c["vessel_value"] == 0:
                continue
            ratios.append(c["margin_m"] / c["vessel_value"])
    return min(ratios) if ratios else None


def _risk_multiplier(margin_ratio: float | None) -> float:
    if margin_ratio is None:
        return 1.0 + MAX_RISK_PENALTY  # unknown clearance treated as max caution
    if margin_ratio >= SAFE_MARGIN_RATIO:
        return 1.0
    risk_fraction = 1.0 - (margin_ratio / SAFE_MARGIN_RATIO)
    return 1.0 + risk_fraction * MAX_RISK_PENALTY


@dataclass
class RankedOption:
    vessel_type: str
    origin_id: str
    port_id: str
    cost_per_tonne_usd: float
    risk_multiplier: float
    risk_adjusted_cost_per_tonne_usd: float
    tightest_margin_ratio: float | None
    voyage: dict
    compatibility: dict

    def as_dict(self) -> dict:
        return {
            "vessel_type": self.vessel_type,
            "origin_id": self.origin_id,
            "port_id": self.port_id,
            "cost_per_tonne_usd": round(self.cost_per_tonne_usd, 3),
            "risk_multiplier": round(self.risk_multiplier, 4),
            "risk_adjusted_cost_per_tonne_usd": round(self.risk_adjusted_cost_per_tonne_usd, 3),
            "tightest_margin_ratio_pct": (
                round(self.tightest_margin_ratio * 100, 2)
                if self.tightest_margin_ratio is not None
                else None
            ),
            "voyage": self.voyage,
            "compatibility": self.compatibility,
        }


class CargoExceedsCapacityError(ValueError):
    """Raised when a fixed cargo_tonnes exceeds a single fixed vessel's
    own DWT — a fact about the vessel, independent of which port is
    picked, so rank_ports_for_vessel checks it once up front instead of
    silently excluding all 6 ports one at a time."""


def _score_option(vessel: dict, origin: dict, port: dict, cargo_tonnes: float | None):
    """Shared by both ranking directions. Returns (RankedOption, compat)
    if the vessel physically fits this port, or (None, compat) if not —
    the caller decides whether a failing compat result is dropped
    (rank_options) or reported with its reasons (rank_ports_for_vessel)."""
    compat = check_compatibility(vessel, port)
    if not compat.compatible:
        return None, compat
    margin_ratio = _tightest_margin_ratio(compat.checks)
    risk_mult = _risk_multiplier(margin_ratio)
    voyage = calculate_voyage(vessel, origin, port, cargo_tonnes=cargo_tonnes)
    risk_adjusted = voyage.cost_per_tonne_usd * risk_mult
    option = RankedOption(
        vessel_type=vessel["vessel_type"],
        origin_id=origin["origin_id"],
        port_id=port["port_id"],
        cost_per_tonne_usd=voyage.cost_per_tonne_usd,
        risk_multiplier=risk_mult,
        risk_adjusted_cost_per_tonne_usd=risk_adjusted,
        tightest_margin_ratio=margin_ratio,
        voyage=voyage.as_dict(),
        compatibility=compat.as_dict(),
    )
    return option, compat


def rank_options(
    port: dict,
    vessels: list,
    origins: list,
    cargo_tonnes: float | None = None,
) -> list[RankedOption]:
    """port: a row from `ports`. vessels: rows from `vessel_classes`.
    origins: rows from `origin_ports`. Returns options sorted best-first
    (lowest risk-adjusted cost per tonne). A vessel/port pair that fails
    Module 4's compatibility gate, or a vessel whose DWT is below a given
    fixed cargo_tonnes, is excluded entirely — not included with a fail
    flag (see app/engine/compatibility.py's matrix endpoint for the full
    pass/fail picture instead)."""
    options = []
    for vessel in vessels:
        if cargo_tonnes is not None and cargo_tonnes > vessel["dwt_tonnes"]:
            continue
        for origin in origins:
            option, _compat = _score_option(vessel, origin, port, cargo_tonnes)
            if option is not None:
                options.append(option)
    options.sort(key=lambda o: o.risk_adjusted_cost_per_tonne_usd)
    return options


def rank_ports_for_vessel(
    vessel: dict,
    origin: dict,
    ports: list,
    cargo_tonnes: float | None = None,
) -> tuple[list[RankedOption], list]:
    """The mirror of rank_options: vessel: a row from `vessel_classes`.
    origin: a row from `origin_ports`. ports: rows from `ports` (all 6).
    Returns (compatible, incompatible) — compatible is sorted best-first
    like rank_options; incompatible is a list of CompatibilityResult
    dicts (via .as_dict()), one per port that fails Module 4's gate,
    WITH its reasons. Unlike rank_options, incompatible ports are never
    silently dropped: a real user choosing among 6 named, enumerable
    destinations benefits from seeing all 6 and why, not a shortened
    list with no explanation for the missing ones.

    Raises CargoExceedsCapacityError if cargo_tonnes exceeds this
    vessel's own DWT — checked once, since it's true at every port."""
    if cargo_tonnes is not None and cargo_tonnes > vessel["dwt_tonnes"]:
        raise CargoExceedsCapacityError(
            f"{cargo_tonnes:,.0f}t exceeds {vessel['vessel_type']}'s "
            f"{vessel['dwt_tonnes']:,.0f}t DWT — pick a smaller cargo size "
            f"or a larger vessel class."
        )
    compatible = []
    incompatible = []
    for port in ports:
        option, compat = _score_option(vessel, origin, port, cargo_tonnes)
        if option is not None:
            compatible.append(option)
        else:
            incompatible.append(compat.as_dict())
    compatible.sort(key=lambda o: o.risk_adjusted_cost_per_tonne_usd)
    return compatible, incompatible
