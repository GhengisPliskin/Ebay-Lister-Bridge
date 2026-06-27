"""
Module: pricing.py
Purpose: Frozen data contract for the Margin-Guard pricing output.
Primary Responsibilities:
  - Define ActiveCompRange and MarginGuardOutput, the typed pricing result.
  - Encode the "active-comp anchored + human-confirmed + floor-protected"
    pricing model committed in blueprint v1.1.
Key Interfaces:
  - Input: VisionAgentOutput + cost inputs + Browse API active comps.
  - Output: MarginGuardOutput consumed by orchestrator.py and ui/app.py.
FMEA Constraints Enforced:
  - PI-006 — floor_applied flags when the deterministic floor overrode the
    comp-derived price, so an unviable price can never be published silently.
  - R-PRICE — missing cost/comp inputs route to missing_inputs for the UI to
    resolve; they are never guessed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ActiveCompRange(BaseModel):
    """
    Low/high bounds of the active comparable listings used as the price anchor.

    Attributes:
        low: Lowest active-comp asking price observed (USD).
        high: Highest active-comp asking price observed (USD).

    FMEA Constraints:
        R-PRICE — populated from Browse API active comps; surfaced in the UI so
        the operator sees the asking-price spread behind the anchor.
    """

    model_config = ConfigDict(extra="forbid")

    low: float = Field(default=0.00, ge=0, description="Lowest active-comp price (USD).")
    high: float = Field(default=0.00, ge=0, description="Highest active-comp price (USD).")


class MarginGuardOutput(BaseModel):
    """
    Frozen Margin-Guard pricing result for a single item.

    Mirrors the blueprint "Margin-Guard output" JSON contract. Pricing is
    active-comp anchored (Browse API), optionally human-confirmed, and
    floor-protected by a deterministic backstop.

    Attributes:
        margin_guard_price: Final suggested price (USD) after anchor/comp/floor
            resolution. This maps to eBay pricingSummary.price in createOffer.
        active_comp_anchor: Automated "current asking" anchor from Browse comps.
        user_confirmed_comp: Operator-entered true sold-comp price, or None until
            the human confirms one in the UI.
        floor_price: Deterministic backstop = (cost + fees) * 1.15.
        floor_applied: True when the floor overrode a below-floor comp price (PI-006).
        active_comp_range: Low/high spread of the active comps behind the anchor.
        reasoning: Plain-English explanation shown to the operator (no raw JSON).
        missing_inputs: Names of missing cost/comp inputs the UI must resolve;
            never guessed (R-PRICE).

    FMEA Constraints:
        PI-006 — floor_applied makes floor overrides explicit and auditable.
        R-PRICE — missing_inputs routes gaps to the human instead of guessing.
    """

    model_config = ConfigDict(extra="forbid")

    margin_guard_price: float = Field(
        default=0.00, ge=0, description="Final suggested price (USD)."
    )
    active_comp_anchor: float = Field(
        default=0.00, ge=0, description="Automated active-comp anchor (USD)."
    )
    user_confirmed_comp: float | None = Field(
        default=None, description="Human-confirmed sold-comp price, or None."
    )
    floor_price: float = Field(
        default=0.00, ge=0, description="Deterministic floor = (cost + fees) * 1.15."
    )
    floor_applied: bool = Field(
        default=False, description="True when the floor overrode the comp price (PI-006)."
    )
    active_comp_range: ActiveCompRange = Field(
        default_factory=ActiveCompRange,
        description="Low/high spread of the active comps behind the anchor.",
    )
    reasoning: str = Field(
        default="", description="Operator-facing explanation of the price decision."
    )
    missing_inputs: list[str] = Field(
        default_factory=list,
        description="Missing cost/comp inputs for the UI to resolve; never guessed.",
    )
