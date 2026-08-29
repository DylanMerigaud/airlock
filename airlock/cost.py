"""What one gate run costs at list price, from the real usage the gate reports.

The prices live in pricing.yaml with their SKU ids and the day they were read; the gate evidence
carries the token counts (Gemini) and the video minutes and features (Video Intelligence). The
provenance gate costs nothing to run. The free monthly quotas are not netted: the number answers
"what would this check cost at scale", the honest question for a studio.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import asdict, dataclass
from typing import Any

import yaml

PRICING_PATH = pathlib.Path(__file__).resolve().parents[1] / "pricing.yaml"


def load_pricing(path: pathlib.Path = PRICING_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    video_minutes: float = 0.0
    features: int = 0
    cost_usd: float = 0.0
    basis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def gemini_usage(evidence: list[dict[str, Any]]) -> tuple[str | None, int, int]:
    """The model name and token counts a claim or brand gate left in its evidence."""
    for item in evidence:
        model = item.get("model") if isinstance(item, dict) else None
        if isinstance(model, dict) and model.get("model"):
            return str(model["model"]), int(model.get("prompt_tokens") or 0), int(model.get("output_tokens") or 0)
    return None, 0, 0


def estimate(gate: str, evidence: list[dict[str, Any]], pricing: dict[str, Any] | None = None) -> Usage:
    p = pricing or load_pricing()
    u = Usage()
    model, tin, tout = gemini_usage(evidence)
    if model:
        rates = p["gemini"].get(model) or {}
        u.tokens_in, u.tokens_out = tin, tout
        u.cost_usd += tin * float(rates.get("input_per_token", 0)) + tout * float(rates.get("output_per_token", 0))
        u.basis = f"{model}: {tin} in, {tout} out"
    if gate == "rights":
        ev = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
        seconds = float(ev.get("duration_s") or 0)
        features = list(ev.get("features") or [])
        minutes = math.ceil(seconds / 60) if seconds > 0 else 0  # billed per started minute
        u.video_minutes, u.features = float(minutes), len(features)
        per_min = p["video_intelligence"]["per_minute"]
        u.cost_usd += sum(minutes * float(per_min.get(f, 0)) for f in features)
        u.basis = f"Video Intelligence: {minutes} min x {len(features)} features" + (f"; {u.basis}" if u.basis else "")
    u.cost_usd = round(u.cost_usd, 6)
    return u
