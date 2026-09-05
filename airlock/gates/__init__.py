"""The four gates. Each one is a plain function: asset in, GateResult out, telemetry as a side effect.

CHECKS is the one table naming them: gate -> (function, source of truth), in the order GATES lists
them. airlock.run, airlock.calibrate, airlock_mcp.server and the ADK pipeline all read it here, so a
gate added or renamed changes in one place.
"""

from __future__ import annotations

from airlock.gates import brand, claim, provenance, rights
from airlock.gates.base import GATES, GateFn

CHECKS: dict[str, tuple[GateFn, str]] = {
    "rights": (rights.check, rights.SOURCE_OF_TRUTH),
    "claim": (claim.check, claim.SOURCE_OF_TRUTH),
    "brand": (brand.check, brand.SOURCE_OF_TRUTH),
    "provenance": (provenance.check, provenance.SOURCE_OF_TRUTH),
}

assert tuple(CHECKS) == GATES, "CHECKS must name every gate in GATES order"

__all__ = ["CHECKS", "GATES", "brand", "claim", "provenance", "rights"]
