"""
Module 4: vessel <-> port physical compatibility engine.

Answers, for a given vessel class and port: can this vessel physically
call here? Checks draft, LOA (length overall), and beam against the
port's stated maximum figures, plus whether the port is flagged as
handling coal at all. This is a hard gate, not a score: if a vessel
doesn't physically fit, it's excluded with the exact reason (dimension,
vessel value, port limit, margin) - not silently down-ranked. Module 6's
optimizer only ever scores vessel/port pairs that already passed here.

REAL vs ASSUMPTION: the honesty labelling lives with the underlying data
(vessels.json marks every row is_assumption: true as typical-class specs;
ports.json marks each port verified: true/false with a source) - this
engine just compares numbers already in the database. See
docs/PROJECT_CONTEXT.md for the full data-provenance breakdown.

If a port is missing a dimension (max_draft_m etc. is NULL - not the
case for any of the 3 currently seeded ports, but will be for a Phase-2
port added before its figures are fully sourced), that dimension is
reported as "unknown" and the overall result is NOT marked compatible -
we don't claim a vessel fits a port we can't actually confirm it fits.
"""
from dataclasses import dataclass

# (result label, vessel dict field, port dict field)
DIMENSIONS = [
    ("draft", "draft_m", "max_draft_m"),
    ("loa", "loa_m", "max_loa_m"),
    ("beam", "beam_m", "max_beam_m"),
]


@dataclass
class CompatibilityResult:
    vessel_type: str
    port_id: str
    compatible: bool
    checks: list
    reasons: list

    def as_dict(self) -> dict:
        return {
            "vessel_type": self.vessel_type,
            "port_id": self.port_id,
            "compatible": self.compatible,
            "checks": self.checks,
            "reasons": self.reasons,
        }


def check_compatibility(vessel: dict, port: dict) -> CompatibilityResult:
    checks = []
    reasons = []
    all_known_and_ok = True

    for label, vessel_field, port_field in DIMENSIONS:
        vessel_value = vessel[vessel_field]
        port_max = port.get(port_field)

        if port_max is None:
            checks.append(
                {
                    "dimension": label,
                    "status": "unknown",
                    "vessel_value": vessel_value,
                    "port_max": None,
                    "margin_m": None,
                }
            )
            reasons.append(
                f"Port has no recorded {label} limit on file - cannot confirm this vessel fits."
            )
            all_known_and_ok = False
            continue

        margin = round(port_max - vessel_value, 2)
        ok = margin >= 0
        checks.append(
            {
                "dimension": label,
                "status": "ok" if ok else "fail",
                "vessel_value": vessel_value,
                "port_max": port_max,
                "margin_m": margin,
            }
        )
        if not ok:
            reasons.append(
                f"{vessel['vessel_type']} {label} {vessel_value}m exceeds "
                f"{port['port_id']}'s max {label} {port_max}m by {abs(margin)}m."
            )
            all_known_and_ok = False

    if not port.get("coal_handling"):
        reasons.append(f"{port['port_id']} is not flagged as a coal-handling port.")
        all_known_and_ok = False

    return CompatibilityResult(
        vessel_type=vessel["vessel_type"],
        port_id=port["port_id"],
        compatible=all_known_and_ok,
        checks=checks,
        reasons=reasons,
    )


def build_matrix(vessels: list, ports: list) -> list:
    """Every vessel x port combination, each as a CompatibilityResult dict.
    Cheap (pure arithmetic on already-seeded rows) - no caching needed,
    unlike the forecast engine."""
    return [
        check_compatibility(vessel, port).as_dict() for vessel in vessels for port in ports
    ]
